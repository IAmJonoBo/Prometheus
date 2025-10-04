# Chiron Dependency Management

Comprehensive dependency management subsystem with frontier-grade security and governance.

## Overview

The `chiron/deps` module provides enterprise-grade dependency management with:

- **Hash-pinned constraints** for reproducible builds
- **SBOM generation** for compliance
- **Vulnerability scanning** with OSV
- **Artifact signing** with Sigstore
- **Policy enforcement** for governance
- **Portable bundles** for air-gapped deployment

## Module Structure

### Core Modules

#### Constraints (`constraints.py`) 🆕

Generate hash-pinned constraints for deterministic installations.

```python
from chiron.deps.constraints import generate_constraints

generate_constraints(
    project_root=Path("."),
    tool="uv",  # or "pip-tools"
    include_extras=["pii", "rag"],
)
```

**CLI:** `chiron deps constraints`

#### Supply Chain (`supply_chain.py`) 🆕

SBOM generation and vulnerability scanning.

```python
from chiron.deps.supply_chain import generate_sbom_and_scan

success, summary = generate_sbom_and_scan(
    project_root=Path("."),
    sbom_output=Path("sbom.json"),
    osv_output=Path("osv.json"),
    lockfile_path=Path("requirements.txt"),
    gate_max_severity="high",
)
```

**CLI:** `chiron deps scan`

#### Signing (`signing.py`) 🆕

Artifact signing with Sigstore cosign.

```python
from chiron.deps.signing import sign_wheelhouse_bundle

result = sign_wheelhouse_bundle(
    bundle_path=Path("wheelhouse-bundle.tar.gz"),
)
```

**CLI:** `chiron deps bundle --sign`

#### Policy (`policy.py`) 🆕

Policy engine for dependency governance.

```python
from chiron.deps.policy import load_policy, PolicyEngine

policy = load_policy(Path("configs/dependency-policy.toml"))
engine = PolicyEngine(policy)

violations = engine.check_upgrade_allowed(
    "torch", "2.3.0", "2.4.0"
)
```

**CLI:** `chiron deps policy`

#### Bundler (`bundler.py`) 🆕

Create portable wheelhouse bundles.

```python
from chiron.deps.bundler import create_wheelhouse_bundle

metadata = create_wheelhouse_bundle(
    wheelhouse_dir=Path("vendor/wheelhouse"),
    output_path=Path("wheelhouse-bundle.tar.gz"),
)
```

**CLI:** `chiron deps bundle`

### Existing Modules

#### Drift (`drift.py`)

Detect dependency drift between lock files and installed packages.

#### Sync (`sync.py`)

Synchronize dependencies across Poetry, pip, and project files.

#### Planner (`planner.py`)

Plan dependency upgrades with resolver verification.

#### Guard (`guard.py`)

Monitor and guard against unsafe dependency changes.

#### Upgrade Advisor (`upgrade_advisor.py`)

Intelligent upgrade recommendations with risk assessment.

#### Safe Upgrade (`safe_upgrade.py`)

Execute upgrades with rollback support.

#### Preflight (`preflight.py`)

Pre-deployment dependency checks.

#### Status (`status.py`)

Dependency status reporting.

#### Graph (`graph.py`)

Dependency graph visualization.

#### Mirror Manager (`mirror_manager.py`)

Manage local package mirrors.

#### Conflict Resolver (`conflict_resolver.py`)

Resolve dependency conflicts.

#### Verify (`verify.py`)

Verify dependency pipeline integration.

## Quick Start

### 1. Generate Hash-Pinned Constraints

```bash
chiron deps constraints --output constraints.txt --extras pii,rag
```

### 2. Scan for Vulnerabilities

```bash
chiron deps scan --lockfile requirements.txt --gate --max-severity high
```

### 3. Check Policy

```bash
chiron deps policy --package torch --upgrade-from 2.3.0 --version 2.4.0
```

### 4. Create Bundle

```bash
chiron deps bundle --wheelhouse vendor/wheelhouse --sign
```

## Complete Workflow

### Development

```bash
# Update dependency
poetry update numpy

# Regenerate constraints
chiron deps constraints

# Check policy
chiron deps policy --package numpy --version 2.0.0

# Scan vulnerabilities
chiron deps scan --lockfile constraints.txt

# Commit changes
git add .
git commit -m "Update numpy"
```

### Release

```bash
# Build wheelhouse with supply chain features
GENERATE_SUPPLY_CHAIN=true \
CREATE_BUNDLE=true \
COMMIT_SHA=$(git rev-parse HEAD) \
bash scripts/build-wheelhouse.sh vendor/wheelhouse

# Verify bundle
sha256sum -c wheelhouse-bundle.tar.gz.sha256
```

