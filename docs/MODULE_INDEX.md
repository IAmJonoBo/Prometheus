# Prometheus Module Index

This document provides a comprehensive index of all modules and their documentation. Each module has a README that describes its purpose, responsibilities, and usage.

## 📋 Navigation Quick Links

- [Current Status](../CURRENT_STATUS.md) - Project health and what works today
- [Architecture Overview](architecture.md) - System design and event flows
- [Module Boundaries](module-boundaries.md) - Detailed module contracts and dependencies
- [Getting Started](getting-started.md) - Development setup guide

---

## Core Pipeline Stages

These six stages form the event-driven pipeline backbone of Prometheus:

### 1. Ingestion

**Path**: [`/ingestion`](../ingestion/README.md)  
**Purpose**: Capture raw intelligence from heterogeneous sources and convert to normalized events  
**Responsibilities**:

- Source adapters (filesystem, web, synthetic)
- Document normalization and metadata extraction
- PII detection and masking (optional Presidio)
- Persistence (in-memory, SQLite, or external stores)
- Scheduler with concurrency control and rate limiting

**Key APIs**: `IngestionService`, connectors, schedulers, persistence adapters

---

### 2. Retrieval

**Path**: [`/retrieval`](../retrieval/README.md)  
**Purpose**: Assemble context for reasoning via hybrid lexical/semantic search  
**Responsibilities**:

- Lexical search (RapidFuzz)
- Vector search (Qdrant with Sentence-Transformers)
- Hybrid search (OpenSearch BM25)
- Cross-encoder reranking
- Query orchestration and result fusion

**Key APIs**: `RetrievalService`, search backends, embedders, rerankers

---

### 3. Reasoning

**Path**: [`/reasoning`](../reasoning/README.md)  
**Purpose**: Coordinate tool-assisted synthesis of evidence into plans and analyses  
**Responsibilities**:

- Agent orchestration (DSPy, Haystack planned)
- Tool calling and critique loops
- Evidence linking and citation tracking
- Placeholder deterministic agents (current)
- LLM integration (planned)

**Key APIs**: `ReasoningService`, agents, orchestrators

---

### 4. Decision

**Path**: [`/decision`](../decision/README.md)  
**Purpose**: Govern how proposed analyses become approved actions with audit trail  
**Responsibilities**:

- Policy evaluation and enforcement
- Decision criticality classification
- Approval workflow coordination
- Ledger recording for audit
- Risk scoring (planned)

**Key APIs**: `DecisionService`, policy engine, ledger

---

### 5. Execution

**Path**: [`/execution`](../execution/README.md)  
**Purpose**: Dispatch approved decisions to downstream systems and track activity  
**Responsibilities**:

- Adapter coordination (in-memory, Temporal, webhooks)
- Workflow definitions and scheduling
- Idempotent change tracking
- Integration with external systems

**Key APIs**: `ExecutionService`, adapters, workflows, schedules

---

### 6. Monitoring

**Path**: [`/monitoring`](../monitoring/README.md)  
**Purpose**: Provide feedback loops, telemetry aggregation, and incident handling  
**Responsibilities**:

- Metrics collection (Prometheus, OpenTelemetry)
- Health checks and diagnostics
- Alert routing and incident response
- Performance tracking across pipeline stages

**Key APIs**: `MonitoringService`, collectors, exporters

---

## Cross-Cutting Concerns

These modules provide shared capabilities across the pipeline:

### Common

**Path**: [`/common`](../common/README.md)  
**Purpose**: Shared contracts, event schemas, and utilities  
**Contents**:

- Event definitions (`contracts/`)
- Base classes and interfaces
- Validation helpers
- Immutable event schemas for stage communication

**Key APIs**: Event contracts, EventBus, shared utilities

---

### Model

**Path**: [`/model`](../model/README.md)  
**Purpose**: Model management, loading, and inference abstractions  
**Responsibilities**:

- Model registry and discovery
- Loading strategies (local, API, quantized)
- Gateway pattern for multi-provider support
- Model evaluation and benchmarking

**Key APIs**: Model loaders, inference clients, evaluation harness

---

### Observability

**Path**: [`/observability`](../observability/README.md)  
**Purpose**: OpenTelemetry instrumentation and telemetry export  
**Responsibilities**:

- Trace context propagation
- Span creation and enrichment
- Metric emission
- Log correlation with traces

**Key APIs**: Tracer, metrics, exporters

---

### Security

**Path**: [`/security`](../security/README.md)  
**Purpose**: Authentication, authorization, and data protection  
**Responsibilities**:

