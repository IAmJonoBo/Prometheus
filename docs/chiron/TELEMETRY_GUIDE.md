# Chiron Telemetry Guide

## Overview

Chiron's telemetry system provides comprehensive observability for all subsystem operations. It tracks operation timing, success/failure rates, and integrates with OpenTelemetry for distributed tracing.

## Features

- **Operation Tracking**: Automatic timing of all operations
- **Success/Failure Metrics**: Track operation outcomes
- **Performance Monitoring**: Measure operation duration
- **OpenTelemetry Integration**: Distributed tracing support
- **Structured Logging**: Context-rich log messages
- **Summary Statistics**: Aggregate metrics and reports

## Basic Usage

### Track an Operation

```python
from chiron.telemetry import track_operation

# Using context manager (recommended)
with track_operation("dependency_scan", package="numpy"):
    # Your operation code
    scan_dependencies()

# Operation is automatically tracked with timing and success/failure
```

### Manual Tracking

```python
from chiron.telemetry import get_telemetry

telemetry = get_telemetry()

# Start tracking
metrics = telemetry.start_operation("package_build", target="wheelhouse")

try:
    # Your operation
    build_package()
    telemetry.complete_operation("package_build", success=True)
except Exception as e:
    telemetry.complete_operation("package_build", success=False, error=str(e))
```

## Viewing Metrics

### CLI Commands

**View summary:**

```bash
python -m chiron telemetry summary
```

Output:

```
=== Chiron Telemetry Summary ===

Total Operations: 45
Success: 43
Failure: 2
Avg Duration: 125.34ms
Success Rate: 95.6%
```

**View detailed metrics:**

```bash
python -m chiron telemetry metrics
```

Output:

```
=== Chiron Operations (45) ===

✓ dependency_scan
  Duration: 234.56ms

✓ package_build
  Duration: 1523.45ms

✗ upload_artifact
  Duration: 89.23ms
  Error: Connection timeout
```

**JSON output:**

```bash
python -m chiron telemetry metrics --json
```

**Clear metrics:**

```bash
python -m chiron telemetry clear
```

### Programmatic Access

```python
from chiron.telemetry import get_telemetry

telemetry = get_telemetry()

# Get all metrics
metrics = telemetry.get_metrics()
for m in metrics:
    print(f"{m.operation}: {m.duration_ms}ms (success: {m.success})")

# Get summary
summary = telemetry.get_summary()
print(f"Total: {summary['total']}, Success rate: {summary['success']}/{summary['total']}")

# Clear metrics
telemetry.clear_metrics()
```

## Advanced Features

### OpenTelemetry Integration

When OpenTelemetry is installed, telemetry automatically creates spans:

```python
from chiron.telemetry import track_operation

# Automatically creates an OpenTelemetry span
with track_operation("complex_workflow", workflow_id="abc123"):
    # Your code - span is active in this context
    perform_work()

# Span is automatically ended and exported
```

**Features with OpenTelemetry:**

- Distributed tracing across services
- Span attributes from metadata
- Exception recording in spans
- Integration with tracing backends (Jaeger, Zipkin, etc.)

### Custom Metadata

Add custom metadata to operations:

```python
with track_operation(
    "dependency_upgrade",
    package="numpy",
    from_version="1.20.0",
    to_version="1.21.0",
    strategy="conservative",
) as metrics:
    # Metadata is available in metrics
    upgrade_dependency()
```

Access metadata:

```python
telemetry = get_telemetry()
for m in telemetry.get_metrics():
    print(f"Operation: {m.operation}")
    print(f"Metadata: {m.metadata}")
```

### Nested Operations

Track nested operations:

```python
with track_operation("full_packaging_workflow"):
    with track_operation("collect_dependencies"):
        collect_deps()

    with track_operation("build_wheels"):
        build_wheels()

    with track_operation("create_archive"):
        create_archive()
```

## Integration Patterns

### With Chiron Deps Module

```python
from chiron.telemetry import track_operation
from chiron.deps import guard

with track_operation("dependency_guard_check"):
    result = guard.main(["--sbom", "sbom.json"])
    if result != 0:
        raise RuntimeError("Guard check failed")
```

### With Chiron Orchestration

```python
from chiron.telemetry import track_operation
from chiron.orchestration import OrchestrationCoordinator

with track_operation("full_dependency_workflow") as metrics:
    coordinator = OrchestrationCoordinator(context)
    result = coordinator.full_dependency_workflow()

    # Add workflow-specific metadata
    metrics.metadata["packages_upgraded"] = len(result.get("upgraded", []))
```

### With Chiron Packaging

```python
from chiron.telemetry import track_operation
from chiron.packaging import OfflinePackagingOrchestrator

with track_operation("offline_packaging", target="wheelhouse") as metrics:
    orchestrator = OfflinePackagingOrchestrator(config)
    result = orchestrator.execute()

    metrics.metadata["wheels_built"] = result.wheels_count
    metrics.metadata["size_mb"] = result.total_size_mb
```

