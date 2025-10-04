# Frontier-grade Dependency & Wheelhouse System

Gap analysis, red team, and upgrades

## Executive Summary

Your current goal—intelligent, policy-driven dependency management plus production-ready wheelhouses (built remotely with cibuildwheel) that can serve air-gapped runners—demands:

1. Hermetic, reproducible builds
2. A private index/offline bundle you control
3. End-to-end provenance (SLSA), SBOMs, and signatures
4. Cross-OS/arch wheels with proper vendoring (auditwheel/delocate/delvewheel)
5. Integration points so any system can consume your artefacts with zero Internet

---

## Gaps (typical in "messy" projects)

- **Determinism**: No universal constraints/lock (hash-pinned), mixed build backends, non-hermetic CI
- **Coverage**: Wheels missing for one or more OS/arch; shared libs not vendored; ABI drift (glibc/macOS)
- **Distribution**: No private PyPI mirror or offline "wheelhouse bundle"; air-gapped installs ad-hoc
- **Security**: No SBOM, OSV scanning, signatures, or SLSA provenance; dependency-confusion exposure
- **Governance**: No policy engine (allow/deny/upgrade windows), no compatibility matrix, no expiry/rotation for caches
- **Observability**: Build provenance, test coverage on critical paths, and supply-chain attestations are absent

## Red Team (what bites first)

- Dependency confusion / typosquatting via default index
- ABI breakage on target hosts (manylinux/macOS/Windows) due to unvendored native libs
- Cache/artefact poisoning in CI or shared runners
- Non-reproducible wheels (timestamps, env drift, non-pinned compilers)
- Transitively vulnerable deps with no OSV gate; silent regressions
- Key/secret sprawl for signing; unverifiable provenance in air-gapped nets
- Incompatible air-gap installs (wrong tags, missing extra indexes, no `--no-index` discipline)

---

## Recommendations (prioritised)

### Must

1. **One source of truth for deps**: use `uv` or `pip-tools` to generate hash-pinned constraints (`--require-hashes`) per environment; commit locks
2. **Hermetic CI**: pinned base images; no network during build except index/mirrors you control; ephemeral runners; deterministic clocks
3. **Cross-platform wheelhouse**: build with `cibuildwheel` for Linux (manylinux_2_28), macOS (universal2/x86_64/arm64 as applicable), Windows; vendor native libs with auditwheel/delocate/delvewheel
4. **Private distribution**:
   - Online side: devpi/Nexus/Artifactory as private index; GHCR/OCI as artefact store
   - Offline side: generate a portable wheelhouse bundle (tar + checksums + simple index) per release
5. **Supply-chain guarantees**: SBOM (CycloneDX), OSV scan gate, signatures (Sigstore cosign), SLSA provenance (OIDC in CI) attached to wheel bundles
6. **Policy engine**: allowlist/denylist, version ceilings, upgrade cadences, backport rules; CI blocks on policy violations
7. **Compatibility matrix & tests**: matrix by OS/arch/Python; contract/integration tests executed against the wheelhouse

### Should

- **OCI packaging for bundles**: publish wheelhouse as an OCI artefact (e.g., `ghcr.io/org/pkg/wheelhouse:<version>`), with SBOM/provenance as additional OCI layers
- **Binary reproducibility check**: rebuild subset out-of-band and compare digests (bit-for-bit or normalized)
- **Proactive CVE backports**: maintain "security constraints" overlay to pin safe minima without jumping majors

### Nice

- **Nix/Guix profile** for maximal hermeticity (optional path)
- **Auto-advice bot**: PR comments proposing safe upgrades, impact radius, and policy rationale

---

## Reference CI Blueprint

GitHub Actions (adapt for GitLab/Buildkite):

