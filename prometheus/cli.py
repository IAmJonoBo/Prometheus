"""Developer CLI for the Prometheus Strategy OS."""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import shlex
import subprocess
import time
from collections.abc import Callable, Iterable, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from importlib import metadata
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

try:
    typer = importlib.import_module("typer")
except ImportError as exc:  # pragma: no cover - CLI dependency guard
    raise RuntimeError("Typer must be installed to use the Prometheus CLI") from exc

if TYPE_CHECKING:
    import typer as _typer

    TyperContext = _typer.Context
else:  # pragma: no cover - runtime alias for type annotations
    TyperContext = typer.Context

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from prometheus_client import Counter, Histogram

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
from prometheus import remediation as remediation_cli
from prometheus.config import PrometheusConfig
from prometheus.debugging import (
    iter_stage_outputs,
    list_runs,
    load_tracebacks,
    select_run,
)
from prometheus.pipeline import PipelineResult, build_orchestrator
from scripts import (
    dependency_drift,
)
from scripts import deps_status as deps_status_module
from scripts import (
    upgrade_guard,
    upgrade_planner,
)
from scripts.deps_status import DependencyStatus, PlannerSettings

_SCRIPT_PROXY_CONTEXT = {
    "allow_extra_args": True,
    "ignore_unknown_options": True,
}

_SYNC_DEPS_MAIN: Callable[[Sequence[str] | None], int | None] | None = None


def _scripts_root() -> Path:
    return Path(__file__).resolve().parents[1] / "scripts"


def _load_sync_dependencies_main() -> Callable[[Sequence[str] | None], int | None]:
    global _SYNC_DEPS_MAIN
    if _SYNC_DEPS_MAIN is not None:
        return _SYNC_DEPS_MAIN

    script_path = _scripts_root() / "sync-dependencies.py"
    spec = importlib.util.spec_from_file_location(
        "prometheus.cli.sync_dependencies",
        script_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load sync-dependencies script at {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[call-arg]
    main = getattr(module, "main", None)
    if main is None:
        raise RuntimeError("sync-dependencies script is missing a main() function")

    _SYNC_DEPS_MAIN = main
    return main


def _run_sync_dependencies(argv: Sequence[str] | None) -> int:
    main = _load_sync_dependencies_main()
    result = main(argv)
    return int(result) if result is not None else 0


def _handle_exit_code(exit_code: int | None) -> None:
    if exit_code:
        raise typer.Exit(exit_code)


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

deps_app = typer.Typer(help="Dependency guard and planner helpers.")
app.add_typer(deps_app, name="deps")

remediation_app = typer.Typer(
    help="Remediation helpers for packaging and runtime failures.",
)
app.add_typer(remediation_app, name="remediation")

DEFAULT_PIPELINE_CONFIG = Path("configs/defaults/pipeline.toml")
DEFAULT_DRYRUN_CONFIG = Path("configs/defaults/pipeline_dryrun.toml")
DEFAULT_DEPENDENCY_CONTRACT = upgrade_guard.DEFAULT_CONTRACT_PATH

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

RunIdArgument = typer.Argument(
    None,
    help=(
        "Dry-run execution identifier. Defaults to the most recent run when omitted."
    ),
)

ListLimitOption = typer.Option(  # noqa: B008 - Typer option declaration
    5,
    "--limit",
    "-n",
    min=1,
    max=50,
    help="Number of runs to display.",
)


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
    limit: int = ListLimitOption,
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
    run_id: str | None = RunIdArgument,
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
    run_id: str | None = RunIdArgument,
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
    "dependency_status",
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


_DEPS_TRACER = trace.get_tracer("prometheus.cli.deps")
_DEPS_OBSERVABILITY_BOOTSTRAPPED = False

DEPS_COMMAND_COUNTER = Counter(
    "dependency_cli_runs_total",
    "Total dependency CLI command executions by outcome.",
    labelnames=("command", "outcome"),
)
DEPS_COMMAND_DURATION = Histogram(
    "dependency_cli_duration_seconds",
    "Dependency CLI command duration in seconds.",
    labelnames=("command",),
)

_DEPS_ATTR_EXIT_CODE = "deps_cli.exit_code"
_DEPS_ATTR_OUTCOME = "deps_cli.outcome"
_DEPS_ATTR_DURATION = "deps_cli.duration_seconds"


def _ensure_deps_observability() -> None:
    global _DEPS_OBSERVABILITY_BOOTSTRAPPED
    if _DEPS_OBSERVABILITY_BOOTSTRAPPED:
        return
    configure_tracing(
        "prometheus-deps-cli",
        resource_attributes={"component": "prometheus.cli.deps"},
    )
    configure_metrics(namespace="prometheus_cli_deps")
    _DEPS_OBSERVABILITY_BOOTSTRAPPED = True


@dataclass
class _DependencyCommandTelemetry:
    span: trace.Span
    outcome: str = "success"
    exit_code: int | None = None


def _resolve_cli_outcome(outcome: str | None, exit_code: int) -> str:
    if outcome:
        return outcome
    return "success" if exit_code == 0 else "nonzero-exit"


@contextmanager
def _dependency_command_span(name: str):
    _ensure_deps_observability()
    start = time.perf_counter()
    with _DEPS_TRACER.start_as_current_span(f"deps_cli.{name}") as span:
        span.set_attribute("deps_cli.command", name)
        telemetry = _DependencyCommandTelemetry(span=span)
        try:
            yield telemetry
        except typer.Exit as exc:
            exit_code = getattr(exc, "exit_code", getattr(exc, "code", 0)) or 0
            telemetry.exit_code = exit_code
            telemetry.outcome = _resolve_cli_outcome(telemetry.outcome, exit_code)
            if exit_code != 0:
                span.set_status(Status(StatusCode.ERROR))
            raise
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR))
            telemetry.exit_code = (
                telemetry.exit_code if telemetry.exit_code is not None else -1
            )
            telemetry.outcome = "error"
            raise
        finally:
            duration = time.perf_counter() - start
            exit_code = telemetry.exit_code if telemetry.exit_code is not None else 0
            telemetry.exit_code = exit_code
            outcome = _resolve_cli_outcome(telemetry.outcome, exit_code)
            telemetry.outcome = outcome
            span.set_attribute(_DEPS_ATTR_EXIT_CODE, exit_code)
            span.set_attribute(_DEPS_ATTR_OUTCOME, outcome)
            span.set_attribute(_DEPS_ATTR_DURATION, duration)
            DEPS_COMMAND_COUNTER.labels(command=name, outcome=outcome).inc()
            DEPS_COMMAND_DURATION.labels(command=name).observe(duration)