### Air-Gapped Deployment

```bash
# On online machine
chiron deps bundle --wheelhouse vendor/wheelhouse --sign

# Transfer to offline machine
# ...

# On offline machine
cosign verify-blob --signature bundle.tar.gz.sig bundle.tar.gz
tar -xzf bundle.tar.gz
pip install --no-index --find-links=wheelhouse -r wheelhouse/requirements.txt
```

## Configuration

### Policy Configuration

Create `configs/dependency-policy.toml`:

```toml
[dependency_policy]
default_allowed = true
max_major_version_jump = 1
require_security_review = true

[dependency_policy.allowlist.numpy]
version_ceiling = "2.9.0"
upgrade_cadence_days = 90

[dependency_policy.denylist.insecure-package]
reason = "Known security issues"
```

## CLI Reference

### `chiron deps constraints`

Generate hash-pinned constraints for reproducible builds.

**Options:**

- `--output`, `-o`: Output path (default: constraints.txt)
- `--tool`: Tool to use (uv or pip-tools)
- `--extras`: Comma-separated extras

**Example:**

```bash
chiron deps constraints --output constraints.txt --extras pii,rag --tool uv
```

### `chiron deps scan`

Scan dependencies for vulnerabilities.

**Options:**

- `--lockfile`, `-l`: Lockfile to scan (required)
- `--output`, `-o`: Output path for report
- `--gate`: Exit with error if vulnerabilities found
- `--max-severity`: Maximum severity to allow (critical, high, medium, low)

**Example:**

```bash
chiron deps scan --lockfile requirements.txt --gate --max-severity high
```

### `chiron deps bundle`

Create portable wheelhouse bundle.

**Options:**

- `--wheelhouse`, `-w`: Wheelhouse directory (default: vendor/wheelhouse)
- `--output`, `-o`: Output path (default: wheelhouse-bundle.tar.gz)
- `--sign`: Sign bundle with cosign

**Example:**

```bash
chiron deps bundle --wheelhouse vendor/wheelhouse --sign
```

### `chiron deps policy`

Check policy compliance.

**Options:**

- `--config`, `-c`: Policy config file
- `--package`, `-p`: Package name
- `--version`, `-v`: Version to check
- `--upgrade-from`: Check upgrade from version

**Example:**

```bash
chiron deps policy --package torch --upgrade-from 2.3.0 --version 2.4.0
```

### `chiron deps mirror` 🆕

Setup and manage private PyPI mirrors.

**Actions:**

- `setup`: Initialize mirror server
- `upload`: Upload wheelhouse to mirror
- `config`: Generate client configuration

**Options:**

- `--wheelhouse`, `-w`: Wheelhouse directory
- `--type`, `-t`: Mirror type (devpi, simple-http)
- `--host`: Server host
- `--port`: Server port

**Example:**

```bash
chiron deps mirror setup --type devpi --host localhost --port 3141
```

### `chiron deps oci` 🆕

Package wheelhouse as OCI artifacts.

**Actions:**

- `package`: Create OCI artifact layout
- `push`: Push to container registry
- `pull`: Pull from container registry

**Options:**

- `--bundle`, `-b`: Path to wheelhouse bundle
- `--repository`, `-r`: Repository name (org/wheelhouse)
- `--tag`, `-t`: Tag for artifact (default: latest)
- `--registry`: OCI registry URL (default: ghcr.io)
- `--sbom`: Path to SBOM file
- `--osv`: Path to OSV scan results

**Example:**

```bash
chiron deps oci push \
  --bundle wheelhouse-bundle.tar.gz \
  --repository org/prometheus-wheelhouse \
  --tag v1.0.0
```

### `chiron deps reproducibility` 🆕

Verify binary reproducibility of wheels.

**Actions:**

- `compute`: Calculate and save wheel digests
- `verify`: Verify against saved digests
- `compare`: Compare two wheel files

**Options:**

- `--wheelhouse`, `-w`: Wheelhouse directory
- `--digests`, `-d`: Digests file (default: wheel-digests.json)
- `--original`: Original wheel (for compare)
- `--rebuilt`: Rebuilt wheel (for compare)

**Example:**

```bash
chiron deps reproducibility compute --wheelhouse vendor/wheelhouse
chiron deps reproducibility verify --wheelhouse vendor/wheelhouse
```

### `chiron deps security` 🆕

Manage security constraints overlay for CVE backports.

**Actions:**

