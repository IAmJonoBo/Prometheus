# End-to-End Tests

This directory contains comprehensive end-to-end tests for the Prometheus Strategy OS pipeline.

## Overview

E2E tests validate the complete pipeline flow from ingestion through monitoring, with real integrations and quality gates. These tests ensure that all components work together correctly and that the system meets its functional and non-functional requirements.

## Test Structure

```
tests/e2e/
├── __init__.py                 # Package initialization
├── test_pipeline_e2e.py        # Full pipeline E2E tests
├── test_auto_sync_e2e.py       # Auto-sync workflow tests
└── README.md                   # This file
```

## Test Files

### test_pipeline_e2e.py

Tests the complete six-stage pipeline execution:

**Test Classes:**
- `TestFullPipelineE2E` - Core pipeline functionality
  - Policy enforcement
  - Monitoring integration
  - Decision thresholds
  - Extra metrics

- `TestConfigurationIntegrationE2E` - Configuration loading
  - Policy config loading
  - Monitoring config loading
  - TOML validation

- `TestEndToEndWorkflowsE2E` - Complete workflows
  - Ingestion to monitoring flow
  - Policy violation handling
  - Continuous monitoring

**Key Tests:**
- `test_pipeline_with_policy_enforcement` - Validates policy configuration and enforcement
- `test_pipeline_with_monitoring_integration` - Tests monitoring signal collection
- `test_policy_enforcement_with_various_thresholds` - Tests approval/review thresholds
- `test_monitoring_with_extra_metrics` - Validates custom metrics

### test_auto_sync_e2e.py

Tests automated dependency synchronization workflows:

**Test Classes:**
- `TestAutoSyncWorkflowE2E` - Auto-sync scenarios
  - Safe update application
  - Guard violation handling
  - Rollback on failure
  - Cross-repo coordination
  - ML risk prediction

- `TestDependencyGuardIntegrationE2E` - Guard integration
  - Policy checks
  - Preflight validation

- `TestFullIntegrationScenarios` - Complete scenarios
  - Full dependency workflow
  - Production scenarios
  - Remediation workflows

**Key Tests:**
- `test_auto_sync_safe_updates` - Tests safe update workflow
- `test_auto_sync_with_violations` - Tests blocking on violations
- `test_auto_sync_with_rollback` - Tests automatic rollback
- `test_cross_repo_coordination` - Tests multi-repo updates
- `test_ml_risk_prediction_integration` - Tests risk scoring
- `test_intelligent_rollback_decision` - Tests rollback logic

## Running Tests

### Run All E2E Tests

```bash
pytest tests/e2e/ -v -m e2e
```

### Run Specific Test File

```bash
pytest tests/e2e/test_pipeline_e2e.py -v
pytest tests/e2e/test_auto_sync_e2e.py -v
```

### Run Specific Test Class

```bash
pytest tests/e2e/test_pipeline_e2e.py::TestFullPipelineE2E -v
pytest tests/e2e/test_auto_sync_e2e.py::TestAutoSyncWorkflowE2E -v
```

### Run Specific Test

```bash
pytest tests/e2e/test_pipeline_e2e.py::TestFullPipelineE2E::test_pipeline_with_policy_enforcement -v
```

### Run with Coverage

```bash
pytest tests/e2e/ -v --cov=. --cov-report=term-missing
```

### Run in Verbose Mode

```bash
pytest tests/e2e/ -vv -s
```

## Test Markers

E2E tests use pytest markers for categorization:

- `@pytest.mark.e2e` - Standard E2E tests
- `@pytest.mark.integration` - Integration-level E2E tests
- `@pytest.mark.slow` - Long-running tests requiring infrastructure

### Run Only E2E Tests

```bash
pytest tests/e2e/ -m e2e
```

### Run Integration Tests

```bash
pytest tests/e2e/ -m integration
```

### Skip Slow Tests

```bash
pytest tests/e2e/ -m "e2e and not slow"
```

## Test Requirements

