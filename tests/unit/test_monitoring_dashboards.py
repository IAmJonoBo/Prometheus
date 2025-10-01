"""Tests for Grafana dashboard scaffolding."""

from __future__ import annotations

import json

from monitoring.dashboards import build_default_dashboards, export_dashboards


def test_default_dashboards_include_ingestion_panels() -> None:
    dashboards = build_default_dashboards()
    ingestion = next(board for board in dashboards if board.slug == "ingestion")

    titles = [panel["title"] for panel in ingestion.panels]
    assert any("Ingestion" in title for title in titles)

    payload = ingestion.to_json()
    assert payload["uid"].startswith("prom-ingest")
    assert "observability" in payload["tags"]
    assert payload["panels"] == ingestion.panels


def test_export_dashboards_writes_json(tmp_path) -> None:
    dashboards = build_default_dashboards()

    exported = export_dashboards(dashboards, tmp_path)

    slugs = sorted(board.slug for board in dashboards)
    exported_slugs = sorted(path.stem for path in exported)
    assert exported_slugs == slugs

    sample_path = exported[0]
    payload = json.loads(sample_path.read_text(encoding="utf-8"))
    assert payload["slug"] == sample_path.stem