- `import-osv`: Import CVEs from OSV scan
- `generate`: Generate pip constraints file
- `check`: Check package version against constraints

**Options:**

- `--overlay`: Security overlay file (default: security-constraints.json)
- `--osv-file`: OSV scan results (for import-osv)
- `--output`, `-o`: Output constraints file (for generate)
- `--package`, `-p`: Package name (for check)
- `--version`, `-v`: Version (for check)

**Example:**

```bash
chiron deps security import-osv --osv-file vendor/wheelhouse/osv.json
chiron deps security generate --output security-constraints.txt
```

## Integration with CI/CD

### GitHub Actions

```yaml
- name: Generate constraints
  run: chiron deps constraints

- name: Scan vulnerabilities
  run: chiron deps scan --lockfile constraints.txt --gate

- name: Create bundle
  env:
    GENERATE_SUPPLY_CHAIN: true
    CREATE_BUNDLE: true
  run: bash scripts/build-wheelhouse.sh vendor/wheelhouse
```

See `.github/workflows/build-wheelhouse-frontier.yml` for complete example.

## Documentation

- **[Frontier Dependency Management](../../docs/chiron/FRONTIER_DEPENDENCY_MANAGEMENT.md)** - Complete guide
- **[Air-Gapped Deployment](../../docs/chiron/AIR_GAPPED_DEPLOYMENT.md)** - Offline deployment
- **[Implementation Summary](../../docs/chiron/CHIRON_UPGRADE_IMPLEMENTATION.md)** - Status and metrics
- **[Migration Guide](../../docs/chiron/MIGRATION_GUIDE_FRONTIER.md)** - Team migration

## Requirements

### Core

- Python 3.11+
- Poetry 1.8.3+

### Optional Tools

- **uv** - Fast constraint generation (recommended)
- **pip-tools** - Alternative constraint tool
- **cyclonedx-bom** - SBOM generation
- **osv-scanner** - Vulnerability scanning
- **cosign** - Artifact signing

### Installation

```bash
# Core tools
pip install uv cyclonedx-bom

# OSV Scanner
curl -L -o osv-scanner https://github.com/google/osv-scanner/releases/latest/download/osv-scanner_linux_amd64
chmod +x osv-scanner
sudo mv osv-scanner /usr/local/bin/

# Cosign
curl -L -o cosign https://github.com/sigstore/cosign/releases/latest/download/cosign-linux-amd64
chmod +x cosign
sudo mv cosign /usr/local/bin/
```

## Testing

Run tests:

```bash
poetry run pytest tests/unit/chiron/deps/
```

Test coverage:

- `test_constraints.py` - Constraints generation
- `test_policy.py` - Policy engine
- Additional tests for other modules

## Architecture

```
chiron/deps/
├── constraints.py          # Hash-pinned constraints
├── supply_chain.py         # SBOM + OSV scanning
├── signing.py              # Artifact signing
├── policy.py               # Policy engine
├── bundler.py              # Wheelhouse bundler
├── private_mirror.py       # PyPI mirror automation (NEW)
├── oci_packaging.py        # OCI artifact support (NEW)
├── reproducibility.py      # Binary reproducibility (NEW)
├── security_overlay.py     # CVE backport management (NEW)
├── drift.py                # Drift detection
├── sync.py                 # Dependency sync
├── planner.py              # Upgrade planning
├── guard.py                # Change monitoring
├── upgrade_advisor.py      # Upgrade recommendations
├── safe_upgrade.py         # Safe upgrade execution
├── preflight.py            # Pre-deployment checks
└── ...
```

## New Features Summary

### Private Mirror Automation (`private_mirror.py`)

- Automates devpi/Nexus setup
- Wheelhouse upload to mirrors
- Client configuration generation
- Support for simple HTTP mirrors

### OCI Packaging (`oci_packaging.py`)

- Packages wheelhouse as OCI artifacts
- ORAS integration for push/pull
- Includes SBOM and security metadata
- Compatible with GHCR, DockerHub, Artifactory

### Binary Reproducibility (`reproducibility.py`)

- Computes and verifies wheel digests
- Compares original vs rebuilt wheels
- Normalized comparison (ignores timestamps)
- Generates reproducibility reports

### Security Overlay (`security_overlay.py`)

- Imports CVEs from OSV scans
- Generates security constraint overlays
- Tracks safe version ranges
- Prevents major version jumps

## Contributing

When adding new features:

1. Follow existing module patterns
2. Add comprehensive docstrings
3. Include unit tests
4. Update CLI if adding user-facing features
5. Document in relevant guides

## License

See main repository LICENSE file.
