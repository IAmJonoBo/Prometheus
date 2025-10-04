"""Tests for policy engine."""

import pytest
from pathlib import Path
from datetime import UTC, datetime, timedelta

from chiron.deps.policy import (
    PackagePolicy,
    PolicyViolation,
    DependencyPolicy,
    PolicyEngine,
    load_policy,
)


@pytest.fixture
def basic_policy() -> DependencyPolicy:
    """Create a basic policy for testing."""
    return DependencyPolicy(
        default_allowed=True,
        max_major_version_jump=1,
        require_security_review=True,
    )


@pytest.fixture
def policy_with_packages() -> DependencyPolicy:
    """Create policy with package rules."""
    policy = DependencyPolicy(
        default_allowed=True,
        max_major_version_jump=1,
    )
    
    # Add allowlist entry
    policy.allowlist["numpy"] = PackagePolicy(
        name="numpy",
        allowed=True,
        version_ceiling="2.9.0",
        version_floor="2.0.0",
        upgrade_cadence_days=90,
    )
    
    # Add denylist entry
    policy.denylist["insecure-pkg"] = PackagePolicy(
        name="insecure-pkg",
        allowed=False,
        reason="Known security issues",
    )
    
    return policy


def test_package_policy_creation():
    """Test PackagePolicy creation."""
    policy = PackagePolicy(
        name="numpy",
        allowed=True,
        version_ceiling="2.0.0",
        version_floor="1.20.0",
        upgrade_cadence_days=30,
        requires_review=True,
        reason="Core dependency",
    )
    
    assert policy.name == "numpy"
    assert policy.allowed is True
    assert policy.version_ceiling == "2.0.0"
    assert policy.upgrade_cadence_days == 30


def test_policy_violation_creation():
    """Test PolicyViolation creation."""
    violation = PolicyViolation(
        package="torch",
        current_version="2.0.0",
        target_version="3.0.0",
        violation_type="major_version_jump",
        message="Major version jump exceeds limit",
        severity="warning",
    )
    
    assert violation.package == "torch"
    assert violation.severity == "warning"


def test_dependency_policy_defaults():
    """Test DependencyPolicy default values."""
    policy = DependencyPolicy()
    
    assert policy.default_allowed is True
    assert policy.max_major_version_jump == 1
    assert policy.require_security_review is True
    assert policy.allow_pre_releases is False
    assert len(policy.allowlist) == 0
    assert len(policy.denylist) == 0


def test_policy_engine_init(basic_policy: DependencyPolicy):
    """Test PolicyEngine initialization."""
    engine = PolicyEngine(basic_policy)
    
    assert engine.policy == basic_policy
    assert len(engine._last_upgrade_timestamps) == 0


def test_check_package_allowed_default(basic_policy: DependencyPolicy):
    """Test checking allowed package with default policy."""
    engine = PolicyEngine(basic_policy)
    
    allowed, reason = engine.check_package_allowed("requests")
    
    assert allowed is True
    assert reason is None


def test_check_package_allowed_in_denylist(policy_with_packages: DependencyPolicy):
    """Test checking package in denylist."""
    engine = PolicyEngine(policy_with_packages)
    
    allowed, reason = engine.check_package_allowed("insecure-pkg")
    
    assert allowed is False
    assert "security issues" in reason.lower()


def test_check_package_allowed_in_allowlist(policy_with_packages: DependencyPolicy):
    """Test checking package in allowlist."""
    engine = PolicyEngine(policy_with_packages)
    
    allowed, reason = engine.check_package_allowed("numpy")
    
    assert allowed is True
    assert reason is None


def test_check_version_allowed_within_bounds(policy_with_packages: DependencyPolicy):
    """Test version check within ceiling/floor."""
    engine = PolicyEngine(policy_with_packages)
    
    allowed, reason = engine.check_version_allowed("numpy", "2.5.0")
    
    assert allowed is True
    assert reason is None


def test_check_version_allowed_above_ceiling(policy_with_packages: DependencyPolicy):
    """Test version check above ceiling."""
    engine = PolicyEngine(policy_with_packages)
    
    allowed, reason = engine.check_version_allowed("numpy", "3.0.0")
    
    assert allowed is False
    assert "ceiling" in reason.lower()


def test_check_version_allowed_below_floor(policy_with_packages: DependencyPolicy):
    """Test version check below floor."""
    engine = PolicyEngine(policy_with_packages)
    
    allowed, reason = engine.check_version_allowed("numpy", "1.19.0")
    
    assert allowed is False
    assert "floor" in reason.lower()