```yaml
name: build-wheelhouse
on: [push, workflow_dispatch, release]
jobs:
  wheels:
    strategy:
      matrix:
        os: [ubuntu-24.04, macos-14, windows-2022]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - name: Install tooling
        run: |
          python -m pip install --upgrade pip
          pip install uv cibuildwheel==2.* cyclonedx-bom==4.* osv-scanner==1.* cosign
      - name: Resolve deps (hash-pinned)
        run: |
          uv pip compile pyproject.toml -o constraints.txt --generate-hashes
          uv pip sync -r constraints.txt
      - name: Build wheels
        env:
          CIBW_BUILD: "cp38-* cp39-* cp310-* cp311-* cp312-*"
          CIBW_SKIP: "pp* *_i686 *-musllinux*"
          CIBW_MANYLINUX_X86_64_IMAGE: "quay.io/pypa/manylinux_2_28_x86_64"
          CIBW_ARCHS: "x86_64"
          CIBW_TEST_COMMAND: "python -c 'import yourpkg; print(yourpkg.__version__)'"
        run: |
          python -m cibuildwheel --output-dir wheelhouse
      - name: SBOM + Vulnerability gate
        run: |
          cyclonedx-py --format json -o wheelhouse/sbom.json .
          osv-scanner --lockfile=constraints.txt --format json > wheelhouse/osv.json
      - name: Bundle wheelhouse (offline)
        run: |
          python - <<'PY'
          import hashlib, tarfile, json, os
          fn="wheelhouse.tar.gz"
          with tarfile.open(fn,"w:gz") as tar:
              tar.add("wheelhouse", arcname="wheelhouse")
          h=hashlib.sha256(open(fn,"rb").read()).hexdigest()
          open("wheelhouse.sha256","w").write(f"{h}  {fn}\n")
          meta={"commit":"${{ github.sha }}"}
          open("wheelhouse.meta.json","w").write(json.dumps(meta,indent=2))
          PY
      - name: Sign artefacts (keyless)
        env: { COSIGN_EXPERIMENTAL: "1" }
        run: |
          cosign sign-blob --yes wheelhouse.tar.gz > wheelhouse.sig
      - uses: actions/upload-artifact@v4
        with: { name: wheelhouse-${{ matrix.os }}, path: wheelhouse* }
```

Optionally add a publish job that uses `oras` to push `wheelhouse.tar.gz`, `sbom.json`, `osv.json`, `slsa.provenance` to GHCR as an OCI artefact.

---

## Air-gapped Consumption (two paths)

### A) Simple, no server

```bash
# On offline runner (bundle already copied in)
tar -xzf wheelhouse.tar.gz
pip install --no-index --find-links=wheelhouse -r requirements.txt
```

### B) Local index (devpi offline)

```bash
# Prepare once (no Internet)
devpi-server --serverdir /srv/devpi --offline &
devpi use http://localhost:3141/root/offline
devpi login root --password=''
devpi index -c offline volatile=False

# Load all wheels
find wheelhouse -name '*.whl' -print0 | xargs -0 -I{} devpi upload --from-dir {}
pip install --index-url http://localhost:3141/root/offline/simple --no-deps yourpkg==X.Y.Z
```

---

## Orchestration & Integration

- **Interfaces**: CLI (`tool smith wheelhouse build|bundle|publish|mirror`), REST (list/query artefacts), and OCI endpoints so any system can pull bundles
- **Policy hooks**: pre-merge bot comments and CI checks:
  1. Hash-pinned?
  2. Policy compliance?
  3. OSV clean?
  4. SBOM present?
  5. Provenance verified?
- **Metadata contract**: each wheelhouse carries `sbom.json`, `osv.json`, `*.sig`, `sha256`, and `slsa.provenance`. Consumers verify before install

---

## KPIs & Gates

- **Reproducibility**: ≥95% identical rebuilds (90%/50% intervals: 90–99% / 80–100%)
- **Coverage**: ≥98% target OS/arch wheels present per release
- **Security**: 0 known criticals at ship; <48h patch SLA for highs
- **Determinism**: 100% installs with `--require-hashes` and `--no-index` in air-gapped jobs

---

## Provenance Block

- **Data**: Industry packaging norms (PEP 517/518; manylinux), cibuildwheel behaviours, SBOM/OSV/Sigstore/SLSA practices
- **Methods**: Threat-model + failure-mode enumeration; CI blueprint; offline install drills
- **Key results**: Deterministic, attested wheelhouse with offline path; reduced attack surface; plug-and-play consumption
- **Uncertainty**: Exact OS/arch matrix and native-lib needs vary by your codebase. Minor tuning likely (e.g., `CIBW_*` env, QEMU)
- **Safer alternative**: Start with Linux-only wheelhouse + private index, then expand to macOS/Windows once green
