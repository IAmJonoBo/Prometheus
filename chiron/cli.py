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

github_app = typer.Typer(help="GitHub Actions integration and artifact sync")
app.add_typer(github_app, name="github")

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


@remediation_app.command("auto")
def remediate_auto(
    failure_type: str = typer.Argument(
        ...,
        help="Type of failure: dependency-sync, wheelhouse, mirror, artifact, drift",
    ),
    input_file: Path = typer.Option(
        None,
        "--input",
        "-i",
        help="Input file (error log or JSON report)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview actions without applying them",
    ),
    auto_apply: bool = typer.Option(
        False,
        "--auto-apply",
        help="Automatically apply high-confidence fixes",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Verbose output",
    ),
) -> None:
    """Intelligent autoremediation for common failures.
    
    Analyzes failure patterns and applies fixes automatically when
    confidence is high, or suggests manual actions otherwise.
    
    Example:
        chiron remediate auto dependency-sync --input error.log --auto-apply
    """
    from chiron.remediation.autoremediate import AutoRemediator
    import logging
    
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    
    remediator = AutoRemediator(dry_run=dry_run, auto_apply=auto_apply)
    
    # Load input if provided
    if input_file:
        if not input_file.exists():
            typer.secho(f"❌ Input file not found: {input_file}", fg=typer.colors.RED)
            raise typer.Exit(1)
        
        if input_file.suffix == ".json":
            import json
            with input_file.open() as f:
                input_data = json.load(f)
        else:
            input_data = input_file.read_text()
    else:
        input_data = {}
    
    # Apply appropriate remediation
    try:
        if failure_type == "dependency-sync":
            if isinstance(input_data, str):
                result = remediator.remediate_dependency_sync_failure(input_data)
            else:
                typer.secho("❌ Dependency sync requires error log as input", fg=typer.colors.RED)
                raise typer.Exit(1)
        
        elif failure_type == "wheelhouse":
            if isinstance(input_data, dict):
                result = remediator.remediate_wheelhouse_failure(input_data)
            else:
                typer.secho("❌ Wheelhouse remediation requires JSON report as input", fg=typer.colors.RED)
                raise typer.Exit(1)
        
        elif failure_type == "mirror":
            mirror_path = Path(input_data) if isinstance(input_data, str) else Path("vendor/mirror")
            result = remediator.remediate_mirror_corruption(mirror_path)
        
        elif failure_type == "artifact":
            if isinstance(input_data, dict):
                artifact_path = Path(input_data.get("artifact_path", "dist"))
                result = remediator.remediate_artifact_validation_failure(input_data, artifact_path)
            else:
                typer.secho("❌ Artifact remediation requires validation JSON as input", fg=typer.colors.RED)
                raise typer.Exit(1)
        
        elif failure_type == "drift":
            if isinstance(input_data, dict):
                result = remediator.remediate_configuration_drift(input_data)
            else:
                typer.secho("❌ Drift remediation requires drift report JSON as input", fg=typer.colors.RED)
                raise typer.Exit(1)
        
        else:
            typer.secho(f"❌ Unknown failure type: {failure_type}", fg=typer.colors.RED)
            raise typer.Exit(1)
        
        # Report results
        if result.success:
            typer.secho("✅ Remediation successful", fg=typer.colors.GREEN)
        else:
            typer.secho("⚠️  Remediation completed with issues", fg=typer.colors.YELLOW)
        
        if result.actions_applied:
            typer.echo("\nActions applied:")
            for action in result.actions_applied:
                typer.secho(f"  ✓ {action}", fg=typer.colors.GREEN)
        
        if result.actions_failed:
            typer.echo("\nActions failed:")
            for action in result.actions_failed:
                typer.secho(f"  ✗ {action}", fg=typer.colors.RED)
        
        if result.warnings:
            typer.echo("\nWarnings:")
            for warning in result.warnings:
                typer.secho(f"  ⚠ {warning}", fg=typer.colors.YELLOW)
        
        if result.errors:
            typer.echo("\nErrors:")
            for error in result.errors:
                typer.secho(f"  • {error}", fg=typer.colors.RED)
        
        if not result.success:
            raise typer.Exit(1)
            
    except Exception as exc:
        typer.secho(f"❌ Remediation failed: {exc}", fg=typer.colors.RED)
        raise typer.Exit(1)
    
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
        typer.echo("  • Sync: completed")


