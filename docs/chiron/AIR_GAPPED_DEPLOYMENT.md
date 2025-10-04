# Air-Gapped Deployment Guide

Complete guide for deploying Prometheus OS in offline/air-gapped environments.

## Quick Start

### 1. Prepare Bundle (Online Machine)

```bash
# Clone repository
git clone https://github.com/IAmJonoBo/Prometheus.git
cd Prometheus

# Build wheelhouse with all supply chain features
GENERATE_SUPPLY_CHAIN=true \
CREATE_BUNDLE=true \
COMMIT_SHA=$(git rev-parse HEAD) \
GIT_REF=$(git branch --show-current) \
EXTRAS=pii,observability,rag,llm,governance,integrations \
bash scripts/build-wheelhouse.sh vendor/wheelhouse

# Bundle will be created at vendor/wheelhouse.tar.gz
```

### 2. Transfer to Air-Gapped Environment

Transfer these files to your offline machine:

- `wheelhouse-bundle.tar.gz`
- `wheelhouse-bundle.tar.gz.sha256`
- `wheelhouse-bundle.tar.gz.sig` (if signed)

### 3. Deploy (Offline Machine)

```bash
# Verify checksum
sha256sum -c wheelhouse-bundle.tar.gz.sha256

# Extract
tar -xzf wheelhouse-bundle.tar.gz

# Install
pip install --no-index \
  --find-links=wheelhouse \
  -r wheelhouse/requirements.txt
```

## Detailed Workflows

### Method 1: Direct Installation (Simplest)

**Best for:** Single-machine deployments, testing

```bash
# Extract bundle
tar -xzf wheelhouse-bundle.tar.gz

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install from wheelhouse
pip install --no-index \
  --find-links=wheelhouse \
  --require-hashes \
  -r wheelhouse/requirements.txt

# Or install specific package
pip install --no-index \
  --find-links=wheelhouse \
  prometheus-os
```

### Method 2: Simple HTTP Server

**Best for:** Multiple machines on same network

```bash
# Extract bundle
tar -xzf wheelhouse-bundle.tar.gz

# Start simple HTTP server
cd wheelhouse
python3 -m http.server 8080

# On client machines
pip install \
  --index-url http://<server-ip>:8080/simple \
  --trusted-host <server-ip> \
  prometheus-os
```

### Method 3: devpi Offline Index (Most Robust)

**Best for:** Production deployments, multiple teams

#### Setup devpi Server

```bash
# Install devpi (on online machine first, then transfer wheels)
pip download devpi-server devpi-client -d devpi-wheels

# Transfer devpi-wheels to offline machine

# On offline machine, install devpi
pip install --no-index --find-links=devpi-wheels devpi-server devpi-client

# Initialize devpi
devpi-server --init --serverdir=/srv/devpi

# Start server
devpi-server --serverdir=/srv/devpi --offline --host=0.0.0.0 --port=3141 &

# Configure devpi
devpi use http://localhost:3141
devpi login root --password=''
devpi index -c offline volatile=False
devpi use offline
```

#### Load Wheelhouse

```bash
# Extract bundle
tar -xzf wheelhouse-bundle.tar.gz

# Upload all wheels to devpi
find wheelhouse -name '*.whl' -print0 | \
  xargs -0 -I{} devpi upload --from-dir {}
```

#### Client Configuration

```bash
# Configure pip to use devpi
cat > ~/.pip/pip.conf <<EOF
[global]
index-url = http://<devpi-server>:3141/root/offline/simple
trusted-host = <devpi-server>
no-cache-dir = false
EOF

# Install packages
pip install prometheus-os
```

### Method 4: Nginx as PyPI Mirror

**Best for:** Enterprise deployments with existing nginx infrastructure

#### nginx Configuration

```nginx
server {
    listen 8080;
    server_name pypi.internal;

    root /var/www/wheelhouse;

    location / {
        autoindex on;
        autoindex_format json;
    }

    location /simple {
        alias /var/www/wheelhouse/simple;
        autoindex on;
    }
}
```

