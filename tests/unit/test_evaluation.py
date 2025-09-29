"""Tests for evaluation helper functions."""

from __future__ import annotations

import pytest

from evaluation import RagEvaluationError
from evaluation import rag as rag_module


def test_evaluate_with_ragas_missing_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """evaluate_with_ragas raises helpful error when ragas is absent."""

    monkeypatch.setattr(rag_module, "_HAS_RAGAS", False)

    with pytest.raises(RagEvaluationError):
        rag_module.evaluate_with_ragas(
            [{"prompt": "p", "completion": "c", "context": "ctx"}]
        )


def test_evaluate_with_trulens_missing_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """evaluate_with_trulens raises helpful error when trulens-eval is absent."""

    monkeypatch.setattr(rag_module, "_HAS_TRULENS", False)

    with pytest.raises(RagEvaluationError):
        rag_module.evaluate_with_trulens(
            [{"prompt": "p", "completion": "c", "context": "ctx"}]
        )
