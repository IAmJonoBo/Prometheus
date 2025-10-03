"""Developer CLI for the Prometheus Strategy OS."""

from __future__ import annotations

import importlib
import json
import os
import time
from collections.abc import Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from importlib import metadata
from pathlib import Path
from typing import Annotated

try:
    typer = importlib.import_module("typer")
except ImportError as exc:  # pragma: no cover - CLI dependency guard
    raise RuntimeError("Typer must be installed to use the Prometheus CLI") from exc

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
from scripts import deps_status as deps_status_module
from scripts import upgrade_guard
from scripts.deps_status import DependencyStatus, PlannerSettings

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

deps_app = typer.Typer(help="Dependency guard and planner helpers.")
app.add_typer(deps_app, name="deps")

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

RunIdArgument = typer.Argument(
    None,
    help=(
        "Dry-run execution identifier. Defaults to the most recent run when" " omitted."
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
    line = f"Dependency status:{status_label}\rDependency status: {status_label}"
    typer.secho(line, fg=colour, bold=True)
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
            "deps_cli.status.planner_run_resolver", bool(planner_run_resolver)
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
