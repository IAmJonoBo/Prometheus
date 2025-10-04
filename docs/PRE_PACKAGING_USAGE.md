# Pre-Packaging Features Usage Guide

This guide demonstrates how to use the newly implemented pre-packaging features.

## 1. Grafana Telemetry Dashboards

### Exporting Dashboards

```bash
# Export all default dashboards to infra/grafana/dashboards/
python3 scripts/export_grafana_dashboards.py
```

### Starting Grafana with Docker Compose

```bash
cd infra
docker-compose up -d grafana prometheus
```

Access Grafana at `http://localhost:3000` (admin/admin)

### Available Dashboards

1. **Ingestion Overview** - PII redactions, throughput, connector latency
2. **Pipeline Overview** - Retrieval success, decision approvals, diagnostics
3. **Dependency Management** - Auto-sync metrics, guard violations, rollback events

## 2. Model Registry Governance

### Basic Usage

```python
from governance.model_registry import (
    ModelRegistryGovernance,
    ModelSignature,
    ModelCadencePolicy,
)
from datetime import datetime, timedelta, UTC
from pathlib import Path

# Initialize governance
governance = ModelRegistryGovernance()

# Register a model signature
signature = ModelSignature(
    model_id="sentence-transformers/all-MiniLM-L6-v2",
    version="1.0.0",
    checksum_sha256="abc123...",
    signed_at=datetime.now(UTC),
    signed_by="security-team",
)
governance.register_model_signature(signature)

# Validate a model
model_path = Path("models/all-MiniLM-L6-v2/")
is_valid, error = governance.validate_model(
    "sentence-transformers/all-MiniLM-L6-v2",
    "1.0.0",
    model_path,
)
print(f"Valid: {is_valid}, Error: {error}")

# Add cadence policy
policy = ModelCadencePolicy(
    model_id="sentence-transformers/all-MiniLM-L6-v2",
    min_days_between_updates=7,
    allowed_update_windows=["weekday"],
    environment="prod",
)
governance.add_policy(policy)

# Check if update is allowed
can_update, reason = governance.check_update_allowed(
    "sentence-transformers/all-MiniLM-L6-v2",
    last_update=datetime.now(UTC) - timedelta(days=3),
)
print(f"Can update: {can_update}, Reason: {reason}")

# Export audit log
governance.export_audit_log(Path("var/model-audit.json"))
```

## 3. Guided Remediation Prompts

### Guard Violation Remediation

```python
from chiron.remediation.prompts import prompt_guard_violation

success = prompt_guard_violation(
    package="numpy",
    severity="needs-review",
    reason="CVE-2024-12345 detected, CVSS score 7.5",
)
```

Interactive prompt will display:
```
======================================================================
🔧 Dependency Guard Violation Detected
======================================================================

Package: numpy
Severity: needs-review
Reason: CVE-2024-12345 detected, CVSS score 7.5

The dependency guard has identified a policy violation that needs attention.
Please select a remediation strategy:

Available remediation options:

  1. Update numpy to latest safe version
  2. Snooze violation for 7 days
  3. Rollback to previous dependency state
  4. Add policy exception (requires approval)
  5. Cancel and exit

Select an option (1-5): 
```

### Wheelhouse Failure Remediation

```python
from chiron.remediation.prompts import prompt_wheelhouse_failure

success = prompt_wheelhouse_failure(
    package="cryptography",
    missing_platforms=["linux_aarch64", "musllinux_x86_64"],
)
```

### Runtime Failure Remediation

```python
from chiron.remediation.prompts import prompt_runtime_failure

success = prompt_runtime_failure(
    error_type="ImportError",
    error_message="No module named 'numpy'",
)
```

## 4. ML Risk Prediction

### Predicting Update Risk

