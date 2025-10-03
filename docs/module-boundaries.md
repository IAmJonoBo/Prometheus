# Module Architecture and Boundaries

This document defines the module structure, public APIs, and architectural boundaries
for the Prometheus Strategy OS. It complements `docs/architecture.md` and
`docs/dependency-graph.md`.

## Overview

Prometheus follows a **modular, event-driven architecture** with six core pipeline
stages that communicate via immutable event contracts. Each stage is isolated in its
own package with well-defined responsibilities and minimal cross-dependencies.

```
┌─────────────────────────────────────────────────────────────────┐
│                       Prometheus Pipeline                        │
├─────────────┬─────────────┬─────────────┬─────────────┬─────────┤
│  Ingestion  │  Retrieval  │  Reasoning  │   Decision  │Execution│
│             │             │             │             │         │
│ connectors  │   hybrid    │orchestrator │   policy    │temporal │
│ schedulers  │   search    │   chains    │   ledger    │webhooks │
│ PII redact  │  reranking  │  synthesis  │  approval   │dispatch │
└─────────────┴─────────────┴─────────────┴─────────────┴─────────┘
      │              │              │              │           │
      └──────────────┴──────────────┴──────────────┴───────────┘
                              │
                    ┌─────────▼──────────┐
                    │  common/contracts  │
                    │  (Event Schemas)   │
                    └────────────────────┘
                              │
                    ┌─────────▼──────────┐
                    │    Monitoring      │
                    │   (Observability)  │
                    └────────────────────┘
```

## Core Principles

1. **Events are the API**: Stages communicate exclusively through immutable events
   defined in `common/contracts/`. Direct function calls between stages are forbidden.

2. **Stage isolation**: Each pipeline stage owns its domain logic, storage, and
   implementation details. Cross-stage imports (except contracts) indicate
   architectural violations.

3. **Dependency inversion**: Stages depend on `common/contracts/`, not on each other.
   The `prometheus/` orchestrator wires stages together at runtime.

4. **Plugin architecture**: Extensions live in `plugins/` with manifests, tests,
   and isolated dependencies.

5. **Observability by default**: All stages emit telemetry via `observability/`
   hooks (metrics, traces, structured logs).

## Module Boundaries

### Pipeline Stages (Core)

#### `ingestion/`
**Responsibility**: Ingest data from diverse sources, normalize, detect PII, persist.

**Public API**:
- `IngestionService` — coordinates connectors and scheduling
- `FilesystemConnector`, `WebConnector`, `SyntheticConnector` — adapters
- `PIIRedactor` — optional PII detection/masking

**Emits**: `IngestionNormalised` events

**Dependencies**: `common/contracts/`, optional `presidio-analyzer`

**Ownership**: Ingestion team (see `CODEOWNERS`)

---

#### `retrieval/`
**Responsibility**: Hybrid search (lexical + vector + reranking) over normalised corpus.

**Public API**:
- `RetrievalService` — query coordination
- `InMemoryRetriever` — baseline implementation
- `build_hybrid_retriever()` — factory for OpenSearch + Qdrant + cross-encoder

**Emits**: `RetrievalContextBundle` events

**Dependencies**: `common/contracts/`, optional `opensearch-py`, `qdrant-client`, `sentence-transformers`

**Ownership**: Retrieval team

---

#### `reasoning/`
**Responsibility**: Orchestrate LLM chains, synthesise insights, build rationale.

**Public API**:
- `ReasoningService` — deterministic placeholder (model gateway evolving)

**Emits**: `ReasoningAnalysisProposed` events

**Dependencies**: `common/contracts/`, `model/gateways`

**Ownership**: Reasoning team

---

#### `decision/`
**Responsibility**: Apply policy checks, classify decision types, record ledger entries.

**Public API**:
- `DecisionService` — policy stub (approves when actions exist)

**Emits**: `DecisionRecorded` events

**Dependencies**: `common/contracts/`

**Ownership**: Decision team

---

#### `execution/`
**Responsibility**: Dispatch approved plans to executors (Temporal, webhooks, in-memory).

**Public API**:
- `ExecutionService` — adapter coordinator
- `TemporalExecutionAdapter`, `WebhookExecutionAdapter` — concrete dispatchers
- `workflows.py` — Temporal workflow definitions
- `schedules.py` — schedule management

**Emits**: `ExecutionPlanDispatched` events

**Dependencies**: `common/contracts/`, optional `temporalio`, `scripts/` (runtime only)

**Known Issue**: Runtime imports from `scripts/` create acceptable cycle
(see ADR-0002)

**Ownership**: Execution team

---

#### `monitoring/`
**Responsibility**: Collect telemetry, route metrics to sinks, emit feedback loops.

**Public API**:
- `MonitoringService` — telemetry coordinator
- `build_collector()` — factory for Prometheus Pushgateway integration
- `GrafanaDashboard` — dashboard provisioning

**Emits**: `MonitoringSignal` events

**Dependencies**: `common/contracts/`, optional `prometheus-client`, `opentelemetry-sdk`

**Ownership**: Monitoring team

---

### Cross-Cutting Concerns

#### `common/`
**Responsibility**: Shared contracts, event system, utilities.

**Submodules**:
- `contracts/` — all event schemas (`BaseEvent`, stage-specific events)
- `events.py` — `EventBus`, `EventFactory`
- `helpers.py` — stage-agnostic utilities

**Public API**: All exports from `common/contracts/`

**Dependencies**: None (except standard library and `pydantic`)

**Constraints**: Must remain stage-agnostic. Stage-specific logic belongs in
the stage package.

**Ownership**: Architecture team

---

#### `model/`
**Responsibility**: Unified model gateway for open-weight LLMs.

