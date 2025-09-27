"""CLI entrypoint for the Prometheus bootstrap pipeline."""

from __future__ import annotations

import argparse
from pathlib import Path

from .config import PrometheusConfig
from .pipeline import build_orchestrator


def main(argv: list[str] | None = None) -> int:
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
    args = parser.parse_args(argv)

    config = PrometheusConfig.load(Path(args.config))
    orchestrator = build_orchestrator(config)
    result = orchestrator.run(args.query)

    print(f"Decision status: {result.decision.status}")
    print(f"Execution notes: {result.execution.notes}")
    print(f"Monitoring signal: {result.monitoring.description}")
    return 0


if __name__ == "__main__":  # pragma: no cover - manual entrypoint
    raise SystemExit(main())