@dataclass
class DependencyStatusPlannerOptions:
    """Planner configuration used by the programmatic status helper."""

    enabled: bool = True
    packages: Sequence[str] | None = None
    allow_major: bool = False
    limit: int | None = None
    run_resolver: bool = False


@dataclass
class DependencyStatusOutputOptions:
    """Output behaviour configuration for the status helper."""

    emit_json: bool = False
    output_path: Path | None = None
    markdown_output: Path | None = None
    show_markdown: bool = False


@dataclass
class DependencyStatusInputPaths:
    """Additional dependency input artefacts consumed by the status helper."""

    preflight: Path | str | None = None
    renovate: Path | str | None = None
    cve: Path | str | None = None
    sbom: Path | str | None = None
    metadata: Path | str | None = None
    profiles: Sequence[str] | None = None


DependencyContractOption = typer.Option(  # noqa: B008 - Typer option declaration
    upgrade_guard.DEFAULT_CONTRACT_PATH,
    "--contract",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    resolve_path=True,
    show_default=True,
    help="Path to the dependency contract profile consumed by the guard.",
)

DependencySbomMaxAgeOption = typer.Option(  # noqa: B008 - Typer option declaration
    None,
    "--sbom-max-age-days",
    min=1,
    help="Maximum age (in days) before the SBOM is treated as stale.",
)

DependencyFailThresholdOption = typer.Option(  # noqa: B008 - Typer option declaration
    upgrade_guard.RISK_NEEDS_REVIEW,
    "--fail-threshold",
    show_default=True,
    help="Guard failure threshold risk level.",
)

PlannerEnabledOption = typer.Option(  # noqa: B008 - Typer option declaration
    True,
    "--planner/--no-planner",
    show_default=True,
    help="Toggle upgrade planner execution within the status aggregation.",
)

PlannerPackagesOption = typer.Option(  # noqa: B008 - Typer option declaration
    None,
    "--planner-package",
    "-P",
    help="Restrict planner evaluation to specific packages (may be repeated).",
)

PlannerAllowMajorOption = typer.Option(  # noqa: B008 - Typer option declaration
    False,
    "--planner-allow-major/--planner-disallow-major",
    show_default=True,
    help="Allow the planner to propose major upgrades.",
)

PlannerLimitOption = typer.Option(  # noqa: B008 - Typer option declaration
    None,
    "--planner-limit",
    min=1,
    help="Maximum number of planner candidates to evaluate (omit for no limit).",
)

PlannerRunResolverOption = typer.Option(  # noqa: B008 - Typer option declaration
    False,
    "--planner-run-resolver/--planner-skip-resolver",
    show_default=True,
    help="Execute Poetry resolver checks for each planner candidate.",
)

StatusJsonOption = typer.Option(  # noqa: B008 - Typer option declaration
    False,
    "--json/--no-json",
    show_default=False,
    help="Emit the combined dependency status as JSON to stdout.",
)

StatusOutputOption = typer.Option(  # noqa: B008 - Typer option declaration
    None,
    "--output",
    file_okay=True,
    dir_okay=False,
    resolve_path=True,
    help="Optional output path to persist the combined dependency status JSON.",
)

StatusGuardMarkdownOption = typer.Option(  # noqa: B008 - Typer option declaration
    None,
    "--markdown-output",
    file_okay=True,
    dir_okay=False,
    resolve_path=True,
    help="Optional file path to write the guard markdown summary.",
)

StatusShowMarkdownOption = typer.Option(  # noqa: B008 - Typer option declaration
    False,
    "--show-markdown/--no-show-markdown",
    show_default=False,
    help="Print the guard markdown summary when available.",
)

StatusInputOption = typer.Option(  # noqa: B008 - Typer option declaration
    None,
    "--input",
    "-i",
    show_default=False,
    help=(
        "Dependency input mapping in the form key=PATH (supported keys: preflight,"
        " renovate, cve, sbom, metadata). May be provided multiple times."
    ),
)

