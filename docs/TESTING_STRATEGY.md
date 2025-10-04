# Testing Strategy

This document describes Prometheus's comprehensive testing approach across unit, integration, contract, and end-to-end levels.

## Quick Reference

| Test Type       | Coverage Target             | Speed           | When to Run      |
| --------------- | --------------------------- | --------------- | ---------------- |
| **Unit**        | ≥80% overall, ≥90% critical | Fast (<30s)     | Every commit     |
| **Integration** | Key event flows             | Medium (~2 min) | Every PR         |
| **Contract**    | All schemas                 | Fast (<10s)     | Schema changes   |
| **E2E**         | Critical user paths         | Slow (~5 min)   | Release branches |

## Current Status

**Coverage**: 68% overall (target: 80%)  
**Tests**: 164 passing, 11 failing  
**Critical Path Coverage**: 90%+ (contracts, services)

See [CURRENT_STATUS.md](../CURRENT_STATUS.md) for latest metrics.

---

## Testing Philosophy

### Principles

1. **Test Behavior, Not Implementation** - Focus on contracts and outcomes, not internal details
2. **Fast Feedback** - Unit tests run in <30 seconds for rapid iteration
3. **Realistic Integration** - Test actual event flows across stage boundaries
4. **Offline by Default** - Tests don't require external services (use mocks/fixtures)
5. **Deterministic** - No flaky tests; seed randomness, freeze time, mock I/O

### Test Pyramid

```
        ╱╲
       ╱E2E╲        5-10 scenarios
      ╱──────╲
     ╱ Integ. ╲     20-30 flows
    ╱──────────╲
   ╱  Contract  ╲   All schemas
  ╱──────────────╲
 ╱     Unit       ╲ 80%+ coverage
╱──────────────────╲
```

**Unit** (70% of tests): Module-level behavior  
**Contract** (15%): Schema validation and compatibility  
**Integration** (10%): Cross-stage event flows  
**E2E** (5%): Full pipeline scenarios

---

## Test Organization

### Directory Structure

```
tests/
├── unit/                    # Module-level tests
│   ├── ingestion/
│   ├── retrieval/
│   ├── reasoning/
│   ├── decision/
│   ├── execution/
│   ├── monitoring/
│   ├── common/
│   ├── prometheus/          # CLI and orchestrator
│   └── scripts/             # Build and automation scripts
├── integration/             # Cross-stage flows
│   ├── test_pipeline_flow.py
│   ├── test_event_propagation.py
│   └── test_adapter_integration.py
├── contracts/               # Schema validation (planned)
│   ├── test_ingestion_events.py
│   ├── test_retrieval_events.py
│   └── test_schema_evolution.py
├── e2e/                     # Full pipeline scenarios (planned)
│   ├── test_basic_query.py
│   ├── test_offline_mode.py
│   └── test_error_recovery.py
├── fixtures/                # Shared test data
│   ├── events/
│   ├── documents/
│   └── configs/
└── conftest.py              # Shared pytest fixtures
```

### Naming Conventions

- **Test files**: `test_<module>.py`
- **Test functions**: `test_<behavior>_<scenario>()`
- **Fixtures**: `<resource>_fixture()` or just `<resource>()`

**Examples**:

```python
def test_ingestion_normalizes_markdown_with_metadata()
def test_retrieval_returns_empty_for_no_matches()
def test_decision_approves_when_policy_allows()
```

---

## Unit Tests

### Scope

Test individual modules in isolation with mocked dependencies.

### Guidelines

1. **One behavior per test** - Test a single assertion or outcome
2. **AAA Pattern** - Arrange (setup), Act (execute), Assert (verify)
3. **Mock external dependencies** - File I/O, HTTP calls, database access
4. **Use fixtures for common setup** - Share reusable test data
5. **Parametrize similar tests** - Use `@pytest.mark.parametrize` for variants

### Example

```python
import pytest
from ingestion.normalizers import MarkdownNormalizer

@pytest.fixture
def sample_markdown():
    return "# Title\n\nParagraph with **bold**."

def test_normalizer_extracts_title(sample_markdown):
    normalizer = MarkdownNormalizer()
    result = normalizer.normalize(sample_markdown)
    assert result.title == "Title"

def test_normalizer_preserves_formatting(sample_markdown):
    normalizer = MarkdownNormalizer()
    result = normalizer.normalize(sample_markdown)
    assert "**bold**" in result.content

@pytest.mark.parametrize("input,expected_title", [
    ("# First", "First"),
    ("## Second", "Second"),
    ("No header", None),
])
def test_normalizer_handles_various_headers(input, expected_title):
    normalizer = MarkdownNormalizer()
    result = normalizer.normalize(input)
    assert result.title == expected_title
```

### Running Unit Tests