```python
from chiron.deps.ml_risk import (
    UpdateRiskPredictor,
    UpdateFeatures,
)

predictor = UpdateRiskPredictor()

# Define update features
features = UpdateFeatures(
    package_name="django",
    version_from="4.2.0",
    version_to="5.0.0",
    major_version_change=True,
    minor_version_change=False,
    patch_version_change=False,
    has_breaking_changes=True,
    security_update=False,
    days_since_last_update=45,
    package_popularity_score=0.95,
    has_test_coverage=True,
    is_transitive_dependency=False,
    dependency_count=5,
)

# Predict risk
risk_score = predictor.predict_risk(features)

print(f"Package: {risk_score.package_name}")
print(f"Risk Score: {risk_score.score:.2f}")
print(f"Confidence: {risk_score.confidence:.2f}")
print(f"Recommendation: {risk_score.recommendation}")
print(f"Contributing Factors:")
for factor, value in risk_score.factors.items():
    print(f"  - {factor}: {value:+.2f}")
```

Output:
```
Package: django
Risk Score: 0.90
Confidence: 0.60
Recommendation: blocked
Contributing Factors:
  - major_version_change: +0.60
  - breaking_changes: +0.80
  - high_dependency_count: +0.30
```

### Recording Outcomes

```python
from chiron.deps.ml_risk import HistoricalOutcome
from datetime import datetime, UTC

outcome = HistoricalOutcome(
    package_name="django",
    version_from="4.2.0",
    version_to="5.0.0",
    timestamp=datetime.now(UTC),
    success=False,
    rolled_back=True,
    failure_reason="Test failures in authentication module",
)

predictor.record_outcome(outcome)
```

## 5. Intelligent Rollback

### Monitoring Health and Deciding Rollback

```python
from chiron.deps.ml_risk import (
    IntelligentRollback,
    HealthMetric,
)
from datetime import datetime, UTC

rollback = IntelligentRollback()

# Add health metrics
rollback.add_health_metric(HealthMetric(
    name="api_error_rate",
    value=0.15,  # 15%
    threshold=0.05,  # 5%
    breached=True,
))

rollback.add_health_metric(HealthMetric(
    name="response_time_p95",
    value=2500,  # ms
    threshold=1000,  # ms
    breached=True,
))

# Make rollback decision
decision = rollback.should_rollback(
    recent_updates=["django", "celery"],
    observation_window_seconds=300,
)

print(f"Should Rollback: {decision.should_rollback}")
print(f"Confidence: {decision.confidence:.2f}")
print(f"Reason: {decision.reason}")
print(f"Breached Metrics: {len(decision.breached_metrics)}")

if decision.partial_rollback_packages:
    print(f"Partial Rollback: {decision.partial_rollback_packages}")

# Execute rollback
if decision.should_rollback:
    success = rollback.execute_rollback(decision, dry_run=False)
```

## 6. Cross-Repository Coordination

### Coordinating Updates Across Repositories

```python
from chiron.deps.cross_repo import (
    CrossRepoCoordinator,
    RepositoryInfo,
)
from pathlib import Path

coordinator = CrossRepoCoordinator()

# Register repositories
coordinator.register_repository(RepositoryInfo(
    name="api-service",
    path=Path("/repos/api-service"),
    dependencies={"django": "4.2.0", "celery": "5.3.0"},
    priority=1,
))

coordinator.register_repository(RepositoryInfo(
    name="worker-service",
    path=Path("/repos/worker-service"),
    dependencies={"django": "5.0.0", "celery": "5.3.0"},
    priority=2,
))

# Analyze for conflicts
conflicts = coordinator.analyze_dependencies()

print(f"Found {len(conflicts)} conflicts:")
for conflict in conflicts:
    print(f"  - {conflict.package_name}")
    for repo, version in conflict.required_versions.items():
        print(f"    {repo}: {version}")

# Coordinate update
results = coordinator.coordinate_update("django", "5.0.0")
for repo, success in results.items():
    print(f"{repo}: {'✓' if success else '✗'}")
```

## 7. Advanced Conflict Resolution

### Resolving Version Conflicts