UpgradeSbomOption = typer.Option(  # noqa: B008 - Typer option declaration
    ...,
    "--sbom",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    resolve_path=True,
    help="Path to the dependency SBOM consumed by the upgrade planner.",
)

UpgradeMetadataOption = typer.Option(  # noqa: B008 - Typer option declaration
    None,
    "--metadata",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    resolve_path=True,
    help="Optional metadata snapshot path passed through to the upgrade planner.",
)

UpgradePoetryOption = typer.Option(  # noqa: B008 - Typer option declaration
    "poetry",
    "--poetry",
    show_default=True,
    help="Poetry executable or path used when applying upgrade commands.",
)

UpgradeProjectRootOption = typer.Option(  # noqa: B008 - Typer option declaration
    None,
    "--project-root",
    exists=True,
    file_okay=False,
    dir_okay=True,
    writable=True,
    resolve_path=True,
    help="Project root directory used as the working directory for commands.",
)

UpgradeApplyOption = typer.Option(  # noqa: B008 - Typer option declaration
    False,
    "--apply/--no-apply",
    show_default=False,
    help="Apply the recommended commands after generating the plan.",
)

UpgradeYesOption = typer.Option(  # noqa: B008 - Typer option declaration
    False,
    "--yes/--no-yes",
    show_default=False,
    help="Skip confirmation prompts when applying recommended commands.",
)

UpgradeVerboseOption = typer.Option(  # noqa: B008 - Typer option declaration
    False,
    "--verbose/--quiet",
    show_default=False,
    help="Print additional planner details to stdout.",
)


_STATUS_SEVERITY_COLOURS = {
    "blocked": typer.colors.RED,
    "needs-review": typer.colors.YELLOW,
    "needs_review": typer.colors.YELLOW,
    "needsreview": typer.colors.YELLOW,
    "safe": typer.colors.GREEN,
}


def _persist_optional_payload(path: Path | None, payload: str, label: str) -> None:
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")
    except OSError as exc:
        typer.secho(f"Unable to write {label} to {path}: {exc}", fg=typer.colors.RED)
        raise typer.Exit(2) from exc


def _echo_bullet_list(title: str, items: Sequence[str]) -> None:
    if not items:
        return
    typer.secho(f"{title}:", bold=True)
    for item in items:
        typer.echo(f"  - {item}")


def _render_optional_fields(fields: Sequence[tuple[str, object | None]]) -> None:
    for label, value in fields:
        if value is None:
            continue
        typer.echo(f"{label}: {value}")


def _render_dependency_status_summary(status: DependencyStatus) -> None:
    summary = status.summary
    severity = str(summary.get("highest_severity", "unknown")).lower()
    colour = _STATUS_SEVERITY_COLOURS.get(severity, typer.colors.BLUE)
    status_label = severity or "unknown"
    label = f"Dependency status:{status_label}"
    typer.secho(label, fg=colour, bold=True)
    typer.echo(f"Dependency status: {status_label}")
    typer.echo(
        f"Generated at: {status.generated_at.astimezone().isoformat(timespec='seconds')}"
    )

    _render_optional_fields(
        (
            ("Packages flagged", summary.get("packages_flagged")),
            ("Contract risk", summary.get("contract_risk")),
            ("Drift severity", summary.get("drift_severity")),
        )
    )

    notes = [str(note) for note in summary.get("notes") or []]
    _echo_bullet_list("Notes", notes)

    typer.echo(f"Guard exit code: {status.guard.exit_code}")
    typer.echo(f"Planner exit code: {summary.get('planner_exit_code')}")

    planner_reason = summary.get("planner_reason")
    if planner_reason:
        typer.echo(f"Planner notes: {planner_reason}")

    planner_summary = summary.get("planner_summary")
    if planner_summary:
        items = [f"{key}: {value}" for key, value in planner_summary.items()]
        _echo_bullet_list("Planner summary", items)

    commands = [str(command) for command in summary.get("recommended_commands") or []]
    _echo_bullet_list("Recommended commands", commands)


def _plan_payload(plan_result: object) -> dict[str, Any]:
    to_dict = getattr(plan_result, "to_dict", None)
    if not callable(to_dict):
        return {}
    try:
        payload = to_dict()
    except Exception:  # pragma: no cover - defensive guard
        return {}
    return payload if isinstance(payload, dict) else {}


def _normalise_plan_summary(plan_result: object) -> dict[str, Any]:
    summary = getattr(plan_result, "summary", None)
    if not isinstance(summary, dict):
        payload = _plan_payload(plan_result)
        candidate_summary = payload.get("summary") if payload else None
        if isinstance(candidate_summary, dict):
            summary = candidate_summary
    return dict(summary) if isinstance(summary, dict) else {}


def _normalise_plan_candidate(candidate: object | None) -> dict[str, Any]:
    if isinstance(candidate, dict):
        return candidate
    if candidate is None:
        return {}
    breakdown = getattr(candidate, "score_breakdown", {})
    return {
        "name": getattr(candidate, "name", "unknown"),
        "current": getattr(candidate, "current", None),
        "latest": getattr(candidate, "latest", None),
        "severity": getattr(candidate, "severity", None),
        "score": getattr(candidate, "score", None),
        "notes": list(getattr(candidate, "notes", []) or []),
        "score_breakdown": dict(breakdown) if isinstance(breakdown, dict) else {},
    }


