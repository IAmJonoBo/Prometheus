# Migration Guide: Adopting Frontier-Grade Dependency Management

This guide helps teams migrate to the new frontier-grade dependency management system.

## Prerequisites

- Python 3.11+
- Poetry 1.8.3+
- Git
- Basic understanding of dependency management

## Migration Paths

### Path A: Minimal (Start Here)

**Goal:** Add hash-pinned constraints for reproducibility

**Time:** ~15 minutes

**Steps:**

1. Install uv:
   ```bash
   pip install uv
   ```

2. Generate constraints:
   ```bash
   chiron deps constraints --output constraints.txt
   ```

3. Use constraints in CI:
   ```yaml
   - name: Install with constraints
     run: |
       pip install -r constraints.txt
   ```

**Benefits:**
- ✅ Reproducible builds
- ✅ Hash verification
- ✅ No dependency confusion

### Path B: Standard (Recommended)

**Goal:** Add SBOM, vulnerability scanning, and policy

**Time:** ~1 hour

**Steps:**

1. Install tools:
   ```bash
   pip install uv cyclonedx-bom
   
   # Install osv-scanner
   curl -L -o osv-scanner https://github.com/google/osv-scanner/releases/latest/download/osv-scanner_linux_amd64
   chmod +x osv-scanner
   sudo mv osv-scanner /usr/local/bin/
   ```

2. Create policy configuration:
   ```bash
   cp configs/dependency-policy.toml.example configs/dependency-policy.toml
   # Edit to match your requirements
   ```

3. Add to CI workflow:
   ```yaml
   - name: Generate constraints
     run: chiron deps constraints --output constraints.txt
   
   - name: Scan vulnerabilities
     run: chiron deps scan --lockfile constraints.txt --gate --max-severity high
   
   - name: Check policy
     run: |
       # Add policy checks to your upgrade workflow
       chiron deps policy --package <name> --version <version>
   ```

**Benefits:**
- ✅ All benefits from Path A
- ✅ Vulnerability detection
- ✅ SBOM for compliance
- ✅ Policy enforcement

### Path C: Complete (Production)

**Goal:** Full supply chain security with signing and bundles

**Time:** ~4 hours

**Steps:**

1. Follow Path B

2. Install cosign:
   ```bash
   curl -L -o cosign https://github.com/sigstore/cosign/releases/latest/download/cosign-linux-amd64
   chmod +x cosign
   sudo mv cosign /usr/local/bin/
   ```

3. Set up wheelhouse bundle generation:
   ```bash
   GENERATE_SUPPLY_CHAIN=true \
   CREATE_BUNDLE=true \
   bash scripts/build-wheelhouse.sh vendor/wheelhouse
   ```

4. Add frontier workflow to CI:
   ```bash
   # Copy and customize the frontier workflow
   cp .github/workflows/build-wheelhouse-frontier.yml \
      .github/workflows/wheelhouse.yml
   ```

5. Set up OIDC for signing:
   - Enable OIDC in repository settings
   - Add `id-token: write` permission to workflow

**Benefits:**
- ✅ All benefits from Path B
- ✅ Signed artifacts
- ✅ SLSA provenance
- ✅ Air-gapped deployment ready

## Migration Checklist

### Pre-Migration

- [ ] Review current dependency management process
- [ ] Identify pain points (reproducibility, security, air-gap)
- [ ] Choose migration path (A, B, or C)
- [ ] Install required tools
- [ ] Create test branch

### During Migration

- [ ] Generate initial constraints file
- [ ] Run vulnerability scan on existing dependencies
- [ ] Create policy configuration
- [ ] Test constraints installation locally
- [ ] Update CI workflows
- [ ] Test CI pipeline
- [ ] Create wheelhouse bundle (if Path C)

### Post-Migration

- [ ] Document new workflow for team
- [ ] Set up scheduled dependency scans
- [ ] Configure alerting for vulnerabilities
- [ ] Train team on new CLI commands
- [ ] Establish policy review process

## Common Issues and Solutions

### Issue: uv not found

**Symptom:** `uv: command not found`

**Solution:**
```bash
pip install uv
# or
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Issue: Hash mismatch during installation

**Symptom:** `ERROR: THESE PACKAGES DO NOT MATCH THE HASHES FROM THE REQUIREMENTS FILE`

**Solution:**
```bash
# Regenerate constraints
chiron deps constraints --output constraints.txt

# Or bypass for specific package (not recommended)
pip install --no-deps <package>
```

### Issue: OSV scanner fails in CI

**Symptom:** `osv-scanner: command not found`

**Solution:**
```yaml
- name: Install osv-scanner
  run: |
    curl -L -o /tmp/osv-scanner https://github.com/google/osv-scanner/releases/latest/download/osv-scanner_linux_amd64
    chmod +x /tmp/osv-scanner
    sudo mv /tmp/osv-scanner /usr/local/bin/
```

### Issue: Policy violations blocking legitimate upgrades

**Symptom:** `Policy violation: version_denied`

**Solution:**
```toml
# Update policy configuration
[dependency_policy.allowlist.<package>]
version_ceiling = "2.0.0"  # Increase ceiling
# or
blocked_versions = []  # Remove from blocked list
```

### Issue: Signing fails without OIDC

**Symptom:** `cosign: COSIGN_EXPERIMENTAL must be set`

**Solution:**
```bash
# Set environment variable
export COSIGN_EXPERIMENTAL=1