@orchestrate_app.command("intelligent-upgrade")
def orchestrate_intelligent_upgrade(
    auto_apply_safe: bool = typer.Option(
        False,
        "--auto-apply-safe",
        help="Automatically apply safe upgrades",
    ),
    update_mirror: bool = typer.Option(
        True,
        "--update-mirror/--no-update-mirror",
        help="Update dependency mirror",
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
    """Execute intelligent upgrade workflow with mirror synchronization."""
    from chiron.orchestration import OrchestrationCoordinator, OrchestrationContext
    
    context = OrchestrationContext(dry_run=dry_run, verbose=verbose)
    coordinator = OrchestrationCoordinator(context)
    
    typer.echo("🚀 Starting intelligent upgrade workflow...")
    results = coordinator.intelligent_upgrade_workflow(
        auto_apply_safe=auto_apply_safe,
        update_mirror=update_mirror,
    )
    
    typer.echo("\n✅ Intelligent upgrade workflow complete")
    if results.get("advice"):
        typer.echo("  • Upgrade advice: generated")
    if results.get("auto_apply"):
        status = results["auto_apply"].get("status", "unknown")
        typer.echo(f"  • Auto-apply: {status}")
    if results.get("mirror_update"):
        typer.echo("  • Mirror: updated")
    if results.get("validation"):
        typer.echo("  • Validation: completed")
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
    
    context = OrchestrationContext(dry_run=dry_run, verbose=verbose)
    coordinator = OrchestrationCoordinator(context)
    
    artifact_path = artifact_dir.resolve()
    if not artifact_path.exists():
        typer.secho(f"Artifact directory not found: {artifact_path}", fg=typer.colors.RED)
        raise typer.Exit(1)
    
    typer.echo(f"Syncing artifacts from {artifact_path}...")
    results = coordinator.sync_remote_to_local(artifact_path, validate=validate)
    
    typer.echo("\n✅ Sync complete")
    if results.get("copy"):
        typer.echo("  • Artifacts: copied")
    if results.get("sync"):
        typer.echo("  • Dependencies: synced")
    if results.get("validation"):
        typer.echo("  • Validation: passed")


@orchestrate_app.command("air-gapped-prep")
def orchestrate_air_gapped_prep(
    include_models: bool = typer.Option(
        True,
        "--models/--no-models",
        help="Include model downloads",
    ),
    include_containers: bool = typer.Option(
        False,
        "--containers/--no-containers",
        help="Include container images",
    ),
    validate: bool = typer.Option(
        True,
        "--validate/--no-validate",
        help="Validate complete package",
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
    """Execute complete air-gapped preparation workflow.
    
    Prepares everything needed for offline deployment:
    - Dependency management and sync
    - Multi-platform wheelhouse building
    - Model downloads
    - Container images (optional)
    - Checksums and manifests
    - Complete validation
    
    This is the recommended workflow for air-gapped deployments.
    """
    from chiron.orchestration import OrchestrationCoordinator, OrchestrationContext
    
    context = OrchestrationContext(dry_run=dry_run, verbose=verbose)
    coordinator = OrchestrationCoordinator(context)
    
    typer.echo("🚀 Starting air-gapped preparation workflow...")
    typer.echo()
    
    results = coordinator.air_gapped_preparation_workflow(
        include_models=include_models,
        include_containers=include_containers,
        validate=validate,
    )
    
    typer.echo()
    typer.echo("=" * 60)
    typer.echo("Air-Gapped Preparation Summary")
    typer.echo("=" * 60)
    
    if results.get("dependencies"):
        typer.echo("✅ Dependencies: synced")
    
    if results.get("wheelhouse"):
        typer.echo("✅ Wheelhouse: built")
    else:
        typer.secho("❌ Wheelhouse: failed", fg=typer.colors.RED)
    
    if results.get("models"):
        typer.echo("✅ Models: downloaded")
    elif results.get("models") is None:
        typer.echo("⊘  Models: skipped")
    else:
        typer.secho("❌ Models: failed", fg=typer.colors.RED)
    
    if results.get("containers"):
        typer.echo("✅ Containers: prepared")
    elif results.get("containers") is None:
        typer.echo("⊘  Containers: skipped")
    else:
        typer.secho("❌ Containers: failed", fg=typer.colors.RED)
    
    if results.get("offline_package"):
        typer.echo("✅ Offline package: created")
    else:
        typer.secho("❌ Offline package: failed", fg=typer.colors.RED)
    
    if results.get("validation"):
        validation_ok = results["validation"].get("success", False)
        if validation_ok:
            typer.echo("✅ Validation: passed")
        else:
            typer.secho("⚠️  Validation: issues found", fg=typer.colors.YELLOW)
            if results.get("remediation"):
                typer.echo("   → Remediation recommendations generated")
    elif results.get("validation") is None:
        typer.echo("⊘  Validation: skipped")
    
    typer.echo()
    
    # Overall success check
    all_success = all(
        v is True or (isinstance(v, dict) and v.get("success"))
        for v in results.values()
        if v is not None
    )
    
    if all_success:
        typer.secho("✅ Air-gapped preparation complete!", fg=typer.colors.GREEN)
    else:
        typer.secho("⚠️  Air-gapped preparation completed with issues", fg=typer.colors.YELLOW)
        raise typer.Exit(1)


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
# GitHub Commands
# ============================================================================

@github_app.command("sync")
def github_sync(
    run_id: str = typer.Argument(
        ...,
        help="GitHub Actions workflow run ID",
    ),
    artifacts: list[str] = typer.Option(
        None,
        "--artifact",
        "-a",
        help="Specific artifacts to download (can be repeated)",
    ),
    output_dir: Path = typer.Option(
        Path("vendor/artifacts"),
        "--output-dir",
        "-o",
        help="Output directory for artifacts",
    ),
    sync_to: str = typer.Option(
        None,
        "--sync-to",
        help="Sync to vendor/, dist/, or var/ after download",
    ),
    merge: bool = typer.Option(
        False,
        "--merge",
        help="Merge with existing content (default: replace)",
    ),
    validate: bool = typer.Option(
        True,
        "--validate/--no-validate",
        help="Validate artifacts after download",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Verbose output",
    ),
) -> None:
    """Download and sync GitHub Actions artifacts.
    
    Downloads artifacts from a specific workflow run and optionally
    validates and syncs them to local directories.
    
    Example:
        chiron github sync 12345678 --artifact wheelhouse-linux --sync-to vendor
    """
    from chiron.github import GitHubArtifactSync
    
    syncer = GitHubArtifactSync(
        target_dir=output_dir,
        verbose=verbose,
    )
    
    # Download artifacts
    typer.echo(f"📥 Downloading artifacts from run {run_id}...")
    result = syncer.download_artifacts(
        run_id,
        artifacts or None,
        output_dir,
    )
    
    if not result.success:
        typer.secho("❌ Artifact download failed:", fg=typer.colors.RED)
        for error in result.errors:
            typer.secho(f"  - {error}", fg=typer.colors.RED)
        raise typer.Exit(1)
    
    typer.secho(f"✅ Downloaded {len(result.artifacts_downloaded)} artifacts", fg=typer.colors.GREEN)
    for name in result.artifacts_downloaded:
        typer.echo(f"  • {name}")
    
    # Validate if requested
    if validate:
        typer.echo("\n🔍 Validating artifacts...")
        all_valid = True
        
        for artifact_name in result.artifacts_downloaded:
            artifact_path = output_dir / artifact_name
            validation = syncer.validate_artifacts(artifact_path, "wheelhouse")
            
            if validation["valid"]:
                typer.secho(f"  ✅ {artifact_name}: Valid", fg=typer.colors.GREEN)
            else:
                typer.secho(f"  ⚠️  {artifact_name}: Issues found", fg=typer.colors.YELLOW)
                for error in validation["errors"]:
                    typer.secho(f"      - {error}", fg=typer.colors.RED)
                all_valid = False
        
        if not all_valid:
            typer.secho("\n⚠️  Some artifacts have validation issues", fg=typer.colors.YELLOW)
    
    # Sync if requested
    if sync_to:
        typer.echo(f"\n🔄 Syncing to {sync_to}/...")
        
        for artifact_name in result.artifacts_downloaded:
            artifact_path = output_dir / artifact_name
            success = syncer.sync_to_local(artifact_path, sync_to, merge)  # type: ignore
            
            if not success:
                typer.secho(f"Failed to sync {artifact_name}", fg=typer.colors.RED)
                raise typer.Exit(1)
        
        typer.secho(f"✅ Synced to {sync_to}/", fg=typer.colors.GREEN)


@github_app.command("validate")
def github_validate(
    artifact_dir: Path = typer.Argument(
        ...,
        help="Directory containing artifacts to validate",
    ),
    artifact_type: str = typer.Option(
        "wheelhouse",
        "--type",
        "-t",
        help="Artifact type: wheelhouse, offline-package, or models",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Verbose output",
    ),
) -> None:
    """Validate GitHub Actions artifacts.
    
    Checks artifact structure, manifest integrity, and content completeness.
    """
    from chiron.github import validate_artifacts
    
    if not artifact_dir.exists():
        typer.secho(f"❌ Directory not found: {artifact_dir}", fg=typer.colors.RED)
        raise typer.Exit(1)
    
    typer.echo(f"🔍 Validating {artifact_type} artifacts in {artifact_dir}...")
    
    validation = validate_artifacts(artifact_dir, artifact_type)  # type: ignore
    
    if validation["valid"]:
        typer.secho("✅ Validation passed", fg=typer.colors.GREEN)
        if validation.get("metadata"):
            typer.echo("\nMetadata:")
            for key, value in validation["metadata"].items():
                typer.echo(f"  {key}: {value}")
    else:
        typer.secho("❌ Validation failed", fg=typer.colors.RED)
        
        if validation.get("errors"):
            typer.echo("\nErrors:")
            for error in validation["errors"]:
                typer.secho(f"  - {error}", fg=typer.colors.RED)
        
        raise typer.Exit(1)
    
    if validation.get("warnings"):
        typer.echo("\nWarnings:")
        for warning in validation["warnings"]:
            typer.secho(f"  - {warning}", fg=typer.colors.YELLOW)


# ============================================================================
# Plugin Commands
# ============================================================================

plugin_app = typer.Typer(help="Plugin management commands")
app.add_typer(plugin_app, name="plugin")


@plugin_app.command("list")
def plugin_list() -> None:
    """List all registered Chiron plugins."""
    from chiron.plugins import list_plugins
    
    plugins = list_plugins()
    
    if not plugins:
        typer.echo("No plugins registered.")
        return
    
    typer.echo(f"Registered Plugins ({len(plugins)}):\n")
    for plugin in plugins:
        typer.echo(f"  • {plugin.name} v{plugin.version}")
        if plugin.description:
            typer.echo(f"    {plugin.description}")
        if plugin.author:
            typer.echo(f"    Author: {plugin.author}")
        typer.echo()


@plugin_app.command("discover")
def plugin_discover(
    entry_point: str = typer.Option(
        "chiron.plugins",
        "--entry-point",
        help="Entry point group to discover plugins from",
    )
) -> None:
    """Discover and register plugins from entry points."""
    from chiron.plugins import discover_plugins, register_plugin
    
    typer.echo(f"Discovering plugins from entry point: {entry_point}")
    
    plugins = discover_plugins(entry_point)
    
    if not plugins:
        typer.echo("No plugins discovered.")
        return
    
    typer.echo(f"\nDiscovered {len(plugins)} plugin(s):\n")
    for plugin in plugins:
        metadata = plugin.metadata
        typer.echo(f"  • {metadata.name} v{metadata.version}")
        register_plugin(plugin)
    
    typer.echo("\n✅ All plugins registered successfully")


# ============================================================================
# Telemetry Commands
# ============================================================================

telemetry_app = typer.Typer(help="Telemetry and observability commands")
app.add_typer(telemetry_app, name="telemetry")


@telemetry_app.command("summary")
def telemetry_summary() -> None:
    """Display telemetry summary for recent operations."""
    from chiron.telemetry import get_telemetry
    
    telemetry = get_telemetry()
    summary = telemetry.get_summary()
    
    typer.echo("=== Chiron Telemetry Summary ===\n")
    typer.echo(f"Total Operations: {summary['total']}")
    typer.echo(f"Success: {summary['success']}")
    typer.echo(f"Failure: {summary['failure']}")
    typer.echo(f"Avg Duration: {summary['avg_duration_ms']:.2f}ms")
    
    if summary['total'] > 0:
        success_rate = (summary['success'] / summary['total']) * 100
        typer.echo(f"Success Rate: {success_rate:.1f}%")


@telemetry_app.command("metrics")
def telemetry_metrics(
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output as JSON",
    )
) -> None:
    """Display detailed metrics for all operations."""
    from chiron.telemetry import get_telemetry
    
    telemetry = get_telemetry()
    metrics = telemetry.get_metrics()
    
    if not metrics:
        typer.echo("No metrics recorded.")
        return
    
    if json_output:
        import json
        data = [m.to_dict() for m in metrics]
        typer.echo(json.dumps(data, indent=2))
    else:
        typer.echo(f"=== Chiron Operations ({len(metrics)}) ===\n")
        for m in metrics:
            status = "✓" if m.success else "✗"
            typer.echo(f"{status} {m.operation}")
            typer.echo(f"  Duration: {m.duration_ms:.2f}ms")
            if m.error:
                typer.echo(f"  Error: {m.error}")
            typer.echo()


@telemetry_app.command("clear")
def telemetry_clear() -> None:
    """Clear all recorded telemetry metrics."""
    from chiron.telemetry import get_telemetry
    
    telemetry = get_telemetry()
    telemetry.clear_metrics()
    typer.echo("✅ Telemetry metrics cleared")


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
