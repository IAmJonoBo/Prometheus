#!/usr/bin/env python3
"""CLI entry point for the offline packaging orchestrator."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from prometheus.packaging import (
    OfflinePackagingOrchestrator,
    PackagingResult,
    load_config,
)

DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Automate offline packaging for air-gapped runners. "
            "The command wraps dependency wheelhouse generation, model downloads, "
            "container exports, checksum calculation, and repository hygiene checks."
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Path to an alternate offline packaging TOML configuration file.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=DEFAULT_REPO_ROOT,
        help="Repository root containing scripts/ and vendor/ directories.",
    )
    parser.add_argument(
        "--only-phase",
        dest="only_phases",
        choices=OfflinePackagingOrchestrator.PHASES,
        action="append",
        help=(
            "Limit execution to one or more phases. Can be supplied multiple times. "
            "Valid phases: %(choices)s"
        ),
    )
    parser.add_argument(
        "--skip-phase",
        dest="skip_phases",
        choices=OfflinePackagingOrchestrator.PHASES,
        action="append",
        help=(
            "Skip one or more phases. Can be supplied multiple times. "
            "Valid phases: %(choices)s"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the commands that would run without executing them.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging for deeper visibility.",
    )
    return parser


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _summarise(result: PackagingResult) -> None:
    for phase in result.phase_results:
        status = "✅" if phase.succeeded else "❌"
        message = f"{status} {phase.name}"
        if phase.detail and not phase.succeeded:
            message = f"{message} — {phase.detail}"
        logging.info(message)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    _configure_logging(args.verbose)

    config = load_config(args.config) if args.config else load_config()
    orchestrator = OfflinePackagingOrchestrator(
        config=config,
        repo_root=args.repo_root.resolve(),
        dry_run=args.dry_run,
    )
    result = orchestrator.run(
        only=args.only_phases,
        skip=args.skip_phases,
    )
    _summarise(result)

    if not result.succeeded:
        failed = result.failed_phases[-1] if result.failed_phases else None
        if failed:
            logging.error("Offline packaging failed during %s", failed.name)
        else:  # pragma: no cover - defensive
            logging.error("Offline packaging failed")
        return 1
    logging.info("Offline packaging completed successfully")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())
