# ADR-0003: Automated Dependency Upgrade Ecosystem

## Status

Accepted

## Context

Prometheus requires a dependency management strategy that balances continuous freshness with stability, particularly for:

1. **Air-gapped deployments**: Offline installations must succeed without network access
2. **Cross-platform support**: Linux, macOS, Windows across Python 3.11 and 3.12
3. **Quality assurance**: Updates must pass comprehensive quality gates before promotion
4. **Developer velocity**: Manual dependency management creates bottlenecks
5. **Security posture**: CVE exposure increases with stale dependencies
6. **Build determinism**: Dependency hash changes should trigger cache invalidation

Previous approaches relied on manual Poetry updates followed by ad-hoc wheelhouse builds. This created several problems:

- Wheelhouse builds were platform-specific and not validated cross-platform
- No automated quality gates prevented broken updates from landing
- Offline verification was manual and inconsistent
- Cache invalidation was based on lock files, not the contract
- Security updates were slow to merge
- No observability into drift or upgrade opportunities

## Decision

We implement a guarded, automated dependency upgrade loop with six stages:

### 1. Single Contract Source of Truth

**Decision**: `configs/dependency-profile.toml` is authoritative for all dependency operations.

**Rationale**: 
- Centralizes governance policies (sdist allowlist, update windows, signatures)
- Enables contract hash-based caching for deterministic builds
- Surfaces ownership and review windows per package
- Documents exceptions and snoozes with expiration dates

### 2. Six-Stage Guarded Loop

**Pipeline**:
1. **SBOM Generation**: CycloneDX SBOM from poetry.lock
2. **Upgrade Evaluation**: Drift analysis + policy gate (scripts/dependency_drift.py, scripts/upgrade_guard.py)
3. **Matrix Build**: Cross-platform wheelhouse builds (Linux/macOS/Windows × Python 3.11/3.12)
4. **Offline Verification**: Test `pip install --no-index --find-links` on each platform
5. **Quality Gates**: Lint (ruff), test (pytest -n auto), coverage, security (pip-audit)
6. **Promotion**: Aggregate verified wheelhouses to vendor/

**Rationale**:
- Each stage can fail fast without affecting production
- Cross-platform verification ensures air-gapped parity before promotion
- Policy gates prevent drift from exceeding update windows
- Quality gates catch regressions before merge

### 3. CI Hardening

**Components**:
- **Quality Gates Job**: Dedicated parallel job for lint/test/security
- **Contract-Based Caching**: Cache key includes contract hash
- **Step Summaries**: Every stage emits structured GitHub step summaries
- **Parallel Tests**: `pytest -n auto` for faster feedback
- **Coverage Tracking**: XML and HTML reports uploaded as artifacts
- **Security Scanning**: pip-audit runs on every PR

**Rationale**:
- Parallel execution reduces CI time
- Contract hash invalidates caches when policy changes
- Summaries provide at-a-glance health status
- Coverage tracking prevents quality regression
- Security scanning surfaces CVEs early

### 4. Performance Optimizations

**Decisions**:
- Parallel test execution with pytest-xdist
- Concurrent platform builds in matrix strategy
- Contract hash-based caching with multi-level restore keys
- Deterministic artifact generation (sorted manifests, stable timestamps)

**Rationale**:
- Test parallelism reduces CI time by ~50%
- Matrix concurrency builds all platforms simultaneously
- Warm caches reduce redundant downloads
- Deterministic builds enable better cache hits

### 5. Renovate Automerge

**Configuration**:
- **Patch/Minor**: Automerge after 3 days if all quality gates pass
- **Major**: Require manual review (no automerge)
- **Security**: Fast-track with 0 days minimum age
- **Status Checks**: generate-sbom, evaluate-upgrades, quality-gates, verify-offline

**Rationale**:
- Low-risk updates merge automatically to reduce maintenance burden
- Major updates get human review for breaking changes
- Security updates prioritize speed over stability windows
- Required status checks enforce quality without manual intervention

### 6. Observability

**Artifacts**:
- Drift reports: Per-package severity (up-to-date, patch, minor, major, conflict)
- Assessment summaries: Upgrade guard markdown reports with policy context
- Quality gate results: Lint, test, coverage, security scan outputs
- Verification matrix: Per-platform offline install success

**Rationale**:
- Drift visibility enables proactive upgrade planning
- Policy context explains why upgrades were blocked/approved
- Quality metrics track project health over time
- Platform verification ensures air-gapped deployments succeed

### 7. Air-Gapped Parity

**Verification**:
- Fresh venv on each platform
- `pip install --no-index --find-links` only
- Binary-only wheelhouse requirement (sdist fallback fails build)
- Checksums and manifests for integrity verification

