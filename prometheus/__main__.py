"""CLI entrypoint for the Prometheus bootstrap pipeline."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from .config import PrometheusConfig
from .pipeline import build_orchestrator


def _run_pipeline(args: argparse.Namespace) -> int:
    config = PrometheusConfig.load(Path(args.config))
    orchestrator = build_orchestrator(config)
    result = orchestrator.run(args.query)

    print(f"Decision status: {result.decision.status}")
    print(f"Execution notes: {result.execution.notes}")
    print(f"Monitoring signal: {result.monitoring.description}")
    return 0


def _parse_pipeline_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default="configs/defaults/pipeline.toml",
        help="Path to the pipeline configuration file.",
    )
    parser.add_argument(
        "--query",
        default="Summarise configured sources",
        help="Query to send through the pipeline.",
    )
    return parser.parse_args(list(argv))


def main(argv: list[str] | None = None) -> int:
    args = list(argv) if argv is not None else sys.argv[1:]

    if args and args[0] == "offline-package":
        from scripts import offline_package

        return offline_package.main(args[1:])

    if args and args[0] == "pipeline":
        args = args[1:]

    parsed = _parse_pipeline_args(args)
    return _run_pipeline(parsed)


if __name__ == "__main__":  # pragma: no cover - manual entrypoint
    raise SystemExit(main())

