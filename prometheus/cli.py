"""Developer CLI for the Prometheus Strategy OS."""

from __future__ import annotations

import importlib
import importlib.metadata
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated

try:
    typer = importlib.import_module("typer")
except ImportError as exc:  # pragma: no cover - CLI dependency guard
    raise RuntimeError("Typer must be installed to use the Prometheus CLI") from exc

from evaluation import RagEvaluationError, evaluate_with_ragas, evaluate_with_trulens
from execution.service import ExecutionConfig
from execution.workers import (
    TemporalValidationReport,
    TemporalWorkerConfig,
    TemporalWorkerMetrics,
    validate_temporal_worker_plan,
)
from monitoring.dashboards import export_dashboards
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

temporal_app = typer.Typer(help="Temporal worker utilities.")
app.add_typer(temporal_app, name="temporal")

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
def offline_package(ctx) -> None:
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


@app.command(name="evaluate-rag")
def evaluate_rag(
    use_trulens: Annotated[
        bool,
        typer.Option(help="Use TruLens instead of Ragas for evaluation."),
    ] = False,
) -> None:
    """Evaluate retrieval outputs using optional RAG toolkits."""

    sample_records = [
        {
            "prompt": "Summarise the operational risks highlighted in the Q3 incident review.",
            "completion": (
                "The review emphasised third-party downtime and credential leakage as the key risks"
                " that require mitigations."
            ),
            "context": (
                "Incident report: external supplier downtime impacted availability for six hours."
                " Credentials were exposed on staging accounts."
            ),
        }
    ]

    try:
        if use_trulens:
            result = evaluate_with_trulens(sample_records)
        else:
            result = evaluate_with_ragas(sample_records)
    except RagEvaluationError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from None

    typer.secho("Evaluation metrics:", fg=typer.colors.GREEN, bold=True)
    for key, value in result.metrics.items():
        typer.echo(f"  - {key}: {value:.4f}")


ExportDirOption = Annotated[
    Path | None,
    typer.Option(
        "--export-dashboards",
        help="Optional directory for exporting Grafana dashboards as JSON.",
        file_okay=False,
        dir_okay=True,
        writable=True,
        resolve_path=True,
    ),
]


TimeoutOption = Annotated[
    float,
    typer.Option(
        "--timeout",
        min=0.5,
        max=30.0,
        help="Socket timeout, in seconds, used when probing Temporal endpoints.",
    ),
]


@temporal_app.command("validate")
def temporal_validate(
    config: ConfigOption = DEFAULT_PIPELINE_CONFIG,
    timeout: TimeoutOption = 2.0,
    export_dashboards_dir: ExportDirOption = None,
) -> None:
    """Validate Temporal connectivity and export dashboards."""

    report, dashboards = _collect_temporal_validation(config, timeout)
    _render_validation_report(report)
    _export_dashboards_if_requested(dashboards, export_dashboards_dir)
    if not report.is_ready:
        raise typer.Exit(1)


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


def _worker_config_from_execution(config: ExecutionConfig) -> TemporalWorkerConfig:
    adapter_options = config.adapter or {}
    worker_options = config.worker or {}
    metrics_config = worker_options.get("metrics", {})

    if "workflows" in worker_options and worker_options["workflows"]:
        workflows = tuple(worker_options["workflows"])
    else:
        default_workflow = adapter_options.get("workflow", "PrometheusPipeline")
        workflows = (default_workflow,)

    return TemporalWorkerConfig(
        host=str(
            worker_options.get("host", adapter_options.get("host", "localhost:7233"))
        ),
        namespace=str(
            worker_options.get("namespace", adapter_options.get("namespace", "default"))
        ),
        task_queue=str(
            worker_options.get(
                "task_queue", adapter_options.get("task_queue", "prometheus-pipeline")
            )
        ),
        workflows=workflows,
        activities=worker_options.get("activities"),
        metrics=TemporalWorkerMetrics(
            prometheus_port=metrics_config.get("prometheus_port"),
            otlp_endpoint=metrics_config.get("otlp_endpoint"),
            dashboard_links=list(metrics_config.get("dashboards", [])),
        ),
    )


def _collect_temporal_validation(
    config_path: Path, timeout: float
) -> tuple[TemporalValidationReport, list]:
    config_obj = PrometheusConfig.load(config_path)
    orchestrator = build_orchestrator(config_obj)
    worker_config = _worker_config_from_execution(config_obj.execution)
    report = validate_temporal_worker_plan(
        worker_config,
        known_dashboards=orchestrator.dashboards,
        timeout=timeout,
    )
    return report, orchestrator.dashboards


def _render_validation_report(report: TemporalValidationReport) -> None:
    typer.secho(report.plan.describe(), bold=True)
    _render_check_results(report.checks)
    _render_dashboard_results(report.dashboards)


def _render_check_results(checks: Sequence) -> None:
    if not checks:
        return
    for check in checks:
        label = "PASS" if check.status else "FAIL"
        colour = typer.colors.GREEN if check.status else typer.colors.RED
        typer.secho(f"[{label}] {check.label} ({check.target})", fg=colour)
        if check.detail and not check.status:
            typer.echo(f"    detail: {check.detail}")


def _render_dashboard_results(dashboards: dict[str, bool]) -> None:
    if not dashboards:
        return
    typer.secho("Dashboards:", bold=True)
    for link, ok in dashboards.items():
        colour = typer.colors.GREEN if ok else typer.colors.YELLOW
        status = "available" if ok else "missing"
        typer.secho(f"  - {link}: {status}", fg=colour)


def _export_dashboards_if_requested(dashboards: list, export_dir: Path | None) -> None:
    if not export_dir:
        return
    exported = export_dashboards(dashboards, export_dir)
    typer.secho("Exported dashboards:", bold=True)
    for path in exported:
        typer.echo(f"  - {path}")