**Rationale**:
- True offline verification catches missing wheels early
- Binary-only policy ensures consistent behavior across environments
- Checksums enable supply chain integrity verification
- Manifests provide auditable dependency graphs

## Consequences

### Positive

1. **Reduced manual effort**: Patch and minor updates merge automatically
2. **Faster security response**: CVE fixes fast-tracked with 0-day minimum age
3. **Cross-platform confidence**: Matrix build catches platform-specific issues
4. **Deterministic builds**: Contract hash ensures cache consistency
5. **Observable drift**: Regular reports surface upgrade opportunities
6. **Air-gapped reliability**: Offline verification prevents deployment failures
7. **Quality enforcement**: Automated gates block regressions

### Negative

1. **CI complexity**: Six-stage pipeline requires more runner time
2. **Matrix cost**: Building 6 platforms increases build minutes
3. **Maintenance burden**: Contract file requires manual updates for policies
4. **Failure modes**: More stages means more potential failure points

### Mitigations

1. **Parallel execution**: Reduce wall-clock time despite more stages
2. **Fail-fast**: Each stage exits early on policy violations
3. **Caching**: Contract hash-based caching reduces redundant work
4. **Observability**: Step summaries provide quick debugging context
5. **Selective runs**: Workflows only run on relevant file changes

## Implementation

### Files Changed

- `.github/workflows/dependency-contract-upgrade.yml`: New guarded loop workflow
- `.github/workflows/ci.yml`: Enhanced with quality gates and contract caching
- `renovate.json`: Automerge configuration with status checks
- `pyproject.toml`: Added pytest-xdist for parallel tests
- `docs/dependency-upgrade-workflow.md`: Complete workflow guide
- `README.md`: Updated with dependency management section

### Existing Components Leveraged

- `scripts/dependency_drift.py`: Drift analysis (already exists)
- `scripts/upgrade_guard.py`: Policy gate (already exists)
- `scripts/build-wheelhouse.sh`: Platform wheelhouse builds (already exists)
- `configs/dependency-profile.toml`: Contract (already exists)

### New Components

- SBOM generation: CycloneDX generation from poetry.lock
- Cross-platform matrix: Build matrix with Linux/macOS/Windows
- Offline verification: Fresh venv + no-index install per platform
- Quality gates job: Parallel lint/test/security in CI
- Promotion stage: Wheelhouse aggregation and vendor/ update

## Alternatives Considered

### Manual Dependency Management

**Description**: Continue with manual Poetry updates and wheelhouse builds.

**Rejected because**:
- High maintenance burden
- Slow security response
- No cross-platform validation
- Inconsistent offline verification

### Dependabot Instead of Renovate

**Description**: Use GitHub's native Dependabot for updates.

**Rejected because**:
- Less flexible configuration
- No post-upgrade task support
- Limited automerge controls
- Cannot enforce custom quality gates

### Single-Platform Wheelhouse

**Description**: Build wheelhouse for one platform only (Linux).

**Rejected because**:
- Air-gapped deployments span multiple platforms
- macOS and Windows developers need offline capability
- Platform-specific issues go undetected
- Violates "tested in CI = safe in production" principle

### Manual Quality Gates

**Description**: Rely on human review for all dependency updates.

**Rejected because**:
- Does not scale with update frequency
- Introduces human error and delays
- Security updates should fast-track automatically
- Patch updates have low risk/high benefit ratio

## Notes

### Rollout Plan

1. **Phase 1**: Deploy workflow, disable automerge (manual trigger only)
2. **Phase 2**: Enable automerge for patch updates only
3. **Phase 3**: Add minor updates to automerge after confidence builds
4. **Phase 4**: Monitor for 2 weeks, tune policy as needed

### Monitoring

Track these metrics:

- Automerge success rate (target: >90% for patch updates)
- Time to merge security updates (target: <24 hours)
- CI build time per workflow (target: <30 minutes)
- Offline verification failure rate (target: <5%)
- Quality gate failure rate (target: trend down over time)

### Future Enhancements

1. **Type checking**: Add mypy/pyright to quality gates
2. **Load testing**: Add performance regression detection
3. **SBOM comparison**: Diff SBOMs across releases
4. **Contract validation**: Schema validation for dependency-profile.toml
5. **Temporal snapshot integration**: Automated dependency snapshots via Temporal schedules

## References

- [Dependency Upgrade Architecture](../dependency-upgrade-architecture.md)
- [Upgrade Guard Strategy](../upgrade-guard.md)
- [Dependency Upgrade Workflow](../dependency-upgrade-workflow.md)
- [Dependency Contract](../../configs/dependency-profile.toml)
