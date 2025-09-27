"""Shared event contracts used across Prometheus pipeline stages."""

from .base import BaseEvent, EventMeta, EvidenceReference
from .decision import ApprovalTask, DecisionRecorded
from .execution import ExecutionPlanDispatched, WorkPackage
from .ingestion import AttachmentManifest, IngestionNormalised
from .monitoring import MetricSample, MonitoringSignal
from .reasoning import Insight, ReasoningAnalysisProposed
from .retrieval import RetrievalContextBundle, RetrievedPassage

__all__ = [
    "ApprovalTask",
    "AttachmentManifest",
    "BaseEvent",
    "DecisionRecorded",
    "EvidenceReference",
    "EventMeta",
    "ExecutionPlanDispatched",
    "Insight",
    "IngestionNormalised",
    "MetricSample",
    "MonitoringSignal",
    "ReasoningAnalysisProposed",
    "RetrievedPassage",
    "RetrievalContextBundle",
    "WorkPackage",
]
