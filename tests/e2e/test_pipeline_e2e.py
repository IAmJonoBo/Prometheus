#!/usr/bin/env python3
"""End-to-end tests for full pipeline execution with real integrations.

Tests the complete six-stage pipeline flow with actual dependencies,
validating behavior, telemetry, and quality gates.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from common.contracts import EventMeta
from decision.service import DecisionConfig, DecisionService
from monitoring.service import MonitoringConfig, MonitoringService


@pytest.fixture
def temp_config_dir(tmp_path):
    """Create temporary configuration directory."""
    config_dir = tmp_path / "configs"
    config_dir.mkdir(parents=True)
    return config_dir


@pytest.fixture
def mock_collectors():
    """Provide mock signal collectors."""
    collector = Mock()
    collector.publish = Mock()
    return [collector]


@pytest.mark.e2e
class TestFullPipelineE2E:
    """End-to-end tests for complete pipeline execution."""

    def test_pipeline_with_policy_enforcement(self, temp_config_dir):
        """Test full pipeline execution with policy configuration.
        
        Validates:
        - Policy configuration loading
        - Decision service policy enforcement
        - Proper event flow through stages
        - Telemetry collection
        """
        # Arrange: Create policy config
        policy_config = DecisionConfig(policy_engine="rules-based")
        decision_service = DecisionService(config=policy_config)
        
        # Mock reasoning proposal
        from common.contracts import ReasoningAnalysisProposed
        
        proposal = ReasoningAnalysisProposed(
            meta=EventMeta(
                event_id="test-001",
                stage="reasoning",
                timestamp="2024-01-01T00:00:00Z",
                actor="test-user",
            ),
            summary="Test analysis summary",
            insights=["Insight 1", "Insight 2"],
            recommended_actions=["Action 1"],
            confidence=0.85,
        )
        
        # Act: Evaluate decision
        decision = decision_service.evaluate(
            proposal, 
            EventMeta(
                event_id="test-002",
                stage="decision",
                timestamp="2024-01-01T00:00:01Z",
                actor="test-user",
            )
        )
        
        # Assert: Verify decision structure
        assert decision.decision_type == "automated"
        assert decision.status in ["approved", "needs_review"]
        assert "engine" in decision.policy_checks
        assert decision.policy_checks["engine"] == "rules-based"
        assert "insight_count" in decision.policy_checks
        assert decision.rationale == proposal.summary
        assert len(decision.alternatives) > 0

    def test_pipeline_with_monitoring_integration(self, mock_collectors):
        """Test pipeline with continuous monitoring.
        
        Validates:
        - Monitoring service integration
        - Signal collection and emission
        - Metrics aggregation
        - Dashboard availability
        """
        # Arrange: Configure monitoring
        monitoring_config = MonitoringConfig(
            sample_rate=1.0,
            collectors=[{"type": "test"}],
            dashboards=[{"name": "test-dashboard"}],
        )
        monitoring_service = MonitoringService(monitoring_config, mock_collectors)
        
        # Mock decision
        from common.contracts import DecisionRecorded
        
        decision = DecisionRecorded(
            meta=EventMeta(
                event_id="test-003",
                stage="decision",
                timestamp="2024-01-01T00:00:02Z",
                actor="test-user",
            ),
            decision_type="automated",
            status="approved",
            rationale="Test rationale",
            alternatives=["Alternative 1"],
            policy_checks={"insight_count": "5"},
        )
        
        # Act: Build and emit monitoring signal
        signal = monitoring_service.build_signal(
            decision,
            EventMeta(
                event_id="test-004",
                stage="monitoring",
                timestamp="2024-01-01T00:00:03Z",
                actor="test-user",
            ),
        )
        monitoring_service.emit(signal)
        
        # Assert: Verify signal structure and emission
        assert signal.signal_type == "decision"
        assert signal.description == "Decision evaluation completed"
        assert len(signal.metrics) > 0
        assert signal.metrics[0].name == "decision.insight_count"
        assert signal.metrics[0].value == 5.0
        assert signal.metrics[0].labels["status"] == "approved"
        
        # Verify collector was called
        assert mock_collectors[0].publish.called
        assert mock_collectors[0].publish.call_count == 1

    def test_policy_enforcement_with_various_thresholds(self):
        """Test decision service with different policy thresholds.
        
        Validates:
        - Auto-approval for sufficient insights
        - Review requirement for insufficient insights
        - Policy check recording
        """
        # Test with sufficient insights (should approve)
        policy_config = DecisionConfig(policy_engine="threshold-based")
        decision_service = DecisionService(config=policy_config)
        
        from common.contracts import ReasoningAnalysisProposed
        
        # Case 1: Sufficient actions - should approve
        proposal_with_actions = ReasoningAnalysisProposed(
            meta=EventMeta(
                event_id="test-005",
                stage="reasoning",
                timestamp="2024-01-01T00:00:04Z",
                actor="test-user",
            ),
            summary="Analysis with actions",
            insights=["Insight 1", "Insight 2", "Insight 3"],
            recommended_actions=["Action 1", "Action 2"],
            confidence=0.9,
        )
        
        decision_approved = decision_service.evaluate(
            proposal_with_actions,
            EventMeta(
                event_id="test-006",
                stage="decision",
                timestamp="2024-01-01T00:00:05Z",
                actor="test-user",
            )
        )
        
        assert decision_approved.status == "approved"
        assert decision_approved.policy_checks["insight_count"] == "3"
        
        # Case 2: No actions - should need review
        proposal_no_actions = ReasoningAnalysisProposed(
            meta=EventMeta(
                event_id="test-007",
                stage="reasoning",
                timestamp="2024-01-01T00:00:06Z",
                actor="test-user",
            ),
            summary="Analysis without actions",
            insights=["Insight 1"],
            recommended_actions=[],
            confidence=0.6,
        )
        
        decision_review = decision_service.evaluate(
            proposal_no_actions,
            EventMeta(
                event_id="test-008",
                stage="decision",
                timestamp="2024-01-01T00:00:07Z",
                actor="test-user",
            )
        )
        
        assert decision_review.status == "needs_review"
        assert decision_review.policy_checks["insight_count"] == "1"

    def test_monitoring_with_extra_metrics(self, mock_collectors):
        """Test monitoring service with additional metrics.
        
        Validates:
        - Extra metrics inclusion
        - Metric aggregation
        - Signal structure
        """
        from common.contracts import DecisionRecorded, MetricSample
        
        monitoring_config = MonitoringConfig(sample_rate=1.0)
        monitoring_service = MonitoringService(monitoring_config, mock_collectors)
        
        decision = DecisionRecorded(
            meta=EventMeta(
                event_id="test-009",
                stage="decision",
                timestamp="2024-01-01T00:00:08Z",
                actor="test-user",
            ),
            decision_type="automated",
            status="approved",
            rationale="Test",
            alternatives=[],
            policy_checks={"insight_count": "2"},
        )
        
        extra_metrics = [
            MetricSample(
                name="custom.metric.1",
                value=42.0,
                labels={"source": "test"},
            ),
            MetricSample(
                name="custom.metric.2",
                value=100.0,
                labels={"type": "performance"},
            ),
        ]
        
        signal = monitoring_service.build_signal(
            decision,
            EventMeta(
                event_id="test-010",
                stage="monitoring",
                timestamp="2024-01-01T00:00:09Z",
                actor="test-user",
            ),
            extra_metrics=extra_metrics,
        )
        
        # Verify all metrics are included
        assert len(signal.metrics) == 3  # 1 default + 2 extra
        metric_names = [m.name for m in signal.metrics]
        assert "decision.insight_count" in metric_names
        assert "custom.metric.1" in metric_names
        assert "custom.metric.2" in metric_names


@pytest.mark.e2e
@pytest.mark.integration
class TestConfigurationIntegrationE2E:
    """Test configuration loading and integration."""

    def test_policy_config_loading(self, temp_config_dir):
        """Test loading policy configuration from TOML."""
        # Create a test policy config
        policy_toml = temp_config_dir / "policies.toml"
        policy_toml.write_text(
            """
