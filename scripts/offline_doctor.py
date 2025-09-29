#!/usr/bin/env python3
"""CLI for diagnosing offline packaging readiness."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from prometheus.packaging import OfflinePackagingOrchestrator, load_config

DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Diagnose whether the offline packaging environment is ready to run. "
            "Outputs tool versions, availability checks, and wheelhouse audit results."
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Optional alternative offline packaging TOML configuration file.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=DEFAULT_REPO_ROOT,
        help="Repository root containing scripts/ and vendor/ directories.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Write diagnostics as pretty-printed JSON to stdout.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging for troubleshooting the doctor command itself.",
    )
    return parser


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _format_examples(values: list[str]) -> str:
    if len(values) <= 5:
        return ", ".join(values)
    return ", ".join(values[:5]) + " …"


def _render_diagnostics(diag: Mapping[str, Any]) -> None:
    repo = diag.get("repo_root")
    config_path = diag.get("config_path") or "<defaults>"
    logging.info("Doctor report for repo=%s config=%s", repo, config_path)

    for section_name in ("python", "pip", "poetry", "docker"):
        section = diag.get(section_name, {})
        status = section.get("status", "unknown")
        logging.info("%s status: %s", section_name.title(), status)
        version = section.get("version")
        if version:
            logging.info("%s version: %s", section_name.title(), version)
        message = section.get("message")
        if message:
            level = logging.WARNING if status != "ok" else logging.INFO
            logging.log(level, "%s: %s", section_name.title(), message)

    wheelhouse = diag.get("wheelhouse", {})
    status = wheelhouse.get("status", "not-run")
    logging.info("Wheelhouse audit status: %s", status)
    missing = wheelhouse.get("missing_requirements") or []
    orphans = wheelhouse.get("orphan_artefacts") or []
    removed = wheelhouse.get("removed_orphans") or []
    if missing:
        logging.warning(
            "Missing wheels for %d requirement(s): %s",
            len(missing),
            _format_examples([str(item) for item in missing]),
        )
    if orphans:
        logging.warning(
            "Orphan wheelhouse artefacts detected: %d (%s)",
            len(orphans),
            _format_examples([str(item) for item in orphans]),
        )
    if removed:
        logging.info(
            "Orphan artefacts removed during audit: %d (%s)",
            len(removed),
            _format_examples([str(item) for item in removed]),
        )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    _configure_logging(args.verbose)

    config = load_config(args.config) if args.config else load_config()
    orchestrator = OfflinePackagingOrchestrator(
        config=config,
        repo_root=args.repo_root.resolve(),
        dry_run=False,
    )
    diagnostics = orchestrator.doctor()

    if args.json:
        json.dump(diagnostics, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        _render_diagnostics(diagnostics)
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())
