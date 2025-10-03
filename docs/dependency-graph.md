# Prometheus Dependency Graph

This diagram shows the internal dependencies between Prometheus modules.
Generated automatically by `scripts/generate_dependency_graph.py`.

## Module Dependencies

```mermaid
graph TD
    api[Api]
    common[Common]
    decision[Decision]:::pipeline
    execution[Execution]:::pipeline
    governance[Governance]
    ingestion[Ingestion]:::pipeline
    model[Model]
    monitoring[Monitoring]:::pipeline
    observability[Observability]
    prometheus[Prometheus]
    reasoning[Reasoning]:::pipeline
    retrieval[Retrieval]:::pipeline
    scripts[Scripts]
    sdk[Sdk]
    security[Security]

    api --> prometheus
    decision --> common
    execution --> common
    execution --> scripts
    ingestion --> common
    monitoring --> common
    prometheus --> common
    prometheus --> decision
    prometheus --> execution
    prometheus --> governance
    prometheus --> ingestion
    prometheus --> monitoring
    prometheus --> observability
    prometheus --> reasoning
    prometheus --> retrieval
    prometheus --> scripts
    reasoning --> common
    retrieval --> common
    scripts --> observability
    scripts --> prometheus
    sdk --> prometheus

    classDef pipeline fill:#e1f5ff,stroke:#01579b,stroke-width:2px
```

## Module Details

### Api
- Files: 4
- Internal dependencies: prometheus
- External dependencies: __future__, dataclasses, datetime, fastapi, functools, os, pathlib, pydantic, typing, uvicorn

### Common
- Files: 10
- External dependencies: __future__, collections, dataclasses, datetime, typing, uuid

### Decision
- Files: 2
- Internal dependencies: common
- External dependencies: __future__, dataclasses

### Execution
- Files: 6
- Internal dependencies: common, scripts
- External dependencies: __future__, asyncio, collections, dataclasses, datetime, importlib, json, logging, pathlib, requests, ...

### Governance
- Files: 4
- External dependencies: __future__, collections, dataclasses, datetime, typing

### Ingestion
- Files: 7
- Internal dependencies: common
- External dependencies: __future__, asyncio, collections, dataclasses, datetime, hashlib, httpx, json, pathlib, presidio_analyzer, ...

### Model
- Files: 6
- External dependencies: __future__, collections, dataclasses, pathlib, typing

### Monitoring
- Files: 4
- Internal dependencies: common
- External dependencies: __future__, collections, dataclasses, importlib, json, pathlib, typing

### Observability
- Files: 4
- External dependencies: __future__, collections, datetime, importlib, json, logging, opentelemetry, os, prometheus_client, socket, ...

### Prometheus
- Files: 17
- Internal dependencies: common, decision, execution, governance, ingestion, monitoring, observability, reasoning, retrieval, scripts
- External dependencies: __future__, argparse, collections, contextlib, copy, dataclasses, datetime, evaluation, fnmatch, functools, ...

### Reasoning
- Files: 2
- Internal dependencies: common
- External dependencies: __future__, dataclasses

### Retrieval
- Files: 5
- Internal dependencies: common
- External dependencies: __future__, argparse, collections, dataclasses, datetime, difflib, importlib, json, logging, math, ...

### Scripts
- Files: 16
- Internal dependencies: observability, prometheus
- External dependencies: __future__, argparse, ast, collections, concurrent, contextlib, dataclasses, datetime, fnmatch, hashlib, ...

### Sdk
- Files: 2
- Internal dependencies: prometheus
- External dependencies: __future__, dataclasses, pathlib

### Security
- Files: 4
- External dependencies: __future__, dataclasses, enum, os, typing
