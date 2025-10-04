# Frontier-Grade Dependency Management

This guide documents the frontier-grade dependency and wheelhouse management system implemented according to `chiron/CHIRON_UPGRADE_PLAN.md`.

## Overview

The enhanced system provides:
- **Hash-pinned constraints** for reproducible builds
- **SBOM generation** with CycloneDX
- **Vulnerability scanning** with OSV Scanner
- **Artifact signing** with Sigstore cosign
- **Policy enforcement** for dependency governance
- **Portable wheelhouse bundles** for air-gapped deployment

## Quick Start

### Generate Hash-Pinned Constraints

```bash
# Using uv (recommended)
chiron deps constraints --output constraints.txt --extras pii,rag

# Using pip-tools
chiron deps constraints --tool pip-tools --output constraints.txt
```

### Scan for Vulnerabilities

```bash
# Scan requirements file
chiron deps scan --lockfile requirements.txt --output osv-report.json

# Use as CI gate (exit with error if high+ vulnerabilities found)
chiron deps scan --lockfile requirements.txt --gate --max-severity high
```

### Create Wheelhouse Bundle

```bash
# Build wheelhouse with supply chain features
GENERATE_SUPPLY_CHAIN=true \
CREATE_BUNDLE=true \
COMMIT_SHA=$(git rev-parse HEAD) \
GIT_REF=$(git branch --show-current) \
bash scripts/build-wheelhouse.sh vendor/wheelhouse

# Or use CLI
chiron deps bundle --wheelhouse vendor/wheelhouse --sign
```

### Check Policy Compliance

```bash
# Check if package is allowed
chiron deps policy --package numpy

# Check specific version
chiron deps policy --package torch --version 2.4.0

# Check upgrade
chiron deps policy --package torch --upgrade-from 2.3.0 --version 2.4.0
```

## Components

### 1. Hash-Pinned Constraints (`chiron/deps/constraints.py`)

Generates `--require-hashes` constraints for deterministic, verifiable installations.

**Features:**
- Support for both uv and pip-tools
- Include specific extras
- Target Python version specification
- Hash verification

**Usage:**

```python
from pathlib import Path
from chiron.deps.constraints import generate_constraints

success = generate_constraints(
    project_root=Path("."),
    output_path=Path("constraints.txt"),
    tool="uv",
    include_extras=["pii", "rag"],
    python_version="3.12",
)
```

### 2. Supply Chain Security (`chiron/deps/supply_chain.py`)

Provides SBOM generation and vulnerability scanning.

**SBOM Generation:**

```python
from pathlib import Path
from chiron.deps.supply_chain import SBOMGenerator

generator = SBOMGenerator(Path("."))
generator.generate(Path("sbom.json"), format="json")
```

**Vulnerability Scanning:**

```python
from pathlib import Path
from chiron.deps.supply_chain import OSVScanner

scanner = OSVScanner(Path("."))
summary = scanner.scan_lockfile(
    Path("requirements.txt"),
    output_path=Path("osv-report.json"),
)

if summary.has_blocking_vulnerabilities("high"):
    print("Blocking vulnerabilities found!")
```

**Combined with CI Gate:**

```python
from chiron.deps.supply_chain import generate_sbom_and_scan

success, summary = generate_sbom_and_scan(
    project_root=Path("."),
    sbom_output=Path("sbom.json"),
    osv_output=Path("osv.json"),
    lockfile_path=Path("requirements.txt"),
    gate_max_severity="high",  # Fail on high+ vulnerabilities
)
```

### 3. Artifact Signing (`chiron/deps/signing.py`)

Sign and verify artifacts using Sigstore cosign (keyless OIDC-based signing).

**Signing:**

```python
from pathlib import Path
from chiron.deps.signing import sign_wheelhouse_bundle

result = sign_wheelhouse_bundle(
    bundle_path=Path("wheelhouse-bundle.tar.gz"),
)

if result.success:
    print(f"Signed: {result.signature_path}")
```

**Verification:**

```python
from pathlib import Path
from chiron.deps.signing import verify_wheelhouse_bundle

verified = verify_wheelhouse_bundle(
    bundle_path=Path("wheelhouse-bundle.tar.gz"),
    signature_path=Path("wheelhouse-bundle.tar.gz.sig"),
)
```

### 4. Policy Engine (`chiron/deps/policy.py`)

Enforce dependency governance rules.

**Policy Configuration (`configs/dependency-policy.toml`):**

```toml
[dependency_policy]
default_allowed = true
max_major_version_jump = 1
require_security_review = true

[dependency_policy.allowlist.numpy]
version_ceiling = "2.9.0"
version_floor = "2.0.0"
upgrade_cadence_days = 90

[dependency_policy.denylist.insecure-package]
reason = "Known security vulnerabilities"
```

**Usage:**

```python
from pathlib import Path
from chiron.deps.policy import load_policy, PolicyEngine

policy = load_policy(Path("configs/dependency-policy.toml"))
engine = PolicyEngine(policy)

# Check package
allowed, reason = engine.check_package_allowed("numpy")

# Check upgrade
violations = engine.check_upgrade_allowed(
    "torch",
    current_version="2.3.0",
    target_version="2.4.0",
)
```

### 5. Wheelhouse Bundler (`chiron/deps/bundler.py`)

Create portable bundles for air-gapped deployment.

**Features:**
- SHA256 checksums for all wheels
- Simple PyPI-compatible index
- Bundle metadata with provenance
- SBOM and OSV scan inclusion

**Usage:**

```python
from pathlib import Path
from chiron.deps.bundler import create_wheelhouse_bundle

metadata = create_wheelhouse_bundle(
    wheelhouse_dir=Path("vendor/wheelhouse"),
    output_path=Path("wheelhouse-bundle.tar.gz"),
    commit_sha="abc123",
    git_ref="main",
)
```