def _normalise_plan_resolver(resolver: object | None) -> dict[str, Any]:
    if isinstance(resolver, dict):
        return resolver
    if resolver is None:
        return {}
    return {
        "status": getattr(resolver, "status", None),
        "reason": getattr(resolver, "reason", None),
    }


def _normalise_plan_attempts(plan_result: object) -> list[dict[str, Any]]:
    attempts: Any = getattr(plan_result, "attempts", None)
    if attempts is None:
        payload = _plan_payload(plan_result)
        attempts = payload.get("attempts") if payload else None
    normalised: list[dict[str, Any]] = []
    for entry in attempts or []:
        if isinstance(entry, dict):
            normalised.append(entry)
            continue
        normalised.append(
            {
                "candidate": _normalise_plan_candidate(
                    getattr(entry, "candidate", None)
                ),
                "resolver": _normalise_plan_resolver(getattr(entry, "resolver", None)),
            }
        )
    return normalised


def _normalise_plan_commands(plan_result: object) -> list[str]:
    commands = getattr(plan_result, "recommended_commands", None)
    if not isinstance(commands, list):
        payload = _plan_payload(plan_result)
        commands = payload.get("recommended_commands") if payload else None
    if isinstance(commands, list):
        return [str(command) for command in commands]
    return []


def _render_plan_summary(summary: dict[str, Any]) -> None:
    if not summary:
        return
    typer.secho("Summary:", bold=True)
    ok = summary.get("ok")
    failed = summary.get("failed")
    skipped = summary.get("skipped")
    parts = []
    if ok is not None:
        parts.append(f"ok={ok}")
    if failed is not None:
        parts.append(f"failed={failed}")
    if skipped is not None:
        parts.append(f"skipped={skipped}")
    if parts:
        typer.echo("  Attempts: " + ", ".join(parts))
    highest = summary.get("highest_severity")
    if highest:
        typer.echo(f"  Highest severity: {highest}")


def _render_plan_scoreboard(attempts: list[dict[str, Any]]) -> None:
    typer.secho("Scoreboard", fg=typer.colors.BLUE, bold=True)
    if not attempts:
        typer.echo("  (no candidates evaluated)")
        return
    for entry in attempts:
        candidate = dict(entry.get("candidate") or {})
        resolver = dict(entry.get("resolver") or {})
        typer.echo(_format_scoreboard_line(candidate, resolver))
        breakdown_text = _format_scoreboard_breakdown(candidate.get("score_breakdown"))
        if breakdown_text:
            typer.echo(f"      breakdown: {breakdown_text}")
        reason = resolver.get("reason")
        if reason:
            typer.echo(f"      resolver reason: {reason}")


def _render_recommended_commands(commands: list[str]) -> None:
    if not commands:
        typer.echo("No recommended commands.")
        return
    typer.secho("Recommended commands:", bold=True)
    for command in commands:
        typer.echo(f"  - {command}")


def _format_scoreboard_line(candidate: dict[str, Any], resolver: dict[str, Any]) -> str:
    name = candidate.get("name") or "unknown"
    current = candidate.get("current") or "?"
    latest = candidate.get("latest") or "?"
    severity = candidate.get("severity") or "unknown"
    status = resolver.get("status") or "unknown"
    segments = [f"  - {name}: {current} -> {latest} [{severity}]"]
    score = candidate.get("score")
    if isinstance(score, (int, float)):
        segments.append(f"score={score:.1f}")
    segments.append(f"status={status}")
    return " ".join(segments)


def _format_scoreboard_breakdown(raw: object) -> str | None:
    if not isinstance(raw, dict) or not raw:
        return None
    parts: list[str] = []
    for key, value in raw.items():
        if isinstance(value, (int, float)):
            parts.append(f"{key}={value:.1f}")
        else:
            parts.append(f"{key}={value}")
    return ", ".join(parts) if parts else None


def _apply_commands(commands: Sequence[str], project_root: Path) -> None:
    for command in commands:
        args = shlex.split(command)
        typer.echo(f"Executing: {' '.join(args)}")
        subprocess.run(args, cwd=project_root, check=True)  # noqa: S603


def _normalise_planner_packages(values: Sequence[str] | None) -> frozenset[str] | None:
    if not values:
        return None
    cleaned = {value.strip() for value in values if value.strip()}
    return frozenset(cleaned) or None


def _build_upgrade_config(
    *,
    sbom_path: Path,
    metadata_path: Path | None,
    packages: frozenset[str] | None,
    allow_major: bool,
    limit: int | None,
    run_resolver: bool,
    poetry: str,
    project_root: Path,
    verbose: bool,
) -> upgrade_planner.PlannerConfig:
    poetry_path = upgrade_planner._resolve_poetry_path(poetry)
    return upgrade_planner.PlannerConfig(
        sbom_path=sbom_path,
        metadata_path=metadata_path,
        packages=packages,
        allow_major=allow_major,
        limit=limit,
        poetry_path=poetry_path,
        project_root=project_root,
        skip_resolver=not run_resolver,
        output_path=None,
        verbose=verbose,
    )


