#!/usr/bin/env python3
"""Render dependency preflight results in a reusable helper.

The script expects a JSON payload produced by ``preflight_deps.py --json`` and
prints a condensed summary grouped by severity. It exits with code ``1`` when
any entry reports ``status == "error"`` so shell wrappers can gate builds.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "payload",
        nargs="?",
        default="-",
        help="Path to JSON payload or '-' to read from stdin",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress human-readable output (exit code still reflects status)",
    )
    parser.add_argument(
        "--fail-on-warn",
        action="store_true",
        help="Exit with code 1 when warnings are present (default: only on errors)",
    )
    return parser.parse_args(argv)


def _load_payload(path: str) -> list[dict[str, Any]]:
    if path == "-":
        try:
            data = json.load(sys.stdin)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise SystemExit(
                f"Failed to parse preflight JSON from stdin: {exc}"
            ) from exc
        return _coerce_list(data)

    candidate = Path(path)
    if not candidate.is_file():
        raise SystemExit(f"Preflight payload not found at: {candidate}")
    try:
        data = json.loads(candidate.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"Failed to parse preflight JSON at {candidate}: {exc}"
        ) from exc
    return _coerce_list(data)


def _coerce_list(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [entry for entry in data if isinstance(entry, dict)]
    raise SystemExit("Preflight payload must be a JSON list of objects")


def _render_summary(
    payload: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    errors = [entry for entry in payload if entry.get("status") == "error"]
    warnings = [entry for entry in payload if entry.get("status") == "warn"]
    errors.sort(key=lambda item: item.get("name", ""))
    warnings.sort(key=lambda item: item.get("name", ""))
    return errors, warnings


def _format_entry(entry: dict[str, Any]) -> str:
    name = entry.get("name", "<unknown>")
    version = entry.get("version", "<unknown>")
    status = entry.get("status", "?")
    message = entry.get("message") or "no details"
    missing = entry.get("missing") or []
    if missing:
        matrix = ", ".join(
            f"py{target.get('python', '?')}@{target.get('platform', '?')}"
            for target in missing
        )
    else:
        matrix = "-"
    return f"  - {name}=={version}: {status} ({message}); targets: {matrix}"


def _emit_summary(
    errors: list[dict[str, Any]], warnings: list[dict[str, Any]], *, quiet: bool
) -> None:
    if quiet:
        return

    if errors or warnings:
        print("Dependency preflight results (ordered by severity):")
    else:
        print("Dependency preflight results:")

    for entry in errors:
        print(_format_entry(entry))
    for entry in warnings:
        print(_format_entry(entry))

    if not errors and not warnings:
        print("  ✔ all dependencies satisfied")


def _determine_exit_code(
    errors: list[dict[str, Any]], warnings: list[dict[str, Any]], *, fail_on_warn: bool
) -> int:
    if errors:
        return 1
    if warnings and fail_on_warn:
        return 1
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    payload = _load_payload(args.payload)

    if not payload:
        _emit_summary([], [], quiet=args.quiet)
        return 0

    errors, warnings = _render_summary(payload)
    _emit_summary(errors, warnings, quiet=args.quiet)
    return _determine_exit_code(errors, warnings, fail_on_warn=args.fail_on_warn)


if __name__ == "__main__":  # pragma: no cover - script entrypoint
    sys.exit(main())
