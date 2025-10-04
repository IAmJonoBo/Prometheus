# Intelligent Dependency Upgrade Management

This document describes the intelligent dependency upgrade management system that has been implemented for Chiron.

## Overview

The intelligent upgrade system provides automatic dependency upgrade advice and intelligent dependency management with the following features:

1. **Automatic Upgrade Recommendations** - Priority-based recommendations with confidence scoring
2. **Mirror-Aware Management** - Integration with dependency mirrors for availability checking
3. **Conflict Detection and Resolution** - Automatic detection of version conflicts with resolution strategies
4. **Safe Upgrade Execution** - Incremental upgrades with rollback support
5. **Comprehensive Analysis** - Security-first prioritization and risk assessment

## Components

### 1. Upgrade Advisor (`chiron/deps/upgrade_advisor.py`)

The upgrade advisor analyzes dependency drift and generates intelligent recommendations.

#### Features

- **Priority Classification**: critical, high, medium, low
- **Confidence Scoring**: 0.0-1.0 based on stability, popularity, and age
- **Auto-Apply Detection**: Identifies safe upgrades that can be automatically applied
- **Risk Assessment**: Identifies potential breaking changes and impacts
- **Mitigation Suggestions**: Provides steps to reduce upgrade risks

#### Usage

```python
from chiron.deps.upgrade_advisor import generate_upgrade_advice
from chiron.deps import drift

# Generate drift report first
components = drift.load_sbom(Path("sbom.json"))
metadata = drift.load_metadata(Path("metadata.json"))
policy = drift.DriftPolicy()
drift_report = drift.evaluate_drift(components, metadata, policy)

# Generate upgrade advice
advice = generate_upgrade_advice(
    drift_report.packages,
    metadata=metadata,
    mirror_root=Path("vendor/wheelhouse"),
    conservative=True,
    security_first=True,
)

# Access recommendations
for rec in advice.recommendations:
    print(f"{rec.package}: {rec.current_version} -> {rec.recommended_version}")
    print(f"  Priority: {rec.priority}")
    print(f"  Confidence: {rec.confidence:.2f}")
    print(f"  Auto-apply safe: {rec.auto_apply_safe}")
```

#### CLI Integration

```bash
# Generate upgrade advice with planner
chiron deps upgrade \
  --sbom var/dependency-sync/sbom.json \
  --generate-advice \
  --mirror-root vendor/wheelhouse \
  --output upgrade-plan.json

# The output will include upgrade advice section with:
# - Safe to auto-apply packages
# - Packages requiring review
# - Priority breakdown
# - Mirror update recommendations
```

### 2. Mirror Enhancements (`chiron/deps/mirror_manager.py`)

Enhanced mirror manager with intelligent package tracking.

#### New Functions

- `check_package_availability()` - Check if a specific package version is in the mirror
- `get_mirror_recommendations()` - Get recommendations for mirror updates based on needed packages

#### Usage

```python
from chiron.deps.mirror_manager import (
    check_package_availability,
    get_mirror_recommendations,
)
from pathlib import Path

mirror_root = Path("vendor/wheelhouse")

# Check single package
info = check_package_availability(mirror_root, "requests", "2.31.0")
if info.available:
    print(f"Package available, last updated: {info.last_updated}")

# Get recommendations for multiple packages
packages_needed = [
    ("requests", "2.31.0"),
    ("urllib3", "1.26.18"),
]
recommendations = get_mirror_recommendations(mirror_root, packages_needed)

print(f"To add: {recommendations['packages_to_add']}")
print(f"To update: {recommendations['packages_to_update']}")
print(f"Available: {recommendations['packages_available']}")
```

### 3. Conflict Resolver (`chiron/deps/conflict_resolver.py`)

Automatic dependency conflict detection and resolution.

#### Features

- **Version Conflict Detection**: Identifies incompatible version constraints
- **Circular Dependency Detection**: Finds circular dependencies
- **Automatic Resolution Suggestions**: Proposes fixes with confidence scores
- **Resolution Types**: pin, upgrade, downgrade, remove, manual

#### Usage

```python
from chiron.deps.conflict_resolver import analyze_dependency_conflicts

# Load dependency specification
dependencies = {
    "dependencies": {
        "package-a": "^2.0.0",
        "package-b": "^1.0.0",
    },
}

# Analyze conflicts
report = analyze_dependency_conflicts(
    dependencies,
    conservative=True,
)

# Review conflicts
for conflict in report.conflicts:
    print(f"Conflict in {conflict.package}:")
    print(f"  Type: {conflict.conflict_type}")
    print(f"  Severity: {conflict.severity}")
    print(f"  Auto-resolvable: {conflict.auto_resolvable}")

    for suggestion in conflict.resolution_suggestions:
        print(f"  - {suggestion}")

# Apply resolutions
for resolution in report.resolutions:
    if resolution.confidence >= 0.8:
        print(f"Applying: {resolution.description}")
        for cmd in resolution.commands:
            print(f"  $ {cmd}")
```