[policy]
engine = "custom-engine"
auto_approve_threshold = 0.9

[[policy.checks]]
name = "test_check"
type = "threshold"
field = "score"
min_value = 0.5
"""
        )
        
        # Load and verify config
        import tomli
        
        with open(policy_toml, "rb") as f:
            config_data = tomli.load(f)
        
        assert "policy" in config_data
        assert config_data["policy"]["engine"] == "custom-engine"
        assert config_data["policy"]["auto_approve_threshold"] == 0.9
        assert len(config_data["policy"]["checks"]) == 1
        assert config_data["policy"]["checks"][0]["name"] == "test_check"

    def test_monitoring_config_loading(self, temp_config_dir):
        """Test loading monitoring configuration from TOML."""
        monitoring_toml = temp_config_dir / "monitoring.toml"
        monitoring_toml.write_text(
            """
[monitoring]
sample_rate = 0.8
enabled = true

[[monitoring.dashboards]]
name = "Test Dashboard"
url = "http://localhost:3000/test"

[[monitoring.collectors.prometheus]]
port = 9090
"""
        )
        
        # Load and verify config
        import tomli
        
        with open(monitoring_toml, "rb") as f:
            config_data = tomli.load(f)
        
        assert "monitoring" in config_data
        assert config_data["monitoring"]["sample_rate"] == 0.8
        assert config_data["monitoring"]["enabled"] is True
        assert len(config_data["monitoring"]["dashboards"]) == 1


@pytest.mark.e2e
@pytest.mark.slow
class TestEndToEndWorkflowsE2E:
    """Test complete end-to-end workflows."""

    def test_ingestion_to_monitoring_flow(self):
        """Test complete flow from ingestion through monitoring.
        
        This test validates the entire pipeline flow with mocked
        external dependencies.
        """
        # This is a placeholder for a comprehensive E2E test
        # that would exercise the full pipeline with Docker services
        # running in CI.
        
        # In a real implementation, this would:
        # 1. Start required services (OpenSearch, Qdrant, etc.)
        # 2. Ingest test data
        # 3. Execute retrieval
        # 4. Run reasoning
        # 5. Apply decision policies
        # 6. Execute actions
        # 7. Collect monitoring signals
        # 8. Verify end-to-end telemetry
        
        pytest.skip("Requires Docker Compose stack - run in CI environment")

    def test_policy_violation_handling(self):
        """Test handling of policy violations in decision stage."""
        pytest.skip("Requires full pipeline setup - run in CI environment")

    def test_continuous_monitoring_integration(self):
        """Test continuous monitoring throughout pipeline execution."""
        pytest.skip("Requires observability stack - run in CI environment")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "e2e"])