def _render_upgrade_plan(
    *,
    sbom_path: Path,
    project_root: Path,
    summary: dict[str, Any],
    attempts: list[dict[str, Any]],
    commands: list[str],
) -> None:
    typer.secho("Dependency Upgrade Plan", fg=typer.colors.BLUE, bold=True)
    typer.echo(f"SBOM: {sbom_path}")
    typer.echo(f"Project root: {project_root}")
    _render_plan_summary(summary)
    _render_plan_scoreboard(attempts)
    _render_recommended_commands(commands)


def _maybe_apply_plan_commands(
    *,
    commands: list[str],
    project_root: Path,
    apply: bool,
    assume_yes: bool,
    telemetry: _DependencyCommandTelemetry,
) -> None:
    if not apply:
        return
    if not commands:
        typer.secho("No recommended commands to apply.", fg=typer.colors.YELLOW)
        return
    if not assume_yes:
        confirmed = typer.confirm("Apply recommended commands?", default=False)
        if not confirmed:
            telemetry.exit_code = 1
            telemetry.outcome = "aborted"
            typer.secho("Aborted without applying commands.", fg=typer.colors.YELLOW)
            return
    try:
        _apply_commands(commands, project_root)
    except subprocess.CalledProcessError as exc:
        telemetry.exit_code = exc.returncode or 1
        telemetry.outcome = "failed"
        typer.secho(f"Command failed: {exc}", fg=typer.colors.RED)
        raise typer.Exit(telemetry.exit_code) from exc
    typer.secho("Recommended commands applied.", fg=typer.colors.GREEN)


def _write_guard_markdown(
    markdown_output: Path | None, markdown_text: str | None
) -> None:
    if markdown_output is None:
        return
    if markdown_text:
        _persist_optional_payload(
            markdown_output, markdown_text, "guard markdown summary"
        )
        typer.secho(
            f"Guard markdown summary written to {markdown_output}",
            fg=typer.colors.BLUE,
        )
    else:
        typer.secho(
            "No guard markdown summary available to write.", fg=typer.colors.YELLOW
        )


def _echo_guard_markdown(show_markdown: bool, markdown_text: str | None) -> None:
    if not show_markdown:
        return
    if markdown_text:
        typer.echo()
        typer.secho("Guard summary:", bold=True)
        typer.echo(markdown_text)
    else:
        typer.secho("No guard markdown summary available.", fg=typer.colors.YELLOW)


def _process_status_outputs(
    status: DependencyStatus,
    payload: str,
    output_path: Path | None,
    markdown_output: Path | None,
    json_output: bool,
    show_markdown: bool,
) -> None:
    if output_path is not None:
        _persist_optional_payload(output_path, payload + "\n", "dependency status JSON")
        typer.secho(f"Dependency status written to {output_path}", fg=typer.colors.BLUE)

    _write_guard_markdown(markdown_output, status.guard.markdown)

    if json_output:
        typer.echo(payload)

    _render_dependency_status_summary(status)

    _echo_guard_markdown(show_markdown, status.guard.markdown)


_STATUS_INPUT_KEYS = {"preflight", "renovate", "cve", "sbom", "metadata"}


def _parse_status_inputs(values: Sequence[str] | None) -> dict[str, Path]:
    if not values:
        return {}
    mapping: dict[str, Path] = {}
    for raw in values:
        key, sep, remainder = raw.partition("=")
        if not sep or not key or not remainder:
            raise typer.BadParameter("Inputs must be provided as key=PATH pairs.")
        label = key.strip().lower()
        if label not in _STATUS_INPUT_KEYS:
            supported = ", ".join(sorted(_STATUS_INPUT_KEYS))
            raise typer.BadParameter(
                f"Unsupported input key '{label}'. Supported keys: {supported}."
            )
        path = Path(remainder).expanduser()
        if not path.exists():
            raise typer.BadParameter(f"Input path not found: {path}")
        if not path.is_file():
            raise typer.BadParameter(f"Input path must be a file: {path}")
        mapping[label] = path.resolve()
    return mapping


