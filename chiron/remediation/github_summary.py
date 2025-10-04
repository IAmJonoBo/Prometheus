from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _load_summary(output_path: Path) -> dict[str, object]:
    baseline: dict[str, object] = {"findings": []}
    if output_path.exists():
        try:
            data = json.loads(output_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = baseline
    else:
        output_path.write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")
        data = baseline
    if not isinstance(data, dict):
        return baseline
    return data


def _append_output(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(payload)


def _render_summary(
    summary: dict[str, object], shard: str, output_path: Path
) -> tuple[str, int]:
    findings = summary.get("findings")
    if not isinstance(findings, list):
        findings = []
    count = len(findings)
    lines = [f"### Runtime remediation for `{shard}`\n\n"]
    if count:
        lines.append(f"* Findings: **{count}** (JSON: `{output_path}`)\n")
        lines.append("* Affected modules:\n")
        preview = findings[:5]
        for finding in preview:
            if isinstance(finding, dict):
                module = finding.get("module")
            else:
                module = None
            if not isinstance(module, str) or not module:
                module = "unknown"
            lines.append(f"  * `{module}`\n")
        remaining = count - len(preview)
        if remaining > 0:
            lines.append(f"  * … {remaining} more\n")
        lines.append("\n")
    else:
        lines.append("* Findings: none\n\n")
    return "".join(lines), count


def main() -> int:
    env = os.environ
    log_path = Path(env["LOG_PATH"]).resolve()
    output_path = Path(env["OUTPUT_PATH"]).resolve()
    failure_path = Path(env["FAILURE_PATH"]).resolve()
    shard = env.get("SHARD", "unknown")

    summary = _load_summary(output_path)
    summary_text, count = _render_summary(summary, shard, output_path)

    github_output = Path(env["GITHUB_OUTPUT"]).resolve()
    _append_output(
        github_output,
        f"findings={count}\n"
        f"summary_path={output_path}\n"
        f"log_path={log_path}\n"
        f"failure_path={failure_path}\n",
    )

    github_env = Path(env["GITHUB_ENV"]).resolve()
    _append_output(github_env, f"DRYRUN_REMEDIATION_FINDINGS={count}\n")

    step_summary = Path(env["GITHUB_STEP_SUMMARY"]).resolve()
    _append_output(step_summary, summary_text)

    if count:
        print(
            f"::warning::Detected {count} runtime remediation finding(s); see {output_path}"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
