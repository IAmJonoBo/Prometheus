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


def _doctor_logger() -> logging.Logger:
    logger = logging.getLogger("offline_doctor")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    if logger.level == logging.NOTSET or logger.level > logging.INFO:
        logger.setLevel(logging.INFO)
    logger.propagate = True
    return logger


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
        "--format",
        choices=["json", "table", "text"],
        default="text",
        help="Output format for diagnostics (default: text).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Shorthand for --format json (deprecated, use --format json).",
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


STATUS_SYMBOLS: dict[str, str] = {
    "ok": "✓",
    "warning": "⚠",
    "error": "✗",
    "skipped": "○",
    "unknown": "?",
}


def _print_tool_status_table(diag: Mapping[str, Any]) -> None:
    print("┌─────────────────┬──────────┬────────────────────┬─────────────────────┐")
    print("│ Component       │ Status   │ Version            │ Notes               │")
    print("├─────────────────┼──────────┼────────────────────┼─────────────────────┤")

    for section_name in ("python", "pip", "poetry", "docker"):
        section = diag.get(section_name, {})
        status = section.get("status", "unknown")
        symbol = STATUS_SYMBOLS.get(status, "?")
        version = section.get("version", "N/A")
        message = section.get("message", "")
        if len(message) > 20:
            message = message[:17] + "..."
        print(
            f"│ {section_name.ljust(15)} │ {symbol} {status.ljust(6)} │ "
            f"{version.ljust(18)} │ {message.ljust(19)} │"
        )

    print("└─────────────────┴──────────┴────────────────────┴─────────────────────┘\n")


def _print_git_info(diag: Mapping[str, Any]) -> None:
    git_info = diag.get("git", {})
    if git_info.get("status") != "skipped":
        print("Git Repository:")
        print(f"  Branch:    {git_info.get('branch', 'N/A')}")
        print(f"  Commit:    {git_info.get('commit', 'N/A')}")
        print(f"  Uncommitted changes: {git_info.get('uncommitted_changes', 'N/A')}")
        if git_info.get("lfs_available"):
            print(f"  LFS tracked files:   {git_info.get('lfs_tracked_files', 'N/A')}")
        print()


def _print_disk_space(diag: Mapping[str, Any]) -> None:
    disk_info = diag.get("disk_space", {})
    if disk_info.get("status"):
        status_symbol = STATUS_SYMBOLS.get(disk_info.get("status", "unknown"), "?")
        print(f"Disk Space: {status_symbol}")
        print(f"  Total: {disk_info.get('total_gb', 'N/A')} GB")
        print(
            f"  Used:  {disk_info.get('used_gb', 'N/A')} GB ({disk_info.get('percent_used', 'N/A')}%)"
        )
        print(f"  Free:  {disk_info.get('free_gb', 'N/A')} GB")
        if disk_info.get("message"):
            print(f"  Note:  {disk_info['message']}")
        print()


def _print_build_artifacts(diag: Mapping[str, Any]) -> None:
    build_info = diag.get("build_artifacts", {})
    if build_info:
        print("Build Artifacts:")
        print(f"  Dist directory:        {build_info.get('dist_exists', False)}")
        print(f"  Wheels in dist:        {build_info.get('wheels_in_dist', 0)}")
        print(f"  Wheelhouse exists:     {build_info.get('wheelhouse_exists', False)}")
        if build_info.get("wheelhouse_exists"):
            print(
                f"  Wheels in wheelhouse:  {build_info.get('wheels_in_wheelhouse', 0)}"
            )
            print(
                f"  Manifest exists:       {build_info.get('manifest_exists', False)}"
            )
            print(
                f"  Requirements exists:   {build_info.get('requirements_exists', False)}"
            )
        print()


def _print_dependencies(diag: Mapping[str, Any]) -> None:
    deps_info = diag.get("dependencies", {})
    if deps_info:
        status_symbol = STATUS_SYMBOLS.get(deps_info.get("status", "unknown"), "?")
        print(f"Dependencies: {status_symbol}")
        print(f"  pyproject.toml: {deps_info.get('pyproject_exists', False)}")
        print(f"  poetry.lock:    {deps_info.get('poetry_lock_exists', False)}")
        if deps_info.get("lock_age_days") is not None:
            print(f"  Lock age:       {deps_info['lock_age_days']} days")
        if deps_info.get("message"):
            print(f"  Note:           {deps_info['message']}")
        print()


