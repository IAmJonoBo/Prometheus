#!/usr/bin/env python3
"""Dependency upgrade guard orchestration."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from opentelemetry import trace
from prometheus_client import Counter

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover - Python <3.11 fallback
    import importlib

    tomllib = importlib.import_module("tomli")  # type: ignore[assignment]

from chiron.deps import drift as dependency_drift
from chiron.deps import mirror_manager
from observability import configure_metrics, configure_tracing

RISK_SAFE = "safe"
RISK_NEEDS_REVIEW = "needs-review"
RISK_BLOCKED = "blocked"

RISK_ORDER = {RISK_SAFE: 0, RISK_NEEDS_REVIEW: 1, RISK_BLOCKED: 2}
SEVERITY_TO_RISK = {
    "critical": RISK_BLOCKED,
    "high": RISK_BLOCKED,
    "medium": RISK_NEEDS_REVIEW,
    "moderate": RISK_NEEDS_REVIEW,
    "low": RISK_NEEDS_REVIEW,
    "info": RISK_SAFE,
    "unknown": RISK_NEEDS_REVIEW,
}

SOURCE_PREFLIGHT = "preflight"
SOURCE_RENOVATE = "renovate"
SOURCE_CVE = "cve"
SOURCE_CONTRACT = "contract"
SOURCE_DRIFT = "drift"

DEFAULT_CONTRACT_PATH = (
    Path(__file__).resolve().parents[1] / "configs" / "dependency-profile.toml"
)
DEFAULT_SNAPSHOT_ROOT = Path(__file__).resolve().parents[1] / "var" / "upgrade-guard"
DEFAULT_SNAPSHOT_RETAIN_DAYS = 30
DEFAULT_SBOM_MAX_AGE_DAYS = 7

FAIL_THRESHOLD_CHOICES = (RISK_SAFE, RISK_NEEDS_REVIEW, RISK_BLOCKED)

TRACER = trace.get_tracer("prometheus.upgrade_guard")
GUARD_RUN_COUNTER = Counter(
    "dependency_guard_runs_total",
    "Total dependency guard executions by outcome.",
    labelnames=("outcome",),
)

DRIFT_SEVERITY_TO_RISK = {
    dependency_drift.RISK_SAFE: RISK_SAFE,
    dependency_drift.RISK_PATCH: RISK_NEEDS_REVIEW,
    dependency_drift.RISK_MINOR: RISK_NEEDS_REVIEW,
    dependency_drift.RISK_MAJOR: RISK_BLOCKED,
    dependency_drift.RISK_CONFLICT: RISK_BLOCKED,
    dependency_drift.RISK_UNKNOWN: RISK_NEEDS_REVIEW,
}


@dataclass(slots=True)
class PackageAssessment:
    """Aggregated upgrade assessment for a single package."""

    name: str
    current: str | None = None
    candidate: str | None = None
    risk: str = RISK_SAFE
    reasons: list[str] = field(default_factory=list)

    def elevate(self, risk: str, reason: str | None = None) -> None:
        """Raise the package risk when the new level is higher."""

        if RISK_ORDER[risk] > RISK_ORDER[self.risk]:
            self.risk = risk
        if reason:
            self.reasons.append(reason)


@dataclass(slots=True)
class SourceSummary:
    name: str
    state: str
    message: str | None
    raw_path: str | None


@dataclass(slots=True)
class GuardData:
    preflight_summary: SourceSummary
    preflight_packages: list[PackageAssessment]
    renovate_summary: SourceSummary
    renovate_packages: list[PackageAssessment]
    cve_summary: SourceSummary
    cve_packages: list[PackageAssessment]
    contract_summary: SourceSummary
    contract_report: dict[str, Any] | None
    contract_data: Mapping[str, Any] | None
    drift_summary: SourceSummary
    drift_report: dict[str, Any] | None
    mirror_status: mirror_manager.MirrorStatus | None
    mirror_error: str | None


@dataclass(slots=True)
class SnapshotContext:
    run_id: str
    generated_at: datetime
    root: Path
    run_dir: Path
    inputs_dir: Path
    reports_dir: Path
    manifest_path: Path


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc


def _load_optional_json(
    path: Path | None, source: str
) -> tuple[SourceSummary, Any | None]:
    if path is None:
        return SourceSummary(source, "missing", "path not provided", None), None
    if not path.exists():
        return SourceSummary(source, "missing", "file not found", str(path)), None
    try:
        data = _read_json(path)
    except ValueError as exc:
        return SourceSummary(source, "error", str(exc), str(path)), None
    return SourceSummary(source, "ok", None, str(path)), data


def _load_contract(path: Path | None) -> tuple[SourceSummary, Mapping[str, Any] | None]:
    if path is None:
        return (
            SourceSummary(SOURCE_CONTRACT, "missing", "path not provided", None),
            None,
        )
    contract_path = Path(path)
    if not contract_path.exists():
        return (
            SourceSummary(
                SOURCE_CONTRACT, "missing", "file not found", str(contract_path)
            ),
            None,
        )
    try:
        with contract_path.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return (
            SourceSummary(SOURCE_CONTRACT, "error", str(exc), str(contract_path)),
            None,
        )
    return SourceSummary(SOURCE_CONTRACT, "ok", None, str(contract_path)), data


def _parse_contract_timestamp(raw: object | None) -> datetime | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def _evaluate_contract_metadata(data: Mapping[str, Any]) -> dict[str, Any]:
    contract_section = data.get("contract")
    contract_status = None
    default_review_days = 14
    last_validated_raw: object | None = None
    if isinstance(contract_section, Mapping):
        contract_status = str(contract_section.get("status") or "unknown")
        last_validated_raw = contract_section.get("last_validated")
        try:
            default_review_days = int(
                contract_section.get("default_review_days") or default_review_days
            )
        except (TypeError, ValueError):
            default_review_days = 14
    signature_policy = _extract_signature_policy(data)
    snoozes = _extract_snoozes(data)
    environment_alignment = _extract_environment_alignment(data)

    validated_at = _parse_contract_timestamp(last_validated_raw)
    threshold_days = max(default_review_days, 1)
    block_threshold = threshold_days * 2
    now = datetime.now(UTC)
    age_days: int | None = None
    status = "unknown"
    risk = RISK_NEEDS_REVIEW
    note = None

    if validated_at is None:
        status = "unknown"
        risk = RISK_NEEDS_REVIEW
        note = "contract.last_validated missing or invalid"
    else:
        delta = now - validated_at
        age_days = int(delta.total_seconds() // 86_400)
        if age_days <= threshold_days:
            status = "fresh"
            risk = RISK_SAFE
            note = f"Validated {age_days} day(s) ago"
        elif age_days <= block_threshold:
            status = "stale"
            risk = RISK_NEEDS_REVIEW
            note = (
                f"Validated {age_days} day(s) ago (threshold {threshold_days} day(s))"
            )
        else:
            status = "expired"
            risk = RISK_BLOCKED
            note = (
                f"Validated {age_days} day(s) ago (threshold {threshold_days} day(s))"
            )

    record = {
        "status": status,
        "risk": risk,
        "note": note,
        "last_validated": str(last_validated_raw) if last_validated_raw else None,
        "age_days": age_days,
        "threshold_days": threshold_days,
        "default_review_days": default_review_days,
        "contract_status": contract_status,
        "signature_policy": signature_policy,
        "snoozes": snoozes,
        "environment_alignment": environment_alignment,
    }
    return record


def _evaluate_drift(
    sbom_path: Path | None,
    metadata_path: Path | None,
    contract_data: Mapping[str, Any] | None,
    sbom_max_age_days: int | None,
) -> tuple[SourceSummary, dict[str, Any] | None]:
    if sbom_path is None:
        return (
            SourceSummary(SOURCE_DRIFT, "missing", "sbom path not provided", None),
            None,
        )
    if not sbom_path.exists():
        return (
            SourceSummary(
                SOURCE_DRIFT, "missing", "sbom file not found", str(sbom_path)
            ),
            None,
        )
    try:
        components = dependency_drift.load_sbom(sbom_path)
    except ValueError as exc:
        return SourceSummary(SOURCE_DRIFT, "error", str(exc), str(sbom_path)), None

    metadata = dependency_drift.load_metadata(metadata_path)
    metadata_reference = None
    if metadata_path and metadata_path.exists():
        metadata_reference = str(metadata_path)
    policy = dependency_drift.DriftPolicy()
    if contract_data:
        updates_policy = _extract_updates_policy(contract_data)
        policy_payload = dict(updates_policy) if updates_policy else None
        policy = dependency_drift.parse_policy(policy_payload)

    report = dependency_drift.evaluate_drift(components, metadata, policy)
    sbom_age_days: int | None = None
    sbom_threshold = (
        sbom_max_age_days
        if isinstance(sbom_max_age_days, int) and sbom_max_age_days >= 0
        else None
    )
    sbom_stale = False
    if sbom_path.exists():
        mtime = datetime.fromtimestamp(sbom_path.stat().st_mtime, tz=UTC)
        delta = datetime.now(UTC) - mtime
        sbom_age_days = int(delta.total_seconds() // 86_400)
        if sbom_threshold is not None and sbom_age_days > sbom_threshold:
            sbom_stale = True
            report.notes.append(
                f"SBOM generated {sbom_age_days} day(s) ago exceeds cadence threshold of {sbom_threshold} day(s)."
            )
    drift_payload = {
        "severity": report.severity,
        "packages": [
            {
                "name": pkg.name,
                "current": pkg.current,
                "latest": pkg.latest,
                "severity": pkg.severity,
                "notes": pkg.notes,
            }
            for pkg in report.packages
        ],
        "notes": report.notes,
        "generated_at": report.generated_at,
        "metadata_path": metadata_reference,
        "sbom_age_days": sbom_age_days,
        "sbom_age_threshold_days": sbom_threshold,
        "sbom_stale": sbom_stale,
    }
    return SourceSummary(SOURCE_DRIFT, "ok", None, str(sbom_path)), drift_payload


def _extract_updates_policy(
    contract_data: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    policies = contract_data.get("policies")
    if not isinstance(policies, Mapping):
        return None
    updates = policies.get("updates")
    if isinstance(updates, Mapping):
        return updates
    return None


def _coerce_str(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_int(value: Any | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_str_list(values: object | None) -> list[str]:
    if not isinstance(values, (list, tuple, set)):
        return []
    result: list[str] = []
    for item in values:
        text = _coerce_str(item)
        if text:
            result.append(text)
    return result


def _coerce_scope(mapping: object | None) -> dict[str, str] | None:
    if not isinstance(mapping, Mapping):
        return None
    scope: dict[str, str] = {}
    for key, value in mapping.items():
        key_text = _coerce_str(key)
        value_text = _coerce_str(value)
        if key_text and value_text:
            scope[key_text] = value_text
    return scope or None


def _extract_signature_policy(
    contract_data: Mapping[str, Any],
) -> dict[str, Any] | None:
    policies = contract_data.get("policies")
    if not isinstance(policies, Mapping):
        return None
    signatures = policies.get("signatures")
    if not isinstance(signatures, Mapping):
        return None
    policy: dict[str, Any] = {
        "required": bool(signatures.get("required", False)),
        "keyring": _coerce_str(signatures.get("keyring")),
        "enforced_artifacts": _coerce_str_list(signatures.get("enforced_artifacts")),
        "attestation_required": _coerce_str_list(
            signatures.get("attestation_required")
        ),
        "grace_period_days": _coerce_int(signatures.get("grace_period_days")),
        "trusted_publishers": _coerce_str_list(signatures.get("trusted_publishers")),
        "allow_unsigned_profiles": _coerce_str_list(
            signatures.get("allow_unsigned_profiles")
        ),
    }
    return policy


def _extract_snoozes(contract_data: Mapping[str, Any]) -> list[dict[str, Any]]:
    governance = contract_data.get("governance")
    if not isinstance(governance, Mapping):
        return []
    entries = governance.get("snoozes")
    if not isinstance(entries, list):
        return []
    snoozes: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        identifier = _coerce_str(entry.get("id"))
        if not identifier:
            continue
        snoozes.append(
            {
                "id": identifier,
                "scope": _coerce_scope(entry.get("scope")),
                "reason": _coerce_str(entry.get("reason")),
                "expires_at": _coerce_str(entry.get("expires_at")),
                "requested_by": _coerce_str(entry.get("requested_by")),
                "approver": _coerce_str(entry.get("approver")),
            }
        )
    return snoozes


def _extract_environment_alignment(
    contract_data: Mapping[str, Any],
) -> dict[str, Any] | None:
    alignment = contract_data.get("environment_alignment")
    if not isinstance(alignment, Mapping):
        return None
    environments_raw = alignment.get("environments")
    environments: list[dict[str, Any]] = []
    if isinstance(environments_raw, list):
        for environment in environments_raw:
            if not isinstance(environment, Mapping):
                continue
            name = _coerce_str(environment.get("name"))
            if not name:
                continue
            environments.append(
                {
                    "name": name,
                    "profiles": _coerce_str_list(environment.get("profiles")),
                    "lockfiles": _coerce_str_list(environment.get("lockfiles")),
                    "model_registry": _coerce_str(environment.get("model_registry")),
                    "last_synced": _coerce_str(environment.get("last_synced")),
                    "sync_window_days": _coerce_int(
                        environment.get("sync_window_days")
                    ),
                    "requires_signatures": bool(
                        environment.get("requires_signatures", False)
                    ),
                }
            )
    payload: dict[str, Any] = {
        "alert_channel": _coerce_str(alignment.get("alert_channel")),
        "default_sync_window_days": _coerce_int(
            alignment.get("default_sync_window_days")
        ),
        "environments": environments,
    }
    return payload


def _max_risk(current: str, candidate: str | None) -> str:
    if candidate is None or candidate not in RISK_ORDER:
        return current
    if RISK_ORDER[candidate] > RISK_ORDER[current]:
        return candidate
    return current


def _describe_signature_failures(
    failures: Sequence[mirror_manager.MirrorArtifact],
) -> list[str]:
    issues: list[str] = []
    for artifact in failures:
        reason = artifact.signature.reason or artifact.signature.status
        issues.append(f"{artifact.name}: {reason}")
    return issues


def _assess_signature_compliance(
    policy: Mapping[str, Any] | None,
    mirror_status: mirror_manager.MirrorStatus | None,
    mirror_error: str | None,
    require_signature: bool,
) -> dict[str, Any]:
    config = policy if isinstance(policy, Mapping) else {}
    required = bool(config.get("required"))
    enforced = set(config.get("enforced_artifacts", []))
    attestation = sorted(config.get("attestation_required", [])) if config else []
    grace_days = config.get("grace_period_days")

    result: dict[str, Any] = {
        "status": "not-required",
        "risk": RISK_SAFE,
        "issues": [],
        "total_artifacts": 0,
        "verified_artifacts": 0,
        "failed_artifacts": 0,
        "attestation_required": attestation,
        "grace_period_days": grace_days,
    }

    if not required and not require_signature:
        return result

    if mirror_status is None:
        result["status"] = "unknown"
        result["risk"] = RISK_NEEDS_REVIEW
        result["issues"] = [mirror_error or "mirror status not provided"]
        return result

    artifacts = list(mirror_status.artifacts)
    if enforced:
        artifacts = [artifact for artifact in artifacts if artifact.name in enforced]

    total = len(artifacts)
    result["total_artifacts"] = total
    if not total:
        result["status"] = "missing-artifacts"
        result["risk"] = RISK_NEEDS_REVIEW
        result["issues"] = ["No mirror artifacts matched signature policy scope"]
        return result

    failures = [artifact for artifact in artifacts if not artifact.signature.verified]
    verified = total - len(failures)
    result["failed_artifacts"] = len(failures)
    result["verified_artifacts"] = verified

    if failures:
        result["status"] = "failed"
        result["risk"] = RISK_BLOCKED
        result["issues"] = _describe_signature_failures(failures)
        return result

    result["status"] = "verified"
    return result


def _assess_snoozes(snoozes: list[dict[str, Any]]) -> dict[str, Any]:
    if not snoozes:
        return {
            "risk": RISK_SAFE,
            "entries": [],
            "counts": {},
        }

    now = datetime.now(UTC)
    entries: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    highest = RISK_SAFE

    for entry in snoozes:
        identifier = entry.get("id") or "unknown"
        expires_raw = entry.get("expires_at")
        expires_at = _parse_contract_timestamp(expires_raw)
        status = "active"
        risk = RISK_SAFE
        days_remaining: int | None = None
        days_overdue: int | None = None

        if expires_at is None:
            status = "unknown"
            risk = RISK_NEEDS_REVIEW
        else:
            delta = expires_at - now
            days = int(delta.total_seconds() // 86_400)
            if delta.total_seconds() < 0:
                status = "expired"
                risk = RISK_BLOCKED
                days_overdue = abs(days)
            elif days <= 3:
                status = "expiring-soon"
                risk = RISK_NEEDS_REVIEW
                days_remaining = max(days, 0)
            else:
                days_remaining = days

        highest = _max_risk(highest, risk)
        counts[status] = counts.get(status, 0) + 1
        entries.append(
            {
                "id": identifier,
                "status": status,
                "risk": risk,
                "expires_at": expires_raw,
                "days_remaining": days_remaining,
                "days_overdue": days_overdue,
            }
        )

    return {
        "risk": highest,
        "entries": entries,
        "counts": counts,
    }


def _apply_contract_enforcements(data: GuardData, args: argparse.Namespace) -> None:
    require_signature = getattr(args, "mirror_require_signature", True)
    contract_report = data.contract_report or {
        "status": data.contract_summary.state,
        "risk": RISK_NEEDS_REVIEW,
        "note": data.contract_summary.message,
        "signature_policy": None,
        "snoozes": [],
    }

    if "signature_policy" not in contract_report:
        contract_report["signature_policy"] = None
    if not isinstance(contract_report.get("snoozes"), list):
        contract_report["snoozes"] = []

    signature_compliance = _assess_signature_compliance(
        contract_report.get("signature_policy"),
        data.mirror_status,
        data.mirror_error,
        require_signature,
    )
    contract_report["signature_compliance"] = signature_compliance
    contract_report["risk"] = _max_risk(
        contract_report.get("risk", RISK_SAFE),
        signature_compliance["risk"],
    )

    snooze_status = _assess_snoozes(contract_report.get("snoozes") or [])
    contract_report["snooze_status"] = snooze_status
    contract_report["risk"] = _max_risk(contract_report["risk"], snooze_status["risk"])

    data.contract_report = contract_report


def _drift_risk(drift_report: Mapping[str, Any] | None) -> str:
    if not drift_report:
        return RISK_SAFE
    if drift_report.get("sbom_stale"):
        return RISK_NEEDS_REVIEW
    severity_value = drift_report.get("severity")
    severity_key = str(severity_value) if severity_value else dependency_drift.RISK_SAFE
    return DRIFT_SEVERITY_TO_RISK.get(severity_key, RISK_NEEDS_REVIEW)


def _infer_risk_from_status(status: str | None) -> str:
    status_lower = (status or "").strip().lower()
    if status_lower in {"error", "fail", "failure", "blocked"}:
        return RISK_BLOCKED
    if status_lower in {"warn", "warning", "allowlisted", "sdist", "degraded"}:
        return RISK_NEEDS_REVIEW
    return RISK_SAFE


def _evaluate_preflight(packages: Iterable[dict[str, Any]]) -> list[PackageAssessment]:
    assessments: dict[str, PackageAssessment] = {}
    for entry in packages:
        _apply_preflight_entry(assessments, entry)
    return list(assessments.values())


def _apply_preflight_entry(
    assessments: dict[str, PackageAssessment],
    entry: dict[str, Any],
) -> None:
    name = str(entry.get("name")) if entry.get("name") else None
    if not name:
        return
    version = str(entry.get("version")) if entry.get("version") else None
    assessment = assessments.setdefault(
        name, PackageAssessment(name=name, current=version)
    )

    status = entry.get("status")
    missing = entry.get("missing_targets") or entry.get("missing") or []
    allowlisted = bool(entry.get("allowlisted"))

    risk = _infer_risk_from_status(status)
    reason_parts = []
    if status:
        reason_parts.append(f"status={status}")
    if missing:
        reason_parts.append(f"missing={len(missing)} targets")
    if allowlisted:
        reason_parts.append("allowlisted sdist")
        risk = max(risk, RISK_NEEDS_REVIEW, key=lambda key: RISK_ORDER[key])
    reason = ", ".join(reason_parts) if reason_parts else None

    assessment.elevate(risk, reason)


def _evaluate_renovate(entries: Iterable[dict[str, Any]]) -> list[PackageAssessment]:
    assessments: dict[str, PackageAssessment] = {}
    for entry in entries:
        name = str(entry.get("name")) if entry.get("name") else None
        if not name:
            continue
        current = (
            str(
                entry.get("version")
                or entry.get("currentVersion")
                or entry.get("current_version")
                or ""
            )
            or None
        )
        latest = (
            str(
                entry.get("latest")
                or entry.get("newVersion")
                or entry.get("latest_version")
                or ""
            )
            or None
        )
        update_type = str(
            entry.get("updateType") or entry.get("update_type") or ""
        ).lower()

        assessment = assessments.setdefault(
            name,
            PackageAssessment(name=name, current=current, candidate=latest),
        )
        if update_type in {"major"}:
            assessment.elevate(RISK_BLOCKED, "major upgrade candidate")
        elif update_type in {"minor"}:
            assessment.elevate(RISK_NEEDS_REVIEW, "minor upgrade candidate")
        elif update_type in {"patch"}:
            assessment.elevate(RISK_SAFE, "patch upgrade candidate")
        elif update_type:
            assessment.elevate(RISK_NEEDS_REVIEW, f"upgrade type={update_type}")
    return list(assessments.values())


def _evaluate_cve(packages: Iterable[dict[str, Any]]) -> list[PackageAssessment]:
    assessments: dict[str, PackageAssessment] = {}
    for entry in packages:
        _apply_cve_entry(assessments, entry)
    return list(assessments.values())


def _apply_cve_entry(
    assessments: dict[str, PackageAssessment],
    entry: Mapping[str, Any],
) -> None:
    name = str(entry.get("name")) if entry.get("name") else None
    if not name:
        return
    current = str(entry.get("version") or entry.get("current") or "") or None
    candidate = str(entry.get("next_version") or entry.get("candidate") or "") or None
    assessment = assessments.setdefault(
        name,
        PackageAssessment(name=name, current=current, candidate=candidate),
    )
    issues = entry.get("issues") or []
    for issue in issues:
        _apply_cve_issue(assessment, issue)


def _apply_cve_issue(assessment: PackageAssessment, issue: Mapping[str, Any]) -> None:
    severity = str(issue.get("severity") or "unknown").lower()
    identifier = str(issue.get("identifier") or issue.get("id") or "cve")
    summary = issue.get("summary") or issue.get("description")
    risk = SEVERITY_TO_RISK.get(severity, RISK_NEEDS_REVIEW)
    reason = f"{identifier} severity={severity}"
    if summary:
        reason = f"{reason}: {summary}"
    assessment.elevate(risk, reason)


def _merge_assessments(*groups: Iterable[PackageAssessment]) -> list[PackageAssessment]:
    merged: dict[str, PackageAssessment] = {}
    for group in groups:
        for assessment in group:
            existing = merged.setdefault(
                assessment.name, PackageAssessment(name=assessment.name)
            )
            if assessment.current and not existing.current:
                existing.current = assessment.current
            if assessment.candidate and not existing.candidate:
                existing.candidate = assessment.candidate
            if assessment.reasons:
                existing.reasons.extend(assessment.reasons)
            existing.elevate(assessment.risk, None)
    return list(merged.values())


def _highest_risk(packages: Iterable[PackageAssessment]) -> str:
    highest = RISK_SAFE
    for package in packages:
        if RISK_ORDER[package.risk] > RISK_ORDER[highest]:
            highest = package.risk
    return highest


def _render_markdown(assessment: dict[str, Any]) -> str:
    summary = assessment.get("summary", {})
    contract_section = assessment.get("contract") or {}
    drift_section = assessment.get("drift") or {}
    packages = assessment.get("packages", [])
    evidence = assessment.get("evidence") or {}

    lines: list[str] = []
    lines.extend(_markdown_header(assessment))
    lines.extend(_markdown_summary_section(summary, contract_section, drift_section))
    if contract_section:
        lines.extend(_markdown_contract_section(contract_section))
    if drift_section:
        lines.extend(_markdown_drift_section(drift_section))
    if packages:
        lines.extend(_markdown_package_section(packages))
    if evidence:
        lines.extend(_markdown_evidence_section(evidence))
    return "\n".join(lines)


def _markdown_header(assessment: Mapping[str, Any]) -> list[str]:
    return [
        "# Upgrade Guard Assessment",
        "",
        f"Generated: {assessment.get('generated_at', 'n/a')}",
        f"Guard version: {assessment.get('guard_version', 'n/a')}",
        "",
    ]


def _markdown_summary_section(
    summary: Mapping[str, Any],
    contract_section: Mapping[str, Any],
    drift_section: Mapping[str, Any],
) -> list[str]:
    lines = ["## Summary", ""]
    lines.append(
        f"- Highest severity: **{summary.get('highest_severity', 'unknown')}**"
    )
    lines.append(f"- Packages flagged: **{summary.get('packages_flagged', 0)}**")
    if contract_section:
        lines.append(
            "- Contract risk: **"
            f"{contract_section.get('risk', 'unknown')}**"
            f" ({contract_section.get('status', 'n/a')})"
        )
    if drift_section:
        lines.append(
            "- Drift severity: **" f"{drift_section.get('severity', 'unknown')}**"
        )
    missing = summary.get("inputs_missing", [])
    if missing:
        lines.append(f"- Missing inputs: {', '.join(missing)}")
    notes = summary.get("notes") or []
    if notes:
        lines.append("- Notes:")
        for note in notes:
            lines.append(f"  - {note}")
    lines.append("")
    return lines


def _markdown_contract_section(contract_section: Mapping[str, Any]) -> list[str]:
    lines = ["## Contract Status", ""]
    lines.append(f"- Last validated: {contract_section.get('last_validated', 'n/a')}")
    age = contract_section.get("age_days")
    if age is not None:
        lines.append(f"- Age: {age} day(s)")
    lines.append(f"- Threshold: {contract_section.get('threshold_days', 'n/a')} day(s)")
    contract_state = contract_section.get("contract_status")
    if contract_state:
        lines.append(f"- Contract state: {contract_state}")
    note = contract_section.get("note")
    if note:
        lines.append(f"  - {note}")
    lines.append("")
    return lines


def _markdown_drift_section(drift_section: Mapping[str, Any]) -> list[str]:
    lines = ["## Drift Analysis", ""]
    lines.append(f"- Severity: {drift_section.get('severity', 'unknown')}")
    metadata_path = drift_section.get("metadata_path")
    if metadata_path:
        lines.append(f"- Metadata snapshot: `{metadata_path}`")
    drift_notes = drift_section.get("notes") or []
    if drift_notes:
        lines.append("- Notes:")
        for note in drift_notes:
            lines.append(f"  - {note}")
    drift_packages = drift_section.get("packages") or []
    if drift_packages:
        lines.append("")
        lines.append("### Drifted Packages")
        lines.append("")
        for package in drift_packages[:10]:
            lines.append(
                "- **{name}** ({current} → {latest}): {severity}".format(
                    name=package.get("name"),
                    current=package.get("current", "n/a"),
                    latest=package.get("latest", "n/a"),
                    severity=package.get("severity", "unknown"),
                )
            )
            for note in package.get("notes", [])[:3]:
                lines.append(f"  - {note}")
        lines.append("")
    return lines


def _markdown_package_section(packages: Iterable[Mapping[str, Any]]) -> list[str]:
    lines = ["## Package Risk", ""]
    for package in packages:
        lines.append(
            "- **{name}** ({current} → {candidate}): {risk}".format(
                name=package.get("name"),
                current=package.get("current", "n/a"),
                candidate=package.get("candidate", "n/a"),
                risk=package.get("risk"),
            )
        )
        reasons = package.get("reasons") or []
        for reason in reasons:
            lines.append(f"  - {reason}")
    lines.append("")
    return lines


def _markdown_evidence_section(evidence: Mapping[str, Any]) -> list[str]:
    lines = ["## Evidence", ""]
    for key, value in evidence.items():
        if value:
            lines.append(f"- {key}: `{value}`")
    lines.append("")
    return lines


def _collect_preflight_packages(
    preflight_data: Mapping[str, Any] | None,
) -> list[PackageAssessment]:
    if not isinstance(preflight_data, Mapping):
        return []
    packages = preflight_data.get("packages", [])
    return _evaluate_preflight(packages)


def _collect_renovate_packages(
    renovate_data: Any,
    summary: SourceSummary,
) -> list[PackageAssessment]:
    if not renovate_data:
        return []
    if isinstance(renovate_data, dict) and "packages" in renovate_data:
        return _evaluate_renovate(renovate_data["packages"])
    if isinstance(renovate_data, list):
        return _evaluate_renovate(renovate_data)
    summary.state = "error"
    summary.message = "unrecognised renovate metadata format"
    return []


def _collect_cve_packages(
    cve_data: Any,
    summary: SourceSummary,
) -> list[PackageAssessment]:
    if not cve_data:
        return []
    if isinstance(cve_data, dict) and "packages" in cve_data:
        return _evaluate_cve(cve_data["packages"])
    if isinstance(cve_data, list):
        return _evaluate_cve(cve_data)
    summary.state = "error"
    summary.message = "unrecognised CVE metadata format"
    return []


def _build_contract_report(
    contract_summary: SourceSummary,
    contract_data: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if contract_data:
        return _evaluate_contract_metadata(contract_data)
    if contract_summary.state in {"missing", "error"}:
        return {
            "status": contract_summary.state,
            "risk": RISK_NEEDS_REVIEW,
            "note": contract_summary.message,
            "last_validated": None,
            "age_days": None,
            "threshold_days": None,
            "default_review_days": None,
            "contract_status": None,
            "signature_policy": None,
            "snoozes": [],
            "environment_alignment": None,
        }
    return None


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate dependency telemetry into a single upgrade guard verdict.",
    )
    parser.add_argument(
        "--preflight", type=Path, help="Path to dependency preflight JSON output."
    )
    parser.add_argument(
        "--renovate", type=Path, help="Path to Renovate metadata JSON file."
    )
    parser.add_argument("--cve", type=Path, help="Path to CVE advisory JSON file.")
    parser.add_argument(
        "--output",
        type=Path,
        help="Write machine-readable assessment JSON to this path.",
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        help="Optional path for a Markdown summary of the assessment.",
    )
    parser.add_argument(
        "--contract",
        type=Path,
        default=DEFAULT_CONTRACT_PATH,
        help="Path to dependency contract TOML file.",
    )
    parser.add_argument(
        "--sbom",
        type=Path,
        help="Path to CycloneDX SBOM JSON for drift analysis.",
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        help="Optional path to metadata snapshot describing latest versions.",
    )
    parser.add_argument(
        "--sbom-max-age-days",
        type=int,
        default=DEFAULT_SBOM_MAX_AGE_DAYS,
        help="Maximum allowed age (in days) for the SBOM before drift cadence is flagged (default: 7).",
    )
    parser.add_argument(
        "--snapshot-root",
        type=Path,
        default=DEFAULT_SNAPSHOT_ROOT,
        help="Directory where guard snapshots are stored (default: var/upgrade-guard).",
    )
    parser.add_argument(
        "--snapshot-tag",
        help="Optional label appended to snapshot run identifier (e.g., environment name).",
    )
    parser.add_argument(
        "--snapshot-retention-days",
        type=int,
        default=DEFAULT_SNAPSHOT_RETAIN_DAYS,
        help="Number of days to retain historical snapshots before pruning (default: 30).",
    )
    parser.add_argument(
        "--skip-snapshots",
        action="store_true",
        help="Disable snapshot generation for this run.",
    )
    parser.add_argument(
        "--mirror-root",
        type=Path,
        help="Optional mirror root directory used for signature verification.",
    )
    parser.add_argument(
        "--mirror-allow-missing",
        dest="mirror_require_signature",
        action="store_false",
        help="Allow missing signatures when evaluating mirror compliance.",
    )
    parser.add_argument(
        "--mirror-require-signature",
        dest="mirror_require_signature",
        action="store_true",
        help="Require signatures when evaluating mirror compliance (default).",
    )
    parser.set_defaults(mirror_require_signature=True)
    parser.add_argument(
        "--fail-threshold",
        choices=FAIL_THRESHOLD_CHOICES,
        default=RISK_NEEDS_REVIEW,
        help="Exit with non-zero status when highest severity meets or exceeds this value (default: needs-review).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print human readable summary to stdout.",
    )
    return parser.parse_args(argv)


def _collect_guard_data(args: argparse.Namespace) -> GuardData:
    preflight_summary, preflight_data = _load_optional_json(
        args.preflight, SOURCE_PREFLIGHT
    )
    renovate_summary, renovate_data = _load_optional_json(
        args.renovate, SOURCE_RENOVATE
    )
    cve_summary, cve_data = _load_optional_json(args.cve, SOURCE_CVE)
    contract_summary, contract_data = _load_contract(args.contract)

    preflight_packages = _collect_preflight_packages(preflight_data)
    renovate_packages = _collect_renovate_packages(renovate_data, renovate_summary)
    cve_packages = _collect_cve_packages(cve_data, cve_summary)
    contract_report = _build_contract_report(contract_summary, contract_data)
    drift_summary, drift_report = _evaluate_drift(
        args.sbom,
        args.metadata,
        contract_data,
        getattr(args, "sbom_max_age_days", None),
    )

    mirror_status = None
    mirror_error: str | None = None
    mirror_root = getattr(args, "mirror_root", None)
    if mirror_root:
        try:
            mirror_status = mirror_manager.discover_mirror(
                mirror_root,
                require_signature=getattr(args, "mirror_require_signature", True),
            )
        except OSError as exc:
            mirror_error = str(exc)

    data = GuardData(
        preflight_summary=preflight_summary,
        preflight_packages=preflight_packages,
        renovate_summary=renovate_summary,
        renovate_packages=renovate_packages,
        cve_summary=cve_summary,
        cve_packages=cve_packages,
        contract_summary=contract_summary,
        contract_report=contract_report,
        contract_data=contract_data,
        drift_summary=drift_summary,
        drift_report=drift_report,
        mirror_status=mirror_status,
        mirror_error=mirror_error,
    )

    _apply_contract_enforcements(data, args)

    return data


def _build_summary_notes(
    summaries: Iterable[SourceSummary],
    contract_report: Mapping[str, Any] | None,
    drift_report: Mapping[str, Any] | None,
) -> list[str]:
    notes: list[str] = []
    for src in summaries:
        if src.state == "error" and src.message:
            notes.append(f"{src.name}: {src.message}")
    if (
        contract_report
        and contract_report.get("note")
        and contract_report.get("risk") != RISK_SAFE
    ):
        notes.append(f"{SOURCE_CONTRACT}: {contract_report['note']}")
    if drift_report and drift_report.get("notes"):
        for note in cast(list[str], drift_report.get("notes"))[:3]:
            notes.append(f"{SOURCE_DRIFT}: {note}")
    return notes


def _compute_highest_risk(
    packages: Iterable[PackageAssessment],
    contract_report: Mapping[str, Any] | None,
    drift_report: Mapping[str, Any] | None,
) -> str:
    highest = _highest_risk(packages)
    if contract_report:
        contract_risk = contract_report.get("risk", RISK_SAFE)
        if (
            contract_risk in RISK_ORDER
            and RISK_ORDER[contract_risk] > RISK_ORDER[highest]
        ):
            highest = cast(str, contract_risk)
    if drift_report:
        drift_risk = _drift_risk(drift_report)
        if RISK_ORDER[drift_risk] > RISK_ORDER[highest]:
            highest = drift_risk
    return highest


def _assemble_assessment(
    data: GuardData,
    packages: list[PackageAssessment],
    highest: str,
    flagged: int,
    summary_notes: list[str],
    generated_at: datetime,
) -> dict[str, Any]:
    sorted_packages = [
        {
            "name": pkg.name,
            "current": pkg.current,
            "candidate": pkg.candidate,
            "risk": pkg.risk,
            "reasons": pkg.reasons,
        }
        for pkg in sorted(
            packages, key=lambda item: (RISK_ORDER[item.risk], item.name), reverse=True
        )
    ]
    summaries = (
        data.preflight_summary,
        data.renovate_summary,
        data.cve_summary,
        data.contract_summary,
        data.drift_summary,
    )

    assessment: dict[str, Any] = {
        "generated_at": generated_at.isoformat(),
        "guard_version": "1.0.0",
        "summary": {
            "highest_severity": highest,
            "packages_flagged": flagged,
            "inputs_missing": [src.name for src in summaries if src.state == "missing"],
            "notes": summary_notes,
        },
        "packages": sorted_packages,
        "evidence": {
            SOURCE_PREFLIGHT: data.preflight_summary.raw_path,
            SOURCE_RENOVATE: data.renovate_summary.raw_path,
            SOURCE_CVE: data.cve_summary.raw_path,
        },
    }

    if data.contract_report:
        assessment["contract"] = data.contract_report
    assessment["summary"]["contract_risk"] = (
        data.contract_report.get("risk", RISK_SAFE)
        if data.contract_report
        else RISK_SAFE
    )
    assessment["evidence"][SOURCE_CONTRACT] = data.contract_summary.raw_path

    if data.drift_report:
        assessment["drift"] = data.drift_report
        assessment["summary"]["drift_severity"] = data.drift_report.get("severity")
        metadata_path = data.drift_report.get("metadata_path")
        if metadata_path:
            assessment["evidence"]["drift_metadata"] = metadata_path
    assessment["evidence"][SOURCE_DRIFT] = data.drift_summary.raw_path

    return assessment


def _persist_outputs(
    assessment: Mapping[str, Any],
    args: argparse.Namespace,
) -> str | None:
    markdown: str | None = None
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(assessment, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    if args.markdown or args.verbose:
        markdown = _render_markdown(cast(dict[str, Any], assessment))
    if args.markdown and markdown is not None:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(markdown, encoding="utf-8")
    return markdown


def _format_snapshot_run_id(moment: datetime, tag: str | None) -> str:
    run_id = moment.strftime("%Y%m%dT%H%M%SZ")
    suffix = (tag or "").strip()
    if suffix:
        cleaned = "".join(
            ch for ch in suffix if ch.isalnum() or ch in {"-", "_"}
        ).strip("-_")
        if cleaned:
            run_id = f"{run_id}-{cleaned}"
    return run_id


def _parse_snapshot_run_id(run_id: str) -> datetime | None:
    candidate = run_id.split("-", 1)[0]
    try:
        base = datetime.strptime(candidate, "%Y%m%dT%H%M%SZ")
    except ValueError:
        return None
    return base.replace(tzinfo=UTC)


def _ensure_snapshot_context(
    args: argparse.Namespace, moment: datetime
) -> SnapshotContext | None:
    if getattr(args, "skip_snapshots", False):
        return None
    root = getattr(args, "snapshot_root", None) or DEFAULT_SNAPSHOT_ROOT
    root = root.resolve()
    run_id = _format_snapshot_run_id(moment, getattr(args, "snapshot_tag", None))
    run_dir = root / run_id
    inputs_dir = run_dir / "inputs"
    reports_dir = run_dir / "reports"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    return SnapshotContext(
        run_id=run_id,
        generated_at=moment,
        root=root,
        run_dir=run_dir,
        inputs_dir=inputs_dir,
        reports_dir=reports_dir,
        manifest_path=run_dir / "manifest.json",
    )


def _copy_snapshot_input(source: str | Path | None, destination: Path) -> str | None:
    if not source:
        return None
    source_path = Path(source)
    if not source_path.exists():
        return None
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(source_path, destination)
    except OSError:  # pragma: no cover - defensive
        return None
    return str(destination)


def _write_snapshot_reports(
    context: SnapshotContext,
    assessment: Mapping[str, Any],
    markdown: str | None,
    data: GuardData,
) -> dict[str, str]:
    reports: dict[str, str] = {}
    assessment_path = context.reports_dir / "assessment.json"
    assessment_path.write_text(
        json.dumps(assessment, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    reports["assessment"] = str(assessment_path)

    if markdown is not None:
        summary_path = context.reports_dir / "summary.md"
        summary_path.write_text(markdown, encoding="utf-8")
        reports["summary_markdown"] = str(summary_path)

    if data.contract_report:
        contract_path = context.reports_dir / "contract.json"
        contract_path.write_text(
            json.dumps(data.contract_report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        reports["contract"] = str(contract_path)

    if data.drift_report:
        drift_path = context.reports_dir / "drift.json"
        drift_path.write_text(
            json.dumps(data.drift_report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        reports["drift"] = str(drift_path)

    return reports


def _prune_snapshot_retention(
    root: Path, retain_days: int, moment: datetime
) -> list[str]:
    if retain_days < 0:
        return []
    removed: list[str] = []
    for entry in root.iterdir():
        if not entry.is_dir():
            continue
        parsed = _parse_snapshot_run_id(entry.name)
        if parsed is None:
            continue
        age_days = int((moment - parsed).total_seconds() // 86_400)
        if age_days > retain_days:
            shutil.rmtree(entry, ignore_errors=True)
            removed.append(entry.name)
    return removed


def _refresh_snapshot_latest(index_dir: Path) -> None:
    latest_path = index_dir / "latest.json"
    entries = sorted(
        (path for path in index_dir.glob("*.json") if path.name != "latest.json"),
        key=lambda path: path.name,
    )
    if not entries:
        latest_path.unlink(missing_ok=True)
        return
    latest_payload = json.loads(entries[-1].read_text(encoding="utf-8"))
    latest_path.write_text(
        json.dumps(latest_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _prune_snapshot_index(root: Path, removed: list[str]) -> None:
    if not removed:
        return
    index_dir = root / "index"
    if not index_dir.exists():
        return
    for run_id in removed:
        (index_dir / f"{run_id}.json").unlink(missing_ok=True)
    _refresh_snapshot_latest(index_dir)


def _build_snapshot_record(
    context: SnapshotContext,
    manifest: Mapping[str, Any],
    assessment: Mapping[str, Any],
    data: GuardData,
) -> dict[str, Any]:
    summary = assessment.get("summary") if isinstance(assessment, Mapping) else None
    sources = {
        SOURCE_PREFLIGHT: data.preflight_summary.state,
        SOURCE_RENOVATE: data.renovate_summary.state,
        SOURCE_CVE: data.cve_summary.state,
        SOURCE_CONTRACT: data.contract_summary.state,
        SOURCE_DRIFT: data.drift_summary.state,
    }
    record = {
        "run_id": context.run_id,
        "generated_at": manifest.get("generated_at"),
        "manifest": str(context.manifest_path),
        "root": str(context.run_dir),
        "reports": manifest.get("reports", {}),
        "summary": summary,
        "fail_threshold": manifest.get("fail_threshold"),
        "highest_severity": manifest.get("highest_severity"),
        "pruned_snapshots": manifest.get("pruned_snapshots", []),
        "sbom": {
            "age_days": manifest.get("sbom_age_days"),
            "stale": manifest.get("sbom_stale"),
        },
        "sources": sources,
    }
    return record


def _write_snapshot_index(
    context: SnapshotContext,
    manifest: Mapping[str, Any],
    assessment: Mapping[str, Any],
    data: GuardData,
) -> Path:
    index_dir = context.root / "index"
    index_dir.mkdir(parents=True, exist_ok=True)
    record = _build_snapshot_record(context, manifest, assessment, data)
    index_path = index_dir / f"{context.run_id}.json"
    index_path.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _refresh_snapshot_latest(index_dir)
    return index_path


def _persist_snapshot_run(
    assessment: Mapping[str, Any],
    markdown: str | None,
    args: argparse.Namespace,
    data: GuardData,
    moment: datetime,
) -> SnapshotContext | None:
    context = _ensure_snapshot_context(args, moment)
    if context is None:
        return None

    inputs_written: dict[str, str | None] = {}
    inputs_written[SOURCE_PREFLIGHT] = _copy_snapshot_input(
        data.preflight_summary.raw_path,
        context.inputs_dir / "preflight.json",
    )
    inputs_written[SOURCE_RENOVATE] = _copy_snapshot_input(
        data.renovate_summary.raw_path,
        context.inputs_dir / "renovate.json",
    )
    inputs_written[SOURCE_CVE] = _copy_snapshot_input(
        data.cve_summary.raw_path,
        context.inputs_dir / "cve.json",
    )
    inputs_written[SOURCE_CONTRACT] = _copy_snapshot_input(
        data.contract_summary.raw_path,
        context.inputs_dir / "contract.toml",
    )
    inputs_written[SOURCE_DRIFT] = _copy_snapshot_input(
        data.drift_summary.raw_path,
        context.inputs_dir / "sbom.json",
    )
    inputs_written["drift_metadata"] = _copy_snapshot_input(
        getattr(args, "metadata", None),
        context.inputs_dir / "metadata.json",
    )

    reports_written = _write_snapshot_reports(context, assessment, markdown, data)

    retain_days = getattr(args, "snapshot_retention_days", DEFAULT_SNAPSHOT_RETAIN_DAYS)
    removed = _prune_snapshot_retention(context.root, retain_days, moment)
    _prune_snapshot_index(context.root, removed)

    manifest = {
        "run_id": context.run_id,
        "generated_at": context.generated_at.isoformat(),
        "inputs": inputs_written,
        "reports": reports_written,
        "retention_days": retain_days,
        "pruned_snapshots": removed,
        "sbom_age_days": (
            data.drift_report.get("sbom_age_days") if data.drift_report else None
        ),
        "sbom_stale": (
            data.drift_report.get("sbom_stale") if data.drift_report else None
        ),
        "fail_threshold": getattr(args, "fail_threshold", None),
        "highest_severity": assessment.get("summary", {}).get("highest_severity"),
    }
    context.manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _write_snapshot_index(context, manifest, assessment, data)
    return context


def _determine_exit_code(highest: str, fail_threshold: str | None) -> int:
    threshold = fail_threshold or RISK_NEEDS_REVIEW
    if RISK_ORDER[highest] >= RISK_ORDER[threshold]:
        return 1 if highest == RISK_NEEDS_REVIEW else 2
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    configure_tracing(
        "prometheus-upgrade-guard",
        resource_attributes={"component": "scripts.upgrade_guard"},
    )
    configure_metrics(namespace="prometheus_upgrade_guard")

    with TRACER.start_as_current_span("upgrade_guard.run") as span:
        span.set_attribute(
            "upgrade_guard.fail_threshold", args.fail_threshold or RISK_NEEDS_REVIEW
        )
        span.set_attribute(
            "upgrade_guard.mirror.enabled", bool(getattr(args, "mirror_root", None))
        )
        try:
            data = _collect_guard_data(args)
            packages = _merge_assessments(
                data.preflight_packages,
                data.renovate_packages,
                data.cve_packages,
            )
            flagged = sum(1 for package in packages if package.risk != RISK_SAFE)

            summary_notes = _build_summary_notes(
                (
                    data.preflight_summary,
                    data.renovate_summary,
                    data.cve_summary,
                    data.contract_summary,
                    data.drift_summary,
                ),
                data.contract_report,
                data.drift_report,
            )
            highest = _compute_highest_risk(
                packages, data.contract_report, data.drift_report
            )
            moment = datetime.now(UTC)
            assessment = _assemble_assessment(
                data, packages, highest, flagged, summary_notes, moment
            )

            span.set_attribute("upgrade_guard.highest_risk", highest)
            span.set_attribute("upgrade_guard.packages_flagged", flagged)
            span.set_attribute(
                "upgrade_guard.mirror.verified",
                bool(data.mirror_status.verified) if data.mirror_status else False,
            )
            span.set_attribute(
                "upgrade_guard.mirror.total_artifacts",
                len(data.mirror_status.artifacts) if data.mirror_status else 0,
            )
            contract_risk = (
                str(data.contract_report.get("risk", RISK_SAFE))
                if data.contract_report
                else RISK_SAFE
            )
            span.set_attribute("upgrade_guard.contract.risk", contract_risk)

            markdown = _persist_outputs(assessment, args)
            _persist_snapshot_run(assessment, markdown, args, data, moment)
            if args.verbose:
                print(markdown or _render_markdown(assessment))

            outcome = highest
            GUARD_RUN_COUNTER.labels(outcome=outcome).inc()
            span.set_attribute("upgrade_guard.outcome", outcome)
            return _determine_exit_code(outcome, args.fail_threshold)
        except Exception as exc:  # pragma: no cover - defensive guard
            span.record_exception(exc)
            span.set_attribute("upgrade_guard.outcome", "error")
            GUARD_RUN_COUNTER.labels(outcome="error").inc()
            raise


if __name__ == "__main__":  # pragma: no cover - CLI
    sys.exit(main())
