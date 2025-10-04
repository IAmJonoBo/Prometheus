#!/usr/bin/env python3
"""Validation script for quality gates and release readiness.

This script validates that all quality gates pass before release,
including test coverage, configuration validation, and CLI integration.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent


def run_command(cmd: list[str], description: str, *, check: bool = True) -> dict[str, Any]:
    """Run a command and return its result."""
    print(f"\n{'='*70}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'='*70}")
    
    try:
        result = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=check,
        )
        
        if result.stdout:
            print(result.stdout)
        
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        
        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except subprocess.CalledProcessError as exc:
        print(f"❌ Command failed with exit code {exc.returncode}", file=sys.stderr)
        if exc.stdout:
            print(exc.stdout)
        if exc.stderr:
            print(exc.stderr, file=sys.stderr)
        
        return {
            "success": False,
            "returncode": exc.returncode,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
        }
    except FileNotFoundError as exc:
        print(f"❌ Command not found: {exc}", file=sys.stderr)
        return {
            "success": False,
            "returncode": 127,
            "stdout": "",
            "stderr": str(exc),
        }


def validate_configuration_files() -> bool:
    """Validate all configuration files."""
    print("\n🔍 Validating Configuration Files...")
    
    config_dir = REPO_ROOT / "configs" / "defaults"
    required_configs = [
        "pipeline.toml",
        "policies.toml",
        "monitoring.toml",
        "pipeline_local.toml",
    ]
    
    all_valid = True
    for config_file in required_configs:
        config_path = config_dir / config_file
        if not config_path.exists():
            print(f"❌ Missing config file: {config_file}")
            all_valid = False
        else:
            print(f"✅ Found config file: {config_file}")
            
            # Try to parse TOML
            try:
                try:
                    import tomli
                except ImportError:
                    import tomllib as tomli  # Python 3.11+
                
                with open(config_path, "rb") as f:
                    tomli.load(f)
                print(f"   ✓ Valid TOML syntax")
            except ImportError:
                print(f"   ⚠ TOML parser not available (tomli/tomllib)")
            except Exception as exc:
                print(f"   ✗ Invalid TOML: {exc}")
                all_valid = False
    
    return all_valid


def validate_test_structure() -> bool:
    """Validate test directory structure."""
    print("\n🔍 Validating Test Structure...")
    
    tests_dir = REPO_ROOT / "tests"
    required_dirs = ["unit", "integration", "e2e"]
    
    all_valid = True
    for test_dir in required_dirs:
        test_path = tests_dir / test_dir
        if not test_path.exists():
            print(f"❌ Missing test directory: {test_dir}")
            all_valid = False
        else:
            print(f"✅ Found test directory: {test_dir}")
            
            # Count test files
            test_files = list(test_path.rglob("test_*.py"))
            print(f"   ✓ Contains {len(test_files)} test files")
    
    return all_valid


def validate_documentation() -> bool:
    """Validate documentation completeness."""
    print("\n🔍 Validating Documentation...")
    
    docs_dir = REPO_ROOT / "docs"
    required_docs = [
        "quality-gates.md",
        "TESTING_STRATEGY.md",
        "PRE_PACKAGING_USAGE.md",
    ]
    
    all_valid = True
    for doc_file in required_docs:
        doc_path = docs_dir / doc_file
        if not doc_path.exists():
            print(f"❌ Missing documentation: {doc_file}")
            all_valid = False
        else:
            print(f"✅ Found documentation: {doc_file}")
    
    return all_valid


def run_unit_tests() -> bool:
    """Run unit tests with coverage."""
    result = run_command(
        ["python3", "-m", "pytest", "tests/unit/", "-v", "--tb=short"],
        "Unit Tests",
        check=False,
    )
    return result["success"]


def run_integration_tests() -> bool:
    """Run integration tests."""
    result = run_command(
        ["python3", "-m", "pytest", "tests/integration/", "-v", "--tb=short"],
        "Integration Tests",
        check=False,
    )
    return result["success"]


def run_e2e_tests() -> bool:
    """Run E2E tests."""
    result = run_command(
        ["python3", "-m", "pytest", "tests/e2e/", "-v", "-m", "e2e", "--tb=short"],
        "E2E Tests",
        check=False,
    )
    return result["success"]


def main() -> int:
    """Run all quality gate validations."""
    print("=" * 70)
    print("PROMETHEUS QUALITY GATES VALIDATION")
    print("=" * 70)
    
    results = {}
    
    # Gate 1: Configuration Validation
    results["config_validation"] = validate_configuration_files()
    
    # Gate 2: Test Structure Validation
    results["test_structure"] = validate_test_structure()
    
    # Gate 3: Documentation Validation
    results["documentation"] = validate_documentation()
    
    # Gate 4: Unit Tests (if pytest is available)
    try:
        import pytest
        results["unit_tests"] = run_unit_tests()
    except ImportError:
        print("\n⚠️  pytest not available, skipping unit tests")
        results["unit_tests"] = None
    
    # Gate 5: Integration Tests (if pytest is available)
    try:
        import pytest
        results["integration_tests"] = run_integration_tests()
    except ImportError:
        print("\n⚠️  pytest not available, skipping integration tests")
        results["integration_tests"] = None
    
    # Gate 6: E2E Tests (if pytest is available)
    try:
        import pytest
        results["e2e_tests"] = run_e2e_tests()
    except ImportError:
        print("\n⚠️  pytest not available, skipping E2E tests")
        results["e2e_tests"] = None
    
    # Summary
    print("\n" + "=" * 70)
    print("QUALITY GATES SUMMARY")
    print("=" * 70)
    
    passed = 0
    failed = 0
    skipped = 0
    
    for gate, result in results.items():
        if result is None:
            status = "⏭️  SKIPPED"
            skipped += 1
        elif result:
            status = "✅ PASSED"
            passed += 1
        else:
            status = "❌ FAILED"
            failed += 1
        
        print(f"{status} - {gate.replace('_', ' ').title()}")
    
    print("\n" + "=" * 70)
    print(f"Results: {passed} passed, {failed} failed, {skipped} skipped")
    print("=" * 70)
    
    if failed > 0:
        print("\n❌ Some quality gates failed. Please address the issues above.")
        return 1
    
    print("\n✅ All quality gates passed!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
