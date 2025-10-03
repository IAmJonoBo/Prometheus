#!/usr/bin/env python3
"""Verify dependency pipeline setup and integration.

This script checks that all components of the dependency management pipeline
are properly wired, scripts are importable, CLI commands are registered, and
workflows reference the correct commands.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]


def check_script_imports() -> dict[str, bool]:
    """Verify all dependency management scripts exist and have main() functions."""
    scripts_dir = REPO_ROOT / "scripts"
    # Scripts that have main() functions (standalone executables)
    standalone_scripts = {
        "upgrade_guard.py": "def main(",
        "upgrade_planner.py": "def main(",
        "dependency_drift.py": "def main(",
        "mirror_manager.py": "def main(",
        "preflight_deps.py": "def main(",
        "sync-dependencies.py": "def main(",
        "offline_package.py": "def main(",
        "offline_doctor.py": "def main(",
        "bootstrap_offline.py": "def main(",
    }

    # Library modules (no main() function required)
    library_modules = {
        "deps_status.py": "generate_status",
    }

    results = {}

    for script_name, main_signature in standalone_scripts.items():
        script_path = scripts_dir / script_name
        if script_path.exists():
            content = script_path.read_text(encoding="utf-8")
            results[f"{script_name} (standalone)"] = main_signature in content
        else:
            results[f"{script_name} (standalone)"] = False

    for script_name, required_function in library_modules.items():
        script_path = scripts_dir / script_name
        if script_path.exists():
            content = script_path.read_text(encoding="utf-8")
            results[f"{script_name} (library)"] = required_function in content
        else:
            results[f"{script_name} (library)"] = False

    return results


def check_cli_commands() -> dict[str, bool]:
    """Verify CLI commands are registered."""
    cli_path = REPO_ROOT / "prometheus" / "cli.py"

    if not cli_path.exists():
        return {"cli_module": False}

    cli_content = cli_path.read_text(encoding="utf-8")

    commands = {
        "deps status": '@deps_app.command("status")' in cli_content,
        "deps upgrade": '@deps_app.command("upgrade")' in cli_content,
        "deps guard": '@deps_app.command("guard"' in cli_content,
        "deps drift": '@deps_app.command("drift"' in cli_content,
        "deps sync": '@deps_app.command("sync"' in cli_content,
        "deps preflight": '@deps_app.command("preflight"' in cli_content,
        "deps mirror": '@deps_app.command("mirror"' in cli_content,
        "deps snapshot ensure": '@snapshot_app.command("ensure")' in cli_content,
        "offline-package": "@app.command" in cli_content
        and "offline-package" in cli_content,
        "offline-doctor": "@app.command" in cli_content
        and "offline-doctor" in cli_content,
    }

    return commands


def check_workflow_integration() -> dict[str, bool]:
    """Verify workflows use CLI commands."""
    workflows_dir = REPO_ROOT / ".github" / "workflows"

    checks = {
        "dependency-preflight uses CLI": False,
        "dependency-contract-check uses CLI": False,
        "offline-packaging uses CLI": False,
    }

    # Check dependency-preflight.yml
    preflight_yml = workflows_dir / "dependency-preflight.yml"
    if preflight_yml.exists():
        content = preflight_yml.read_text(encoding="utf-8")
        checks["dependency-preflight uses CLI"] = (
            "prometheus deps preflight" in content
            and "prometheus deps guard" in content
            and "prometheus deps snapshot ensure" in content
        )

    # Check dependency-contract-check.yml
    contract_yml = workflows_dir / "dependency-contract-check.yml"
    if contract_yml.exists():
        content = contract_yml.read_text(encoding="utf-8")
        checks["dependency-contract-check uses CLI"] = "prometheus deps sync" in content

    # Check offline-packaging-optimized.yml
    packaging_yml = workflows_dir / "offline-packaging-optimized.yml"
    if packaging_yml.exists():
        content = packaging_yml.read_text(encoding="utf-8")
        checks["offline-packaging uses CLI"] = (
            "prometheus offline-package" in content
            or "prometheus offline-doctor" in content
        )

    return checks


def check_documentation() -> dict[str, bool]:
    """Verify documentation exists and references key concepts."""
    docs_dir = REPO_ROOT / "docs"

    checks = {
        "dependency-governance.md exists": False,
        "packaging workflow linked": False,
    }

    governance_doc = docs_dir / "dependency-governance.md"
    if governance_doc.exists():
        checks["dependency-governance.md exists"] = True
        content = governance_doc.read_text(encoding="utf-8")
        checks["packaging workflow linked"] = (
            "packaging-workflow-integration.md" in content
        )

    return checks


def main() -> int:  # noqa: C901
    """Run all verification checks."""
    print("🔍 Verifying Dependency Pipeline Setup")
    print("=" * 60)

    all_passed = True

    # Check script imports
    print("\n📦 Checking Script Imports...")
    script_results = check_script_imports()
    for name, passed in script_results.items():
        status = "✅" if passed else "❌"
        print(f"  {status} {name}")
        if not passed:
            all_passed = False

    # Check CLI commands
    print("\n🖥️  Checking CLI Commands...")
    cli_results = check_cli_commands()
    for name, passed in cli_results.items():
        status = "✅" if passed else "❌"
        print(f"  {status} {name}")
        if not passed:
            all_passed = False

    # Check workflow integration
    print("\n⚙️  Checking Workflow Integration...")
    workflow_results = check_workflow_integration()
    for name, passed in workflow_results.items():
        status = "✅" if passed else "❌"
        print(f"  {status} {name}")
        if not passed:
            all_passed = False

    # Check documentation
    print("\n📚 Checking Documentation...")
    doc_results = check_documentation()
    for name, passed in doc_results.items():
        status = "✅" if passed else "❌"
        print(f"  {status} {name}")
        if not passed:
            all_passed = False

    # Summary
    print("\n" + "=" * 60)
    if all_passed:
        print("✅ All checks passed! Dependency pipeline is properly configured.")
        return 0
    else:
        print("❌ Some checks failed. Review the output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
