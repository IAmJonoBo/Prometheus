"""Command-line entry point for the retrieval regression harness."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from retrieval.evaluation import (
    RegressionReport,
    RegressionSampleEvaluation,
    RegressionSuiteConfig,
    RegressionThresholdError,
    run_regression_suite,
)
from retrieval.service import InMemoryRetriever


def _build_retriever(kind: str):
    if kind == "in-memory":
        return InMemoryRetriever()
    msg = f"Unsupported retriever kind: {kind}"
    raise argparse.ArgumentTypeError(msg)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the retrieval regression harness against a dataset."
    )
    parser.add_argument(
        "dataset",
        type=Path,
        help="Path to the regression dataset TOML file.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=None,
        help="Override the top-k depth configured in the dataset.",
    )
    parser.add_argument(
        "--backend",
        choices=["in-memory"],
        default="in-memory",
        help="Retriever backend to evaluate.",
    )
    args = parser.parse_args(argv)

    retriever = _build_retriever(args.backend)
    config = RegressionSuiteConfig(dataset_path=args.dataset, top_k=args.top_k)
    try:
        report = run_regression_suite(config, retriever)
    except RegressionThresholdError as exc:
        payload: dict[str, Any] = {
            "metrics": _metrics_payload(exc.metrics),
            "thresholds": {
                "min_hits": exc.thresholds.min_hits,
                "min_recall_at_k": exc.thresholds.min_recall_at_k,
                "min_mean_reciprocal_rank": exc.thresholds.min_mean_reciprocal_rank,
            },
            "status": "failed",
            "reason": str(exc),
        }
        if exc.report is not None:
            payload["samples"] = _sample_payloads(exc.report)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 1

    result = {
        "metrics": _metrics_payload(report.metrics),
        "samples": _sample_payloads(report),
        "status": "passed",
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _metrics_payload(metrics) -> dict[str, float | int]:  # type: ignore[no-untyped-def]
    return {
        "recall_at_k": metrics.recall_at_k,
        "mean_reciprocal_rank": metrics.mean_reciprocal_rank,
        "hits": metrics.hits,
        "total": metrics.total,
    }


def _sample_payloads(report: RegressionReport) -> list[dict[str, Any]]:
    def _to_payload(sample: RegressionSampleEvaluation) -> dict[str, Any]:
        return {
            "query": sample.query,
            "relevant_uris": sorted(sample.relevant_uris),
            "retrieved_uris": list(sample.retrieved_uris),
            "matching_uris": sorted(sample.matching_uris),
            "recall_at_k": sample.recall_at_k,
            "reciprocal_rank": sample.reciprocal_rank,
            "hit": sample.hit,
        }

    return [_to_payload(sample) for sample in report.samples]


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
