# Architecture Refactoring TODO

This document tracks staged improvements for the architecture refactoring initiative.
Each item links to relevant ADRs, issues, and ownership.

## Completed ✅

- [x] Initial architecture assessment and coverage audit
- [x] Add mypy type checking infrastructure (`mypy.ini`)
- [x] Create dependency graph generator (`scripts/generate_dependency_graph.py`)
- [x] Generate initial dependency graph documentation (`docs/dependency-graph.md`)
- [x] Add CODEOWNERS file for ownership boundaries
- [x] Create ADR-0002 for type checking and dependency management
- [x] Enhance CI with quality-gates job (type checking, linting, coverage)
- [x] Update `.gitignore` to exclude test artifacts
- [x] Document module boundaries (`docs/module-boundaries.md`)

## Phase 1: Stabilization (Priority: High)

### 1.1 Fix Failing Tests 🔴

**Status**: Blocked by test failures  
**Owner**: Core team  
**Effort**: 2-4 hours  
**Dependencies**: None

- [ ] Fix 11 failing tests identified in baseline assessment
  - [ ] `tests/execution/test_schedules.py` — 2 async mock issues
  - [ ] `tests/unit/prometheus/test_cli_proxies.py` — 3 CLI proxy issues
  - [ ] `tests/unit/scripts/test_deps_status.py` — 1 signature mismatch
  - [ ] `tests/unit/scripts/test_offline_doctor.py` — 1 import error
  - [ ] `tests/unit/scripts/test_offline_package.py` — 3 import errors
  - [ ] `tests/unit/test_pipeline.py` — 1 module attribute error

**Acceptance Criteria**:

- All tests pass (`poetry run pytest`)
- No new test failures introduced
- Coverage remains ≥68%

---

### 1.2 Fix Type Checking Errors ⚠️

**Status**: In progress  
**Owner**: Core team  
**Effort**: 4-8 hours  
**Dependencies**: None

- [ ] Fix ~50 mypy errors in pipeline modules
  - [x] `common/events.py` — unused type ignore comment
  - [ ] `execution/workflows.py` — missing return type annotations for stubs
  - [ ] `ingestion/pii.py`, `connectors.py` — unused type ignore comments
  - [ ] `monitoring/collectors.py` — variable type alias issues
  - [ ] `retrieval/evaluation.py` — missing type annotations

**Acceptance Criteria**:

- `poetry run mypy common/ ingestion/ retrieval/ reasoning/ decision/ execution/
monitoring/` passes
- CI quality-gates job passes without type warnings
- Gradual migration plan documented in ADR-0002

---

### 1.3 Enforce Coverage Thresholds 📊

**Status**: Not started  
**Owner**: Core team  
**Effort**: 2-3 hours  
**Dependencies**: 1.1 (tests must pass first)

- [ ] Increase coverage threshold from 60% to 80% in CI
- [ ] Add per-module coverage requirements in `pyproject.toml`
- [ ] Identify and test uncovered critical paths:
  - [ ] `prometheus/remediation/` (currently 0-56%)
  - [ ] `scripts/format_yaml.py` (0%)
  - [ ] `scripts/preflight_deps.py` (0%)

**Acceptance Criteria**:

- Overall coverage ≥80%
- Critical paths (contracts, services) ≥90%
- CI fails on coverage regressions

---

## Phase 2: Quality Gates (Priority: Medium)

### 2.1 Add Performance Budgets 🚀

**Status**: Not started  
**Owner**: Performance team  
**Effort**: 1-2 days  
**Dependencies**: 1.1, 1.2

- [ ] Add pytest-benchmark for performance regression tests
- [ ] Define budgets per module (see `docs/module-boundaries.md` § Performance Budgets)
- [ ] Add CI job to fail on budget violations
- [ ] Document budget methodology in ADR

**Acceptance Criteria**:

- Performance tests run in CI
- Budgets enforced for ingestion, retrieval, reasoning, decision
- Regression alerts on Slack/email

---

### 2.2 Add Security Scanning 🔒

**Status**: Partial (SBOM exists)  
**Owner**: Security team  
**Effort**: 1 day  
**Dependencies**: None

- [ ] Add pip-audit to CI for vulnerability scanning
- [ ] Add Bandit for Python security linting
- [ ] Add Semgrep for pattern-based security checks
- [ ] Fail CI on high/critical vulnerabilities

