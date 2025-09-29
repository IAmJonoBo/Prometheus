"""Developer CLI for the Prometheus Strategy OS."""

from __future__ import annotations

import importlib.metadata
import os
from pathlib import Path
from typing import Annotated

import typer

from observability import configure_logging, configure_metrics, configure_tracing

from .config import PrometheusConfig
from .pipeline import PipelineResult, build_orchestrator

app = typer.Typer(
    add_completion=False,
    help=(
        "Utility commands for running the Prometheus pipeline and"
        " supporting developer workflows."
    ),
)

DEFAULT_PIPELINE_CONFIG = Path("configs/defaults/pipeline.toml")


def _package_version() -> str:
    try:
        return importlib.metadata.version("prometheus-os")
    except (
        importlib.metadata.PackageNotFoundError
    ):  # pragma: no cover - editable installs
        return "0.0.0"


def _bootstrap_observability() -> None:
    service = os.getenv("PROMETHEUS_SERVICE_NAME", "prometheus-pipeline")
    configure_logging(service_name=service)
    configure_tracing(service)
    metrics_host = os.getenv("PROMETHEUS_METRICS_HOST")
    metrics_port = _read_int(os.getenv("PROMETHEUS_METRICS_PORT"))
    configure_metrics(
        namespace=service,
        host=metrics_host,
        port=metrics_port,
        extra_labels={"version": _package_version()},
    )


def _read_int(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _run_pipeline(config_path: Path, query: str, actor: str | None) -> PipelineResult:
    _bootstrap_observability()
    config = PrometheusConfig.load(config_path)
    orchestrator = build_orchestrator(config)
    return orchestrator.run(query, actor=actor)


def _summarise_pipeline(result: PipelineResult) -> None:
    typer.secho("Pipeline execution complete", fg=typer.colors.GREEN, bold=True)
    typer.echo(f"Ingested payloads: {len(result.ingestion):d}")
    typer.echo(f"Retrieval strategy: {result.retrieval.strategy!r}")
    typer.echo(f"Reasoning planner: {result.reasoning.metadata.get('planner', 'n/a')}")
    typer.echo(
        "Decision status: "
        f"{result.decision.status} (type={result.decision.decision_type})"
    )
    note_lines = result.execution.notes or ["No execution notes recorded"]
    typer.echo("Execution notes:")
    for line in note_lines:
        typer.echo(f"  - {line}")
    typer.echo(f"Monitoring signal: {result.monitoring.description}")


QueryArgument = Annotated[
    str,
    typer.Argument(
        help="Query to submit through the pipeline.",
    ),
]

ConfigOption = Annotated[
    Path,
    typer.Option(  # noqa: B008 - Typer option declaration
        "--config",
        "-c",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="Path to a pipeline configuration file.",
    ),
]

ActorOption = Annotated[
    str | None,
    typer.Option(  # noqa: B008 - Typer option declaration
        "--actor",
        help="Actor identifier used when emitting pipeline events.",
    ),
]


@app.command()
def pipeline(
    query: QueryArgument = "Summarise configured sources",
    config: ConfigOption = DEFAULT_PIPELINE_CONFIG,
    actor: ActorOption = None,
) -> None:
    """Run the full pipeline with the supplied configuration."""

    result = _run_pipeline(config, query, actor)
    _summarise_pipeline(result)


@app.command(
    name="offline-package",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def offline_package(ctx: typer.Context) -> None:
    """Proxy command for the offline packaging orchestrator."""

    from scripts import offline_package as offline_cli

    argv = list(ctx.args)
    exit_code = offline_cli.main(argv or None)
    if exit_code != 0:
        raise typer.Exit(exit_code)


@app.command()
def plugins(
    config: ConfigOption = DEFAULT_PIPELINE_CONFIG,
) -> None:
    """List pipeline plugins registered during bootstrap."""

    config_obj = PrometheusConfig.load(config)
    orchestrator = build_orchestrator(config_obj)
    names = sorted(orchestrator.registry.names())
    if not names:
        typer.echo("No plugins registered.")
        return
    typer.secho("Registered plugins:", bold=True)
    for name in names:
        typer.echo(f"  - {name}")


def main(argv: list[str] | None = None) -> int:
    command = typer.main.get_command(app)
    args = None if argv is None else list(argv)
    try:
        result = command.main(
            args=args,
            prog_name="prometheus",
            standalone_mode=False,
        )
    except typer.Exit as exc:  # pragma: no cover - Click controls exit
        return int(exc.exit_code)
    if isinstance(result, int):
        return result
    return 0


__all__ = ["app", "main", "pipeline", "offline_package", "plugins"]
