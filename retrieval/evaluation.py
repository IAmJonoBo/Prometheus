"""Retrieval regression and evaluation harnesses."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from common.contracts import RetrievedPassage


@dataclass(slots=True)
class RegressionSample:
    """Represents a single retrieval regression sample."""

    query: str
    relevant_uris: Iterable[str]

    def __post_init__(self) -> None:
        if not isinstance(self.relevant_uris, frozenset):
            self.relevant_uris = frozenset(self.relevant_uris)


@dataclass(slots=True)
class RegressionMetrics:
    """Aggregate metrics for regression evaluations."""

    recall_at_k: float
    mean_reciprocal_rank: float
    hits: int
    total: int


class RetrievalRegressionHarness:
    """Runs regression suites against a retriever implementation."""

    def __init__(self, retriever, *, k: int = 5) -> None:
        self._retriever = retriever
        self._k = k

    def evaluate(self, samples: Sequence[RegressionSample]) -> RegressionMetrics:
        """Execute regression evaluation and return aggregate metrics."""

        if not samples:
            raise ValueError("At least one regression sample is required")

        total = len(samples)
        hits = 0
        recall_sum = 0.0
        reciprocal_rank_sum = 0.0

        for sample in samples:
            retrieved = list(self._retriever.retrieve(sample.query))
            top_k = retrieved[: self._k]
            relevant_hits = _matching_uris(top_k, sample.relevant_uris)
            hits += 1 if relevant_hits else 0
            recall_sum += _recall_at_k(top_k, sample.relevant_uris)
            reciprocal_rank_sum += _reciprocal_rank(top_k, sample.relevant_uris)

        recall_at_k = recall_sum / total
        mean_reciprocal_rank = reciprocal_rank_sum / total
        return RegressionMetrics(
            recall_at_k=recall_at_k,
            mean_reciprocal_rank=mean_reciprocal_rank,
            hits=hits,
            total=total,
        )


def _matching_uris(
    passages: Iterable[RetrievedPassage],
    expected: Iterable[str],
) -> set[str]:
    expected_set = {uri for uri in expected}
    return {passage.metadata.get("uri", "") for passage in passages if passage.metadata.get("uri") in expected_set}


def _recall_at_k(passages: Sequence[RetrievedPassage], expected: Iterable[str]) -> float:
    expected_set = {uri for uri in expected}
    if not expected_set:
        return 1.0
    found = sum(1 for passage in passages if passage.metadata.get("uri") in expected_set)
    return found / len(expected_set)


def _reciprocal_rank(passages: Sequence[RetrievedPassage], expected: Iterable[str]) -> float:
    expected_set = {uri for uri in expected}
    if not expected_set:
        return 1.0
    for index, passage in enumerate(passages, start=1):
        if passage.metadata.get("uri") in expected_set:
            return 1.0 / float(index)
    return 0.0