## Configuration

### Enable/Disable Telemetry

Set environment variable:

```bash
export CHIRON_TELEMETRY_ENABLED=false
python -m chiron deps status  # Telemetry disabled
```

### Configure OpenTelemetry

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

# Configure OpenTelemetry
provider = TracerProvider()
processor = SimpleSpanProcessor(ConsoleSpanExporter())
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)

# Chiron telemetry will now use this configuration
from chiron.telemetry import track_operation

with track_operation("test"):
    print("This creates a span!")
```

## Best Practices

### 1. Use Context Managers

**Recommended:**

```python
with track_operation("operation_name"):
    do_work()
```

**Avoid:**

```python
telemetry.start_operation("operation_name")
do_work()
telemetry.complete_operation("operation_name", success=True)
```

Context managers automatically handle success/failure and cleanup.

### 2. Add Meaningful Metadata

**Good:**

```python
with track_operation(
    "dependency_scan",
    package="numpy",
    version="1.21.0",
    scan_type="security",
):
    scan()
```

**Poor:**

```python
with track_operation("scan"):
    scan()
```

### 3. Use Descriptive Operation Names

**Good:**

- `dependency_guard_check`
- `package_wheel_build`
- `artifact_upload_s3`

**Poor:**

- `check`
- `build`
- `upload`

### 4. Track Significant Operations

Track operations that:

- Take significant time (>100ms)
- Can fail
- Are important for debugging
- Need performance monitoring

Don't track:

- Simple getters/setters
- Trivial operations
- Hot loops

### 5. Clean Up Metrics Periodically

```python
from chiron.telemetry import get_telemetry

# In long-running processes, clear old metrics
telemetry = get_telemetry()
if len(telemetry.get_metrics()) > 1000:
    telemetry.clear_metrics()
```

## Troubleshooting

### Metrics Not Appearing

**Check if telemetry is enabled:**

```python
from chiron.telemetry import get_telemetry

telemetry = get_telemetry()
print(f"Metrics count: {len(telemetry.get_metrics())}")
```

**Verify operation completed:**

```python
with track_operation("test") as metrics:
    # Operation must exit this block for metrics to be recorded
    pass

# Now metrics are recorded
```

### OpenTelemetry Not Working

**Check installation:**

```bash
pip list | grep opentelemetry
```

**Install if missing:**

```bash
pip install opentelemetry-api opentelemetry-sdk
```

**Verify configuration:**

```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)
print(f"Tracer: {tracer}")
```

### High Memory Usage

**Clear metrics regularly:**

```bash
python -m chiron telemetry clear
```

**Or in code:**

```python
from chiron.telemetry import get_telemetry

telemetry = get_telemetry()
telemetry.clear_metrics()
```

## API Reference

### Functions

- `track_operation(operation: str, **metadata)` - Context manager for tracking operations
- `get_telemetry()` - Get global telemetry instance

### Classes

#### OperationMetrics

```python
@dataclass
class OperationMetrics:
    operation: str
    started_at: datetime
    completed_at: datetime | None
    duration_ms: float | None
    success: bool | None
    error: str | None
    metadata: dict[str, Any]

    def mark_complete(success: bool, error: str | None = None)
    def to_dict() -> dict[str, Any]
```

#### ChironTelemetry

```python
class ChironTelemetry:
    def start_operation(operation: str, **metadata) -> OperationMetrics
    def complete_operation(operation: str, success: bool = True, error: str | None = None)
    def get_metrics() -> list[OperationMetrics]
    def clear_metrics()
    def get_summary() -> dict[str, Any]
```

## Examples

### Complete Workflow Tracking

```python
from chiron.telemetry import track_operation

def full_workflow():
    with track_operation("full_workflow") as workflow_metrics:
        # Stage 1
        with track_operation("stage_1_preflight") as stage1:
            run_preflight()
            stage1.metadata["checks_passed"] = 10

        # Stage 2
        with track_operation("stage_2_build") as stage2:
            build_packages()
            stage2.metadata["packages_built"] = 25

        # Stage 3
        with track_operation("stage_3_validate") as stage3:
            validate_output()
            stage3.metadata["validation_errors"] = 0

        workflow_metrics.metadata["total_stages"] = 3

# View results
from chiron.telemetry import get_telemetry
telemetry = get_telemetry()
summary = telemetry.get_summary()
print(f"Workflow completed: {summary}")
```

### Error Handling with Telemetry

```python
from chiron.telemetry import track_operation

def risky_operation():
    with track_operation("risky_operation", retry_count=0) as metrics:
        try:
            perform_risky_work()
        except TemporaryError as e:
            # Retry logic
            metrics.metadata["retry_count"] += 1
            retry_work()
        except PermanentError as e:
            # Error is automatically recorded in telemetry
            raise
```

## See Also

- [Chiron Architecture](ARCHITECTURE.md)
- [Chiron Plugin Guide](PLUGIN_GUIDE.md)
- [OpenTelemetry Documentation](https://opentelemetry.io/docs/python/)