**Acceptance Criteria**:

- Security scans run on every PR
- Vulnerability reports published to GitHub Security tab
- False positives documented in `.bandit` config

---

### 2.3 Add Dependency Drift Monitoring 📦

**Status**: Tooling exists (`scripts/dependency_drift.py`)  
**Owner**: DevOps team  
**Effort**: 4 hours  
**Dependencies**: None

- [ ] Add CI job to run `scripts/dependency_drift.py` weekly
- [ ] Auto-create issues for outdated dependencies
- [ ] Document upgrade policy in `docs/dependency-governance.md`

**Acceptance Criteria**:

- Weekly drift reports in GitHub Actions
- Auto-created issues for security updates
- Upgrade policy enforced via Renovate/Dependabot

---

## Phase 3: Advanced Refactoring (Priority: Low)

### 3.1 Extract Shared Utilities 🔧

**Status**: Not started  
**Owner**: Architecture team  
**Effort**: 2-3 days  
**Dependencies**: 1.1, 1.2

- [ ] Audit `scripts/` and `prometheus/` for duplicate utilities
- [ ] Extract to `common/helpers/` or new `prometheus/lib/` module
- [ ] Update imports and deprecate old paths
- [ ] Document in ADR

**Current Duplication**:

- JSON loading/validation across `scripts/`
- Path resolution patterns in `ingestion/`, `scripts/`
- Retry logic in multiple modules

**Acceptance Criteria**:

- ≥3 utility modules extracted
- All call sites migrated
- No duplicate logic detected by linter

---

### 3.2 Introduce Dependency Injection 💉

**Status**: Not started  
**Owner**: Architecture team  
**Effort**: 1 week  
**Dependencies**: 1.1, 1.2, 3.1

- [ ] Add lightweight DI framework (e.g., `python-dependency-injector`)
- [ ] Refactor `PrometheusOrchestrator` to use DI container
- [ ] Replace hard-coded adapters with runtime injection
- [ ] Document DI patterns in `docs/developer-experience.md`

**Acceptance Criteria**:

- Orchestrator uses DI container
- Adapters injected via configuration
- Test mocking simplified
- ADR documenting DI choice

---

### 3.3 Add Contract Testing 📜

**Status**: Not started  
**Owner**: QA team  
**Effort**: 1 week  
**Dependencies**: 1.1, 1.2

- [ ] Add Pact or similar contract testing framework
- [ ] Define contracts for all `common/contracts/` events
- [ ] Add CI job to validate contracts on schema changes
- [ ] Document contract evolution policy in ADR

**Acceptance Criteria**:

- Contract tests for all event schemas
- CI fails on breaking contract changes
- Migration helpers auto-generated
- ADR documenting contract versioning

---

### 3.4 Add E2E Integration Tests 🧪

**Status**: Partial (smoke tests exist)  
**Owner**: QA team  
**Effort**: 1-2 weeks  
**Dependencies**: 1.1, 1.2

- [ ] Add Docker Compose stack for E2E environment
- [ ] Add `pytest-docker` fixtures for service orchestration
- [ ] Create E2E test suite exercising full pipeline
- [ ] Add CI job for E2E tests (triggered on release branches)

**Acceptance Criteria**:

- ≥5 E2E scenarios covering critical paths
- E2E tests run in CI on release branches
- Docker stack documented in `docs/testing.md`

---

## Phase 4: Observability and Monitoring (Priority: Medium)

### 4.1 Add Distributed Tracing 🔍

**Status**: Partial (OpenTelemetry configured)  
**Owner**: Observability team  
**Effort**: 1 week  
**Dependencies**: 1.1, 1.2

- [ ] Add trace context propagation across stages
- [ ] Instrument all pipeline stages with spans
- [ ] Add Jaeger/Tempo backend for trace collection
- [ ] Add trace sampling and export configuration

**Acceptance Criteria**:

- Traces span entire pipeline execution
- Trace IDs logged in all events
- Jaeger UI accessible in local/staging environments
- Sampling rate configurable per environment

---

### 4.2 Add SLO/SLI Monitoring 📈

**Status**: Not started  
**Owner**: SRE team  
**Effort**: 1 week  
**Dependencies**: 4.1