**Bundle Contents:**
```
wheelhouse/
├── *.whl                      # All wheel files
├── requirements.txt           # Requirements list
├── SHA256SUMS                 # Checksums file
├── bundle-metadata.json       # Bundle metadata
├── sbom.json                  # SBOM (if included)
├── osv.json                   # OSV scan (if included)
└── simple/                    # Simple index
    ├── index.html             # Main index
    └── <package>/
        └── index.html         # Package-specific index
```

## CI/CD Integration

### GitHub Actions Workflow

The frontier-grade workflow (`.github/workflows/build-wheelhouse-frontier.yml`) provides:

1. **Multi-platform wheel building** with cibuildwheel
2. **Hash-pinned constraints** generation
3. **SBOM generation** with CycloneDX
4. **Vulnerability scanning** with OSV
5. **Artifact signing** with cosign (keyless)
6. **SLSA provenance** attestation
7. **Policy enforcement** gate

**Workflow Steps:**

```yaml
- Generate hash-pinned constraints
- Build platform wheels (Linux, macOS, Windows)
- Create comprehensive wheelhouse bundle
- Generate SBOM
- Run vulnerability scan
- Create portable bundle with checksums
- Sign bundle with cosign
- Generate SLSA attestation
- Upload artifacts
```

### Environment Variables

**For `scripts/build-wheelhouse.sh`:**

```bash
GENERATE_SUPPLY_CHAIN=true  # Enable supply chain features
CREATE_BUNDLE=true          # Create portable bundle
COMMIT_SHA=<sha>            # Git commit SHA
GIT_REF=<ref>               # Git reference (branch/tag)
```

## Air-Gapped Deployment

### Option A: Simple (No Server)

```bash
# On online machine
chiron deps bundle --wheelhouse vendor/wheelhouse --sign

# Transfer wheelhouse-bundle.tar.gz and .sig to offline machine

# On offline machine
# 1. Verify signature
cosign verify-blob \
  --signature wheelhouse-bundle.tar.gz.sig \
  wheelhouse-bundle.tar.gz

# 2. Extract
tar -xzf wheelhouse-bundle.tar.gz

# 3. Install
pip install --no-index \
  --find-links=wheelhouse \
  -r wheelhouse/requirements.txt
```

### Option B: Local PyPI Index

```bash
# On offline machine
# 1. Extract bundle
tar -xzf wheelhouse-bundle.tar.gz

# 2. Start local PyPI server
python -m http.server 8080 --directory wheelhouse/simple

# 3. Install using local index
pip install \
  --index-url http://localhost:8080/simple \
  --trusted-host localhost \
  <package-name>
```

### Option C: devpi Offline

```bash
# Setup devpi
devpi-server --serverdir /srv/devpi --offline &
devpi use http://localhost:3141/root/offline
devpi login root --password=''
devpi index -c offline volatile=False

# Load wheels
find wheelhouse -name '*.whl' -print0 | \
  xargs -0 -I{} devpi upload --from-dir {}

# Install
pip install \
  --index-url http://localhost:3141/root/offline/simple \
  --no-deps <package-name>
```

## Policy Examples

### Conservative Security Policy

```toml
[dependency_policy]
default_allowed = false  # Deny by default
max_major_version_jump = 0  # No major jumps
require_security_review = true
allow_pre_releases = false

[dependency_policy.allowlist.requests]
version_floor = "2.32.0"  # Known CVE fixes
upgrade_cadence_days = 30
requires_review = false
```

### Aggressive Update Policy

```toml
[dependency_policy]
default_allowed = true
max_major_version_jump = 2
require_security_review = false
allow_pre_releases = true
default_upgrade_cadence_days = 7
```

## Testing

Test the new modules:

```bash
# Test constraints generation
poetry run python -c "
from pathlib import Path
from chiron.deps.constraints import generate_constraints
generate_constraints(Path('.'), tool='uv')
"

# Test SBOM generation
poetry run python -c "
from pathlib import Path
from chiron.deps.supply_chain import SBOMGenerator
SBOMGenerator(Path('.')).generate(Path('test-sbom.json'))
"

# Test policy engine
poetry run python -c "
from pathlib import Path
from chiron.deps.policy import load_policy, PolicyEngine
policy = load_policy()
engine = PolicyEngine(policy)
print(engine.check_package_allowed('numpy'))
"
```

## Troubleshooting

### uv not found

```bash
pip install uv
```

### osv-scanner not found

Download from: https://github.com/google/osv-scanner

```bash
# Linux
curl -L -o osv-scanner https://github.com/google/osv-scanner/releases/latest/download/osv-scanner_linux_amd64
chmod +x osv-scanner
sudo mv osv-scanner /usr/local/bin/
```

### cosign not found

Download from: https://github.com/sigstore/cosign

```bash
# Linux
curl -L -o cosign https://github.com/sigstore/cosign/releases/latest/download/cosign-linux-amd64
chmod +x cosign
sudo mv cosign /usr/local/bin/
```

### cyclonedx-py not found

```bash
pip install cyclonedx-bom
```

## References

- [CHIRON_UPGRADE_PLAN.md](../chiron/CHIRON_UPGRADE_PLAN.md) - Original recommendations
- [PEP 517](https://peps.python.org/pep-0517/) - Build system requirements
- [PEP 518](https://peps.python.org/pep-0518/) - Build system dependencies
- [Sigstore](https://www.sigstore.dev/) - Artifact signing
- [OSV](https://osv.dev/) - Open Source Vulnerabilities
- [CycloneDX](https://cyclonedx.org/) - SBOM standard
- [SLSA](https://slsa.dev/) - Supply chain integrity