#### Deploy Wheelhouse

```bash
# Extract to nginx root
sudo tar -xzf wheelhouse-bundle.tar.gz -C /var/www/

# Set permissions
sudo chown -R www-data:www-data /var/www/wheelhouse

# Restart nginx
sudo systemctl restart nginx
```

#### Client Configuration

```bash
pip install \
  --index-url http://pypi.internal:8080/simple \
  --trusted-host pypi.internal \
  prometheus-os
```

## Verification

### Verify Bundle Integrity

```bash
# Verify checksum
sha256sum -c wheelhouse-bundle.tar.gz.sha256

# Verify signature (if signed)
export COSIGN_EXPERIMENTAL=1
cosign verify-blob \
  --signature wheelhouse-bundle.tar.gz.sig \
  wheelhouse-bundle.tar.gz
```

### Verify Bundle Contents

```bash
# Extract and check
tar -tzf wheelhouse-bundle.tar.gz | head -20

# Check wheel count
tar -tzf wheelhouse-bundle.tar.gz | grep -c '\.whl$'

# Verify checksums in bundle
tar -xzf wheelhouse-bundle.tar.gz
cd wheelhouse
sha256sum -c SHA256SUMS
```

### Verify SBOM

```bash
# Extract SBOM
tar -xzf wheelhouse-bundle.tar.gz wheelhouse/sbom.json

# View SBOM
cat wheelhouse/sbom.json | jq '.components | length'
cat wheelhouse/sbom.json | jq '.components[] | {name, version}'
```

### Verify No Vulnerabilities

```bash
# Extract OSV scan results
tar -xzf wheelhouse-bundle.tar.gz wheelhouse/osv.json

# Check for vulnerabilities
python3 <<'PY'
import json
from pathlib import Path

osv = json.loads(Path("wheelhouse/osv.json").read_text())
results = osv.get("results", [])
total = sum(len(r.get("packages", [{}])[0].get("vulnerabilities", [])) for r in results)
print(f"Total vulnerabilities: {total}")
if total > 0:
    print("WARNING: Vulnerabilities found!")
    exit(1)
PY
```

## Troubleshooting

### Issue: Hash mismatch during installation

**Cause:** Bundle corrupted during transfer

**Solution:**

```bash
# Verify checksum
sha256sum -c wheelhouse-bundle.tar.gz.sha256

# Re-transfer if checksum fails
```

### Issue: Wheel not found for platform

**Cause:** Platform-specific wheel not included in bundle

**Solution:**

```bash
# Build platform-specific wheelhouse on online machine with matching platform
PLATFORM=linux_x86_64 bash scripts/build-wheelhouse.sh

# Or allow source distributions for specific packages
ALLOW_SDIST_FOR=package-name bash scripts/build-wheelhouse.sh
```

### Issue: SSL certificate verification errors

**Cause:** Trying to access external PyPI

**Solution:**

```bash
# Ensure --no-index flag is used
pip install --no-index --find-links=wheelhouse prometheus-os

# Or use trusted-host for local server
pip install --trusted-host <server-ip> --index-url http://<server-ip>:8080/simple prometheus-os
```

### Issue: Package installation fails with "No matching distribution"

**Cause:** Package requires compilation or specific Python version

**Solution:**

```bash
# Check Python version matches wheelhouse build
python --version

# Check if source distributions are available
ls wheelhouse/*.tar.gz

# Install with --no-deps if dependencies missing
pip install --no-index --find-links=wheelhouse --no-deps prometheus-os
```

## Bundle Contents Reference

```
wheelhouse/
├── *.whl                      # Binary wheels for all platforms
├── requirements.txt           # Complete requirements list
├── SHA256SUMS                 # SHA256 checksums for all wheels
├── bundle-metadata.json       # Bundle metadata and provenance
├── sbom.json                  # Software Bill of Materials (CycloneDX)
├── osv.json                   # Vulnerability scan results (OSV)
├── platform_manifest.json     # Platform build information
└── simple/                    # PyPI-compatible simple index
    ├── index.html             # Package list
    └── <package>/
        └── index.html         # Links to package wheels
```

