# Developer Experience

Prometheus aims for a developer experience that matches the ambition of the
strategy OS. The guidance below mirrors `Promethus Brief.md` so contributors can
iterate quickly without compromising safety, quality, or extensibility.

## Repository structure

- `ingestion/ … monitoring/` map one-to-one with pipeline stages. Keep stage
  code, fixtures, and tests scoped locally and expose contracts via `common/`.
- `common/` hosts shared dataclasses, utilities, and client libraries; avoid
  cross-stage imports outside published interfaces.
- `plugins/` contains optional capabilities. Each plugin declares metadata,
  dependencies, and tests so it can ship independently.
- `ux/` holds front-end assets; `docs/` and `docs/ADRs/` capture design history;
  `tests/` mirrors the pipeline for unit, integration, and end-to-end suites.
- `sdk/` exposes the lightweight Python client and CLI helpers for automation.

## Coding standards & tooling

- Enforce 80-character markdown lines and language-specific formatters (Black,
  Ruff, ESLint/Prettier, etc.) via pre-commit.
- Use conventional commits to keep history searchable and drive automated
  release notes.
- Linting, typing, and security scans run locally with `pre-commit`, then again
  in CI. Property-based tests (Hypothesis, fast-check) are encouraged for data
  pipelines and policy rules.

## Testing strategy

- **Unit tests:** Cover pure functions and adapters; fail fast on schema drift.
- **Property tests:** Exercise ingestion parsers, prompt templating, and policy
  evaluators over generated inputs.
- **Integration tests:** Spin up stage combinations (e.g., ingestion → retrieval
  → reasoning) with fixtures to confirm contracts, citations, and observability
  signals.
- **End-to-end rehearsals:** Replay golden scenarios nightly from document drop
  to execution hand-off; compare against approved artefacts.
- **Load & security tests:** Run scheduled stress tests, fuzz prompt inputs,
  scan dependencies, and validate secret hygiene. Fail builds on critical CVEs.

## CI/CD pipeline

1. Open a PR referencing an ADR or roadmap item; describe affected capabilities.
2. GitHub Actions build containers, run linters, unit/integration suites,
   security scans, doc link checks, and SBOM generation.
3. Evaluation harness executes retrieval, groundedness, and safety benchmarks;
   results attach to the PR.
4. On merge, artefacts are signed (Sigstore) and pushed to registries. Staging
   canaries run smoke tests before production promotion.
5. Feature flags gate incomplete work; trunk remains releasable at all times.

## Local development workflow

- Bootstrap environments with `uv` or `poetry` for Python and `pnpm` for web
  assets. Use `.env.example` from `configs/` as baseline.
- Launch supportive services via docker-compose profiles (vector DB, tracing,
  telemetry) when needed for integration tests.
- Seed test data from `tests/fixtures/` or the CLI to reproduce scenarios.
- Run `scripts/benchmark-env.sh` to update hardware-aware defaults after
  significant machine changes.
- Use `poetry run prometheus pipeline --help` to explore the developer CLI.
  The Typer app also proxies offline packaging via
  `poetry run prometheus offline-package -- --help`, forwarding flags to the
  existing orchestrator without duplicating argument definitions.
- Optional extras mirror platform capabilities:
  - `poetry install --with pii` enables Presidio-powered ingestion guards
  - `poetry install --with rag,llm` pulls Haystack, DSPy, RAGAS, TruLens, MTEB,
    llama.cpp, and sentencepiece for advanced retrieval and evaluation work
  - `poetry install --with governance,integrations` adds Keycloak/OpenFGA SDKs,
    boto3, redis, and the Cassandra driver for policy and integration testing
- Run `poetry run prometheus evaluate-rag` to score retrieval pipelines using
  RAGAS by default (pass `--use-trulens` to switch to TruLens when installed).
  The CLI normalises metric names across recent RAGAS releases (the
  `context_precision` rename introduced in 0.1.19 is mapped back to the legacy
  `context_relevancy` key) so dashboards and regression harnesses keep working
  after upgrades.
