# LFS and Multi-Platform Wheelhouse Optimization

This document describes the comprehensive optimization of Git LFS and
multi-platform wheelhouse builds implemented for the Prometheus repository to
enable efficient air-gapped development and deployment.

## Overview

The optimization focuses on three key areas:

1. **Git LFS Configuration** - Enhanced for air-gapped environments with
   performance tuning
2. **Multi-Platform Wheelhouse** - Automated builds for Linux, macOS, and Windows
3. **CI/CD Optimization** - GitHub Actions workflows with caching and matrix builds

## Key Improvements

### 1. Enhanced .gitattributes

- **Comprehensive LFS patterns** for all binary assets (wheels, models, images, data)
- **Platform-specific organization** with `vendor/wheelhouse/platform/` structure
- **Smart exclusions** to keep small text files out of LFS for better performance
- **Extended coverage** for container images, ML models, and datasets

### 2. Multi-Platform Wheelhouse Build Script

**File:** `scripts/build-wheelhouse.sh`

**New Features:**

- Automatic platform detection (Linux, macOS, Windows)
- Platform-specific wheel organization
- Retry logic with configurable timeouts
- Performance optimizations with parallel downloads
- Platform manifest generation for tracking
- Archive creation with compression
- Multi-platform manifest collation saved to
  `dist/wheelhouse/{manifests,archives}/` via `scripts/manage-deps.sh`

**Usage:**

```bash
# Build for current platform
./scripts/build-wheelhouse.sh

# Build for specific platform
PLATFORM=linux_x86_64 ./scripts/build-wheelhouse.sh

# Include development dependencies
INCLUDE_DEV=true ./scripts/build-wheelhouse.sh

# Build with specific extras
EXTRAS="pii,rag,llm" ./scripts/build-wheelhouse.sh

# Build with observability exporters bundled
EXTRAS="observability" ./scripts/build-wheelhouse.sh
```

> **Tip:** Add the `observability` extra whenever tracing exporters need to be
> pre-bundled, such as for CI dry-run instrumentation or offline telemetry
> validation. Combine it with other extras in the `EXTRAS` list as required.

### 3. Optimized GitHub Actions Workflow

**File:** `.github/workflows/offline-packaging-optimized.yml`

**Optimizations:**

- **Matrix builds** across Ubuntu, macOS, and Windows
- **Caching strategies** for pip and Poetry dependencies
- **LFS performance tuning** with concurrent transfers
- **Multi-platform wheel collection** and organization
- **Artifact retention** with automatic cleanup
- **Parallel processing** and timeout handling

### 4. Enhanced LFS Verification

**File:** `scripts/ci/verify-lfs.sh`

**Improvements:**

- Retry logic for failed LFS operations
- Performance configuration (batch transfers, concurrent operations)
- Air-gapped environment detection
- Comprehensive status reporting
- Timeout and error handling

### 5. Development Setup Automation

**File:** `scripts/setup-dev-optimized.sh`

**Features:**

- One-command development environment setup
- LFS performance optimization
- Local wheelhouse building
- Git aliases and hooks setup
- direnv configuration for environment variables
- Comprehensive documentation generation

## Air-Gapped Environment Support

### Pre-requisites for Air-Gapped Deployment

1. **Hydrate LFS objects:**

   ```bash
   git lfs fetch --all
   git lfs checkout
   ```

2. **Build comprehensive wheelhouse:**

   ```bash
   INCLUDE_DEV=true EXTRAS="observability,all-extras" \
     ./scripts/build-wheelhouse.sh
   ```

3. **Create transfer archives:**

   ```bash
   tar -czf prometheus-vendor.tar.gz vendor/
   tar -czf prometheus-lfs.tar.gz .git/lfs/
   ```

### Installation in Air-Gapped Environment

1. **Extract vendor directory:**

   ```bash
   tar -xzf prometheus-vendor.tar.gz
   ```

2. **Install from wheelhouse:**

   ```bash
   pip install --no-index --find-links vendor/wheelhouse -r vendor/wheelhouse/requirements.txt
   ```

3. **Verify installation:**

   ```bash
   ./scripts/validate-setup.sh
   ```

## Performance Improvements

### LFS Optimizations