```python
from chiron.deps.cross_repo import (
    ConflictResolver,
    DependencyConflict,
    ResolutionStrategy,
    create_resolution_plan,
)

resolver = ConflictResolver()

# Define a conflict
conflict = DependencyConflict(
    package_name="requests",
    required_versions={
        "api-service": "2.28.0",
        "worker-service": "2.31.0",
        "scheduler": "2.30.0",
    },
    is_resolvable=True,
)

# Resolve with specific strategy
resolved_version = resolver.resolve_conflict(
    conflict,
    strategy=ResolutionStrategy.HIGHEST_VERSION,
)

print(f"Resolved to: {resolved_version}")
print(f"Strategy used: {conflict.resolution_strategy}")

# Or let it auto-select strategy
resolved_version = resolver.resolve_conflict(conflict)

# Create comprehensive resolution plan
conflicts = [conflict]  # List of all conflicts
plan = create_resolution_plan(conflicts, resolver)

print(f"Resolution Plan:")
print(f"  Conflicts: {len(plan.conflicts)}")
print(f"  Resolutions: {plan.resolutions}")
print(f"  Execution Order: {plan.execution_order}")
print(f"  Estimated Risk: {plan.estimated_risk:.2f}")

# Export plan
import json
with open("resolution-plan.json", "w") as f:
    json.dump(plan.to_dict(), f, indent=2)
```

## 8. Running E2E Tests

```bash
# Run all e2e tests
pytest tests/integration/test_dependency_e2e.py -v -m e2e

# Run specific test class
pytest tests/integration/test_dependency_e2e.py::TestDependencySyncE2E -v

# Run with coverage
pytest tests/integration/test_dependency_e2e.py --cov=chiron --cov=governance
```

## Integration with Existing Commands

### Dependency Guard with Risk Prediction

```python
# In your guard workflow
from chiron.deps.ml_risk import UpdateRiskPredictor, UpdateFeatures

predictor = UpdateRiskPredictor()

# Extract features from proposed update
features = extract_update_features(package_update)

# Predict risk
risk = predictor.predict_risk(features)

# Integrate with guard severity
if risk.recommendation == "blocked":
    guard_severity = "blocked"
elif risk.recommendation == "needs-review":
    guard_severity = "needs-review"
else:
    guard_severity = "safe"
```

### Auto-Sync with Intelligent Rollback

```python
# In your auto-sync workflow
from chiron.deps.ml_risk import IntelligentRollback, HealthMetric

# After applying updates
rollback = IntelligentRollback()

# Monitor health metrics
rollback.add_health_metric(collect_health_metric("error_rate"))
rollback.add_health_metric(collect_health_metric("latency"))

# Decide if rollback needed
decision = rollback.should_rollback(recently_updated_packages)

if decision.should_rollback:
    # Trigger rollback mechanism
    perform_rollback(decision.partial_rollback_packages or all_packages)
```

## Configuration Files

### Model Registry Policy

Create `configs/model-registry-policy.toml`:

```toml
[global]
require_signatures = true
default_snooze_days = 7

[[models]]
model_id = "sentence-transformers/all-MiniLM-L6-v2"
min_days_between_updates = 14
allowed_update_windows = ["weekday"]
environment = "prod"

[[models]]
model_id = "cross-encoder/ms-marco-MiniLM-L-6-v2"
min_days_between_updates = 7
allowed_update_windows = ["weekday", "weekend"]
environment = "dev"
```

## Best Practices

1. **Telemetry**: Always export dashboards after updates
2. **Model Registry**: Validate signatures before deployment
3. **Remediation**: Use guided prompts in CI for consistent decisions
4. **Risk Prediction**: Record outcomes to improve predictions
5. **Rollback**: Monitor health metrics continuously after updates
6. **Cross-Repo**: Analyze conflicts before coordinated updates
7. **Testing**: Run e2e tests before production rollout

## Troubleshooting

### Dashboard Not Showing Data
- Ensure Prometheus is scraping metrics
- Check metric names match dashboard queries
- Verify time range in Grafana

### Model Validation Fails
- Check checksum calculation
- Verify signature is registered
- Ensure model file exists and is readable

### Remediation Prompt Hangs
- Check for blocking input operations
- Verify TTY is available
- Test in non-interactive mode first

### Risk Prediction Returns Low Confidence
- Add more historical outcomes
- Verify feature extraction accuracy
- Check historical data persistence

## Next Steps

1. Integrate with existing CLI commands
2. Add configuration for policies
3. Set up continuous monitoring
4. Train ML models on historical data
5. Extend e2e tests with real integrations