- Build dependency wheelhouses on a machine with network access by running
  `scripts/build-wheelhouse.sh` (optionally `INCLUDE_DEV=true` and
  `EXTRAS=pii`). Commit the resulting `vendor/wheelhouse/` bundle via Git LFS
  so air-gapped environments can install with
  `python -m pip install --no-index --find-links vendor/wheelhouse -r
vendor/wheelhouse/requirements.txt` before invoking `poetry install`.
  Hosts without a `python3` shim (for example GitHub-hosted Windows runners)
  can set `PYTHON_BIN="py -3"` or point to a fully qualified interpreter path
  to guide the script’s auto-detection.

### Offline packaging runbook

The fastest path is the orchestrator CLI:

```bash
poetry run prometheus offline-package
```

It reads `configs/defaults/offline_package.toml`, validates interpreter and
toolchain versions, exports the wheelhouse, warms model caches, captures the
reference container images, emits manifests, regenerates checksums, ensures
`git-lfs` hooks are present, repairs misconfigured hooks, normalises fragile
symlinks, verifies hydrated LFS artefacts, and updates `.gitattributes`. The
dependencies phase now audits `vendor/wheelhouse` to surface missing wheels or
stray artefacts; enable `[cleanup.remove_orphan_wheels]` (or the CLI override)
to prune leftovers automatically. Use `--only-phase`/`--skip-phase` to re-run
subsets or supply `--dry-run` for a no-op rehearsal. Configuration overrides
live in the same TOML file; copy it elsewhere and pass `--config` when
customising extras, images, or Hugging Face tokens.

Wheelhouse findings land in the CLI log and the optional
`vendor/packaging-run.json` telemetry under `wheelhouse_audit`. That manifest
powers the status board and the doctor report so automation can highlight
orphan wheels before they break air-gapped installs.

Watch the tail-end log lines for repository hygiene results. The orchestrator
reports how many symlinks were rewritten and which LFS directories were
verified so operators can catch missing `git-lfs` installs before a commit.
Hook repairs are summarised with the resolved hooks directory so trunk-managed
workflows stay aligned. Those counters land in `vendor/packaging-run.json`
under `repository_hygiene` for CI or audit consumption.

When manual control is required, follow these steps on a workstation with
internet access to prepare assets for air-gapped runners:

1. **Refresh lockfile.** Run `poetry lock --no-update` to ensure
   `poetry.lock` matches the tip commit.
2. **Run preflight doctor.** Execute
   `poetry run python scripts/offline_doctor.py --format table` to confirm
   Python, pip, Poetry, Docker, and the wheelhouse are ready without mutating
   the repository. Add `--format json` when integrating the output into
   automation or dashboards.
3. **Build wheelhouse.** Execute `INCLUDE_DEV=true EXTRAS=pii
scripts/build-wheelhouse.sh`; the script exports wheels and
   `requirements.txt` under `vendor/wheelhouse/`. **Note:** The CI workflow now
   automatically builds and uploads the wheelhouse as part of the `app_bundle`
   artifact on every push to main and PR. This includes:
   - All project dependencies (main + extras)
   - Development dependencies
   - `pip-audit` for offline security scanning
   - Platform-specific wheels
   - Complete manifest with metadata
   
   Manual wheelhouse builds are only needed for local testing or custom
   configurations not covered by CI.
4. **Cache model artefacts.** The toolkit now defaults `HF_HOME`,
   `SENTENCE_TRANSFORMERS_HOME`, and `SPACY_HOME` to directories under
   `vendor/models/`, so simply run `python scripts/download_models.py`.
   The script preloads the default
   Sentence-Transformers embedder, the ms-marco cross-encoder,
   and the `en_core_web_lg` spaCy pipeline. Add `--sentence-transformer`,
   `--cross-encoder`, or `--spacy-model` flags to pull additional artefacts,
   or use `--skip-spacy` when the PII extra is disabled.