- PII tokenization and masking
- Encryption helpers
- Authorization policy hooks
- Audit logging (planned)

**Key APIs**: PII redactor, encryption utilities

---

### Governance

**Path**: [`/governance`](../governance/README.md)  
**Purpose**: Compliance, audit trail, and policy management scaffolding  
**Responsibilities**:

- Audit log formatting
- Compliance report generation
- Policy versioning and validation
- Data lineage tracking (planned)

**Key APIs**: Audit logger, compliance exporters

---

## Infrastructure & Deployment

### Infra

**Path**: [`/infra`](../infra/README.md)  
**Purpose**: Docker Compose stacks for local and staging environments  
**Contents**:

- PostgreSQL, OpenSearch, Qdrant configurations
- Temporal server and worker setup
- Prometheus + Grafana observability stack
- Development and production profiles

**Key Files**: `docker-compose.yml`, service configurations

---

### Configs

**Path**: [`/configs`](../configs/README.md)  
**Purpose**: Configuration profiles and schemas  
**Contents**:

- Default profiles (`defaults/`)
- Environment-specific overrides
- Configuration validation schemas
- Example configurations

**Key Files**: `pipeline.toml`, `pipeline_local.toml`

---

## APIs & Interfaces

### API

**Path**: [`/api`](../api/README.md)  
**Purpose**: FastAPI REST service exposing pipeline operations  
**Endpoints**:

- `/health` - Health check
- `/v1/pipeline/run` - Execute pipeline
- Additional endpoints planned

**Tech**: FastAPI, Pydantic, async/await

---

### SDK

**Path**: [`/sdk`](../sdk/README.md)  
**Purpose**: Python client library for external integrations  
**Capabilities**:

- HTTP client wrapper
- Typed request/response models
- Retry and error handling
- Usage examples

**Tech**: httpx, Pydantic

---

### CLI

**Path**: [`/prometheus`](../prometheus/README.md)  
**Purpose**: Typer-based command-line interface  
**Commands**:

- `prometheus pipeline` - Run pipeline
- `prometheus offline-package` - Create offline bundle
- `prometheus offline-doctor` - Validate offline readiness
- Additional commands in `cli.py`

**Tech**: Typer, Rich for output formatting

---

## User Interfaces

### Web

**Path**: [`/web`](../web/README.md)  
**Purpose**: Next.js-based web application (placeholder)  
**Status**: Skeleton structure, not production-ready  
**Planned Features**:

- Dashboard with metrics and analytics
- Interactive query builder
- Collaboration workspace
- Visualization library integration

**Tech**: Next.js App Router, TanStack Query, TailwindCSS

---

### Desktop

**Path**: [`/desktop`](../desktop/README.md)  
**Purpose**: Tauri-based desktop application (placeholder)  
**Status**: Skeleton structure, not production-ready  
**Planned Features**:

- Offline-first operation
- Local model execution
- System tray integration
- Cross-platform support

**Tech**: Tauri v2, Rust + WebView

---

### UX

**Path**: [`/ux`](../ux/README.md)  
**Purpose**: UX research, design artifacts, and accessibility guidelines  
**Contents**:

- User flows and wireframes
- Design system components
- Accessibility compliance (WCAG AA+)
- Usability testing results

---

## Development & Testing

### Tests

**Path**: [`/tests`](../tests/README.md)  
**Purpose**: Comprehensive test suite across all pipeline stages  
**Structure**:

- `unit/` - Module-level tests
- `integration/` - Cross-stage event flows
- `e2e/` - Full pipeline scenarios
- `contracts/` - Schema validation (planned)

**Tech**: pytest, pytest-asyncio, fixtures

**Coverage**: 68% overall, 90%+ on critical paths

---

### CI

**Path**: [`/CI`](../CI/README.md)  
**Purpose**: CI/CD workflows, caching, and artifact management  
**Workflows**:

- Build and test
- Quality gates (lint, type check, coverage)
- Artifact packaging and publishing
- Dependency scanning

**Tech**: GitHub Actions, Docker, poetry

---

## Chiron Subsystem (Developer Tooling)

### Chiron

**Path**: [`/chiron`](chiron/README.md)  
**Purpose**: Packaging, dependency management, and developer tooling subsystem  
**Responsibilities**:

- Offline packaging orchestration
- Dependency management (guard, upgrade, drift, sync, preflight)
- Automated remediation of packaging failures
- Unified workflow coordination
- Diagnostics and health checks
- GitHub Actions integration

**Modules**:

