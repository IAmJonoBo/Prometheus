"""Retrieval regression and evaluation harnesses."""

from __future__ import annotations

import tomllib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, runtime_checkable
from uuid import uuid4

from common.contracts import EventMeta, IngestionNormalised, RetrievedPassage


@dataclass(slots=True)
class RegressionSample:
    """Represents a single retrieval regression sample."""

    query: str
    relevant_uris: frozenset[str]

    def __post_init__(self) -> None:
        if not isinstance(self.relevant_uris, frozenset):
            object.__setattr__(self, "relevant_uris", frozenset(self.relevant_uris))


@dataclass(slots=True)
class RegressionMetrics:
    """Aggregate metrics for regression evaluations."""

    recall_at_k: float
    mean_reciprocal_rank: float
    hits: int
    total: int


@dataclass(slots=True)
class RegressionThresholds:
    """Threshold expectations for regression metrics."""

    min_hits: int | None = None
    min_recall_at_k: float | None = None
    min_mean_reciprocal_rank: float | None = None


@dataclass(slots=True)
class RegressionSuite:
    """Collection of documents, samples, and thresholds for regression."""

    documents: list[IngestionNormalised]
    samples: list[RegressionSample]
    thresholds: RegressionThresholds
    top_k: int


@dataclass(slots=True)
class RegressionSampleEvaluation:
    """Detailed evaluation results for a regression sample."""

    query: str
    relevant_uris: frozenset[str]
    retrieved_uris: tuple[str, ...]
    matching_uris: frozenset[str]
    recall_at_k: float
    reciprocal_rank: float

    @property
    def hit(self) -> bool:
        """Return ``True`` when at least one relevant URI was retrieved."""

        return bool(self.matching_uris)


@dataclass(slots=True)
class RegressionReport:
    """Full evaluation report including aggregate and per-sample metrics."""

    metrics: RegressionMetrics
    samples: list[RegressionSampleEvaluation]


@dataclass(slots=True)
class RegressionSuiteConfig:
    """Configuration describing a regression suite to execute."""

    dataset_path: Path
    top_k: int | None = None


class RegressionThresholdError(RuntimeError):
    """Raised when regression metrics fail to satisfy thresholds."""

    def __init__(
        self,
        message: str,
        *,
        metrics: RegressionMetrics,
        thresholds: RegressionThresholds,
        report: RegressionReport | None = None,
    ) -> None:
        super().__init__(message)
        self.metrics = metrics
        self.thresholds = thresholds
        self.report = report


@runtime_checkable
class _SupportsIngest(Protocol):
    def ingest(self, documents: Iterable[IngestionNormalised]) -> None: ...


class RetrievalRegressionHarness:
    """Runs regression suites against a retriever implementation."""

    def __init__(self, retriever, *, k: int = 5) -> None:
        self._retriever = retriever
        self._k = k

    def evaluate(self, samples: Sequence[RegressionSample]) -> RegressionReport:
        """Execute regression evaluation and return detailed results."""

        if not samples:
            raise ValueError("At least one regression sample is required")

        total = len(samples)
        hits = 0
        recall_sum = 0.0
        reciprocal_rank_sum = 0.0
        sample_results: list[RegressionSampleEvaluation] = []

        for sample in samples:
            retrieved = list(self._retriever.retrieve(sample.query))
            top_k = retrieved[: self._k]
            matching = _matching_uris(top_k, sample.relevant_uris)
            recall_at_k = _recall_at_k(top_k, sample.relevant_uris)
            reciprocal_rank = _reciprocal_rank(top_k, sample.relevant_uris)
            hits += 1 if matching else 0
            recall_sum += recall_at_k
            reciprocal_rank_sum += reciprocal_rank
            sample_results.append(
                RegressionSampleEvaluation(
                    query=sample.query,
                    relevant_uris=sample.relevant_uris,
                    retrieved_uris=_retrieved_uri_tuple(top_k),
                    matching_uris=frozenset(matching),
                    recall_at_k=recall_at_k,
                    reciprocal_rank=reciprocal_rank,
                )
            )

        recall_at_k = recall_sum / total
        mean_reciprocal_rank = reciprocal_rank_sum / total
        metrics = RegressionMetrics(
            recall_at_k=recall_at_k,
            mean_reciprocal_rank=mean_reciprocal_rank,
            hits=hits,
            total=total,
        )
        return RegressionReport(metrics=metrics, samples=sample_results)


def load_regression_suite(path: Path) -> RegressionSuite:
    """Load a regression suite definition from a TOML document."""

    with path.open("rb") as handle:
        payload = tomllib.load(handle)

    documents = [_build_document(entry) for entry in payload.get("documents", [])]
    if not documents:
        raise ValueError("Regression dataset must define at least one document")

    samples = [_build_sample(entry) for entry in payload.get("samples", [])]
    if not samples:
        raise ValueError("Regression dataset must define at least one sample")

    thresholds_raw = payload.get("thresholds", {})
    thresholds = RegressionThresholds(
        min_hits=thresholds_raw.get("min_hits"),
        min_recall_at_k=thresholds_raw.get("min_recall_at_k"),
        min_mean_reciprocal_rank=thresholds_raw.get("min_mean_reciprocal_rank"),
    )
    top_k = int(payload.get("top_k", 5))
    return RegressionSuite(
        documents=documents,
        samples=samples,
        thresholds=thresholds,
        top_k=top_k,
    )


