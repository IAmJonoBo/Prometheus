"""Developer CLI for the Prometheus Strategy OS."""

from __future__ import annotations

import importlib
import json
import os
from collections.abc import Sequence
from datetime import datetime
from importlib import metadata
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
from .debugging import (
    iter_stage_outputs,
    list_runs,
    load_tracebacks,
    select_run,
)
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

debug_app = typer.Typer(help="Developer debugging helpers.")
dry_run_debug_app = typer.Typer(help="Inspect recorded dry-run artefacts.")
debug_app.add_typer(dry_run_debug_app, name="dry-run")
app.add_typer(debug_app, name="debug")

DEFAULT_PIPELINE_CONFIG = Path("configs/defaults/pipeline.toml")
DEFAULT_DRYRUN_CONFIG = Path("configs/defaults/pipeline_dryrun.toml")

WARNINGS_HEADER = "Warnings:"
WARNINGS_NONE = "Warnings: none"
TRACEBACKS_HEADER = "Tracebacks:"


def _package_version() -> str:
    try:
        return metadata.version("prometheus-os")
    except metadata.PackageNotFoundError:  # pragma: no cover - editable installs
        return "0.0.0"


def _bootstrap_observability(mode: str | None = None) -> None:
    service = os.getenv("PROMETHEUS_SERVICE_NAME", "prometheus-pipeline")
    runtime_mode = mode or os.getenv("PROMETHEUS_RUN_MODE", "production")
    os.environ["PROMETHEUS_RUN_MODE"] = runtime_mode
    configure_logging(service_name=service)
    configure_tracing(service, resource_attributes={"run.mode": runtime_mode})
    metrics_host = os.getenv("PROMETHEUS_METRICS_HOST")
    metrics_port = _read_int(os.getenv("PROMETHEUS_METRICS_PORT"))
    configure_metrics(
        namespace=service,
        host=metrics_host,
        port=metrics_port,
        extra_labels={
            "version": _package_version(),
            "mode": runtime_mode,
        },
    )


def _read_int(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _run_pipeline(config_path: Path, query: str, actor: str | None) -> PipelineResult:
    config = PrometheusConfig.load(config_path)
    _bootstrap_observability(config.runtime.mode)
    orchestrator = build_orchestrator(config)
    return orchestrator.run(query, actor=actor)


def _run_pipeline_dry(config_path: Path, query: str, actor: str | None):
    config = PrometheusConfig.load(config_path)
    _bootstrap_observability(config.runtime.mode)
    orchestrator = build_orchestrator(config)
    if config.runtime.mode != "dry-run":
        typer.secho(
            "Configuration runtime mode is not 'dry-run'; executing with provided settings.",
            fg=typer.colors.YELLOW,
        )
    if not config.runtime.feature_flags.get("dry_run_enabled", True):
        typer.secho(
            "Dry-run feature flag disabled in configuration",
            fg=typer.colors.RED,
            bold=True,
        )
        raise typer.Exit(code=1)
    return orchestrator.run_dry_run(query, actor=actor)


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


def _summarise_dry_run(execution) -> None:
    outcome = execution.outcome
    typer.secho("Dry-run artefacts", fg=typer.colors.BLUE, bold=True)
    typer.echo(f"Run ID: {outcome.run_id}")
    typer.echo(f"Artifacts stored at: {outcome.root}")
    typer.echo(f"Manifest: {outcome.manifest_path}")
    typer.echo(f"Events: {outcome.events_path}")
    typer.echo(f"Metrics: {outcome.metrics_path}")
    if outcome.lineage_path:
        typer.echo(f"Lineage: {outcome.lineage_path}")
    if outcome.tracebacks_path:
        _summarise_tracebacks(outcome.tracebacks_path)
    if outcome.warnings:
        typer.secho(WARNINGS_HEADER, fg=typer.colors.YELLOW, bold=True)
        for message in outcome.warnings:
            typer.echo(f"  - {message}")
    else:
        typer.echo(WARNINGS_NONE)
    if outcome.resource_usage:
        typer.secho("Resource usage:", fg=typer.colors.CYAN, bold=True)
        for key, value in outcome.resource_usage.items():
            typer.echo(f"  - {key}: {value}")
    else:
        typer.echo("Resource usage: unavailable")


def _summarise_tracebacks(path: Path) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        typer.secho(
            f"Unable to load tracebacks from {path}: {exc}",
            fg=typer.colors.YELLOW,
        )
        return
    if not payload:
        typer.echo(f"{TRACEBACKS_HEADER} none recorded (file: {path})")
        return
    typer.secho(TRACEBACKS_HEADER, fg=typer.colors.RED, bold=True)
    max_entries = 5
    for entry in payload[:max_entries]:
        stage = entry.get("stage", "unknown")
        message = entry.get("error_message", "")
        typer.echo(f"  - {stage}: {message}")
    if len(payload) > max_entries:
        typer.echo(f"  ... truncated {len(payload) - max_entries} additional entries")


def _format_timestamp(value) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, datetime):
        return value.astimezone().isoformat(timespec="seconds")
    return str(value)


def _echo_warnings(warnings: Sequence[str]) -> None:
    if not warnings:
        typer.echo(WARNINGS_NONE)
        return
    typer.secho(WARNINGS_HEADER, fg=typer.colors.YELLOW, bold=True)
    for warning in warnings:
        typer.echo(f"  - {warning}")


