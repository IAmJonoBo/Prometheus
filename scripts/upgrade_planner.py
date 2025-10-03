#!/usr/bin/env python3
"""Dependency upgrade planning with Poetry resolver verification."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from packaging.utils import canonicalize_name
from prometheus_client import Counter, Histogram

from observability import configure_metrics, configure_tracing
from scripts import dependency_drift

SEVERITY_ORDER = {
    dependency_drift.RISK_PATCH: 0,
    dependency_drift.RISK_MINOR: 1,
    dependency_drift.RISK_MAJOR: 2,
}

VALID_SEVERITIES = set(SEVERITY_ORDER)


class PlannerError(RuntimeError):
    """Raised when upgrade planner encounters a blocking error."""


@dataclass(slots=True)
class PlannerConfig:
    sbom_path: Path
    metadata_path: Path | None
    packages: frozenset[str] | None
    allow_major: bool
    limit: int | None
    poetry_path: str
    project_root: Path
    skip_resolver: bool
    output_path: Path | None
    verbose: bool


@dataclass(slots=True)
class UpgradeCandidate:
    name: str
    canonical_name: str
    current: str | None
    latest: str | None
    severity: str
    notes: list[str]
    score: float = 0.0
    score_breakdown: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "canonical_name": self.canonical_name,
            "current": self.current,
            "latest": self.latest,
            "severity": self.severity,
            "notes": list(self.notes),
            "score": self.score,
            "score_breakdown": dict(self.score_breakdown),
        }


@dataclass(slots=True)
class ResolverResult:
    status: str
    command: list[str]
    returncode: int | None
    duration_s: float | None
    stdout: str | None
    stderr: str | None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": self.status,
            "command": list(self.command),
            "returncode": self.returncode,
            "duration_s": self.duration_s,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }
        if self.reason:
            payload["reason"] = self.reason
        return payload


@dataclass(slots=True)
class PlanEntry:
    candidate: UpgradeCandidate
    resolver: ResolverResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate": self.candidate.to_dict(),
            "resolver": self.resolver.to_dict(),
        }


@dataclass(slots=True)
class PlannerResult:
    generated_at: datetime
    config: PlannerConfig
    attempts: list[PlanEntry]
    summary: dict[str, int]
    recommended_commands: list[str]
    exit_code: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "sbom_path": str(self.config.sbom_path),
            "metadata_path": (
                str(self.config.metadata_path) if self.config.metadata_path else None
            ),
            "packages_requested": (
                sorted(self.config.packages) if self.config.packages else None
            ),
            "allow_major": self.config.allow_major,
            "skip_resolver": self.config.skip_resolver,
            "project_root": str(self.config.project_root),
            "summary": dict(self.summary),
            "recommended_commands": list(self.recommended_commands),
            "attempts": [entry.to_dict() for entry in self.attempts],
        }


TRACER = trace.get_tracer("prometheus.upgrade_planner")
PLANNER_RUN_COUNTER = Counter(
    "dependency_planner_runs_total",
    "Total dependency upgrade planner executions by outcome.",
    labelnames=("outcome",),
)
PLANNER_ATTEMPT_COUNTER = Counter(
    "dependency_planner_attempts_total",
    "Dependency upgrade planner attempts grouped by resolver status.",
    labelnames=("status",),
)
PLANNER_RESOLVER_DURATION = Histogram(
    "dependency_planner_resolver_duration_seconds",
    "Duration of dependency upgrade resolver executions in seconds.",
    labelnames=("status",),
)
PLANNER_STAGE_DURATION = Histogram(
    "dependency_planner_stage_duration_seconds",
    "Duration of dependency planner stages in seconds.",
    labelnames=("stage",),
)

_OBSERVABILITY_BOOTSTRAPPED = False


def _ensure_observability() -> None:
    global _OBSERVABILITY_BOOTSTRAPPED
    if _OBSERVABILITY_BOOTSTRAPPED:
        return
    configure_tracing(
        "prometheus-upgrade-planner",
        resource_attributes={"component": "scripts.upgrade_planner"},
    )
    configure_metrics(namespace="prometheus_upgrade_planner")
    _OBSERVABILITY_BOOTSTRAPPED = True


def generate_plan(config: PlannerConfig) -> PlannerResult:
    _ensure_observability()
    total_start = time.perf_counter()
    with TRACER.start_as_current_span("upgrade_planner.generate_plan") as span:
        span.set_attribute("upgrade_planner.allow_major", config.allow_major)
        span.set_attribute(
            "upgrade_planner.limit",
            config.limit if config.limit is not None else -1,
        )
        span.set_attribute("upgrade_planner.skip_resolver", config.skip_resolver)
        span.set_attribute(
            "upgrade_planner.packages_requested",
            len(config.packages) if config.packages else 0,
        )
        try:
            report_start = time.perf_counter()
            report, policy = _build_drift_report(config.sbom_path, config.metadata_path)
            PLANNER_STAGE_DURATION.labels(stage="report").observe(
                time.perf_counter() - report_start
            )

            selection_start = time.perf_counter()
            candidates = _select_candidates(report.packages, config, policy)
            PLANNER_STAGE_DURATION.labels(stage="selection").observe(
                time.perf_counter() - selection_start
            )
            span.set_attribute("upgrade_planner.candidates", len(candidates))

            attempts: list[PlanEntry] = []
            for candidate in candidates:
                entry = _evaluate_candidate(candidate, config)
                attempts.append(entry)
                _record_attempt_metrics(entry)

            summary = _summarise_attempts(attempts)
            recommended = [
                shlex.join(
                    [config.poetry_path, "update", entry.candidate.canonical_name]
                )
                for entry in attempts
                if entry.resolver.status == "ok"
            ]
            exit_code = 2 if summary["failed"] > 0 else 0

            span.set_attribute("upgrade_planner.summary.ok", summary.get("ok", 0))
            span.set_attribute(
                "upgrade_planner.summary.failed", summary.get("failed", 0)
            )
            span.set_attribute(
                "upgrade_planner.summary.skipped", summary.get("skipped", 0)
            )
            span.set_attribute("upgrade_planner.recommended_commands", len(recommended))
            span.set_attribute("upgrade_planner.exit_code", exit_code)

            outcome = "success" if exit_code == 0 else "failed"
            if exit_code != 0:
                span.set_status(Status(StatusCode.ERROR))
            PLANNER_RUN_COUNTER.labels(outcome=outcome).inc()
            span.set_attribute("upgrade_planner.outcome", outcome)

            return PlannerResult(
                generated_at=datetime.now(UTC),
                config=config,
                attempts=attempts,
                summary=summary,
                recommended_commands=recommended,
                exit_code=exit_code,
            )
        except Exception as exc:  # pragma: no cover - defensive guard
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR))
            PLANNER_RUN_COUNTER.labels(outcome="error").inc()
            raise
        finally:
            total_duration = time.perf_counter() - total_start
            PLANNER_STAGE_DURATION.labels(stage="total").observe(total_duration)
            span.set_attribute(
                "upgrade_planner.duration_ms", round(total_duration * 1000, 3)
            )


def _build_drift_report(sbom_path: Path, metadata_path: Path | None) -> tuple[
    dependency_drift.DependencyDriftReport,
    dependency_drift.DriftPolicy,
]:
    if not sbom_path.exists():
        raise PlannerError(f"SBOM file not found: {sbom_path}")
    components = dependency_drift.load_sbom(sbom_path)
    metadata = dependency_drift.load_metadata(metadata_path)
    policy = dependency_drift.DriftPolicy()
    report = dependency_drift.evaluate_drift(components, metadata, policy)
    return report, policy


def _select_candidates(
    packages: Iterable[dependency_drift.PackageDrift],
    config: PlannerConfig,
    policy: dependency_drift.DriftPolicy,
) -> list[UpgradeCandidate]:
    selected: list[UpgradeCandidate] = []
    packages_filter = (
        {str(canonicalize_name(pkg)) for pkg in config.packages}
        if config.packages
        else None
    )

    for package in packages:
        candidate = _build_candidate(package, packages_filter, config.allow_major)
        if candidate is not None:
            _score_candidate(candidate, policy, config)
            selected.append(candidate)

    selected.sort(
        key=lambda candidate: (
            -candidate.score,
            SEVERITY_ORDER.get(candidate.severity, 99),
            candidate.name.lower(),
        )
    )

    if config.limit is not None:
        selected = selected[: config.limit]

    return selected


def _build_candidate(
    package: dependency_drift.PackageDrift,
    packages_filter: set[str] | None,
    allow_major: bool,
) -> UpgradeCandidate | None:
    raw_name = (package.name or "").strip()
    if not raw_name:
        return None
    canonical = str(canonicalize_name(raw_name))
    if not canonical:
        return None
    severity = package.severity
    if severity not in VALID_SEVERITIES:
        return None
    if severity == dependency_drift.RISK_MAJOR and not allow_major:
        return None
    if packages_filter is not None and canonical not in packages_filter:
        return None
    return UpgradeCandidate(
        name=package.name,
        canonical_name=canonical,
        current=package.current,
        latest=package.latest,
        severity=severity,
        notes=list(package.notes),
    )


def _score_candidate(
    candidate: UpgradeCandidate,
    policy: dependency_drift.DriftPolicy,
    config: PlannerConfig,
) -> None:
    breakdown: dict[str, float] = {}

    severity_weights = {
        dependency_drift.RISK_PATCH: 3.0,
        dependency_drift.RISK_MINOR: 6.0,
        dependency_drift.RISK_MAJOR: 9.0,
    }
    severity_score = severity_weights.get(candidate.severity, 1.0)
    breakdown["severity"] = severity_score

    overrides = getattr(policy, "package_overrides", None)
    override = overrides.get(candidate.canonical_name) if overrides else None

    contract_penalty = 0.0
    if candidate.severity == dependency_drift.RISK_MAJOR and not config.allow_major:
        contract_penalty += 4.0
    if override and override.get("stay_on_major"):
        contract_penalty += 2.0
    breakdown["contract"] = -contract_penalty

    resolver_weight = 2.0
    if config.skip_resolver:
        resolver_weight *= 0.5
    breakdown["resolver"] = resolver_weight

    recency_weight = 1.5
    breakdown["recency"] = recency_weight

    total_score = sum(breakdown.values())
    candidate.score = round(total_score, 2)
    candidate.score_breakdown = breakdown


def _build_poetry_command(poetry_path: str, package: str) -> list[str]:
    return [
        poetry_path,
        "update",
        package,
        "--dry-run",
        "--no-ansi",
        "--no-interaction",
    ]


def _run_resolver(candidate: UpgradeCandidate, config: PlannerConfig) -> ResolverResult:
    command = _build_poetry_command(config.poetry_path, candidate.name)
    start = time.perf_counter()
    completed = subprocess.run(  # noqa: S603
        command,
        cwd=config.project_root,
        capture_output=True,
        text=True,
        env=_resolver_env(),
        check=False,
    )

    duration = time.perf_counter() - start
    status = "ok" if completed.returncode == 0 else "failed"
    with TRACER.start_as_current_span("upgrade_planner.resolver") as span:
        span.set_attribute("upgrade_planner.package", candidate.canonical_name)
        span.set_attribute("upgrade_planner.resolver.status", status)
        span.set_attribute("upgrade_planner.resolver.returncode", completed.returncode)
        span.set_attribute(
            "upgrade_planner.resolver.duration_ms", round(duration * 1000, 3)
        )
        if status != "ok":
            span.set_status(Status(StatusCode.ERROR))

    return ResolverResult(
        status=status,
        command=command,
        returncode=completed.returncode,
        duration_s=round(duration, 3),
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _resolver_env() -> dict[str, str]:
    env = dict(os.environ)
    env.setdefault("POETRY_NO_INTERACTION", "1")
    env.setdefault("POETRY_CACHE_DIR", str(Path("var").resolve() / "poetry-cache"))
    return env


def _summarise_attempts(attempts: Sequence[PlanEntry]) -> dict[str, int]:
    summary = {"ok": 0, "failed": 0, "skipped": 0}
    for entry in attempts:
        status = entry.resolver.status
        summary[status] = summary.get(status, 0) + 1
    return summary


def _evaluate_candidate(
    candidate: UpgradeCandidate, config: PlannerConfig
) -> PlanEntry:
    if candidate.latest is None:
        result = ResolverResult(
            status="skipped",
            command=[],
            returncode=None,
            duration_s=None,
            stdout=None,
            stderr=None,
            reason="latest version metadata unavailable",
        )
        return PlanEntry(candidate=candidate, resolver=result)

    if config.skip_resolver:
        result = ResolverResult(
            status="skipped",
            command=_build_poetry_command(config.poetry_path, candidate.name),
            returncode=None,
            duration_s=None,
            stdout=None,
            stderr=None,
            reason="resolver verification skipped by configuration",
        )
        return PlanEntry(candidate=candidate, resolver=result)

    try:
        result = _run_resolver(candidate, config)
    except FileNotFoundError as exc:  # pragma: no cover - defensive
        raise PlannerError(
            f"Poetry executable not found: {config.poetry_path}"
        ) from exc

    return PlanEntry(candidate=candidate, resolver=result)


def _record_attempt_metrics(entry: PlanEntry) -> None:
    status = entry.resolver.status or "unknown"
    PLANNER_ATTEMPT_COUNTER.labels(status=status).inc()
    duration = entry.resolver.duration_s
    if duration is not None:
        PLANNER_RESOLVER_DURATION.labels(status=status).observe(float(duration))


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan dependency upgrades using drift data and Poetry resolver dry-runs.",
    )
    parser.add_argument(
        "--sbom", required=True, type=Path, help="Path to CycloneDX SBOM JSON file."
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        help="Optional metadata snapshot describing latest package versions.",
    )
    parser.add_argument(
        "--package",
        "--packages",
        action="append",
        dest="packages",
        help="Limit planning to the specified package (can be provided multiple times).",
    )
    parser.add_argument(
        "--allow-major",
        action="store_true",
        help="Include major-version upgrades in the plan (default: exclude majors).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of packages to include in the plan.",
    )
    parser.add_argument(
        "--poetry",
        default=os.environ.get("POETRY_BINARY", "poetry"),
        help="Poetry executable to invoke for resolver verification (default: poetry).",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Project root where Poetry commands are executed (default: current working directory).",
    )
    parser.add_argument(
        "--skip-resolver",
        action="store_true",
        help="Skip Poetry resolver dry-runs (report only).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the plan JSON output.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print a human-readable summary to stdout.",
    )
    return parser.parse_args(argv)


def _build_config(args: argparse.Namespace) -> PlannerConfig:
    packages_input = (
        {value.strip() for value in args.packages} if args.packages else set()
    )
    canonical_packages = frozenset(
        str(canonicalize_name(value)) for value in packages_input if value
    )
    packages = canonical_packages or None
    if args.limit is not None and args.limit < 0:
        raise PlannerError("limit must be non-negative")
    project_root = args.project_root.resolve()
    poetry_path = _resolve_poetry_path(str(args.poetry))
    return PlannerConfig(
        sbom_path=args.sbom.resolve(),
        metadata_path=args.metadata.resolve() if args.metadata else None,
        packages=packages,
        allow_major=bool(args.allow_major),
        limit=args.limit,
        poetry_path=poetry_path,
        project_root=project_root,
        skip_resolver=bool(args.skip_resolver),
        output_path=args.output.resolve() if args.output else None,
        verbose=bool(args.verbose),
    )


def _resolve_poetry_path(raw: str) -> str:
    candidate = raw.strip()
    if not candidate:
        raise PlannerError("Poetry executable path cannot be empty")
    expanded = os.path.expanduser(candidate)
    path = Path(expanded)
    if path.exists():
        return str(path.resolve())
    located = shutil.which(expanded)
    if located:
        return located
    raise PlannerError(f"Poetry executable not found: {raw}")


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        config = _build_config(args)
        result = generate_plan(config)
    except PlannerError as exc:
        print(f"upgrade planner error: {exc}", file=sys.stderr)
        return 2

    plan_dict = result.to_dict()

    if config.output_path:
        config.output_path.parent.mkdir(parents=True, exist_ok=True)
        config.output_path.write_text(
            json.dumps(plan_dict, indent=2) + "\n", encoding="utf-8"
        )

    if config.verbose or not config.output_path:
        _print_summary(plan_dict)

    return result.exit_code


def _print_summary(plan: dict[str, Any]) -> None:
    print("Upgrade Plan Summary")
    summary = plan.get("summary", {})
    print(
        "  Attempts: ok={ok} failed={failed} skipped={skipped}".format(
            ok=summary.get("ok", 0),
            failed=summary.get("failed", 0),
            skipped=summary.get("skipped", 0),
        )
    )
    attempts = plan.get("attempts") or []
    if attempts:
        print("  Scoreboard:")
        for entry in attempts:
            candidate = entry.get("candidate", {})
            name = candidate.get("name", "unknown")
            current = candidate.get("current") or "?"
            latest = candidate.get("latest") or "?"
            score = candidate.get("score", 0)
            severity = candidate.get("severity", "unknown")
            breakdown = candidate.get("score_breakdown") or {}
            parts = ", ".join(f"{key}={value:.1f}" for key, value in breakdown.items())
            print(
                f"    - {name}: {current} -> {latest} | severity={severity} | score={score:.2f}"
            )
            if parts:
                print(f"      factors: {parts}")
    commands = plan.get("recommended_commands") or []
    if commands:
        print("  Recommended commands:")
        for command in commands:
            print(f"    - {command}")
    else:
        print("  No successful upgrade candidates identified.")


if __name__ == "__main__":  # pragma: no cover - CLI
    sys.exit(main())
