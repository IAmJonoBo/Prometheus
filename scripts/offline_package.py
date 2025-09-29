#!/usr/bin/env python3
"""CLI entry point for the offline packaging orchestrator."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

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
    parser.add_argument(
        "--auto-update",
        dest="auto_update",
        action="store_true",
        default=None,
        help=(
            "Enable automatic dependency updates for the selected run. "
            "Overrides the configuration flag."
        ),
    )
    parser.add_argument(
        "--no-auto-update",
        dest="auto_update",
        action="store_false",
        help="Disable automatic dependency updates for this run.",
    )
    parser.add_argument(
        "--auto-update-max",
        choices=["patch", "minor", "major", "unknown"],
        help="Maximum update severity to auto-apply (default: value from config).",
    )
    parser.add_argument(
        "--auto-update-allow",
        action="append",
        dest="auto_update_allow",
        help="Package name to whitelist for automatic updates (repeatable).",
    )
    parser.add_argument(
        "--auto-update-deny",
        action="append",
        dest="auto_update_deny",
        help="Package name to block from automatic updates (repeatable).",
    )
    parser.add_argument(
        "--auto-update-batch",
        type=int,
        dest="auto_update_batch",
        help="Maximum number of packages to update automatically in a single run.",
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


def _log_dependency_update_summary(
    summary: Mapping[str, Any],
    updates: Sequence[Mapping[str, Any]],
) -> None:
    if not summary:
        return

    counts = summary.get("counts", {})
    has_updates = summary.get("has_updates", False)
    auto_applied = summary.get("auto_applied") or []

    if auto_applied:
        logging.info(
            "Auto-applied dependency updates: %s",
            ", ".join(str(item) for item in auto_applied),
        )

    if not has_updates:
        logging.info(
            "Dependency status: %s",
            summary.get(
                "primary_recommendation",
                "No dependency recommendations available.",
            ),
        )
        return

    logging.warning(
        "Dependency updates detected: major=%d minor=%d patch=%d unknown=%d",
        counts.get("major", 0),
        counts.get("minor", 0),
        counts.get("patch", 0),
        counts.get("unknown", 0),
    )

    top_candidates = []
    for item in updates:
        name = item.get("name")
        current = item.get("current_version")
        latest = item.get("latest_version")
        if not (name and current and latest):
            continue
        top_candidates.append(f"{name} {current}→{latest}")
        if len(top_candidates) == 5:
            break
    if top_candidates:
        logging.warning("Top candidates: %s", ", ".join(top_candidates))

    for action in summary.get("next_actions", []):
        logging.info("Next step: %s", action)


def _log_auto_update_policy(policy: Any) -> None:
    allow = ", ".join(policy.allow) if getattr(policy, "allow", None) else "-"
    deny = ", ".join(policy.deny) if getattr(policy, "deny", None) else "-"
    batch = getattr(policy, "max_batch", None)
    batch_repr = str(batch) if batch is not None else "unlimited"
    logging.info(
        "Auto-update policy: enabled=%s max_update_type=%s allow=%s deny=%s max_batch=%s",
        getattr(policy, "enabled", False),
        getattr(policy, "max_update_type", "patch"),
        allow,
        deny,
        batch_repr,
    )


def _log_repository_hygiene(orchestrator: OfflinePackagingOrchestrator) -> None:
    replacements = orchestrator.symlink_replacements
    pointer_paths = orchestrator.pointer_scan_paths
    if replacements:
        logging.info("Symlink normalisation replaced %d entries", replacements)
    else:
        logging.info("Symlink normalisation made no changes")

    if pointer_paths:
        logging.info(
            "Verified git-lfs materialisation for %s", ", ".join(pointer_paths)
        )
    else:
        logging.info("LFS pointer verification skipped for this run")

    hooks_path = orchestrator.git_hooks_path
    repairs = orchestrator.hook_repairs
    removals = getattr(orchestrator, "hook_removals", [])
    if hooks_path is not None:
        display_path = str(hooks_path)
        if repairs:
            logging.info(
                "Git LFS hooks repaired at %s (%s)",
                display_path,
                ", ".join(repairs),
            )
        else:
            logging.info("Git LFS hooks already healthy at %s", display_path)
        if removals:
            logging.info(
                "Removed stray Git LFS hook stubs at %s (%s)",
                display_path,
                ", ".join(removals),
            )


def _format_examples(values: Sequence[str]) -> str:
    if len(values) <= 5:
        return ", ".join(values)
    return ", ".join(values[:5]) + " …"


def _log_wheelhouse_audit(audit: Mapping[str, Any]) -> None:
    status = audit.get("status", "not-run")
    if status == "not-run":
        logging.info("Wheelhouse audit not executed in this run")
        return
    if status == "skipped":
        reason = audit.get("reason", "unspecified")
        logging.info("Wheelhouse audit skipped (%s)", reason)
        return
    if status == "error":
        logging.error("Wheelhouse audit failed: %s", audit.get("reason", "unknown"))
        return

    wheel_count = audit.get("wheel_count", 0)
    requirement_count = audit.get("requirement_count", 0)
    logging.info(
        "Wheelhouse audit status: %s (wheels=%d requirements=%d)",
        status,
        wheel_count,
        requirement_count,
    )

    missing = audit.get("missing_requirements") or []
    orphans = audit.get("orphan_artefacts") or []
    removed = audit.get("removed_orphans") or []
    inactive = audit.get("inactive_requirements") or []

    if missing:
        logging.warning(
            "Missing wheels for %d active requirement(s): %s",
            len(missing),
            _format_examples([str(value) for value in missing]),
        )
    if orphans:
        logging.warning(
            "Remaining orphan wheelhouse artefacts: %d (%s)",
            len(orphans),
            _format_examples([str(value) for value in orphans]),
        )
    if removed:
        logging.info(
            "Removed orphan artefacts during cleanup: %d (%s)",
            len(removed),
            _format_examples([str(value) for value in removed]),
        )
    if inactive:
        logging.info(
            "Inactive requirement markers evaluated to false: %s",
            _format_examples([str(value) for value in inactive]),
        )


def _apply_auto_update_overrides(config: Any, args: argparse.Namespace) -> None:
    policy = config.updates.auto
    explicit_flag = args.auto_update
    if explicit_flag is True:
        policy.enabled = True
    elif explicit_flag is False:
        policy.enabled = False

    overrides: dict[str, Any] = {}
    if args.auto_update_max:
        overrides["max_update_type"] = args.auto_update_max

    if args.auto_update_allow is not None:
        overrides["allow"] = _unique_preserving_order(args.auto_update_allow)

    if args.auto_update_deny is not None:
        overrides["deny"] = _unique_preserving_order(args.auto_update_deny)

    if args.auto_update_batch is not None:
        if args.auto_update_batch < 0:
            raise ValueError("--auto-update-batch must be non-negative")
        overrides["max_batch"] = args.auto_update_batch

    if not overrides:
        return

    enable_allowed = explicit_flag is not False
    for attr, value in overrides.items():
        setattr(policy, attr, value)
        if enable_allowed:
            policy.enabled = True


def _unique_preserving_order(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value is None:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(value)
    return unique


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    _configure_logging(args.verbose)

    config = load_config(args.config) if args.config else load_config()
    _apply_auto_update_overrides(config, args)
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
    _log_auto_update_policy(config.updates.auto)
    _log_dependency_update_summary(
        orchestrator.dependency_summary,
        orchestrator.dependency_updates,
    )
    _log_repository_hygiene(orchestrator)
    _log_wheelhouse_audit(orchestrator.wheelhouse_audit)

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
