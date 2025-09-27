"""Tests for the retrieval evaluation harness."""

from __future__ import annotations

from pathlib import Path

import pytest

from common.contracts import RetrievedPassage
from retrieval.evaluation import (
    RegressionSample,
    RegressionSuiteConfig,
    RegressionThresholdError,
    RetrievalRegressionHarness,
    load_regression_suite,
    run_regression_suite,
)
from retrieval.service import InMemoryRetriever


class _StubRetriever:
    def __init__(self) -> None:
        self._responses = {
            "alpha": [
                RetrievedPassage(
                    source_id="lexical",
                    snippet="alpha document",
                    score=0.9,
                    metadata={"uri": "doc-1"},
                ),
                RetrievedPassage(
                    source_id="vector",
                    snippet="beta doc",
                    score=0.5,
                    metadata={"uri": "doc-2"},
                ),
            ],
            "beta": [
                RetrievedPassage(
                    source_id="lexical",
                    snippet="beta doc",
                    score=0.7,
                    metadata={"uri": "doc-2"},
                )
            ],
        }

    def retrieve(self, query: str):  # type: ignore[no-untyped-def]
        return self._responses.get(query, [])


def test_retrieval_regression_harness_reports_metrics() -> None:
    harness = RetrievalRegressionHarness(_StubRetriever(), k=2)
    samples = [
        RegressionSample(query="alpha", relevant_uris=frozenset({"doc-1"})),
        RegressionSample(query="beta", relevant_uris=frozenset({"doc-3"})),
    ]

    report = harness.evaluate(samples)

    assert report.metrics.total == 2
    assert report.metrics.hits == 1
    assert 0.0 <= report.metrics.recall_at_k <= 1.0
    assert 0.0 <= report.metrics.mean_reciprocal_rank <= 1.0
    assert len(report.samples) == 2
    assert report.samples[0].hit is True
    assert report.samples[1].hit is False
    assert report.samples[0].matching_uris == frozenset({"doc-1"})


def test_regression_harness_requires_samples() -> None:
    harness = RetrievalRegressionHarness(_StubRetriever(), k=2)

    try:
        harness.evaluate([])
    except ValueError as exc:
        assert "sample" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected ValueError for empty regression set")


def _write_dataset(tmp_path, *, min_hits: int = 1, top_k: int = 2) -> str:
    content = f"""
top_k = {top_k}

[thresholds]
min_hits = {min_hits}
min_recall_at_k = 0.5
min_mean_reciprocal_rank = 0.25

[[documents]]
uri = "doc-1"
source_system = "seed"
content = "alpha passage"

[[samples]]
query = "alpha"
relevant_uris = ["doc-1"]
"""
    dataset = tmp_path / "regression.toml"
    dataset.write_text(content, encoding="utf-8")
    return str(dataset)


def test_load_regression_suite_from_toml(tmp_path) -> None:
    dataset_path = _write_dataset(tmp_path)

    suite = load_regression_suite(Path(dataset_path))

    assert suite.top_k == 2
    assert suite.documents[0].canonical_uri == "doc-1"
    assert suite.samples[0].relevant_uris == frozenset({"doc-1"})
    assert suite.thresholds.min_hits == 1
    assert suite.thresholds.min_recall_at_k == 0.5


def test_run_regression_suite_meets_thresholds(tmp_path) -> None:
    dataset_path = Path(_write_dataset(tmp_path, min_hits=1, top_k=1))
    retriever = InMemoryRetriever()

    report = run_regression_suite(
        RegressionSuiteConfig(dataset_path=dataset_path), retriever
    )

    assert report.metrics.hits == 1
    assert report.metrics.total == 1
    assert report.samples[0].hit is True


def test_run_regression_suite_raises_on_threshold_failure(tmp_path) -> None:
    dataset_path = Path(_write_dataset(tmp_path, min_hits=2))
    retriever = InMemoryRetriever()

    config = RegressionSuiteConfig(dataset_path=Path(dataset_path))

    with pytest.raises(RegressionThresholdError) as excinfo:
        run_regression_suite(config, retriever)

    error = excinfo.value
    assert error.report is not None
    assert error.report.metrics.hits == 1
    assert error.report.samples[0].hit is True