@deps_app.command("status")
def deps_status(  # noqa: D401
    contract: Path = DependencyContractOption,
    inputs: list[str] | None = StatusInputOption,
    sbom_max_age_days: int | None = DependencySbomMaxAgeOption,
    fail_threshold: str = DependencyFailThresholdOption,
    planner_enabled: bool = PlannerEnabledOption,
    planner_packages: list[str] | None = PlannerPackagesOption,
    planner_allow_major: bool = PlannerAllowMajorOption,
    planner_limit: int | None = PlannerLimitOption,
    planner_run_resolver: bool = PlannerRunResolverOption,
    json_output: bool = StatusJsonOption,
    output_path: Path | None = StatusOutputOption,
    markdown_output: Path | None = StatusGuardMarkdownOption,
    show_markdown: bool = StatusShowMarkdownOption,
) -> None:
    """Generate and display the aggregated dependency status."""

    inputs_map = _parse_status_inputs(inputs)
    planner_settings = PlannerSettings(
        enabled=bool(planner_enabled),
        packages=tuple(planner_packages) if planner_packages else None,
        allow_major=bool(planner_allow_major),
        limit=planner_limit,
        skip_resolver=not planner_run_resolver,
    )

    with _dependency_command_span("status") as telemetry:
        span = telemetry.span
        span.set_attribute("deps_cli.status.json", bool(json_output))
        span.set_attribute(
            "deps_cli.status.output_path",
            str(output_path) if output_path else "",
        )
        span.set_attribute(
            "deps_cli.status.markdown_output",
            str(markdown_output) if markdown_output else "",
        )
        span.set_attribute("deps_cli.status.show_markdown", bool(show_markdown))
        span.set_attribute(
            "deps_cli.status.planner_enabled", bool(planner_settings.enabled)
        )
        if inputs_map:
            span.set_attribute("deps_cli.status.input_keys", sorted(inputs_map.keys()))
        if sbom_max_age_days is not None:
            span.set_attribute(
                "deps_cli.status.sbom_max_age_days", int(sbom_max_age_days)
            )
        span.set_attribute(
            "deps_cli.status.planner_allow_major", bool(planner_settings.allow_major)
        )
        span.set_attribute(
            "deps_cli.status.planner_run_resolver", not planner_settings.skip_resolver
        )
        if planner_settings.packages:
            span.set_attribute(
                "deps_cli.status.planner_packages", list(planner_settings.packages)
            )
        if planner_settings.limit is not None:
            span.set_attribute(
                "deps_cli.status.planner_limit", int(planner_settings.limit)
            )

        status = deps_status_module.generate_status(
            preflight=inputs_map.get("preflight"),
            renovate=inputs_map.get("renovate"),
            cve=inputs_map.get("cve"),
            contract=contract,
            sbom=inputs_map.get("sbom"),
            metadata=inputs_map.get("metadata"),
            sbom_max_age_days=sbom_max_age_days,
            fail_threshold=fail_threshold,
            planner_settings=planner_settings,
        )

        payload = json.dumps(status.to_dict(), indent=2, sort_keys=True)
        _process_status_outputs(
            status=status,
            payload=payload,
            output_path=output_path,
            markdown_output=markdown_output,
            json_output=json_output,
            show_markdown=show_markdown,
        )

        telemetry.exit_code = status.exit_code
        telemetry.outcome = str(status.summary.get("highest_severity") or "unknown")
        span.set_attribute("deps_cli.status.highest_severity", telemetry.outcome)
        span.set_attribute("deps_cli.status.exit_code", status.exit_code)

        if status.exit_code:
            raise typer.Exit(status.exit_code)


def _coerce_string_sequence(value: object | None) -> tuple[str, ...] | None:
    if value is None:
        return None
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, Iterable):
        items = [str(item) for item in value]
    else:
        items = [str(value)]
    cleaned = [item for item in items if item]
    return tuple(cleaned) if cleaned else None


def _clone_planner_options(
    planner: DependencyStatusPlannerOptions | None,
) -> DependencyStatusPlannerOptions:
    if planner is None:
        return DependencyStatusPlannerOptions()
    return DependencyStatusPlannerOptions(
        enabled=planner.enabled,
        packages=_coerce_string_sequence(planner.packages),
        allow_major=planner.allow_major,
        limit=planner.limit,
        run_resolver=planner.run_resolver,
    )


def _merge_legacy_planner_options(
    planner_options: DependencyStatusPlannerOptions, legacy: dict[str, Any]
) -> None:
    if "planner_enabled" in legacy:
        planner_options.enabled = bool(legacy.pop("planner_enabled"))
    if "planner_packages" in legacy:
        planner_options.packages = _coerce_string_sequence(
            legacy.pop("planner_packages")
        )
    if "planner_allow_major" in legacy:
        planner_options.allow_major = bool(legacy.pop("planner_allow_major"))
    if "planner_limit" in legacy:
        planner_options.limit = legacy.pop("planner_limit")
    if "planner_run_resolver" in legacy:
        planner_options.run_resolver = bool(legacy.pop("planner_run_resolver"))


def _clone_input_paths(
    paths: DependencyStatusInputPaths | None,
) -> DependencyStatusInputPaths:
    if paths is None:
        return DependencyStatusInputPaths()
    return DependencyStatusInputPaths(
        preflight=paths.preflight,
        renovate=paths.renovate,
        cve=paths.cve,
        sbom=paths.sbom,
        metadata=paths.metadata,
        profiles=_coerce_string_sequence(paths.profiles),
    )


def _merge_legacy_input_paths(
    extra_input_paths: DependencyStatusInputPaths, legacy: dict[str, Any]
) -> None:
    for name in ("preflight", "renovate", "cve", "sbom", "metadata"):
        if name in legacy:
            setattr(extra_input_paths, name, legacy.pop(name))
    if "profiles" in legacy:
        extra_input_paths.profiles = _coerce_string_sequence(legacy.pop("profiles"))


def _clone_output_options(
    output: DependencyStatusOutputOptions | None,
) -> DependencyStatusOutputOptions:
    if output is None:
        return DependencyStatusOutputOptions()
    return DependencyStatusOutputOptions(
        emit_json=output.emit_json,
        output_path=output.output_path,
        markdown_output=output.markdown_output,
        show_markdown=output.show_markdown,
    )