```bash
# All unit tests
poetry run pytest tests/unit/

# Specific module
poetry run pytest tests/unit/ingestion/

# With coverage
poetry run pytest tests/unit/ --cov=ingestion --cov-report=html
```

---

## Integration Tests

### Scope

Test interactions between multiple stages via actual event flows.

### Guidelines

1. **Test event contracts** - Ensure stages communicate via defined schemas
2. **Use in-memory adapters** - Avoid external dependencies
3. **Verify side effects** - Check that events trigger expected actions
4. **Test error propagation** - Ensure failures are handled gracefully

### Example

```python
import pytest
from prometheus.orchestrator import PrometheusOrchestrator
from common.events import IngestionNormalized, RetrievalCompleted

def test_ingestion_to_retrieval_flow(tmp_path):
    """Verify ingestion events trigger retrieval."""
    config = {
        "ingestion": {"persistence": {"type": "memory"}},
        "retrieval": {"backend": "rapidfuzz"},
    }
    orchestrator = PrometheusOrchestrator(config)

    # Ingest a document
    doc_path = tmp_path / "test.md"
    doc_path.write_text("# Test\nContent")
    orchestrator.ingest(str(doc_path))

    # Verify retrieval can find it
    results = orchestrator.retrieve("test content")
    assert len(results) > 0
    assert "Content" in results[0].text
```

### Running Integration Tests

```bash
poetry run pytest tests/integration/
```

---

## Contract Tests

### Scope

Validate event schemas and ensure backward compatibility.

### Guidelines

1. **Test serialization roundtrips** - Ensure events can be serialized and deserialized
2. **Validate required fields** - Check that mandatory fields are present
3. **Test schema evolution** - Ensure old events still parse with new schemas
4. **Generate golden fixtures** - Save known-good events for regression testing

### Example (Planned)

```python
import pytest
from common.contracts import IngestionNormalized
from pydantic import ValidationError

def test_ingestion_normalized_requires_source():
    with pytest.raises(ValidationError):
        IngestionNormalized(
            # Missing required 'source' field
            content="Test",
            format="markdown",
        )

def test_ingestion_normalized_roundtrip():
    event = IngestionNormalized(
        source="test.md",
        content="Test",
        format="markdown",
    )
    serialized = event.model_dump_json()
    deserialized = IngestionNormalized.model_validate_json(serialized)
    assert deserialized == event

def test_ingestion_normalized_backwards_compatible(golden_event_v1):
    """Ensure current schema can parse v1 events."""
    event = IngestionNormalized.model_validate(golden_event_v1)
    assert event.source is not None
```

### Running Contract Tests

```bash
poetry run pytest tests/contracts/
```

---

## End-to-End Tests

### Scope

Test complete user scenarios through the full pipeline.

### Guidelines

1. **Test realistic workflows** - Mirror actual user journeys
2. **Use Docker Compose for services** - Spin up dependencies in CI
3. **Assert on final outcomes** - Verify end-user observable behavior
4. **Test error recovery** - Ensure system degrades gracefully

### Example (Planned)

```python
import pytest
from sdk import PrometheusClient

@pytest.mark.e2e
def test_basic_query_flow(prometheus_stack):
    """Test ingestion → retrieval → reasoning → decision → execution."""
    client = PrometheusClient(base_url=prometheus_stack.api_url)

    # Ingest a document
    client.ingest_url("https://example.com/article.html")

    # Run a query
    result = client.query("What is the main topic?")

    # Verify outcome
    assert result.status == "completed"
    assert len(result.evidence) > 0
    assert result.decision.approved is True
```

### Running E2E Tests

```bash
# Requires services running
cd infra && docker compose up -d
poetry run pytest tests/e2e/ -m e2e
```

---

## Test Coverage

### Current Coverage

Run coverage report:

```bash
poetry run pytest --cov=. --cov-report=html
open htmlcov/index.html
```

### Coverage Gaps (Prioritized)