### Dependencies

E2E tests require the following Python packages:
- `pytest` - Test framework
- `pytest-cov` - Coverage reporting
- Common Prometheus packages (contracts, decision, monitoring, etc.)

### External Services (for full integration tests)

Some tests require external services (marked with `pytest.skip`):
- OpenSearch - Document indexing
- Qdrant - Vector storage
- PostgreSQL - Persistence
- Temporal - Workflow orchestration
- Grafana/Prometheus - Observability

These services are typically provided via Docker Compose:

```bash
cd infra
docker-compose up -d
```

## Writing New E2E Tests

### Test Template

```python
import pytest
from common.contracts import EventMeta
from decision.service import DecisionConfig, DecisionService

@pytest.mark.e2e
class TestMyFeatureE2E:
    """E2E tests for my feature."""
    
    def test_my_scenario(self):
        """Test my specific scenario.
        
        Validates:
        - Expected behavior 1
        - Expected behavior 2
        - Expected behavior 3
        """
        # Arrange
        config = DecisionConfig(policy_engine="test")
        
        # Act
        result = some_operation(config)
        
        # Assert
        assert result.status == "expected"
```

### Best Practices

1. **Clear Test Names**: Use descriptive names that explain what is being tested
2. **Documentation**: Include docstrings explaining validation criteria
3. **Arrange-Act-Assert**: Follow AAA pattern for test structure
4. **Fixtures**: Use pytest fixtures for common setup
5. **Markers**: Apply appropriate markers (@pytest.mark.e2e, etc.)
6. **Assertions**: Make specific assertions about behavior
7. **Cleanup**: Ensure tests clean up resources
8. **Independence**: Tests should not depend on each other

### Test Coverage Goals

E2E tests should aim for:
- **Scenario Coverage**: All major user scenarios
- **Edge Cases**: Boundary conditions and error cases
- **Integration Points**: All component interactions
- **Configuration**: All configuration options
- **Error Handling**: Graceful degradation and recovery

## Skipped Tests

Some tests are skipped with `pytest.skip()` because they require:
- Docker Compose stack running
- Specific environment configuration
- Interactive user input
- Production-like infrastructure

These tests are intended to run in:
- CI/CD pipelines with infrastructure
- Staging/pre-production environments
- Manual testing scenarios

To run skipped tests, ensure required infrastructure is available and remove the skip decorator or provide required conditions.

## Debugging E2E Tests

### Verbose Output

```bash
pytest tests/e2e/ -vv -s
```

### Print Debug Info

```bash
pytest tests/e2e/ -vv -s --tb=long
```

### Run Single Test for Debugging

```bash
pytest tests/e2e/test_pipeline_e2e.py::TestFullPipelineE2E::test_pipeline_with_policy_enforcement -vv -s
```

### Use pdb for Interactive Debugging

Add `import pdb; pdb.set_trace()` in test code, then run:

```bash
pytest tests/e2e/ -s
```

## CI Integration

E2E tests should be run in CI with:

```yaml
- name: Run E2E Tests
  run: |
    docker-compose -f infra/docker-compose.yml up -d
    pytest tests/e2e/ -v -m e2e --cov=. --cov-report=xml
    docker-compose -f infra/docker-compose.yml down
```

## Monitoring Test Results

Track E2E test metrics:
- **Pass Rate**: Percentage of tests passing
- **Execution Time**: Time to run all tests
- **Flakiness**: Tests that fail intermittently
- **Coverage**: Code coverage from E2E tests

## Related Documentation

- [Quality Gates](../../docs/quality-gates.md)
- [Testing Strategy](../../docs/TESTING_STRATEGY.md)
- [Release Readiness](../../docs/RELEASE_READINESS.md)
- [Integration Tests](../integration/README.md)
- [Unit Tests](../unit/README.md)

## Support

For questions or issues with E2E tests:
1. Check test documentation and docstrings
2. Review related test files for examples
3. Consult testing strategy documentation
4. Open an issue with test failure details