def _merge_legacy_output_options(
    output_options: DependencyStatusOutputOptions, legacy: dict[str, Any]
) -> None:
    if "json_output" in legacy:
        output_options.emit_json = bool(legacy.pop("json_output"))
    if "output_path" in legacy:
        output_options.output_path = legacy.pop("output_path")
    if "markdown_output" in legacy:
        output_options.markdown_output = legacy.pop("markdown_output")
    if "show_markdown" in legacy:
        output_options.show_markdown = bool(legacy.pop("show_markdown"))


def _ensure_output_paths(output_options: DependencyStatusOutputOptions) -> None:
    if output_options.output_path is not None and not isinstance(
        output_options.output_path, Path
    ):
        output_options.output_path = Path(output_options.output_path)
    if output_options.markdown_output is not None and not isinstance(
        output_options.markdown_output, Path
    ):
        output_options.markdown_output = Path(output_options.markdown_output)


def _build_dependency_inputs_map(
    inputs: Sequence[str] | None,
    extra_input_paths: DependencyStatusInputPaths,
) -> dict[str, Path]:
    inputs_map = _parse_status_inputs(list(inputs) if inputs else None)

    extra_inputs_map: dict[str, Path] = {}
    for label in ("preflight", "renovate", "cve", "sbom", "metadata"):
        value = getattr(extra_input_paths, label)
        if value is not None:
            extra_inputs_map[label] = Path(value)

    profiles = _coerce_string_sequence(extra_input_paths.profiles)
    if profiles:
        for entry in profiles:
            key, sep, remainder = entry.partition("=")
            if not sep or not key or not remainder:
                raise TypeError("Profiles must be provided as key=PATH pairs.")
            extra_inputs_map[key.strip().lower()] = Path(remainder)

    if extra_inputs_map:
        inputs_map.update(extra_inputs_map)
    return inputs_map


def _should_emit_status_output(output_options: DependencyStatusOutputOptions) -> bool:
    return (
        output_options.emit_json
        or output_options.output_path is not None
        or output_options.markdown_output is not None
        or output_options.show_markdown
    )


def dependency_status(
    *,
    contract: Path,
    inputs: Sequence[str] | None = None,
    extra_inputs: DependencyStatusInputPaths | None = None,
    planner: DependencyStatusPlannerOptions | None = None,
    output: DependencyStatusOutputOptions | None = None,
    sbom_max_age_days: int | None = None,
    fail_threshold: str = upgrade_guard.RISK_NEEDS_REVIEW,
    verbose: bool | None = None,
    **legacy_kwargs: Any,
) -> DependencyStatus:
    """Programmatic entry point mirroring the `deps status` command."""

    del verbose  # Accepted for backwards compatibility but ignored.

    legacy = dict(legacy_kwargs)

    planner_options = _clone_planner_options(planner)
    extra_input_paths = _clone_input_paths(extra_inputs)
    output_options = _clone_output_options(output)

    _merge_legacy_planner_options(planner_options, legacy)
    _merge_legacy_input_paths(extra_input_paths, legacy)
    _merge_legacy_output_options(output_options, legacy)

    if legacy:
        unexpected = ", ".join(sorted(legacy.keys()))
        raise TypeError(f"Unexpected keyword arguments: {unexpected}")

    inputs_map = _build_dependency_inputs_map(inputs, extra_input_paths)

    planner_settings = PlannerSettings(
        enabled=bool(planner_options.enabled),
        packages=planner_options.packages,
        allow_major=bool(planner_options.allow_major),
        limit=planner_options.limit,
        skip_resolver=not planner_options.run_resolver,
    )

    status = deps_status_module.generate_status(
        preflight=inputs_map.get("preflight"),
        renovate=inputs_map.get("renovate"),
        cve=inputs_map.get("cve"),
        contract=contract,
        sbom=inputs_map.get("sbom"),
        metadata=inputs_map.get("metadata"),
        sbom_max_age_days=sbom_max_age_days,
        fail_threshold=fail_threshold,
        planner_settings=planner_settings,
    )

    _ensure_output_paths(output_options)

    if _should_emit_status_output(output_options):
        payload = json.dumps(status.to_dict(), indent=2, sort_keys=True)
        _process_status_outputs(
            status=status,
            payload=payload,
            output_path=output_options.output_path,
            markdown_output=output_options.markdown_output,
            json_output=output_options.emit_json,
            show_markdown=output_options.show_markdown,
        )

    return status