## Security Best Practices

1. **Always verify checksums** before extracting bundles
2. **Verify signatures** if using signed bundles
3. **Review SBOM** for unexpected packages
4. **Check OSV scan** for known vulnerabilities
5. **Use hash-pinned requirements** for reproducibility
6. **Audit bundle contents** before deployment
7. **Keep devpi/mirrors** on isolated network segments
8. **Use TLS** for HTTP-based methods in production
9. **Rotate bundles** regularly (weekly/monthly)
10. **Document bundle provenance** (commit SHA, build date, etc.)

## Automation Examples

### Automated Bundle Update

```bash
#!/bin/bash
# update-wheelhouse.sh

set -euo pipefail

BUNDLE_DIR=/srv/wheelhouse-bundles
LATEST_BUNDLE="${BUNDLE_DIR}/wheelhouse-$(date +%Y%m%d).tar.gz"

# Build new bundle
GENERATE_SUPPLY_CHAIN=true \
CREATE_BUNDLE=true \
COMMIT_SHA=$(git rev-parse HEAD) \
GIT_REF=$(git branch --show-current) \
bash scripts/build-wheelhouse.sh vendor/wheelhouse

# Move to bundle directory
mv vendor/wheelhouse.tar.gz "${LATEST_BUNDLE}"

# Create symlink to latest
ln -sf "$(basename "${LATEST_BUNDLE}")" "${BUNDLE_DIR}/latest.tar.gz"

# Clean old bundles (keep last 10)
ls -t "${BUNDLE_DIR}"/wheelhouse-*.tar.gz | tail -n +11 | xargs rm -f

echo "Bundle updated: ${LATEST_BUNDLE}"
```

### Automated Deployment Check

```bash
#!/bin/bash
# check-deployment.sh

set -euo pipefail

WHEELHOUSE_DIR=/var/www/wheelhouse

# Check wheel count
wheel_count=$(find "${WHEELHOUSE_DIR}" -name '*.whl' | wc -l)
echo "Wheels available: ${wheel_count}"

if [ "${wheel_count}" -lt 100 ]; then
    echo "WARNING: Low wheel count"
    exit 1
fi

# Verify checksums
if [ -f "${WHEELHOUSE_DIR}/SHA256SUMS" ]; then
    cd "${WHEELHOUSE_DIR}"
    sha256sum -c SHA256SUMS >/dev/null 2>&1 || {
        echo "ERROR: Checksum verification failed"
        exit 1
    }
    echo "Checksums verified"
fi

# Check for vulnerabilities
if [ -f "${WHEELHOUSE_DIR}/osv.json" ]; then
    vuln_count=$(python3 -c "
import json
from pathlib import Path
data = json.loads(Path('${WHEELHOUSE_DIR}/osv.json').read_text())
print(sum(len(r.get('packages', [{}])[0].get('vulnerabilities', [])) for r in data.get('results', [])))
")
    echo "Vulnerabilities: ${vuln_count}"

    if [ "${vuln_count}" -gt 0 ]; then
        echo "WARNING: Vulnerabilities found"
    fi
fi

echo "Deployment check complete"
```

## Additional Resources

- [Frontier Dependency Management](./FRONTIER_DEPENDENCY_MANAGEMENT.md) - Complete guide
- [CHIRON_UPGRADE_PLAN.md](../../chiron/CHIRON_UPGRADE_PLAN.md) - Original recommendations
- [Offline Packaging](./OFFLINE_PACKAGING.md) - General offline packaging guide
- [devpi Documentation](https://devpi.net/) - Private PyPI server
- [PEP 503](https://peps.python.org/pep-0503/) - Simple Repository API