def test_check_version_blocked():
    """Test version in blocked list."""
    policy = DependencyPolicy()
    policy.allowlist["pkg"] = PackagePolicy(
        name="pkg",
        blocked_versions=["1.0.0", "1.0.1"],
    )
    
    engine = PolicyEngine(policy)
    
    allowed, reason = engine.check_version_allowed("pkg", "1.0.0")
    
    assert allowed is False
    assert "blocked" in reason.lower()


def test_check_upgrade_allowed_simple(basic_policy: DependencyPolicy):
    """Test simple upgrade check."""
    engine = PolicyEngine(basic_policy)
    
    violations = engine.check_upgrade_allowed("requests", "2.28.0", "2.29.0")
    
    # Should have no violations for minor version bump
    assert len(violations) == 0


def test_check_upgrade_allowed_major_jump(basic_policy: DependencyPolicy):
    """Test upgrade with major version jump."""
    engine = PolicyEngine(basic_policy)
    
    violations = engine.check_upgrade_allowed("requests", "2.28.0", "4.0.0")
    
    # Should have violation for exceeding max jump (2 > 1)
    assert len(violations) > 0
    assert any(v.violation_type == "major_version_jump" for v in violations)


def test_check_upgrade_denied_package():
    """Test upgrade for denied package."""
    policy = DependencyPolicy()
    policy.denylist["bad-pkg"] = PackagePolicy(
        name="bad-pkg",
        allowed=False,
        reason="Security issue",
    )
    
    engine = PolicyEngine(policy)
    
    violations = engine.check_upgrade_allowed("bad-pkg", "1.0.0", "1.1.0")
    
    assert len(violations) > 0
    assert any(v.violation_type == "package_denied" for v in violations)


def test_check_upgrade_denied_version():
    """Test upgrade to denied version."""
    policy = DependencyPolicy()
    policy.allowlist["pkg"] = PackagePolicy(
        name="pkg",
        version_ceiling="2.0.0",
    )
    
    engine = PolicyEngine(policy)
    
    violations = engine.check_upgrade_allowed("pkg", "1.5.0", "2.5.0")
    
    assert len(violations) > 0
    assert any(v.violation_type == "version_denied" for v in violations)


def test_check_upgrade_requires_review():
    """Test upgrade requiring review."""
    policy = DependencyPolicy()
    policy.allowlist["pkg"] = PackagePolicy(
        name="pkg",
        requires_review=True,
    )
    
    engine = PolicyEngine(policy)
    
    violations = engine.check_upgrade_allowed("pkg", "1.0.0", "1.1.0")
    
    assert len(violations) > 0
    assert any(v.violation_type == "review_required" for v in violations)
    # Should be info, not error
    review_violation = next(v for v in violations if v.violation_type == "review_required")
    assert review_violation.severity == "info"


def test_record_upgrade(basic_policy: DependencyPolicy):
    """Test recording upgrade timestamp."""
    engine = PolicyEngine(basic_policy)
    
    before = datetime.now(UTC)
    engine.record_upgrade("requests")
    after = datetime.now(UTC)
    
    assert "requests" in engine._last_upgrade_timestamps
    timestamp = engine._last_upgrade_timestamps["requests"]
    assert before <= timestamp <= after


def test_load_policy_defaults(tmp_path: Path):
    """Test loading policy with defaults when file not found."""
    config_path = tmp_path / "nonexistent.toml"
    
    policy = DependencyPolicy.from_toml(config_path)
    
    assert policy.default_allowed is True
    assert len(policy.allowlist) == 0


def test_load_policy_from_toml(tmp_path: Path):
    """Test loading policy from TOML file."""
    config_path = tmp_path / "policy.toml"
    config_path.write_text("""
[dependency_policy]
default_allowed = false
max_major_version_jump = 2
require_security_review = false
allow_pre_releases = true

[dependency_policy.allowlist.numpy]
version_ceiling = "2.0.0"
version_floor = "1.20.0"
upgrade_cadence_days = 30
requires_review = true
reason = "Core dependency"

[dependency_policy.denylist.bad-pkg]
reason = "Security issue"
""")
    
    policy = DependencyPolicy.from_toml(config_path)
    
    assert policy.default_allowed is False
    assert policy.max_major_version_jump == 2
    assert policy.require_security_review is False
    assert policy.allow_pre_releases is True
    
    assert "numpy" in policy.allowlist
    numpy_policy = policy.allowlist["numpy"]
    assert numpy_policy.version_ceiling == "2.0.0"
    assert numpy_policy.upgrade_cadence_days == 30
    
    assert "bad-pkg" in policy.denylist


def test_convenience_function_load_policy(tmp_path: Path):
    """Test load_policy convenience function."""
    config_path = tmp_path / "policy.toml"
    config_path.write_text("""
[dependency_policy]
default_allowed = true
""")
    
    policy = load_policy(config_path)
    
    assert isinstance(policy, DependencyPolicy)
    assert policy.default_allowed is True
