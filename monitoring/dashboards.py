"""Grafana dashboard scaffolding for Prometheus observability."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "GrafanaDashboard",
    "build_default_dashboards",
    "export_dashboards",
]


@dataclass(slots=True)
class GrafanaDashboard:
    """Minimal Grafana dashboard description."""

    title: str
    uid: str
    slug: str
    panels: list[dict[str, Any]]
    tags: list[str] = field(default_factory=lambda: ["prometheus-os", "observability"])
    description: str = ""

    def to_json(self) -> dict[str, Any]:
        """Render the dashboard as a Grafana import payload."""

        return {
            "title": self.title,
            "uid": self.uid,
            "slug": self.slug,
            "tags": list(self.tags),
            "timezone": "browser",
            "panels": list(self.panels),
            "description": self.description,
        }


def _stat_panel(title: str, query: str, *, grid_pos: dict[str, int]) -> dict[str, Any]:
    """Return a compact stat panel definition."""

    return {
        "type": "stat",
        "title": title,
        "gridPos": grid_pos,
        "targets": [
            {
                "expr": query,
                "legendFormat": "value",
                "refId": "A",
            }
        ],
        "options": {
            "reduceOptions": {"calcs": ["last"], "fields": ""},
            "orientation": "horizontal",
        },
    }


def _table_panel(title: str, query: str, *, grid_pos: dict[str, int]) -> dict[str, Any]:
    """Return a table panel definition."""

    return {
        "type": "table",
        "title": title,
        "gridPos": grid_pos,
        "targets": [
            {
                "expr": query,
                "format": "table",
                "refId": "A",
            }
        ],
    }


def _build_ingestion_dashboard() -> GrafanaDashboard:
    panels = [
        _stat_panel(
            "Ingestion Throughput",
            "sum(rate(ingestion_scheduler_runs_total[5m]))",
            grid_pos={"h": 8, "w": 12, "x": 0, "y": 0},
        ),
        _stat_panel(
            "PII Redactions",
            "sum(infractions:ingestion_redactions_total)",
            grid_pos={"h": 8, "w": 12, "x": 12, "y": 0},
        ),
        _table_panel(
            "Connector Latency",
            "avg by (connector)(ingestion_connector_latency_seconds)",
            grid_pos={"h": 9, "w": 24, "x": 0, "y": 8},
        ),
    ]
    return GrafanaDashboard(
        title="Prometheus Ingestion Overview",
        uid="prom-ingest-001",
        slug="ingestion",
        panels=panels,
        description="Operational metrics for ingestion scheduling and redaction.",
    )


def _build_pipeline_dashboard() -> GrafanaDashboard:
    panels = [
        _stat_panel(
            "Retrieval Success Rate",
            "avg(prometheus_retrieval_success_ratio)",
            grid_pos={"h": 8, "w": 12, "x": 0, "y": 0},
        ),
        _stat_panel(
            "Decision Approvals",
            "sum(rate(decision_approved_total[1h]))",
            grid_pos={"h": 8, "w": 12, "x": 12, "y": 0},
        ),
        _table_panel(
            "Run Diagnostics",
            "last_over_time(prometheus_pipeline_incidents[6h])",
            grid_pos={"h": 9, "w": 24, "x": 0, "y": 8},
        ),
    ]
    return GrafanaDashboard(
        title="Prometheus Pipeline Overview",
        uid="prom-pipeline-001",
        slug="pipeline",
        panels=panels,
        description="End-to-end pipeline health across retrieval, decision, and incidents.",
    )


def _build_dependency_sync_dashboard() -> GrafanaDashboard:
    """Build dashboard for dependency auto-sync and guard metrics."""
    
    panels = [
        _stat_panel(
            "Auto-Sync Success Rate",
            "rate(dependency_auto_sync_success_total[24h]) / rate(dependency_auto_sync_runs_total[24h])",
            grid_pos={"h": 8, "w": 8, "x": 0, "y": 0},
        ),
        _stat_panel(
            "Guard Violations",
            "sum(dependency_guard_violations_total)",
            grid_pos={"h": 8, "w": 8, "x": 8, "y": 0},
        ),
        _stat_panel(
            "Rollback Events",
            "sum(rate(dependency_auto_sync_rollback_total[24h]))",
            grid_pos={"h": 8, "w": 8, "x": 16, "y": 0},
        ),
        _table_panel(
            "Auto-Sync Timing",
            "histogram_quantile(0.95, rate(dependency_auto_sync_duration_seconds_bucket[5m]))",
            grid_pos={"h": 9, "w": 12, "x": 0, "y": 8},
        ),
        _table_panel(
            "Update Trends",
            "dependency_updates_available by (package)",
            grid_pos={"h": 9, "w": 12, "x": 12, "y": 8},
        ),
        _stat_panel(
            "Preflight Failures",
            "sum(dependency_preflight_failures_total)",
            grid_pos={"h": 8, "w": 8, "x": 0, "y": 17},
        ),
        _stat_panel(
            "Mirror Health",
            "dependency_mirror_signature_valid_ratio",
            grid_pos={"h": 8, "w": 8, "x": 8, "y": 17},
        ),
        _stat_panel(
            "Model Registry Checks",
            "sum(model_registry_signature_checks_total)",
            grid_pos={"h": 8, "w": 8, "x": 16, "y": 17},
        ),
    ]
    return GrafanaDashboard(
        title="Prometheus Dependency Management",
        uid="prom-deps-001",
        slug="dependency-management",
        panels=panels,
        tags=["prometheus-os", "observability", "dependencies", "auto-sync"],
        description="Dependency auto-sync metrics, guard violations, and update trends.",
    )


def build_default_dashboards(
    extras: Iterable[GrafanaDashboard] | None = None,
) -> list[GrafanaDashboard]:
    """Return default Grafana dashboards for the Strategy OS."""

    dashboards: list[GrafanaDashboard] = [
        _build_ingestion_dashboard(),
        _build_pipeline_dashboard(),
        _build_dependency_sync_dashboard(),
    ]
    if extras:
        dashboards.extend(extras)
    return dashboards


def export_dashboards(
    dashboards: Iterable[GrafanaDashboard],
    destination: Path,
) -> list[Path]:
    """Write dashboards to JSON files and return the exported paths."""

    destination.mkdir(parents=True, exist_ok=True)
    exported: list[Path] = []
    for dashboard in dashboards:
        payload = dashboard.to_json()
        path = destination / f"{dashboard.slug}.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        exported.append(path)
    return exported