@deps_app.command("upgrade")
def deps_upgrade(  # noqa: D401, PLR0912, PLR0915
    sbom: Path = UpgradeSbomOption,
    metadata: Path | None = UpgradeMetadataOption,
    planner_packages: list[str] | None = PlannerPackagesOption,
    planner_allow_major: bool = PlannerAllowMajorOption,
    planner_limit: int | None = PlannerLimitOption,
    planner_run_resolver: bool = PlannerRunResolverOption,
    poetry: str = UpgradePoetryOption,
    project_root: Path | None = UpgradeProjectRootOption,
    apply: bool = UpgradeApplyOption,
    yes: bool = UpgradeYesOption,
    verbose: bool = UpgradeVerboseOption,
) -> None:
    """Generate a dependency upgrade plan and optionally apply commands."""

    sbom_path = sbom.resolve()
    metadata_path = metadata.resolve() if metadata else None
    root = (project_root or sbom_path.parent).resolve()
    package_values = tuple(planner_packages) if planner_packages else ()
    package_set = (
        frozenset({value.strip() for value in package_values if value.strip()}) or None
    )

    with _dependency_command_span("upgrade") as telemetry:
        span = telemetry.span
        span.set_attribute("deps_cli.upgrade.apply", bool(apply))
        span.set_attribute("deps_cli.upgrade.allow_major", bool(planner_allow_major))
        span.set_attribute("deps_cli.upgrade.run_resolver", bool(planner_run_resolver))
        span.set_attribute("deps_cli.upgrade.verbose", bool(verbose))
        span.set_attribute("deps_cli.upgrade.sbom", str(sbom_path))
        span.set_attribute("deps_cli.upgrade.metadata", str(metadata_path or ""))
        span.set_attribute("deps_cli.upgrade.project_root", str(root))
        if package_set:
            span.set_attribute("deps_cli.upgrade.packages", sorted(package_set))
        if planner_limit is not None:
            span.set_attribute("deps_cli.upgrade.limit", int(planner_limit))

        try:
            poetry_path = upgrade_planner._resolve_poetry_path(poetry)
            config = upgrade_planner.PlannerConfig(
                sbom_path=sbom_path,
                metadata_path=metadata_path,
                packages=package_set,
                allow_major=bool(planner_allow_major),
                limit=planner_limit,
                poetry_path=poetry_path,
                project_root=root,
                skip_resolver=not planner_run_resolver,
                output_path=None,
                verbose=bool(verbose),
            )
            plan_result = upgrade_planner.generate_plan(config)
        except upgrade_planner.PlannerError as exc:
            typer.secho(f"Upgrade planner error: {exc}", fg=typer.colors.RED)
            telemetry.exit_code = 2
            telemetry.outcome = "error"
            raise typer.Exit(2) from exc

        summary = _normalise_plan_summary(plan_result)
        attempts = _normalise_plan_attempts(plan_result)
        commands = _normalise_plan_commands(plan_result)
        exit_code = getattr(plan_result, "exit_code", 1)
        telemetry.exit_code = exit_code
        telemetry.outcome = summary.get("highest_severity", "success")
        span.set_attribute("deps_cli.upgrade.exit_code", exit_code)
        span.set_attribute("deps_cli.upgrade.recommended", len(commands))

        typer.secho("Dependency Upgrade Plan", fg=typer.colors.BLUE, bold=True)
        typer.echo(f"SBOM: {sbom_path}")
        typer.echo(f"Project root: {root}")
        _render_plan_summary(summary)
        _render_plan_scoreboard(attempts)
        _render_recommended_commands(commands)

        if exit_code != 0:
            raise typer.Exit(exit_code)

        if apply:
            if not commands:
                typer.secho("No recommended commands to apply.", fg=typer.colors.YELLOW)
                return
            if not yes:
                confirmed = typer.confirm("Apply recommended commands?", default=False)
                if not confirmed:
                    telemetry.exit_code = 1
                    telemetry.outcome = "aborted"
                    typer.secho(
                        "Aborted without applying commands.",
                        fg=typer.colors.YELLOW,
                    )
                    return
            try:
                _apply_commands(commands, root)
            except subprocess.CalledProcessError as exc:
                telemetry.exit_code = exc.returncode or 1
                telemetry.outcome = "failed"
                typer.secho(f"Command failed: {exc}", fg=typer.colors.RED)
                raise typer.Exit(telemetry.exit_code) from exc

            typer.secho("Recommended commands applied.", fg=typer.colors.GREEN)


@deps_app.command("guard", context_settings=_SCRIPT_PROXY_CONTEXT)
def deps_guard(ctx: TyperContext) -> None:
    """Run the dependency guard report generator."""

    exit_code = upgrade_guard.main(list(ctx.args) or None)
    _handle_exit_code(exit_code)


@deps_app.command("drift", context_settings=_SCRIPT_PROXY_CONTEXT)
def deps_drift(ctx: TyperContext) -> None:
    """Compute dependency drift summaries using the stored inputs."""

    exit_code = dependency_drift.main(list(ctx.args) or None)
    _handle_exit_code(exit_code)


@deps_app.command("sync", context_settings=_SCRIPT_PROXY_CONTEXT)
def deps_sync(ctx: TyperContext) -> None:
    """Synchronise dependency manifests from the contract file."""

    args = list(ctx.args)
    exit_code = _run_sync_dependencies(args or None)
    _handle_exit_code(exit_code)


@remediation_app.command(
    "wheelhouse",
    context_settings=_SCRIPT_PROXY_CONTEXT,
)
def remediation_wheelhouse(ctx: TyperContext) -> None:
    """Proxy to the remediation wheelhouse command."""

    args = ["wheelhouse", *ctx.args]
    exit_code = remediation_cli.main(args)
    _handle_exit_code(exit_code)


@remediation_app.command(
    "runtime",
    context_settings=_SCRIPT_PROXY_CONTEXT,
)
def remediation_runtime(ctx: TyperContext) -> None:
    """Proxy to the remediation runtime command."""

    args = ["runtime", *ctx.args]
    exit_code = remediation_cli.main(args)
    _handle_exit_code(exit_code)