### 4. Safe Upgrade Executor (`chiron/deps/safe_upgrade.py`)

Safe automatic upgrade execution with rollback support.

#### Features

- **Incremental Upgrades**: Batch processing with configurable size
- **Checkpoint System**: Automatic backups before each batch
- **Health Checks**: Validates environment after upgrades
- **Automatic Rollback**: Reverts to last checkpoint on failure
- **Progress Tracking**: Detailed reporting of upgrade status

#### Usage

```python
from chiron.deps.safe_upgrade import execute_safe_upgrades
from pathlib import Path

packages_to_upgrade = [
    ("requests", "2.31.0"),
    ("urllib3", "1.26.18"),
    ("certifi", "2023.7.22"),
]

report = execute_safe_upgrades(
    packages_to_upgrade,
    project_root=Path("."),
    auto_rollback=True,
    max_batch_size=5,
)

print(f"Status: {report.final_status}")
print(f"Successful: {report.summary['successful']}/{report.summary['total']}")

if report.rollback_performed:
    print("⚠️  Rollback was performed due to failures")

for upgrade in report.upgrades:
    if upgrade.success:
        print(f"✓ {upgrade.package}: {upgrade.previous_version} -> {upgrade.new_version}")
    else:
        print(f"✗ {upgrade.package}: {upgrade.error_message}")
```

### 5. Intelligent Upgrade Workflow

Complete workflow combining all components.

#### Orchestration

```python
from chiron.orchestration import OrchestrationCoordinator, OrchestrationContext

context = OrchestrationContext(dry_run=False, verbose=True)
coordinator = OrchestrationCoordinator(context)

# Run intelligent upgrade workflow
results = coordinator.intelligent_upgrade_workflow(
    auto_apply_safe=True,
    update_mirror=True,
)
```

#### CLI

```bash
# Run complete intelligent upgrade workflow
chiron orchestrate intelligent-upgrade \
  --auto-apply-safe \
  --update-mirror \
  --verbose

# This will:
# 1. Generate upgrade advice
# 2. Auto-apply safe upgrades
# 3. Update dependency mirror
# 4. Run validation checks
```

## Workflow Integration

### Standard Dependency Workflow

```bash
# 1. Run preflight checks
chiron deps preflight

# 2. Check for upgrades with advice
chiron deps upgrade \
  --sbom var/dependency-sync/sbom.json \
  --generate-advice \
  --mirror-root vendor/wheelhouse \
  --output upgrade-plan.json \
  --verbose

# 3. Review recommendations
cat upgrade-plan.json | jq '.upgrade_advice'

# 4. Apply safe upgrades
# (Manual review of plan, then apply selected packages)
poetry update <package-name>

# 5. Update mirror
python -m chiron.deps.mirror_manager \
  --update \
  --source vendor/wheelhouse-temp \
  --mirror-root vendor/wheelhouse \
  --prune

# 6. Validate
chiron deps preflight
```

### Automated Workflow

```bash
# Run complete automated workflow
chiron orchestrate intelligent-upgrade \
  --auto-apply-safe \
  --update-mirror \
  --verbose

# Or with full dependency workflow
chiron orchestrate full-dependency \
  --auto-upgrade \
  --verbose
```

## Configuration

### Conservative Mode

When `conservative=True`:

- Higher confidence threshold for auto-apply (0.75 vs 0.65)
- Only patch versions considered for auto-apply
- More detailed risk assessment

### Security-First Mode

When `security_first=True`:

- Security patches elevated to critical priority
- Patch versions get medium priority (vs low)
- Security keywords trigger automatic priority boost

## Best Practices

1. **Always Generate Advice**: Use `--generate-advice` flag to get intelligent recommendations
2. **Review Before Auto-Apply**: Check recommendations before using `--auto-apply-safe`
3. **Keep Mirror Updated**: Run mirror updates regularly to ensure availability
4. **Use Checkpoints**: Enable automatic rollback for safety
5. **Monitor Conflicts**: Run conflict analysis before major upgrades
6. **Validate After Upgrades**: Always run preflight checks after applying upgrades

## Testing

Tests are located in `tests/unit/chiron/deps/`:

- `test_upgrade_advisor.py` - Tests for upgrade advisor
- `test_conflict_resolver.py` - Tests for conflict resolver
- `test_mirror_enhancements.py` - Tests for mirror enhancements

Run tests with:

```bash
poetry run pytest tests/unit/chiron/deps/ -v
```

## Future Enhancements

- Integration with CVE databases for real-time security advisories
- Machine learning-based confidence scoring
- Automated dependency tree optimization
- Integration with CI/CD for continuous upgrade monitoring
- Support for multiple package managers (npm, cargo, etc.)
