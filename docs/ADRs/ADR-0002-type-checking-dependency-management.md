# ADR-0002: Type Checking and Dependency Management

## Status

Accepted

## Context

During the architecture refactoring audit (October 2025), we assessed the quality
of the codebase's type safety, modularity, and dependency management practices.
The assessment revealed:

### Strengths

- Clean modular architecture with pipeline stages communicating via immutable
  contracts in `common/contracts/`
- Extensive use of type annotations (Python 3.12+ `from __future__ import annotations`)
- Well-isolated stage modules with minimal cross-dependencies
- Strong test coverage (68% overall, with critical paths >90%)

### Gaps

- No automated type checking (mypy/pyright) in CI pipeline
- One circular dependency: `prometheus` → `execution` → `scripts` → `prometheus`
- Coverage thresholds not enforced in CI
- Missing formal dependency graph documentation

## Decision

We will:

1. **Add mypy type checking** with strict mode for `common/` and gradual
   strictness for other modules, integrated into CI pipeline
2. **Document the circular dependency** as acceptable since it occurs via
   runtime function-local imports in `execution/workflows.py` calling utility
   scripts
3. **Generate dependency graph** automatically via `scripts/generate_dependency_graph.py`
   and keep it current in docs
4. **Add CODEOWNERS** file to establish ownership boundaries
5. **Enhance CI** to enforce type checking, coverage thresholds (≥80% for
   critical paths), and dependency graph validation

### Circular Dependency Analysis

The identified cycle (`prometheus` → `execution` → `scripts` → `prometheus`)
is **acceptable** because:

- It occurs via function-local imports in `execution/workflows.py` (lines 276, 280)
- The imports are deferred until workflow execution, not at module load time
- Breaking the cycle would require extracting shared utilities into `common/`,
  which would violate the principle that `common/` should be stage-agnostic
- The workflow legitimately needs to orchestrate dependency management scripts

### Type Checking Strategy

**Immediate (strict)**:

- `common/` (contracts, utilities)
- New code in all modules

**Gradual migration**:

- `ingestion/`, `retrieval/`, `reasoning/`, `decision/`, `execution/`, `monitoring/`
- Set `disallow_incomplete_defs = True` initially
- Progress toward `disallow_untyped_defs = True` per module

**Excluded**:

- Generated code
- Third-party libraries without type stubs (configured in mypy.ini)

## Consequences

### Benefits

- Type errors caught before runtime
- Better IDE support and refactoring confidence
- Dependency boundaries clearly documented and monitored
- Ownership boundaries established via CODEOWNERS

### Costs

- Initial type checking failures may require annotation fixes
- CI runtime increases slightly (~30s for type checking)
- Dependency graph must be regenerated when module structure changes

### Migration Path

1. ✅ Add mypy.ini configuration with gradual strictness
2. ✅ Add mypy to dev dependencies
3. ✅ Create dependency graph generator script
4. ✅ Generate initial dependency graph documentation
5. ✅ Add CODEOWNERS file
6. ⏭ Enhance CI workflow with type checking job
7. ⏭ Fix initial type checking errors
8. ⏭ Add coverage threshold enforcement
9. ⏭ Document in developer-experience.md

## References

- [PEP 484 – Type Hints](https://peps.python.org/pep-0484/)
- [mypy documentation](https://mypy.readthedocs.io/)
- Prometheus Brief.md § Developer Experience
- docs/architecture.md § Module contracts