- **Batch transfers:** Enabled for multiple file operations
- **Concurrent transfers:** Up to 8 parallel connections
- **Optimized timeouts:** 300 seconds for large files
- **Progress monitoring:** Real-time transfer status

### CI/CD Optimizations

- **Caching:** Pip and Poetry dependencies cached across builds
- **Matrix optimization:** Parallel builds across platforms
- **Artifact management:** Automatic cleanup of old builds
- **Failure handling:** Retry logic and graceful degradation

### Local Development Optimizations

- **Pre-commit hooks:** Automatic LFS file detection
- **Git aliases:** Convenient LFS status and management commands
- **Environment variables:** Optimized for offline development
- **Symlink normalization:** Better cross-platform compatibility

## Usage Instructions

### For Developers

1. **Initial setup:**

   ```bash
   ./scripts/setup-dev-optimized.sh
   ```

2. **Build wheelhouse for development:**

   ```bash
   git wheelhouse  # Uses git alias created by setup script
   ```

3. **Check LFS status:**

   ```bash
   git lfs-status
   git lfs-check
   ```

### For CI/CD

The optimized workflow runs automatically on:

- Weekly schedule (Mondays at 03:00 UTC)
- Manual dispatch with platform selection
- Configurable rebuild options

### For Air-Gapped Environments

1. **Preparation (with network access):**

   ```bash
   # Run full packaging
   poetry run python scripts/offline_package.py

   # Create comprehensive archives
   ./scripts/create-airgap-bundle.sh  # If available
   ```

2. **Deployment (air-gapped):**

   ```bash
   # Extract and verify
   tar -xzf prometheus-airgap-bundle.tar.gz
   ./scripts/validate-setup.sh
   ```

## Validation and Testing

**File:** `scripts/validate-setup.sh`

Comprehensive validation includes:

- Script syntax verification
- Configuration file validation
- GitHub Actions workflow testing
- Platform detection testing
- Documentation completeness checks

Run validation:

```bash
./scripts/validate-setup.sh
```

## Configuration Files

### Updated Configurations

1. **`configs/defaults/offline_package.toml`** - Added performance section
2. **`.gitattributes`** - Enhanced with comprehensive LFS patterns
3. **`.github/workflows/`** - New optimized workflow

### New Performance Settings

```toml
[performance]
parallel_downloads = 4
lfs_batch_size = 100
lfs_timeout = 300
lfs_concurrent_transfers = 8
prefer_binary_wheels = true
wheel_cache_enabled = true
```

## Troubleshooting

### Common Issues

1. **LFS Objects Not Hydrated:**

   ```bash
   git lfs fetch --all && git lfs checkout
   ```

2. **Platform Detection Issues:**

   ```bash
   PLATFORM=linux_x86_64 ./scripts/build-wheelhouse.sh
   ```

3. **Network Timeouts:**

   ```bash
   LFS_TIMEOUT=600 RETRY_COUNT=5 ./scripts/ci/verify-lfs.sh
   ```

### Performance Issues

1. **Slow LFS Operations:**
   - Check network connection
   - Verify LFS server status
   - Increase timeout values

2. **Large Wheelhouse Size:**
   - Use platform-specific builds
   - Exclude unnecessary extras
   - Enable binary-only downloads

## Migration Guide

### From Existing Setup

1. **Backup existing vendor directory:**

   ```bash
   cp -r vendor/ vendor.backup/
   ```

2. **Run setup script:**

   ```bash
   ./scripts/setup-dev-optimized.sh
   ```

3. **Rebuild wheelhouse:**

   ```bash
   ./scripts/build-wheelhouse.sh
   ```

4. **Validate setup:**

   ```bash
   ./scripts/validate-setup.sh
   ```

## Future Enhancements

### Planned Improvements

1. **Container optimization** for Docker-based air-gapped deployments
2. **Model caching** for ML workloads
3. **Cross-compilation support** for additional architectures
4. **Automated testing** of air-gapped scenarios

### Contributing

When adding new binary assets:

1. Update `.gitattributes` with appropriate LFS patterns
2. Test with `./scripts/validate-setup.sh`
3. Document in air-gapped deployment guide

---

Generated by the LFS and Multi-Platform Wheelhouse Optimization project.
For questions or issues, see the troubleshooting section or contact the team.