- [ ] Define SLOs for each pipeline stage (see `docs/module-boundaries.md`)
- [ ] Implement SLI metric collection
- [ ] Add Grafana dashboards for SLO tracking
- [ ] Add alerting for SLO violations

**Acceptance Criteria**:

- SLOs defined in code (e.g., OpenSLO spec)
- Grafana dashboards auto-provisioned
- Alerts fire on SLO breaches
- Error budgets tracked

---

### 4.3 Add Cost Tracking 💰

**Status**: Not started  
**Owner**: FinOps team  
**Effort**: 1 week  
**Dependencies**: 4.1

- [ ] Add cost sampling to monitoring events
- [ ] Track model inference costs (tokens, compute)
- [ ] Track storage costs (ingestion, retrieval indexes)
- [ ] Add cost dashboard and budgets

**Acceptance Criteria**:

- Cost per pipeline run tracked
- Cost breakdown by stage in dashboard
- Budget alerts configured
- Cost optimization recommendations auto-generated

---

## Phase 5: Documentation and DX (Priority: Low)

### 5.1 Add API Documentation 📚

**Status**: Partial (docstrings exist)  
**Owner**: Documentation team  
**Effort**: 3-4 days  
**Dependencies**: 1.1, 1.2

- [ ] Add Sphinx or MkDocs for API documentation
- [ ] Auto-generate docs from docstrings
- [ ] Add tutorials and examples
- [ ] Publish docs to GitHub Pages

**Acceptance Criteria**:

- API docs auto-generated from code
- Docs published at `https://IAmJonoBo.github.io/Prometheus/`
- Tutorials cover common use cases
- Docs updated on every release

---

### 5.2 Add Developer Onboarding 👨‍💻

**Status**: Partial (`README-dev-setup.md` exists)  
**Owner**: DX team  
**Effort**: 1 week  
**Dependencies**: 5.1

- [ ] Create interactive onboarding tutorial
- [ ] Add VS Code dev container configuration
- [ ] Add IntelliJ/PyCharm run configurations
- [ ] Document common troubleshooting scenarios

**Acceptance Criteria**:

- New contributors can run pipeline in <15 minutes
- Dev container works out-of-box
- IDE configurations committed to repo
- Troubleshooting guide covers ≥10 common issues

---

### 5.3 Add Architecture Decision Log Automation 🤖

**Status**: Not started  
**Owner**: Architecture team  
**Effort**: 2 days  
**Dependencies**: None

- [ ] Add ADR template generator script
- [ ] Add ADR linter to validate format
- [ ] Add CI check to ensure new ADRs follow template
- [ ] Auto-link ADRs to issues/PRs

**Acceptance Criteria**:

- ADR template in `.github/ADR_TEMPLATE.md`
- Script generates ADR with metadata pre-filled
- CI validates ADR format
- ADRs automatically linked in PR descriptions

---

## Metrics and Success Criteria

### Current Baseline (October 2025)

- **Tests**: 164 passing, 11 failing
- **Coverage**: 68% overall
- **Type errors**: ~50 across pipeline modules
- **Cyclic dependencies**: 1 (acceptable; see ADR-0002)
- **CI runtime**: ~10-15 minutes

### Target State (Q1 2026)

- **Tests**: All passing, ≥200 total tests
- **Coverage**: ≥80% overall, ≥90% critical paths
- **Type errors**: 0 (strict mode enabled)
- **Cyclic dependencies**: ≤1 (documented in ADRs)
- **CI runtime**: <20 minutes with full quality gates
- **SLO attainment**: ≥99.5% per stage
- **Documentation**: Complete API docs, tutorials, ADRs
- **Developer onboarding**: <15 minutes to first run

## Issue Tracking

All TODO items will be tracked as GitHub issues with labels:

- `refactor` — architectural refactoring work
- `phase-1`, `phase-2`, etc. — staged rollout phases
- `priority-high`, `priority-medium`, `priority-low`
- `type-checking`, `testing`, `observability`, `docs`

## References

- [ADR-0001: Initial Architecture](./docs/ADRs/ADR-0001-initial-architecture.md)
- [ADR-0002: Type Checking and Dependency Management](./docs/ADRs/ADR-0002-type-checking-dependency-management.md)
- [Module Boundaries](./docs/module-boundaries.md)
- [Dependency Graph](./docs/dependency-graph.md)
- [Prometheus Brief](./Prometheus Brief.md)