def _print_wheelhouse(diag: Mapping[str, Any]) -> None:
    wheelhouse = diag.get("wheelhouse", {})
    status = wheelhouse.get("status", "not-run")
    print(f"Wheelhouse Audit: {STATUS_SYMBOLS.get(status, '?')} {status}")

    missing = wheelhouse.get("missing_requirements") or []
    orphans = wheelhouse.get("orphan_artefacts") or []
    removed = wheelhouse.get("removed_orphans") or []

    if missing:
        print(f"  Missing wheels: {len(missing)} requirement(s)")
        print(f"    Examples: {_format_examples([str(item) for item in missing])}")

    if orphans:
        print(f"  Orphan artefacts: {len(orphans)}")
        print(f"    Examples: {_format_examples([str(item) for item in orphans])}")

    if removed:
        print(f"  Removed orphans: {len(removed)}")
        print(f"    Examples: {_format_examples([str(item) for item in removed])}")

    print()


def _print_overall_status(diag: Mapping[str, Any]) -> None:
    has_errors = any(
        diag.get(section, {}).get("status") == "error"
        for section in (
            "python",
            "pip",
            "poetry",
            "docker",
            "disk_space",
            "dependencies",
        )
    )
    has_warnings = any(
        diag.get(section, {}).get("status") == "warning"
        for section in (
            "python",
            "pip",
            "poetry",
            "docker",
            "disk_space",
            "dependencies",
            "build_artifacts",
        )
    )

    if has_errors:
        print("❌ ERRORS DETECTED - Review above for details")
        print("   Some components are missing or misconfigured.")
    elif has_warnings:
        print("⚠️  WARNINGS DETECTED - System may work but review recommended")
        print("   Some components may need updates.")
    else:
        print("✅ ALL CHECKS PASSED - System ready for offline packaging")
    print()


def _render_diagnostics(diag: Mapping[str, Any]) -> None:
    """Render diagnostics in text format (logging output)."""
    logger = _doctor_logger()

    repo = diag.get("repo_root")
    config_path = diag.get("config_path") or "<defaults>"
    logger.info("Doctor report for repo=%s config=%s", repo, config_path)

    for section_name in ("python", "pip", "poetry", "docker"):
        section = diag.get(section_name, {})
        status = section.get("status", "unknown")
        logger.info("%s status: %s", section_name.title(), status)
        version = section.get("version")
        if version:
            logger.info("%s version: %s", section_name.title(), version)
        message = section.get("message")
        if message:
            level = logging.WARNING if status != "ok" else logging.INFO
            logger.log(level, "%s: %s", section_name.title(), message)

    wheelhouse = diag.get("wheelhouse", {})
    status = wheelhouse.get("status", "not-run")
    logger.info("Wheelhouse audit status: %s", status)
    missing = wheelhouse.get("missing_requirements") or []
    orphans = wheelhouse.get("orphan_artefacts") or []
    removed = wheelhouse.get("removed_orphans") or []
    if missing:
        logger.warning(
            "Missing wheels for %d requirement(s): %s",
            len(missing),
            _format_examples([str(item) for item in missing]),
        )
    if orphans:
        logger.warning(
            "Orphan wheelhouse artefacts detected: %d (%s)",
            len(orphans),
            _format_examples([str(item) for item in orphans]),
        )
    if removed:
        logger.info(
            "Orphan artefacts removed during audit: %d (%s)",
            len(removed),
            _format_examples([str(item) for item in removed]),
        )


def _render_table(diag: Mapping[str, Any]) -> None:
    """Render diagnostics in table format."""
    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║           Offline Packaging Diagnostic Report               ║")
    print("╚══════════════════════════════════════════════════════════════╝\n")

    repo = diag.get("repo_root", "N/A")
    config_path = diag.get("config_path") or "<defaults>"
    print(f"Repository: {repo}")
    print(f"Config:     {config_path}")
    print(f"Generated:  {diag.get('generated_at', 'N/A')}\n")

    _print_tool_status_table(diag)
    _print_git_info(diag)
    _print_disk_space(diag)
    _print_build_artifacts(diag)
    _print_dependencies(diag)
    _print_wheelhouse(diag)
    _print_overall_status(diag)


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

    # Determine output format (--json flag overrides --format for backward compatibility)
    output_format = "json" if args.json else args.format

    if output_format == "json":
        json.dump(diagnostics, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    elif output_format == "table":
        _render_table(diagnostics)
    else:  # text format
        _render_diagnostics(diagnostics)
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())