1. **prometheus/remediation/** - 0-56% (needs tests)
2. **scripts/format_yaml.py** - 0% (needs tests)
3. **scripts/preflight_deps.py** - 0% (needs tests)
4. **execution/workflows.py** - Async stubs not tested

See [TODO-refactoring.md](../TODO-refactoring.md) Phase 1.3 for action items.

### Coverage Targets

- **Overall**: ≥80%
- **Contracts/Services**: ≥90%
- **Utilities/Scripts**: ≥70%

---

## Mocking & Fixtures

### Common Fixtures (in `conftest.py`)

```python
import pytest
from pathlib import Path

@pytest.fixture
def sample_docs(tmp_path):
    """Create sample documents for testing."""
    docs = []
    for i in range(3):
        doc = tmp_path / f"doc_{i}.md"
        doc.write_text(f"# Document {i}\nContent {i}")
        docs.append(doc)
    return docs

@pytest.fixture
def mock_llm(mocker):
    """Mock LLM calls to avoid external API dependencies."""
    mock = mocker.patch("reasoning.agents.LLMClient")
    mock.return_value.generate.return_value = "Mocked response"
    return mock

@pytest.fixture
def in_memory_config():
    """Configuration using only in-memory adapters."""
    return {
        "ingestion": {"persistence": {"type": "memory"}},
        "retrieval": {"backend": "rapidfuzz"},
        "execution": {"sync_target": "in-memory"},
    }
```

### Using pytest-mock

```bash
poetry add --group dev pytest-mock
```

```python
def test_with_mocked_http(mocker):
    mock_get = mocker.patch("requests.get")
    mock_get.return_value.status_code = 200
    mock_get.return_value.text = "<html>Mocked</html>"

    result = ingest_url("https://example.com")
    assert result.content == "Mocked"
```

---

## Performance Tests

### Scope

Ensure pipeline stages meet performance budgets (see [module-boundaries.md](module-boundaries.md)).

### Guidelines

1. **Use pytest-benchmark** - Measure execution time
2. **Test with realistic data** - Use representative corpora
3. **Regression detection** - Compare against baseline
4. **Profile slow tests** - Use `pytest --profile` or `py-spy`

### Example (Planned)

```python
import pytest

def test_ingestion_speed(benchmark, sample_large_doc):
    """Ensure ingestion completes within budget (<5s)."""
    normalizer = MarkdownNormalizer()
    result = benchmark(normalizer.normalize, sample_large_doc)
    assert result is not None

@pytest.mark.benchmark(group="retrieval")
def test_retrieval_latency(benchmark, populated_index):
    """Ensure retrieval query completes <500ms."""
    retriever = HybridRetriever(populated_index)
    result = benchmark(retriever.search, "test query")
    assert len(result) > 0
```

---

## CI Integration

### GitHub Actions Workflow

```yaml
- name: Run Tests
  run: |
    poetry run pytest tests/unit/ tests/integration/ \
      --cov=. \
      --cov-report=xml \
      --cov-report=term \
      --junitxml=test-results.xml

- name: Upload Coverage
  uses: codecov/codecov-action@v3
  with:
    files: ./coverage.xml
    fail_ci_if_error: true
```

### Quality Gates

Tests must pass for PR merge:

- ✅ All unit tests pass
- ✅ All integration tests pass
- ✅ Coverage doesn't decrease
- ✅ No new type errors

---

## Writing Good Tests

### DO ✅

- **Test public interfaces** - Not internal implementation details
- **Use descriptive names** - `test_retrieval_returns_sorted_by_relevance()`
- **Keep tests independent** - No shared state between tests
- **Use fixtures for setup** - Share reusable test data
- **Assert specific outcomes** - Not just "no error"
- **Test edge cases** - Empty input, max limits, invalid data

### DON'T ❌

- **Test private methods** - They're implementation details
- **Use time.sleep()** - Makes tests slow and flaky
- **Hardcode paths** - Use `tmp_path` fixture
- **Test multiple things** - One assertion per test (generally)
- **Ignore failing tests** - Fix or remove them
- **Commit commented-out tests** - Delete or fix them

---

## Troubleshooting

### Flaky Tests

If tests fail intermittently:

1. Check for time dependencies (`time.time()`, `datetime.now()`)
2. Look for race conditions (async, threads)
3. Verify mocks are properly isolated
4. Ensure temp files are cleaned up

**Fix**: Use `freezegun` for time, `pytest-asyncio` for async, isolated temp dirs.

### Slow Tests

If tests take too long:

1. Profile with `pytest --durations=10`
2. Mock expensive operations (I/O, network, model inference)
3. Use smaller test data
4. Run slow tests separately (`@pytest.mark.slow`)

### Import Errors

If tests can't import modules:

1. Verify `poetry install` completed
2. Check `PYTHONPATH` includes project root
3. Ensure `__init__.py` files exist
4. Check for circular imports

---

## Resources

- [pytest Documentation](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [pytest-benchmark](https://pytest-benchmark.readthedocs.io/)
- [Coverage.py](https://coverage.readthedocs.io/)
- [Test-Driven Development Guide](https://testdriven.io/)

---

## Next Steps

See [TODO-refactoring.md](../TODO-refactoring.md) for current testing initiatives:

- Phase 1.1: Fix 11 failing tests
- Phase 1.3: Increase coverage to 80%
- Phase 3.3: Add contract testing framework
- Phase 3.4: Add E2E integration tests with Docker

**Maintainers**: See [CODEOWNERS](../CODEOWNERS)  
**Last Updated**: January 2025
