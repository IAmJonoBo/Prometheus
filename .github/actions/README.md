# Composite Actions

This directory contains reusable composite actions for GitHub workflows in the Prometheus project.

## Available Actions

### setup-python-poetry

Standardizes Python and Poetry installation across all workflows.

**Location**: `.github/actions/setup-python-poetry/`

**Purpose**: Ensures consistent Python and Poetry versions, reducing duplication and drift.

**Inputs**:

- `python-version` (optional, default: "3.12"): Python version to install
- `poetry-version` (optional, default: "1.8.3"): Poetry version to install
- `cache-pip` (optional, default: "true"): Enable pip caching
- `install-poetry-export` (optional, default: "false"): Install poetry-plugin-export
- `working-directory` (optional, default: "."): Working directory for commands

**Outputs**:

- `poetry-version`: Installed Poetry version
- `python-version`: Installed Python version

**Example Usage**:

```yaml
- name: Setup Python and Poetry
  uses: ./.github/actions/setup-python-poetry
  with:
    python-version: "3.12"
    poetry-version: "1.8.3"
    cache-pip: "true"
    install-poetry-export: "true"
```

**Benefits**:

- Single source of truth for Poetry version
- Automatic pip upgrade
- Consistent verification across workflows
- Optional plugin installation

**Used By**:

- ci.yml (build, quality-gates jobs)
- dependency-preflight.yml
- dependency-orchestration.yml
- offline-packaging-optimized.yml (dependency-suite job)

---

### build-wheelhouse

Encapsulates wheelhouse building for offline installations.

**Location**: `.github/actions/build-wheelhouse/`

**Purpose**: Provides consistent wheelhouse generation with validation and manifest creation.

**Inputs**:

- `output-dir` (optional, default: "dist/wheelhouse"): Output directory
- `extras` (optional, default: "pii,observability,rag,llm,governance,integrations"): Extras to include
- `include-dev` (optional, default: "true"): Include development dependencies
- `include-pip-audit` (optional, default: "true"): Include pip-audit for offline security scanning
- `create-archive` (optional, default: "false"): Create tar.gz archive
- `validate` (optional, default: "true"): Run offline doctor validation

**Outputs**:

- `wheelhouse-path`: Path to generated wheelhouse
- `wheel-count`: Number of wheels generated

**Example Usage**:

```yaml
- name: Build wheelhouse
  uses: ./.github/actions/build-wheelhouse
  with:
    output-dir: "dist/wheelhouse"
    extras: "pii,observability,rag,llm,governance,integrations"
    include-dev: "true"
    include-pip-audit: "true"
    validate: "true"
```

**Features**:

- Calls `scripts/build-wheelhouse.sh` with consistent parameters
- Adds pip-audit for offline security scanning
- Generates comprehensive manifest.json
- Includes platform_manifest.json data if available
- Validates wheelhouse with offline_doctor.py
- Creates GitHub Step Summary

**Used By**:

- ci.yml (build job)
- dependency-preflight.yml (rehearsal)
- offline-packaging-optimized.yml (dependency-suite job)

---

### verify-artifacts

Standardizes artifact verification across workflows.

**Location**: `.github/actions/verify-artifacts/`

**Purpose**: Provides consistent validation with configurable failure modes.

**Inputs**:

- `artifact-dir` (optional, default: "dist"): Directory to verify
- `run-offline-doctor` (optional, default: "true"): Run offline_doctor.py
- `run-verify-script` (optional, default: "true"): Run verify_artifacts.sh
- `fail-on-warnings` (optional, default: "false"): Fail job on warnings

**Outputs**:

- `validation-status`: Overall status (pass/warn/fail/skipped)

**Example Usage**:

```yaml
- name: Verify artifacts
  uses: ./.github/actions/verify-artifacts
  with:
    artifact-dir: "dist"
    run-offline-doctor: "true"
    run-verify-script: "true"
    fail-on-warnings: "false"
```

**Features**:

- Verifies artifact directory exists
- Runs offline_doctor.py validation (table format)
- Runs verify_artifacts.sh script
- Checks for BUILD_INFO file
- Generates comprehensive GitHub Step Summary
- Configurable failure behavior

**Used By**:

- ci.yml (build job)
- offline-packaging-optimized.yml (dependency-suite job)

## Design Principles

### 1. Composability

Each action does one thing well and can be combined with others:

