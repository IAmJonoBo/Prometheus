# New Workflow Integration Checklist

Use this checklist when adding a new GitHub workflow to ensure proper integration with the existing pipeline architecture.

## Pre-Development

- [ ] Review [docs/workflow-orchestration.md](./workflow-orchestration.md) for architecture
- [ ] Review [docs/cross-workflow-integration.md](./cross-workflow-integration.md) for patterns
- [ ] Identify cross-cutting concerns with existing workflows
- [ ] Determine if reusable workflows or composite actions are appropriate
- [ ] Check if similar functionality already exists in another workflow

## Workflow Configuration

### Basic Structure

- [ ] Add descriptive workflow name
- [ ] Configure appropriate triggers (push, PR, schedule, workflow_dispatch)
- [ ] Set appropriate permissions (principle of least privilege)
- [ ] Configure concurrency controls if needed
- [ ] Add path filters to reduce unnecessary runs

### Environment Setup

- [ ] Use `setup-python-poetry` composite action for Python/Poetry setup

  ```yaml
  - uses: ./.github/actions/setup-python-poetry
    with:
      python-version: "3.12"
      poetry-version: "1.8.3"
  ```

- [ ] Set standard environment variables:

  ```yaml
  env:
    POETRY_NO_INTERACTION: "1"
    PYTHONIOENCODING: utf-8
  ```

- [ ] Configure appropriate runners (ubuntu-latest, container, matrix)

### Composite Action Usage

- [ ] Use `build-wheelhouse` for wheelhouse generation

  ```yaml
  - uses: ./.github/actions/build-wheelhouse
    with:
      output-dir: "dist/wheelhouse"
      extras: "pii,observability,rag,llm,governance,integrations"
      include-dev: "true"
      validate: "true"
  ```

- [ ] Use `verify-artifacts` for artifact validation
  ```yaml
  - uses: ./.github/actions/verify-artifacts
    with:
      artifact-dir: "dist"
      fail-on-warnings: "false"
  ```

### Artifact Management

- [ ] Name artifacts uniquely with workflow/run context:

  ```yaml
  name: ${{ github.workflow }}-${{ github.run_id }}
  ```

- [ ] Set appropriate retention days:
  - Production artifacts: 30 days
  - Transient/CI artifacts: 7 days
  - Development/testing: 1-3 days

- [ ] Add cleanup job if generating many artifacts:

  ```yaml
  cleanup:
    needs: [main-job]
    if: github.event_name != 'pull_request'
    # Keep last 5, delete older
  ```

- [ ] Upload artifacts with appropriate conditions:
  ```yaml
  if: always()  # For debug artifacts
  if: success()  # For production artifacts
  ```

### Error Handling

- [ ] Use `continue-on-error: true` for non-critical steps
- [ ] Add appropriate warning/error annotations:

  ```yaml
  echo "::warning::Descriptive warning message"
  echo "::error::Descriptive error message"
  ```

- [ ] Generate GitHub Step Summary for key information:
  ```yaml
  echo "## Summary" >> "$GITHUB_STEP_SUMMARY"
  ```

## Integration

### Dependency Coordination

- [ ] Document required repository secrets/variables
- [ ] Check for conflicts with existing workflows
- [ ] Add workflow dependencies if needed (`needs:`)
- [ ] Configure appropriate job dependencies within workflow

### Shared Resources

- [ ] Reference shared configuration files from `configs/`
- [ ] Use shared scripts from `scripts/`
- [ ] Follow Poetry version standard (1.8.3)
- [ ] Follow Python version standard (3.12)

### Testing

- [ ] Test workflow on feature branch first
- [ ] Verify artifact upload/download works
- [ ] Check GitHub Step Summary renders correctly
- [ ] Test with workflow_dispatch if applicable
- [ ] Verify cleanup jobs work correctly
- [ ] Test failure scenarios

## Documentation

### Code Documentation

- [ ] Add descriptive comments at workflow and job level
- [ ] Document all workflow_dispatch inputs
- [ ] Document required secrets/variables
- [ ] Add inline comments for complex logic