def run_regression_suite(config: RegressionSuiteConfig, retriever) -> RegressionReport:
    """Execute the configured regression suite and enforce thresholds."""

    suite = load_regression_suite(config.dataset_path)
    if isinstance(retriever, _SupportsIngest):
        retriever.ingest(suite.documents)
    k = config.top_k or suite.top_k
    report = RetrievalRegressionHarness(retriever, k=k).evaluate(suite.samples)
    _verify_thresholds(report, suite.thresholds)
    return report


def _matching_uris(
    passages: Iterable[RetrievedPassage],
    expected: frozenset[str],
) -> set[str]:
    expected_set = set(expected)
    return {
        passage.metadata.get("uri", "")
        for passage in passages
        if passage.metadata.get("uri") in expected_set
    }


def _recall_at_k(
    passages: Sequence[RetrievedPassage], expected: frozenset[str]
) -> float:
    expected_set = set(expected)
    if not expected_set:
        return 1.0
    found = sum(
        1 for passage in passages if passage.metadata.get("uri") in expected_set
    )
    return found / len(expected_set)


def _reciprocal_rank(
    passages: Sequence[RetrievedPassage], expected: frozenset[str]
) -> float:
    expected_set = set(expected)
    if not expected_set:
        return 1.0
    for index, passage in enumerate(passages, start=1):
        if passage.metadata.get("uri") in expected_set:
            return 1.0 / float(index)
    return 0.0


def _verify_thresholds(
    report: RegressionReport, thresholds: RegressionThresholds
) -> None:
    metrics = report.metrics
    failures: list[str] = []
    if thresholds.min_hits is not None and metrics.hits < thresholds.min_hits:
        failures.append(f"hits {metrics.hits} < required {thresholds.min_hits}")
    if (
        thresholds.min_recall_at_k is not None
        and metrics.recall_at_k < thresholds.min_recall_at_k
    ):
        failures.append(
            f"recall@k {metrics.recall_at_k:.3f} < "
            f"required {thresholds.min_recall_at_k:.3f}"
        )
    if (
        thresholds.min_mean_reciprocal_rank is not None
        and metrics.mean_reciprocal_rank < thresholds.min_mean_reciprocal_rank
    ):
        failures.append(
            f"MRR {metrics.mean_reciprocal_rank:.3f} < "
            f"required {thresholds.min_mean_reciprocal_rank:.3f}"
        )
    if failures:
        raise RegressionThresholdError(
            "; ".join(failures),
            metrics=metrics,
            thresholds=thresholds,
            report=report,
        )


def _retrieved_uri_tuple(passages: Sequence[RetrievedPassage]) -> tuple[str, ...]:
    return tuple(str(passage.metadata.get("uri", "")) for passage in passages)


def _build_document(entry: dict[str, object]) -> IngestionNormalised:
    try:
        uri = str(entry["uri"])
    except KeyError as exc:  # pragma: no cover - defensive guard
        raise ValueError("Regression document missing 'uri'") from exc
    source = str(entry.get("source_system", "regression"))
    content = str(entry.get("content", ""))
    provenance_raw = entry.get("provenance", {})
    provenance: dict[str, str]
    if isinstance(provenance_raw, dict):
        provenance = {str(key): str(value) for key, value in provenance_raw.items()}
    else:
        provenance = {}
    provenance.setdefault("content", content)
    provenance.setdefault("description", content)
    event_id = str(entry.get("event_id", f"regression-{uuid4()}"))
    correlation_id = str(entry.get("correlation_id", "retrieval-regression"))
    meta = EventMeta(
        event_id=event_id,
        correlation_id=correlation_id,
        occurred_at=datetime.now(UTC),
    )
    return IngestionNormalised(
        meta=meta,
        source_system=source,
        canonical_uri=uri,
        provenance=provenance,
    )


def _build_sample(entry: dict[str, object]) -> RegressionSample:
    try:
        query = str(entry["query"])
    except KeyError as exc:  # pragma: no cover - defensive guard
        raise ValueError("Regression sample missing 'query'") from exc
    raw_relevant = entry.get("relevant_uris", [])
    if isinstance(raw_relevant, str):  # pragma: no cover - defensive guard
        raise ValueError("relevant_uris must be a sequence of URIs")
    if not isinstance(raw_relevant, Iterable):
        raise ValueError("relevant_uris must be iterable")
    relevant = frozenset(str(uri) for uri in raw_relevant)
    return RegressionSample(query=query, relevant_uris=relevant)