```yaml
- uses: ./.github/actions/setup-python-poetry
- uses: ./.github/actions/build-wheelhouse
- uses: ./.github/actions/verify-artifacts
```

### 2. Consistency

All actions follow the same patterns:

- Clear input/output specifications
- Consistent error handling
- GitHub Step Summary generation
- Shell script safety (set -euo pipefail)

### 3. Flexibility

Actions provide sensible defaults but allow customization:

- Optional inputs with defaults
- Configurable behavior via inputs
- Continue-on-error support where appropriate

### 4. Observability

Actions provide visibility into their operation:

- GitHub Step Summary generation
- Clear log output
- Status outputs for downstream logic

## Creating New Composite Actions

When creating a new composite action:

1. **Identify duplication** across workflows (3+ occurrences)
2. **Extract common logic** into a reusable action
3. **Define clear inputs/outputs** with sensible defaults
4. **Add error handling** with meaningful messages
5. **Generate summaries** in GitHub Step Summary
6. **Document thoroughly** in this README
7. **Test** with multiple workflows before merging

### Template

```yaml
name: Action Name
description: Brief description of what the action does

inputs:
  param1:
    description: Description of param1
    required: false
    default: "default-value"

outputs:
  output1:
    description: Description of output1
    value: ${{ steps.step-id.outputs.output1 }}

runs:
  using: composite
  steps:
    - name: Step 1
      id: step-id
      shell: bash
      run: |
        # Your logic here
        echo "output1=value" >> "$GITHUB_OUTPUT"
```

## Testing Composite Actions

### Local Testing

Composite actions are harder to test locally since they use GitHub-specific features. Best practices:

1. **Test in feature branch**: Push to a feature branch and trigger workflows
2. **Use workflow_dispatch**: Add manual trigger to test workflows
3. **Check outputs**: Verify outputs are correct in workflow logs
4. **Test edge cases**: Try with different input combinations

### Integration Testing

Before merging composite action changes:

1. Test with each workflow that uses the action
2. Verify GitHub Step Summary renders correctly
3. Check artifact generation/validation
4. Test failure scenarios
5. Verify outputs are usable by downstream steps

## Versioning

Composite actions in this repository:

- **No versioning**: Always use latest from the same branch
- **Branch-based**: Use `uses: ./.github/actions/action-name`
- **No tags**: Not needed for same-repo actions

For external consumption (if needed in future):

- Follow semantic versioning
- Tag releases (v1.0.0, v1.1.0, etc.)
- Maintain CHANGELOG.md

## Troubleshooting

### Action Not Found

**Error**: `Error: Unable to resolve action ./.github/actions/action-name`

**Causes**:

1. Action directory doesn't exist
2. action.yml file missing or misnamed
3. Workflow triggered before action merged

**Solutions**:

1. Verify action directory exists: `.github/actions/action-name/`
2. Verify action.yml exists (not action.yaml)
3. Use correct branch in testing

### Invalid action.yml

**Error**: `Error: Action configuration is invalid`

**Causes**:

1. YAML syntax error
2. Missing required fields (name, description, runs)
3. Invalid input/output definitions

**Solutions**:

1. Validate YAML syntax
2. Check required fields are present
3. Verify input/output structure

### Step Failure

**Error**: Step in composite action fails

**Causes**:

1. Shell script error
2. Missing dependency
3. Wrong working directory

**Solutions**:

1. Add `set -euo pipefail` to bash scripts
2. Check dependencies are installed before use
3. Verify working-directory is correct

## Best Practices

### Do's ✅

- Use composite actions for logic used 3+ times
- Provide sensible defaults for all inputs
- Generate GitHub Step Summary for key information
- Use `shell: bash` for all run steps
- Add clear error messages with `echo "::error::..."`
- Test with multiple workflows before merging
- Document in this README

### Don'ts ❌

- Don't use composite actions for single-use logic
- Don't hard-code values that should be inputs
- Don't ignore errors (use proper error handling)
- Don't assume dependencies are installed
- Don't use `shell: python` (install Python first)
- Don't add version tags for same-repo actions

## References

- [GitHub Composite Actions Documentation](https://docs.github.com/en/actions/creating-actions/creating-a-composite-action)
- [Workflow Syntax Reference](https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions)
- [Workflow Orchestration Guide](../../docs/workflow-orchestration.md)
- [Cross-Workflow Integration Guide](../../docs/cross-workflow-integration.md)