- `chiron/packaging/` — Offline packaging and metadata
- `chiron/deps/` — Dependency guard, upgrade, drift, sync, preflight
- `chiron/remediation/` — Wheelhouse and runtime fixes
- `chiron/orchestration/` — Workflow coordination
- `chiron/doctor/` — Diagnostics and validation
- `chiron/cli.py` — Unified CLI entry point

**Key Commands**:

- `python -m chiron version`
- `python -m chiron deps status`
- `python -m chiron deps constraints` — Hash-pinned constraints
- `python -m chiron deps scan` — Vulnerability scanning
- `python -m chiron deps bundle` — Portable wheelhouse bundles
- `python -m chiron deps policy` — Policy compliance
- `python -m chiron deps mirror` — Private PyPI mirrors 🆕
- `python -m chiron deps oci` — OCI artifact packaging 🆕
- `python -m chiron deps reproducibility` — Binary reproducibility 🆕
- `python -m chiron deps security` — Security overlay management 🆕
- `python -m chiron package offline`
- `python -m chiron doctor offline`
- `python -m chiron orchestrate full-dependency`

**Documentation**: [Chiron README](chiron/README.md), [Quick Reference](chiron/QUICK_REFERENCE.md)

**Note**: Chiron is architecturally separate from the Prometheus pipeline stages. Old imports from `prometheus.packaging`, `prometheus.remediation`, and `scripts/` are maintained via compatibility shims.

---

## Extensions & Plugins

### Plugins

**Path**: [`/plugins`](../plugins/README.md)  
**Purpose**: Optional capabilities packaged for isolated deployment  
**Status**: Infrastructure exists, plugin manifest schema defined  
**Planned Plugins**:

- Additional ingestion connectors
- Custom retrieval backends
- Specialized reasoning agents
- Integration adapters

**Tech**: Python package-based, manifest-driven discovery

---

### Collaboration

**Path**: [`/collaboration`](../collaboration/README.md)  
**Purpose**: Real-time collaboration features (CRDT, shared workspaces)  
**Status**: Placeholder for future development  
**Planned Features**:

- Yjs CRDT integration
- WebSocket sync server
- Conflict-free document editing
- Presence awareness

**Tech**: Yjs, y-websocket, IndexedDB

---

## Documentation

### Docs

**Path**: [`/docs`](README.md)  
**Purpose**: Comprehensive project documentation  
**Structure**:

- Architecture and design docs
- Developer guides and runbooks
- ADRs (Architecture Decision Records)
- API reference and tutorials
- Archive of legacy documentation

**Maintained By**: All contributors (see CODEOWNERS)

---

## Module Dependency Overview

```
┌─────────────┐
│     CLI     │◄───┐
└──────┬──────┘    │
       │           │
       ▼           │
┌─────────────┐   │
│  Prometheus │   │
│ Orchestrator│   │
└──────┬──────┘   │
       │           │
       ▼           │
┌──────────────────┴──────────────┐
│     Pipeline Stages             │
│ Ingestion → Retrieval → ...     │
└────────┬─────────────────────────┘
         │
         ▼
┌─────────────────────┐
│  Common Contracts   │
│  Observability      │
│  Security           │
└─────────────────────┘
```

See [dependency-graph.md](dependency-graph.md) for detailed module dependencies.

---

## Finding Your Way

### I want to...

**Add a new ingestion source**  
→ Start with [`/ingestion/README.md`](../ingestion/README.md)

**Improve search quality**  
→ See [`/retrieval/README.md`](../retrieval/README.md)

**Integrate an LLM**  
→ Check [`/reasoning/README.md`](../reasoning/README.md) and [`/model/README.md`](../model/README.md)

**Add approval workflows**  
→ Review [`/decision/README.md`](../decision/README.md)

**Connect to external systems**  
→ Explore [`/execution/README.md`](../execution/README.md)

**Add telemetry/metrics**  
→ Read [`/monitoring/README.md`](../monitoring/README.md) and [`/observability/README.md`](../observability/README.md)

**Build a plugin**  
→ See [`/plugins/README.md`](../plugins/README.md)

**Understand the architecture**  
→ Start with [architecture.md](architecture.md) and [module-boundaries.md](module-boundaries.md)

---

## Maintenance

This index is maintained as part of the living documentation. When adding new modules or significantly refactoring existing ones:

1. Update this index with the new structure
2. Ensure each module has a current README
3. Update [module-boundaries.md](module-boundaries.md) if interfaces change
4. Regenerate [dependency-graph.md](dependency-graph.md) if dependencies shift

**Last Updated**: January 2025  
**Maintainers**: See [CODEOWNERS](../CODEOWNERS)