5. **Capture container images (optional).** `docker pull` the reference
   Temporal, Qdrant, and OpenSearch images used in local testing, then `docker
save` them into `vendor/images/` tarballs.
6. **Generate checksums.** Run `find vendor -type f -print0 | sort -z | xargs
-0 shasum -a 256 > vendor/CHECKSUMS.sha256` for auditable verification.
7. **Commit via Git LFS.** Ensure `git lfs install` has been run, add the
   populated `vendor/` directories, check for stray symlinks or pointer files,
   and push to the remote. The orchestrator now performs `git lfs push --all`
   automatically, so every packaging run uploads large artefacts alongside the
   pointer commit.
8. **Clean up (optional).** Remove local artefacts only after validating the
   push; leave `.gitattributes` untouched so the tracking rules persist.

### Automated CI Packaging

The CI workflow (`.github/workflows/ci.yml`) now automates wheelhouse
generation on every push to main and pull request. This ensures offline
packages are always available and prevents issues like missing wheels (see PR
#90). The workflow:

- Builds a complete wheelhouse with all dependencies and extras
- Includes `pip-audit` for offline security scanning
- Validates the wheelhouse has actual wheel files (not just manifest)
- Tests offline installation in the `consume` job
- Uploads artifacts with 30-day retention
- Generates a comprehensive build summary

To download CI-built wheelhouse artifacts:
1. Navigate to the Actions tab in GitHub
2. Select the workflow run for your commit
3. Download the `app_bundle` artifact
4. Extract and find the wheelhouse in `dist/wheelhouse/`

The consume job verifies offline installation works by:
- Checking wheel count in the wheelhouse
- Creating a test virtualenv
- Installing packages using `--no-index --find-links`
- Verifying pip-audit availability for security scanning

Air-gapped machines can now run `python3 scripts/bootstrap_offline.py` to
install dependencies from the cached wheelhouse without touching PyPI. The
script honours the wheelhouse manifest, supports `--dry-run` rehearsals, and
can create a virtual environment automatically. Supply
`--wheelhouse-url/--models-url/--images-url` to hydrate from workflow
artefacts when Git LFS is unreachable. After the bootstrap completes, load
bundled models, import container images with `docker load`, and proceed to
`poetry install` for application metadata such as scripts.

## Plugin & SDK experience

- Implement plugins by subclassing the published interfaces in `common/` and
  registering via entry points. Provide README, manifest, and tests per plugin.
- Maintain semantic versioning for plugin APIs; deprecations require one release
  notice and migration guides.
- The CLI and SDK expose staging-friendly commands (`prometheus pipeline`,
  `prometheus plugins`, etc.) or the `sdk.PrometheusClient` helper to run
  pipelines locally.

## Documentation & knowledge sharing

- Document any public-facing change alongside code: update module READMEs,
  `docs/tech-stack.md`, topic guides, and ADRs as needed. CI flags PRs that
  touch contracts without doc updates.
- Record demos and usability findings; link to monitoring feedback loops so
  operational teams can learn new workflows.
- Keep `docs/ROADMAP.md` current with milestone status, risks, and open
  questions.

## Maintenance & hygiene

- Run `scripts/cleanup-macos-cruft.sh` or enable `.githooks/` to remove Finder
  artefacts.
- Track dependency freshness; schedule regular upgrade windows with full
  regression runs and performance benchmarks.
- Apply deprecation tags before removing APIs or events; maintain compatibility
  shims until consumers migrate.

## Contribution process

- Every PR receives code review from a stage owner plus security or compliance
  delegate when relevant.
- ADRs capture significant design shifts; update the architecture docs and link
  related issues for traceability.
- Use discussions and office hours to vet plugin proposals or large refactors
  before implementation.

Following these practices keeps Prometheus adaptable, auditable, and pleasant to
build. When workflow pain emerges, log it in the DX backlog so we can iterate
rapidly.
