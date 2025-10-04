"""Chiron CLI — Unified interface for packaging, dependency, and developer tooling.

This is the main CLI entry point for the Chiron subsystem. It provides commands for:
- Offline packaging and deployment preparation
- Dependency management (guard, upgrade, drift, sync, preflight)
- Remediation of packaging and runtime failures
- Orchestration of complex workflows
- Diagnostics and health checks
"""

from __future__ import annotations

import importlib
import json
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

try:
    typer = importlib.import_module("typer")
except ImportError as exc:
    raise RuntimeError("Typer must be installed to use the Chiron CLI") from exc

if TYPE_CHECKING:
    import typer as _typer
    TyperContext = _typer.Context
else:
    TyperContext = typer.Context

logger = logging.getLogger(__name__)

# ============================================================================
# Main Chiron CLI
# ============================================================================

app = typer.Typer(
    add_completion=False,
    help="Chiron — Packaging, dependency management, and developer tooling subsystem",
)

# ============================================================================
# Sub-applications
# ============================================================================

deps_app = typer.Typer(help="Dependency management commands")
app.add_typer(deps_app, name="deps")

packaging_app = typer.Typer(help="Offline packaging commands")
app.add_typer(packaging_app, name="package")

remediation_app = typer.Typer(help="Remediation commands")
app.add_typer(remediation_app, name="remediate")

orchestrate_app = typer.Typer(help="Orchestration workflows")
app.add_typer(orchestrate_app, name="orchestrate")

doctor_app = typer.Typer(help="Diagnostics and health checks")
app.add_typer(doctor_app, name="doctor")

tools_app = typer.Typer(help="Developer tools and utilities")
app.add_typer(tools_app, name="tools")

_SCRIPT_PROXY_CONTEXT = {
    "allow_extra_args": True,
    "ignore_unknown_options": True,
}


# ============================================================================
# Version Command
# ============================================================================

@app.command()
def version() -> None:
    """Display Chiron version."""
    from chiron import __version__
    typer.echo(f"Chiron version {__version__}")


# ============================================================================
# Packaging Commands
# ============================================================================

@packaging_app.command(
    "offline",
    context_settings=_SCRIPT_PROXY_CONTEXT,
)
def package_offline(ctx: TyperContext) -> None:
    """Execute offline packaging workflow.
    
    Build complete offline deployment artifacts including dependencies,
    models, and containers. Use 'chiron doctor offline' to verify readiness.
    """
    from chiron.doctor import package_cli
    
    argv = list(ctx.args)
    exit_code = package_cli.main(argv or None)
    if exit_code != 0:
        raise typer.Exit(exit_code)


# ============================================================================
# Doctor Commands
# ============================================================================

@doctor_app.command(
    "offline",
    context_settings=_SCRIPT_PROXY_CONTEXT,
)
def doctor_offline(ctx: TyperContext) -> None:
    """Diagnose offline packaging readiness.
    
    Validates tool availability, wheelhouse health, and configuration
    without mutating the repository.
    """
    from chiron.doctor import offline as doctor_module
    
    argv = list(ctx.args)
    exit_code = doctor_module.main(argv or None)
    if exit_code != 0:
        raise typer.Exit(exit_code)


@doctor_app.command(
    "bootstrap",
    context_settings=_SCRIPT_PROXY_CONTEXT,
)
def doctor_bootstrap(ctx: TyperContext) -> None:
    """Bootstrap offline environment from wheelhouse.
    
    Install dependencies from the offline wheelhouse, useful for
    air-gapped or restricted network environments.
    """
    from chiron.doctor import bootstrap
    
    argv = list(ctx.args)
    exit_code = bootstrap.main(argv)
    if exit_code != 0:
        raise typer.Exit(exit_code)


@doctor_app.command(
    "models",
    context_settings=_SCRIPT_PROXY_CONTEXT,
)
def doctor_models(ctx: TyperContext) -> None:
    """Download model artifacts for offline use.
    
    Pre-populate caches for Sentence-Transformers, Hugging Face,
    and spaCy models for air-gapped deployment.
    """
    from chiron.doctor import models
    
    argv = list(ctx.args)
    exit_code = models.main(argv)
    if exit_code != 0:
        raise typer.Exit(exit_code)


# ============================================================================
# Dependency Commands
# ============================================================================

@deps_app.command("status")
def deps_status(
    contract: Path = typer.Option(
        Path("configs/dependencies/contract.toml"),
        "--contract",
        help="Path to dependency contract file",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output as JSON",
    ),
) -> None:
    """Show dependency status and health."""
    from chiron.deps.status import generate_status
    
    try:
        status = generate_status(contract_path=contract, inputs={})
        
        if json_output:
            typer.echo(json.dumps(status, indent=2))
        else:
            typer.echo("=== Dependency Status ===")
            typer.echo(f"Contract: {contract}")
            typer.echo(f"Status: {status.get('status', 'unknown')}")
    except Exception as exc:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)