def _echo_stage_outputs(manifest: dict[str, object]) -> None:
    typer.secho("Stage outputs:", bold=True)
    stage_outputs = iter_stage_outputs(manifest)
    if not stage_outputs:
        typer.echo("  (none recorded)")
        return
    for name, path in stage_outputs:
        typer.echo(f"  - {name}: {path}")


def _echo_traceback_entries(entries: Sequence[dict[str, object]]) -> None:
    if not entries:
        typer.echo(f"{TRACEBACKS_HEADER} none")
        return
    typer.secho(TRACEBACKS_HEADER, fg=typer.colors.RED, bold=True)
    for entry in entries:
        stage = str(entry.get("stage", "unknown"))
        message = str(entry.get("error_message", ""))
        typer.echo(f"  - {stage}: {message}")


def _echo_optional_path(label: str, path: str | None) -> None:
    if path:
        typer.echo(f"{label}: {path}")


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

RunIdArgument = Annotated[
    str | None,
    typer.Argument(
        None,
        help=(
            "Dry-run execution identifier. Defaults to the most recent run when"
            " omitted."
        ),
    ),
]

ListLimitOption = Annotated[
    int,
    typer.Option(
        5,
        "--limit",
        "-n",
        min=1,
        max=50,
        help="Number of runs to display.",
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


@app.command(name="pipeline-dry-run")
def pipeline_dry_run(
    query: QueryArgument = "Summarise dry-run fixtures",
    config: ConfigOption = DEFAULT_DRYRUN_CONFIG,
    actor: ActorOption = None,
) -> None:
    """Execute the pipeline in dry-run mode and persist artefacts."""

    execution = _run_pipeline_dry(config, query, actor)
    _summarise_pipeline(execution.pipeline)
    _summarise_dry_run(execution)


@dry_run_debug_app.command("list")
def debug_list(
    config: ConfigOption = DEFAULT_DRYRUN_CONFIG,
    limit: ListLimitOption = 5,
) -> None:
    """List recorded dry-run runs."""

    config_obj = PrometheusConfig.load(config)
    root = Path(config_obj.runtime.artifact_root).expanduser()
    records = list_runs(root)
    if not records:
        typer.echo(f"No dry-run runs found under {root}.")
        return
    display_count = min(limit, len(records))
    typer.secho(
        f"Showing {display_count} of {len(records)} runs from {root}",
        fg=typer.colors.BLUE,
        bold=True,
    )
    for record in records[:display_count]:
        started = _format_timestamp(record.started_at)
        completed = _format_timestamp(record.completed_at)
        typer.echo(
            "- {run_id} | query={query} | started={started} | "
            "completed={completed} | warnings={warnings} | "
            "tracebacks={tracebacks}".format(
                run_id=record.run_id,
                query=record.query or "n/a",
                started=started,
                completed=completed,
                warnings=len(record.warnings),
                tracebacks=len(record.tracebacks),
            )
        )


@dry_run_debug_app.command("inspect")
def debug_inspect(
    run_id: RunIdArgument = None,
    config: ConfigOption = DEFAULT_DRYRUN_CONFIG,
) -> None:
    """Inspect a recorded dry-run execution."""

    config_obj = PrometheusConfig.load(config)
    root = Path(config_obj.runtime.artifact_root).expanduser()
    record = select_run(root, run_id)
    if record is None:
        typer.secho(
            f"No dry-run artefacts found under {root}.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)

    typer.secho(f"Dry-run {record.run_id}", fg=typer.colors.BLUE, bold=True)
    typer.echo(f"Root: {record.root}")
    typer.echo(f"Query: {record.query or 'n/a'}")
    typer.echo(f"Actor: {record.actor or 'n/a'}")
    typer.echo(
        f"Started: {_format_timestamp(record.started_at)} | "
        f"Completed: {_format_timestamp(record.completed_at)}"
    )

    _echo_warnings(record.warnings)
    _echo_stage_outputs(record.manifest)

    manifest = record.manifest
    governance = manifest.get("governance")
    lineage_path = (
        governance.get("lineage_path") if isinstance(governance, dict) else None
    )
    _echo_optional_path("Events", manifest.get("events_path"))
    _echo_optional_path("Metrics", manifest.get("metrics_path"))
    _echo_optional_path("Lineage", lineage_path)

    tracebacks = load_tracebacks(record)
    _echo_traceback_entries(tracebacks)


@dry_run_debug_app.command("replay")
def debug_replay(
    run_id: RunIdArgument = None,
    config: ConfigOption = DEFAULT_DRYRUN_CONFIG,
    actor: ActorOption = None,
) -> None:
    """Replay a recorded dry-run query."""

    config_obj = PrometheusConfig.load(config)
    root = Path(config_obj.runtime.artifact_root).expanduser()
    record = select_run(root, run_id)
    if record is None:
        typer.secho(
            f"No dry-run artefacts found under {root}.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)
    if not record.query:
        typer.secho(
            "Recorded run is missing the original query; cannot replay.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)

    replay_actor = actor if actor is not None else record.actor
    typer.secho(
        f"Replaying query '{record.query}' (actor={replay_actor or 'n/a'})",
        fg=typer.colors.BLUE,
        bold=True,
    )
    execution = _run_pipeline_dry(config, record.query, replay_actor)
    _summarise_pipeline(execution.pipeline)
    _summarise_dry_run(execution)


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


__all__ = [
    "app",
    "main",
    "pipeline",
    "pipeline_dry_run",
    "offline_package",
    "plugins",
]


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