### Integration Documentation

- [ ] Update [docs/workflow-orchestration.md](./workflow-orchestration.md) with new workflow
- [ ] Update [docs/cross-workflow-integration.md](./cross-workflow-integration.md) if sharing artifacts
- [ ] Update [CI/README.md](../CI/README.md) if relevant to CI pipeline
- [ ] Add workflow to repository README if user-facing

### Diagrams

- [ ] Add workflow to architecture diagrams if significant
- [ ] Update artifact flow diagrams if producing artifacts
- [ ] Document job dependencies visually if complex

## Security & Compliance

### Security Review

- [ ] Review all `run:` blocks for command injection vulnerabilities
- [ ] Never echo secrets to logs
- [ ] Use `${{ secrets.NAME }}` for sensitive values
- [ ] Minimize permissions (prefer `contents: read`)
- [ ] Review third-party actions for security

### Best Practices

- [ ] Pin third-party actions to SHA or major version

  ```yaml
  uses: actions/checkout@v5  # Good
  uses: actions/checkout@8ade135  # Better (SHA)
  ```

- [ ] Use `set -euo pipefail` in bash scripts
- [ ] Validate inputs before use
- [ ] Sanitize user-provided inputs

## Performance

### Optimization

- [ ] Use caching where appropriate (pip, Poetry, npm, etc.)
- [ ] Minimize checkout depth (`fetch-depth: 1` if possible)
- [ ] Use `skip-` flags to avoid unnecessary work
- [ ] Consider matrix builds for parallelization
- [ ] Skip LFS if not needed (`lfs: false`)

### Resource Management

- [ ] Set appropriate job timeouts
- [ ] Consider self-hosted runners for intensive tasks
- [ ] Monitor workflow duration and optimize bottlenecks
- [ ] Review artifact sizes and optimize if large

## Monitoring & Observability

### Metrics

- [ ] Add OpenTelemetry spans if using observability framework
- [ ] Generate summary statistics in Step Summary
- [ ] Log key metrics (duration, artifact size, wheel count, etc.)

### Notifications

- [ ] Add Slack notifications for critical workflows (optional)
- [ ] Configure appropriate failure alerts
- [ ] Add status badge to README if user-facing

### Debugging

- [ ] Add debug mode via workflow_dispatch input
- [ ] Preserve logs on failure
- [ ] Upload debug artifacts on failure
- [ ] Add tee to capture command output

## Final Review

### Pre-Merge Checklist

- [ ] All tests pass on feature branch
- [ ] Documentation updated and reviewed
- [ ] No secrets in workflow file
- [ ] Follows repository conventions
- [ ] Peer review completed
- [ ] No merge conflicts with main

### Post-Merge Verification

- [ ] Workflow runs successfully on main
- [ ] Artifacts generated correctly
- [ ] GitHub Step Summary displays properly
- [ ] Cleanup jobs execute as expected
- [ ] No breaking changes to other workflows

## Example: Minimal Workflow Template

```yaml
name: Example Workflow
# Brief description of what this workflow does

on:
  push:
    branches: [main]
    paths:
      - "relevant/**"
  pull_request:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read

env:
  POETRY_NO_INTERACTION: "1"

jobs:
  example-job:
    name: Example job description
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v5
        with:
          fetch-depth: 0

      - name: Setup Python and Poetry
        uses: ./.github/actions/setup-python-poetry
        with:
          python-version: "3.12"
          poetry-version: "1.8.3"

      - name: Run example task
        run: |
          echo "Running example task"
          # Your logic here

      - name: Upload artifacts
        uses: actions/upload-artifact@v4
        with:
          name: example-${{ github.run_id }}
          path: output/
          retention-days: 7
          if-no-files-found: warn
```

## Additional Resources

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Composite Actions Guide](https://docs.github.com/en/actions/creating-actions/creating-a-composite-action)
- [Workflow Syntax Reference](https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions)
- [Security Hardening Guide](https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions)