@deps_app.command(
    "guard",
    context_settings=_SCRIPT_PROXY_CONTEXT,
)
def deps_guard(ctx: TyperContext) -> None:
    """Run dependency guard checks."""
    from chiron.deps import guard
    
    argv = list(ctx.args)
    exit_code = guard.main(argv or None)
    if exit_code != 0:
        raise typer.Exit(exit_code)


@deps_app.command(
    "upgrade",
    context_settings=_SCRIPT_PROXY_CONTEXT,
)
def deps_upgrade(ctx: TyperContext) -> None:
    """Plan dependency upgrades."""
    from chiron.deps import planner
    
    argv = list(ctx.args)
    exit_code = planner.main(argv or None)
    if exit_code != 0:
        raise typer.Exit(exit_code)


@deps_app.command(
    "drift",
    context_settings=_SCRIPT_PROXY_CONTEXT,
)
def deps_drift(ctx: TyperContext) -> None:
    """Detect dependency drift."""
    from chiron.deps import drift
    
    argv = list(ctx.args)
    exit_code = drift.main(argv or None)
    if exit_code != 0:
        raise typer.Exit(exit_code)


@deps_app.command(
    "sync",
    context_settings=_SCRIPT_PROXY_CONTEXT,
)
def deps_sync(ctx: TyperContext) -> None:
    """Synchronize manifests from contract."""
    from chiron.deps import sync
    
    argv = list(ctx.args)
    exit_code = sync.main(argv or None)
    if exit_code != 0:
        raise typer.Exit(exit_code)


@deps_app.command(
    "preflight",
    context_settings=_SCRIPT_PROXY_CONTEXT,
)
def deps_preflight(ctx: TyperContext) -> None:
    """Run dependency preflight checks."""
    from chiron.deps import preflight
    
    argv = list(ctx.args)
    exit_code = preflight.main(argv or None)
    if exit_code != 0:
        raise typer.Exit(exit_code)


@deps_app.command(
    "graph",
    context_settings=_SCRIPT_PROXY_CONTEXT,
)
def deps_graph(ctx: TyperContext) -> None:
    """Generate dependency graph visualization.
    
    Analyzes Python imports across the codebase and generates
    a dependency graph showing relationships between modules.
    """
    from chiron.deps import graph
    
    argv = list(ctx.args)
    exit_code = graph.main()
    if exit_code != 0:
        raise typer.Exit(exit_code)


@deps_app.command(
    "verify",
    context_settings=_SCRIPT_PROXY_CONTEXT,
)
def deps_verify(ctx: TyperContext) -> None:
    """Verify dependency pipeline setup and integration.
    
    Checks that all components of the dependency management pipeline
    are properly wired, scripts are importable, and CLI commands work.
    """
    from chiron.deps import verify
    
    argv = list(ctx.args)
    exit_code = verify.main()
    if exit_code != 0:
        raise typer.Exit(exit_code)



# ============================================================================
# Tools Commands
# ============================================================================

@tools_app.command(
    "format-yaml",
    context_settings=_SCRIPT_PROXY_CONTEXT,
)
def tools_format_yaml(ctx: TyperContext) -> None:
    """Format YAML files consistently across the repository.
    
    Runs yamlfmt with additional conveniences like removing macOS
    resource fork files and Git-aware discovery.
    """
    from chiron.tools import format_yaml
    
    exit_code = format_yaml.main()
    if exit_code != 0:
        raise typer.Exit(exit_code)


# ============================================================================
# Remediation Commands
# ============================================================================

@remediation_app.command(
    "wheelhouse",
    context_settings=_SCRIPT_PROXY_CONTEXT,
)
def remediate_wheelhouse(ctx: TyperContext) -> None:
    """Remediate wheelhouse issues."""
    from chiron import remediation
    
    args = ["wheelhouse", *ctx.args]
    exit_code = remediation.main(args)
    if exit_code != 0:
        raise typer.Exit(exit_code)


@remediation_app.command(
    "runtime",
    context_settings=_SCRIPT_PROXY_CONTEXT,
)
def remediate_runtime(ctx: TyperContext) -> None:
    """Remediate runtime issues."""
    from chiron import remediation
    
    args = ["runtime", *ctx.args]
    exit_code = remediation.main(args)
    if exit_code != 0:
        raise typer.Exit(exit_code)


# ============================================================================
# Orchestration Commands
# ============================================================================

@orchestrate_app.command("status")
def orchestrate_status(
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show detailed status",
    ),
) -> None:
    """Show orchestration status."""
    from chiron.orchestration import OrchestrationCoordinator, OrchestrationContext
    
    context = OrchestrationContext(verbose=verbose)
    coordinator = OrchestrationCoordinator(context)
    
    status = coordinator.get_status()
    
    typer.echo("=== Orchestration Status ===")
    typer.echo(f"  Dependencies Synced: {status['context']['dependencies_synced']}")
    typer.echo(f"  Wheelhouse Built: {status['context']['wheelhouse_built']}")
    typer.echo(f"  Validation Passed: {status['context']['validation_passed']}")
    
    if status.get("recommendations"):
        typer.echo("\nRecommendations:")
        for rec in status["recommendations"]:
            typer.echo(f"  • {rec}")
    
    if verbose:
        typer.echo("\nFull Status:")
        typer.echo(json.dumps(status, indent=2))