# Or configure OIDC in GitHub Actions
permissions:
  id-token: write
```

## Workflow Examples

### Development Workflow

```bash
# 1. Update dependencies
poetry update <package>

# 2. Regenerate constraints
chiron deps constraints --output constraints.txt

# 3. Check policy
chiron deps policy --package <name> --version <new-version>

# 4. Scan for vulnerabilities
chiron deps scan --lockfile constraints.txt

# 5. Commit changes
git add pyproject.toml poetry.lock constraints.txt
git commit -m "Update <package> to <version>"
```

### Release Workflow

```bash
# 1. Create wheelhouse bundle
GENERATE_SUPPLY_CHAIN=true \
CREATE_BUNDLE=true \
COMMIT_SHA=$(git rev-parse HEAD) \
GIT_REF=$(git describe --tags) \
bash scripts/build-wheelhouse.sh vendor/wheelhouse

# 2. Sign bundle
chiron deps bundle --wheelhouse vendor/wheelhouse --sign

# 3. Verify bundle
sha256sum -c wheelhouse-bundle.tar.gz.sha256
cosign verify-blob --signature wheelhouse-bundle.tar.gz.sig wheelhouse-bundle.tar.gz

# 4. Upload to artifact storage
# (implementation depends on your infrastructure)
```

### Air-Gapped Deployment Workflow

```bash
# On online machine:
# 1. Create bundle
GENERATE_SUPPLY_CHAIN=true CREATE_BUNDLE=true \
bash scripts/build-wheelhouse.sh vendor/wheelhouse

# 2. Transfer to offline machine
scp wheelhouse-bundle.tar.gz offline-machine:/tmp/

# On offline machine:
# 3. Verify and extract
sha256sum -c wheelhouse-bundle.tar.gz.sha256
tar -xzf wheelhouse-bundle.tar.gz

# 4. Install
pip install --no-index --find-links=wheelhouse -r wheelhouse/requirements.txt
```

## Team Training

### For Developers

**Key Commands:**
```bash
# Check if package is allowed
chiron deps policy --package <name>

# Generate constraints
chiron deps constraints

# Scan for vulnerabilities
chiron deps scan --lockfile requirements.txt
```

**When to Use:**
- Before adding new dependencies
- Before upgrading existing dependencies
- Before releasing new versions

### For DevOps/SRE

**Key Concepts:**
- Hash-pinned constraints ensure reproducibility
- SBOM provides inventory for compliance
- OSV scanning detects known vulnerabilities
- Policy engine enforces governance rules
- Signed bundles enable verification

**Monitoring:**
- Set up alerts for vulnerability scans
- Monitor bundle generation success rate
- Track policy violations
- Review blocked packages regularly

## Best Practices

### 1. Regenerate Constraints Regularly

```bash
# Weekly or after dependency changes
chiron deps constraints --output constraints.txt
git commit -am "Update constraints"
```

### 2. Review Policy Quarterly

```bash
# Check for outdated rules
chiron deps policy

# Update ceilings for major releases
# Review denylist for deprecated packages
```

### 3. Scan Before Merge

```yaml
# In CI
- name: Security gate
  run: |
    chiron deps scan --lockfile constraints.txt --gate --max-severity high
```

### 4. Sign Release Artifacts

```bash
# Always sign production bundles
chiron deps bundle --wheelhouse vendor/wheelhouse --sign
```

### 5. Document Exceptions

```toml
# In policy config, always include reason
[dependency_policy.allowlist.special-package]
version_ceiling = "3.0.0"
reason = "Ticket #1234: Required for feature X"
```

## Rollback Plan

If you need to rollback:

1. **Revert constraints generation:**
   ```bash
   git revert <commit-with-constraints>
   ```

2. **Disable policy checks:**
   ```bash
   # Comment out policy checks in CI temporarily
   ```

3. **Keep vulnerability scanning:**
   ```bash
   # Even during rollback, keep scanning
   chiron deps scan --lockfile requirements.txt
   ```

## Success Metrics

Track these metrics to measure success:

- **Reproducibility:** % of builds with identical outputs
- **Security:** # of vulnerabilities detected and fixed
- **Policy compliance:** % of upgrades passing policy checks
- **Air-gap readiness:** Time to create verified bundle
- **Team adoption:** % of developers using new tools

## Support and Resources

- [Feature Documentation](./FRONTIER_DEPENDENCY_MANAGEMENT.md)
- [Air-Gapped Deployment Guide](./AIR_GAPPED_DEPLOYMENT.md)
- [Implementation Summary](./CHIRON_UPGRADE_IMPLEMENTATION.md)
- [Original Plan](../../chiron/CHIRON_UPGRADE_PLAN.md)

## FAQ

**Q: Do I need all tools installed?**  
A: No. Start with `uv` for constraints. Add others as needed.

**Q: Can I use this with poetry?**  
A: Yes. Generate constraints from poetry.lock or use `poetry export`.

**Q: What about private packages?**  
A: Configure in policy allowlist. Use `--extra-index-url` for private PyPI.

**Q: How often should I regenerate constraints?**  
A: Weekly or after any dependency change.

**Q: What if a package isn't in OSV database?**  
A: OSV covers most Python packages. Report gaps to OSV team.

**Q: Can I customize the policy?**  
A: Yes. Edit `configs/dependency-policy.toml` to match your needs.