**Public API**:
- `ModelGateway` — abstract interface
- `LlamaCppProvider`, `VLLMProvider` — concrete backends
- `SentenceTransformerEmbeddings` — embedding adapter

**Dependencies**: optional `llama-cpp-python`, `vllm`, `sentence-transformers`

**Ownership**: Model team

---

#### `observability/`
**Responsibility**: Configure logging, metrics, tracing for all stages.

**Public API**:
- `configure_logging()`, `configure_metrics()`, `configure_tracing()`

**Dependencies**: `prometheus-client`, `opentelemetry-sdk`

**Ownership**: Observability team

---

#### `security/`
**Responsibility**: Authentication, secrets management, policy enforcement.

**Public API**:
- `AuthManager`, `SecretsManager`, `PolicyEngine` (placeholders)

**Dependencies**: optional `openfga-sdk`, `python-keycloak`

**Ownership**: Security team

---

#### `governance/`
**Responsibility**: Lineage tracking, audit trails, compliance reporting.

**Public API**:
- `LineageEvent` — PROV-O compatible lineage records

**Dependencies**: `common/contracts/`

**Ownership**: Governance team

---

### Orchestration and Interfaces

#### `prometheus/`
**Responsibility**: CLI, configuration, orchestrator wiring, dry-run mode.

**Public API**:
- `PrometheusOrchestrator` — runtime coordinator
- `PrometheusConfig`, `RuntimeConfig` — configuration schemas
- `cli.py` — Typer CLI entrypoint

**Dependencies**: All pipeline stages, `common/`, `observability/`, `execution/`, `scripts/`

**Ownership**: Core team

---

#### `api/`
**Responsibility**: FastAPI REST interface for pipeline operations.

**Public API**:
- `/pipeline` endpoints for query/status
- `bootstrap.py` — application factory

**Dependencies**: `prometheus/`, `fastapi`, `uvicorn`

**Ownership**: API team

---

#### `scripts/`
**Responsibility**: Automation utilities (offline packaging, dependency management).

**Public API**:
- `generate_dependency_graph.py`, `sync-dependencies.py`, `upgrade_guard.py`, etc.

**Dependencies**: `prometheus/`, `observability/`, optional `temporalio`

**Ownership**: DevOps team

---

#### `sdk/`
**Responsibility**: Client library for external integrations.

**Public API**:
- `PrometheusClient` — HTTP client wrapper

**Dependencies**: `prometheus/`, `httpx`

**Ownership**: SDK team

---

## Dependency Rules

### Allowed Dependencies

1. **Pipeline stages** → `common/contracts/` ✅
2. **`prometheus/` orchestrator** → all stages ✅
3. **`api/`** → `prometheus/` ✅
4. **`scripts/`** → `prometheus/`, `observability/` ✅
5. **`sdk/`** → `prometheus/` ✅
6. **Stages** → `model/`, `observability/`, `security/` (with optional guards) ✅

### Forbidden Dependencies

1. **Pipeline stage A** → **Pipeline stage B** ❌ (use events instead)
2. **`common/`** → any pipeline stage ❌ (must stay agnostic)
3. **Cross-stage circular imports** ❌ (except runtime function-local; see ADR-0002)

## Public APIs and Interfaces

Each module exposes its public API via `__init__.py` and `__all__`. Internal
modules prefixed with `_` are private.

### Stage Service Interface

All pipeline stages implement a common service pattern:

```python
@dataclass
class StageService:
    """Abstract stage service."""
    
    def process(self, event: InputEvent) -> OutputEvent:
        """Process input and emit output event."""
        ...
```

### Event Contract Interface

All events extend `BaseEvent`:

```python
@dataclass(slots=True, kw_only=True)
class BaseEvent:
    meta: EventMeta
    # Stage-specific fields...
```

## Testing Strategy

- **Unit tests**: `tests/unit/<module>/` test module internals
- **Integration tests**: `tests/integration/` test event flows across stages
- **Contract tests**: `tests/contracts/` validate event schema compatibility
- **E2E tests**: `tests/e2e/` test full pipeline runs

Coverage targets:
- Critical paths (contracts, services): ≥90%
- Stage implementations: ≥80%
- Utilities, scripts: ≥70%

## Performance Budgets

- **Ingestion**: <5s per document (average)
- **Retrieval**: <500ms for top-k query
- **Reasoning**: <10s for synthesis (quantised models)
- **Decision**: <100ms for policy check
- **Execution**: <1s for dispatch
- **Monitoring**: <50ms for metric emission

## Security Boundaries

- **PII redaction**: Required in `ingestion/` before persistence
- **Tenant isolation**: Enforced via `meta.tenant_id` in events
- **Audit logs**: All decision events written to immutable ledger
- **Secrets**: Never logged; injected via environment variables

## Migration and Deprecation

When breaking changes are needed:

1. **Announce** in `docs/ADRs/` with migration timeline
2. **Deprecate** old API with warnings (one minor version)
3. **Migrate** call sites with automated refactoring
4. **Remove** deprecated API (next major version)

## Tooling

- **Dependency graph**: `poetry run python scripts/generate_dependency_graph.py --check-cycles`
- **Type checking**: `poetry run mypy <module>/ --config-file mypy.ini`
- **Linting**: `poetry run ruff check`
- **Coverage**: `poetry run pytest --cov=. --cov-fail-under=80`

## References

- `docs/architecture.md` — implementation snapshot and guiding principles
- `docs/dependency-graph.md` — generated module dependency visualization
- `docs/ADRs/` — architectural decision records
- `Prometheus Brief.md` — original requirements and vision
- `CODEOWNERS` — ownership boundaries
