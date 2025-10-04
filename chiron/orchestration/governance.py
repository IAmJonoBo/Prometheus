"""Derive governance artefacts for dry-run CI executions."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SEVERITY_ORDER = {"ok": 0, "warning": 1, "critical": 2}


@dataclass(slots=True)
class GovernanceOutcome:
    summary_path: Path
    ci_event_path: Path
    issue_path: Path
    severity: str
    issue_required: bool
    fail_job: bool


def _load_summary(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.setdefault("warnings", [])
    payload.setdefault("resource_usage", {})
    payload.setdefault("status", "success")
    return payload


def _infer_severity(summary: dict[str, Any], exit_code: int) -> str:
    if summary.get("status", "success").lower() != "success" or exit_code != 0:
        return "critical"
    if summary.get("warnings"):
        return "warning"
    return "ok"


def _write_ci_event(path: Path, summary: dict[str, Any], severity: str) -> None:
    event = {
        "shard": summary.get("shard", "unknown"),
        "run_id": summary.get("run_id"),
        "query": summary.get("query"),
        "severity": severity,
        "warnings": summary.get("warnings", []),
        "artifact_root": summary.get("artifact_root"),
        "completed_at": summary.get("completed_at"),
        "resource_usage": summary.get("resource_usage", {}),
        "lineage": summary.get("lineage"),
    }
    path.write_text(json.dumps(event, indent=2), encoding="utf-8")


def _write_issue(path: Path, summary: dict[str, Any], severity: str) -> None:
    lines = [
        f"## Dry-run governance alert ({summary.get('shard', 'unknown')})",
        "",
        f"* Run ID: `{summary.get('run_id')}`",
        f"* Completed: {summary.get('completed_at', 'unknown')}",
        f"* Severity: **{severity.upper()}**",
        "",
        "### Query",
        "",
        summary.get("query", "n/a"),
        "",
    ]
    warnings = summary.get("warnings", [])
    if warnings:
        lines.extend(["### Warnings", ""])
        for warning in warnings:
            lines.append(f"- {warning}")
        lines.append("")
    lineage = summary.get("lineage")
    if lineage:
        lines.extend(["### Artefacts", "", f"- Lineage: `{lineage}`"])
    lines.append(f"- Manifest: `{summary.get('manifest')}`")
    lines.append(f"- Metrics: `{summary.get('metrics')}`")
    lines.append(f"- Events: `{summary.get('events')}`")
    issue_body = "\n".join(lines) + "\n"
    path.write_text(issue_body, encoding="utf-8")


def _should_fail(severity: str, fail_threshold: str) -> bool:
    return SEVERITY_ORDER[severity] >= SEVERITY_ORDER[fail_threshold]


def _should_raise_issue(severity: str, issue_threshold: str) -> bool:
    return SEVERITY_ORDER[severity] >= SEVERITY_ORDER[issue_threshold]


def _resolve_threshold(value: str, default: str) -> str:
    value = (value or "").lower() or default
    if value not in SEVERITY_ORDER:
        raise ValueError(f"Unsupported severity threshold: {value}")
    return value


def process(
    summary_path: Path, ci_event_path: Path, issue_path: Path
) -> GovernanceOutcome:
    exit_code = int(os.getenv("DRYRUN_EXIT_CODE", "0"))
    issue_threshold = _resolve_threshold(
        os.getenv("DRYRUN_GOVERNANCE_ISSUE_THRESHOLD", "warning"), "warning"
    )
    fail_threshold = _resolve_threshold(
        os.getenv("DRYRUN_GOVERNANCE_FAIL_THRESHOLD", "critical"), "critical"
    )

    summary = _load_summary(summary_path)
    severity = _infer_severity(summary, exit_code)
    _write_ci_event(ci_event_path, summary, severity)

    issue_required = _should_raise_issue(severity, issue_threshold)
    if issue_required:
        _write_issue(issue_path, summary, severity)
    else:
        issue_path.write_text("", encoding="utf-8")

    fail_job = _should_fail(severity, fail_threshold)

    return GovernanceOutcome(
        summary_path=summary_path,
        ci_event_path=ci_event_path,
        issue_path=issue_path,
        severity=severity,
        issue_required=issue_required,
        fail_job=fail_job,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--ci-event", required=True, type=Path)
    parser.add_argument("--issue", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    outcome = process(args.summary, args.ci_event, args.issue)
    github_output = Path(os.environ.get("GITHUB_OUTPUT", ""))
    if github_output:
        with github_output.open("a", encoding="utf-8") as handle:
            handle.write(f"severity={outcome.severity}\n")
            handle.write(
                f"issue_required={'true' if outcome.issue_required else 'false'}\n"
            )
            handle.write(f"fail_job={'true' if outcome.fail_job else 'false'}\n")
            handle.write(f"ci_event={outcome.ci_event_path}\n")
            handle.write(f"issue_file={outcome.issue_path}\n")


if __name__ == "__main__":  # pragma: no cover - script entrypoint
    main()
