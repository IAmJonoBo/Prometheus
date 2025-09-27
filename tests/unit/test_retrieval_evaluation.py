"""Tests for the retrieval evaluation harness."""

from __future__ import annotations

from common.contracts import RetrievedPassage
from retrieval.evaluation import RegressionSample, RetrievalRegressionHarness


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

    metrics = harness.evaluate(samples)

    assert metrics.total == 2
    assert metrics.hits == 1
    assert 0.0 <= metrics.recall_at_k <= 1.0
    assert 0.0 <= metrics.mean_reciprocal_rank <= 1.0


def test_regression_harness_requires_samples() -> None:
    harness = RetrievalRegressionHarness(_StubRetriever(), k=2)

    try:
        harness.evaluate([])
    except ValueError as exc:
        assert "sample" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected ValueError for empty regression set")
