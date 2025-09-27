"""Tests for Grafana dashboard scaffolding."""

from __future__ import annotations

from monitoring.dashboards import build_default_dashboards


def test_default_dashboards_include_ingestion_panels() -> None:
    dashboards = build_default_dashboards()
    ingestion = next(board for board in dashboards if board.slug == "ingestion")

    titles = [panel["title"] for panel in ingestion.panels]
    assert any("Ingestion" in title for title in titles)

    payload = ingestion.to_json()
    assert payload["uid"].startswith("prom-ingest")
    assert "observability" in payload["tags"]
    assert payload["panels"] == ingestion.panels