@orchestrate_app.command("full-dependency")
def orchestrate_full_dependency(
    auto_upgrade: bool = typer.Option(
        False,
        "--auto-upgrade",
        help="Automatically plan upgrades",
    ),
    force_sync: bool = typer.Option(
        False,
        "--force-sync",
        help="Force dependency sync",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Dry run mode",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Verbose output",
    ),
) -> None:
    """Execute full dependency workflow."""
    from chiron.orchestration import OrchestrationCoordinator, OrchestrationContext
    
    context = OrchestrationContext(dry_run=dry_run, verbose=verbose)
    coordinator = OrchestrationCoordinator(context)
    
    typer.echo("Starting full dependency workflow...")
    results = coordinator.full_dependency_workflow(
        auto_upgrade=auto_upgrade,
        force_sync=force_sync,
    )
    
    typer.echo("\n✅ Dependency workflow complete")
    if results.get("preflight"):
        typer.echo("  • Preflight: completed")
    if results.get("guard"):
        guard_status = results["guard"].get("status", "unknown")
        typer.echo(f"  • Guard: {guard_status}")
    if results.get("upgrade"):
        typer.echo("  • Upgrade: planned")
    if results.get("sync"):
        typer.echo(f"  • Sync: {'success' if results['sync'] else 'failed'}")


@orchestrate_app.command("full-packaging")
def orchestrate_full_packaging(
    validate: bool = typer.Option(
        True,
        "--validate/--no-validate",
        help="Validate after packaging",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Dry run mode",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Verbose output",
    ),
) -> None:
    """Execute full packaging workflow."""
    from chiron.orchestration import OrchestrationCoordinator, OrchestrationContext
    
    context = OrchestrationContext(dry_run=dry_run, verbose=verbose)
    coordinator = OrchestrationCoordinator(context)
    
    typer.echo("Starting full packaging workflow...")
    results = coordinator.full_packaging_workflow(validate=validate)
    
    typer.echo("\n✅ Packaging workflow complete")
    if results.get("wheelhouse"):
        typer.echo(f"  • Wheelhouse: {'built' if results['wheelhouse'] else 'failed'}")
    if results.get("offline_package"):
        typer.echo(f"  • Offline package: {'success' if results['offline_package'] else 'failed'}")
    if results.get("validation"):
        validation_ok = results["validation"].get("success", False)
        typer.echo(f"  • Validation: {'passed' if validation_ok else 'failed'}")
        if not validation_ok and results.get("remediation"):
            typer.echo("  • Remediation: recommendations generated")


@orchestrate_app.command("sync-remote")
def orchestrate_sync_remote(
    artifact_dir: Path = typer.Argument(
        ...,
        help="Directory containing remote artifacts",
    ),
    validate: bool = typer.Option(
        True,
        "--validate/--no-validate",
        help="Validate after sync",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Dry run mode",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Verbose output",
    ),
) -> None:
    """Sync remote artifacts to local environment."""
    from chiron.orchestration import OrchestrationCoordinator, OrchestrationContext
    
    artifact_path = artifact_dir.resolve()
    if not artifact_path.exists():
        typer.secho(
            f"Error: Artifact directory not found: {artifact_path}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)
    
    context = OrchestrationContext(dry_run=dry_run, verbose=verbose)
    coordinator = OrchestrationCoordinator(context)
    
    typer.echo(f"Syncing artifacts from {artifact_path}...")
    results = coordinator.sync_remote_to_local(artifact_path, validate=validate)
    
    typer.echo("\n✅ Sync complete")
    if results.get("copy"):
        typer.echo("  • Artifacts: copied")
    if results.get("sync"):
        typer.echo("  • Dependencies: synced")
    if results.get("validation"):
        typer.echo("  • Validation: passed")


@orchestrate_app.command(
    "governance",
    context_settings=_SCRIPT_PROXY_CONTEXT,
)
def orchestrate_governance(ctx: TyperContext) -> None:
    """Process dry-run governance artifacts.
    
    Derive governance artifacts for dry-run CI executions,
    analyzing results and determining severity levels.
    """
    from chiron.orchestration import governance
    
    exit_code = governance.main()
    if exit_code != 0:
        raise typer.Exit(exit_code)


# ============================================================================
# Main Entry Point
# ============================================================================

def main() -> int:
    """Main CLI entry point."""
    try:
        app()
        return 0
    except Exception as exc:
        logger.exception("Chiron CLI failed")
        typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
