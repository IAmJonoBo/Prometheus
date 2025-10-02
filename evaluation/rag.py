"""RAG evaluation helpers integrating optional third-party toolkits."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

try:  # pragma: no cover - optional import path
    from ragas import evaluate as _ragas_evaluate
    from ragas.metrics import answer_relevancy as _ragas_answer_relevancy
    from ragas.metrics import faithfulness as _ragas_faithfulness

    try:  # ragas <=0.1.16
        from ragas.metrics import context_relevancy as _ragas_context_metric

        _ragas_context_metric_name = "context_relevancy"
    except ImportError:  # pragma: no cover - ragas >=0.1.17 renamed the metric
        from ragas.metrics import context_precision as _ragas_context_metric

        _ragas_context_metric_name = "context_precision"

    _HAS_RAGAS = True
except ModuleNotFoundError:  # pragma: no cover - absence scenario
    _HAS_RAGAS = False

try:  # pragma: no cover - optional import path
    from trulens_eval import Tru as _Tru
    from trulens_eval import TruBasicApp as _TruBasicApp
    from trulens_eval.feedback.provider.openai import OpenAI as _TruOpenAI

    _HAS_TRULENS = True
except ModuleNotFoundError:  # pragma: no cover - absence scenario
    _HAS_TRULENS = False


class RagEvaluationError(RuntimeError):
    """Raised when optional evaluation dependencies are unavailable."""


@dataclass(slots=True)
class RagEvaluationResult:
    """Normalised view of a RAG evaluation run."""

    metrics: Mapping[str, float]
    details: Mapping[str, float] | None = None


def evaluate_with_ragas(records: Iterable[Mapping[str, str]]) -> RagEvaluationResult:
    """Evaluate RAG outputs with Ragas if the dependency is installed."""

    if not _HAS_RAGAS:
        raise RagEvaluationError(
            "ragas is not available. Install extras via 'poetry install --with rag' "
            "to enable RAG evaluation."
        )

    dataset = list(records)
    if not dataset:
        raise ValueError("At least one record is required for RAG evaluation.")

    result = _ragas_evaluate(
        dataset,
        metrics=[
            _ragas_faithfulness,
            _ragas_answer_relevancy,
            _ragas_context_metric,
        ],
    )
    metrics = {k: float(v) for k, v in result.items()}  # ragas returns numpy scalars
    if (
        _ragas_context_metric_name == "context_precision"
        and "context_relevancy" not in metrics
        and "context_precision" in metrics
    ):
        metrics["context_relevancy"] = metrics["context_precision"]
    return RagEvaluationResult(metrics=metrics)


def evaluate_with_trulens(
    records: Iterable[Mapping[str, str]],
    *,
    app_id: str | None = None,
) -> RagEvaluationResult:
    """Evaluate RAG outputs with TruLens if available.

    Parameters
    ----------
    records:
        Iterable of dictionaries with keys: `prompt`, `completion`, `context`.
    app_id:
        Optional TruLens application identifier; if omitted a transient app is used.
    """

    if not _HAS_TRULENS:
        raise RagEvaluationError(
            "trulens-eval is not available. Install extras via 'poetry install --with rag' "
            "to enable TruLens evaluations."
        )

    examples = list(records)
    if not examples:
        raise ValueError("At least one record is required for RAG evaluation.")

    provider = _TruOpenAI()
    app = _TruBasicApp(app_id or "prometheus-rag-app", provider)
    tru = _Tru()
    with tru.start_reversible_session(app):
        for example in examples:
            prompt = example.get("prompt", "")
            completion = example.get("completion", "")
            context = example.get("context", "")
            app.add_record(prompt=prompt, completion=completion, context=context)

    feedback = tru.get_leaderboard(app_ids=[app.app_id])
    metrics = {
        "groundedness": float(feedback.get("groundedness", 0.0)),
        "relevance": float(feedback.get("context_relevance", 0.0)),
    }
    return RagEvaluationResult(metrics=metrics, details=feedback)
