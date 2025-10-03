# Upgrade Guard Strategy

## Purpose

The upgrade guard protects production deployments from risky dependency
changes. It aggregates dependency preflight telemetry, Renovate metadata,
external CVE intelligence, and governance signals from the dependency
contract, then emits a scored recommendation that feeds CI and governance
workflows. This document lays out the orchestration design and interfaces
needed to implement the guard without blocking future extensions.

## Objectives

- Detect incompatibilities before Renovate opens an upgrade PR.
- Continuously surface critical or high CVEs that affect pinned dependencies.
- Flag upgrades that are safe, risky, or blocked with a clear severity rubric.
- Produce actionable artefacts: machine-readable summaries for automation and
  human-readable reports for maintainers.
- Run in fully offline or partially connected environments without failing
  hard when inputs are unavailable.

## Architecture Overview

The guard runs as an orchestrated job invoked locally, via CI, and inside the
pipeline dry-run workflow. It uses the following high-level stages:

1. **Data acquisition** collects inputs from existing tooling:
   - `scripts/preflight_deps.py --json` to summarise wheel coverage issues.
   - Renovate metadata exported from `.renovaterc` or GitHub API responses.
   - CVE feeds pulled from OSV or pre-fetched JSON files in `vendor/security/`.
     Each fetch writes a JSON artefact to `var/upgrade-guard/<timestamp>/inputs/`.
   - The dependency contract (`configs/dependency-profile.toml`) that encodes
     policy defaults, validation cadence, and allowlists.
2. **Normalisation** parses raw payloads into a shared schema (`UpgradeGuardInput`).
   Missing payloads are represented with `source_state="missing"` so the guard
   can degrade gracefully.
3. **Scoring** applies a policy matrix combining:
   - Highest CVSS severity per package.
   - Presence of preflight errors (missing wheels, ABI breaks).
   - Renovate instability signals (major version jumps, known breaking change tags).
     The scoring engine emits an `UpgradeGuardAssessment` containing per-package
     risk levels (`safe`, `needs-review`, `blocked`) and rollup severity.
4. **Governance emission** publishes:
   - A Markdown summary stored at
     `var/upgrade-guard/<timestamp>/summary.md` for humans, including contract
     freshness state and policy notes.
   - A JSON decision envelope at
     `var/upgrade-guard/<timestamp>/assessment.json` for automation.
   - A `CIFailureRaised` (or future `UpgradeGuardRaised`) event on the pipeline
     bus when severity is `needs-review` or `blocked`.
5. **Outputs and retention**: each run materialises a deterministic snapshot at
   `var/upgrade-guard/<run-id>/` containing:
   - the normalised assessment (`reports/assessment.json`)
   - a Markdown summary (`reports/summary.md`)
   - source evidence copies under `inputs/` (preflight, Renovate, CVE feed,
     contract, SBOM, and metadata)
   - a machine-readable `manifest.json` describing copied artefacts, cadence
     measurements, and any pruned history

   Snapshots are linked from dry-run manifests and uploaded as CI artefacts. A
   rolling retention window (default 30 days) keeps the directory bounded while
   preserving recent evidence.

## Data Contracts

### UpgradeGuardInput

```json
{
  "source": "preflight|renovate|cve",
  "source_state": "ok|missing|error",
  "generated_at": "ISO-8601",
  "packages": [
    {
      "name": "str",
      "version": "str",
      "next_version": "str|null",
      "issues": [
        {
          "type": "cve|wheel|breaking-change",
          "identifier": "str",
          "severity": "critical|high|medium|low|info",
          "summary": "str"
        }
      ]
    }
  ],
  "metadata": { "raw_path": "str", "notes": "str" }
}
```

### UpgradeGuardAssessment

```json
{
  "generated_at": "ISO-8601",
  "guard_version": "semver",
  "summary": {
    "highest_severity": "critical|high|medium|low|info|unknown",
    "packages_flagged": 4,
    "inputs_missing": ["cve"],
    "notes": []
  },
  "packages": [
    {
      "name": "str",
      "current": "str",
      "candidate": "str|null",
      "risk": "safe|needs-review|blocked",
      "reasons": ["Critical CVE CVE-2025-1234", "Missing manylinux wheel"]
    }
  ],
  "contract": {
    "risk": "safe|needs-review|blocked",
    "status": "fresh|stale|expired|unknown",
    "note": "str",
    "last_validated": "ISO-8601",
    "age_days": 17,
    "threshold_days": 14,
    "contract_status": "active"
  },
  "evidence": {
    "preflight": "path",
    "renovate": "path",
    "cve": "path",
    "contract": "path"
  }
}
```

The guard writes this payload and attaches it to governance events as an
`EvidenceReference`.

## Execution Surface

- **`prometheus upgrade-guard` CLI** – Runs the guard over configured
  dependencies, printing a Markdown summary and setting the exit code (0 safe,
  1 warning, 2 blocked). When CycloneDX SBOMs and version metadata snapshots
  are available, pass them with `--sbom` and `--metadata` so drift analysis is
  included in the final verdict. Snapshot lifecycle controls are exposed via
  `--snapshot-root`, `--snapshot-retention-days`, `--snapshot-tag`, and
  `--skip-snapshots`. SBOM cadence can be enforced with `--sbom-max-age-days`
  (default 7 days).
- **`prometheus deps guard` CLI** – Proxies the same guard workflow through the
  `deps` command group, delegating to `scripts/upgrade_guard.py` while recording
  telemetry. It accepts the same flags as the standalone guard command, making
  it easier to run guard assessments alongside other dependency tooling.
- **`prometheus upgrade-planner` CLI** – Consumes the same SBOM and metadata
  artefacts to produce a resolver-verified upgrade plan. Use `--packages` to
  focus on specific dependencies, `--allow-major` to surface higher-risk
  candidates, and `--skip-resolver` when Poetry is unavailable. The command can
  emit JSON to a file via `--output`, while `--verbose` prints a human-readable
  summary with recommended `poetry update` commands.
- **Dry-run workflow** – Invokes the guard after dependency preflight, stores
  outputs alongside other artefacts, and links them from the dry-run manifest.
- **CI (GitHub Actions)** – Dedicated job consumes Renovate branch metadata,
  executes the guard, and fails the job when severity is `needs-review` or
  `blocked`.

## Configuration

Add a new `[upgrade_guard]` section to `configs/defaults/pipeline_dryrun.toml`:

```toml
[upgrade_guard]
allow_partial_inputs = true
cve_feed = "vendor/security/osv-latest.json"
renovate_metadata = "var/renovate/metadata.json"
score_weights = { cve = 5, preflight_error = 4, breaking_change = 3 }
```

Feature flag `upgrade_guard` (already present) will gate execution in the dry
run orchestrator. The CLI will accept overrides via options.

## Error Handling & Edge Cases

- **Missing inputs**: when offline or metadata is absent, the guard records the
  source as `missing`, emits a warning, and marks overall severity as
  `unknown` unless other inputs raise issues. The CLI exits with code 0 but
  notes the missing data so teams can remediate.
- **Stale dependency contract**: when `contract.last_validated` exceeds
  `default_review_days`, the guard raises severity to `needs-review`; once the
  age doubles that threshold the verdict escalates to `blocked` with
  actionable notes in the summary and Markdown output.
- **Conflicting signals**: preflight success but CVE critical → severity is
  `needs-review`; the guard favours higher severity signals to stay conservative.
- **Allowlisted CVEs or wheels**: the configuration supports allowlist patterns
  that downgrade issues to informational, aligning with existing preflight
  allowlists.
- **Stale Renovate data**: metadata older than configurable threshold (default
  48h) triggers an informational warning and relies on other sources.
- **Stale SBOM snapshots**: when the SBOM exceeds the configured cadence window
  (default 7 days) the guard escalates severity to `needs-review`, annotating
  drift notes with the age and adding the measurement to the snapshot manifest.
- **Large dependency sets**: guard processes inputs incrementally to avoid
  loading massive JSON files; streaming parsing (e.g., ijson) will be used in a
  follow-up implementation when files exceed 10 MB.
- **Offline environments**: the guard prefers local feeds under `vendor/` and
  never fails when remote fetches time out; it simply logs the failure and
  records `source_state="error"`.
- **Sensitive data**: output paths live under `var/upgrade-guard` and exclude
  credentials; governance events only reference summary files, not raw CVE feeds.

## Integration with Governance

When severity ≥ `needs-review`, the guard emits a governance event with
references to:

- Preflight summary (existing `allowlisted-sdists.json`).
- Renovate metadata artefact.
- CVE assessment file.
- Drift SBOM plus metadata snapshot (recorded under `evidence.drift` and
  `evidence.drift_metadata`).
- Markdown summary (for humans).

CI workflows can use the JSON output to open GitHub issues automatically with
recommended remediation steps, while dry-run runs publish the same content in
artefact bundles.

## Implementation Notes & Next Steps

1. Implement `scripts/upgrade_guard.py` orchestrating acquisition, scoring, and
   output generation with contract-aware evaluation.
2. Extend `prometheus/cli.py` with an `upgrade-guard` command that reuses the
   script entrypoint.
3. Update dry-run pipeline to invoke guard after dependency preflight when the
   feature flag is enabled.
4. Add unit tests covering input normalisation, scoring, and governance events.
5. Document operational playbooks in `docs/developer-experience.md`.

This design provides the scaffolding required by ADR-0002 while leaving room
for richer data sources (SBOMs, SLSA attestations) in future iterations.
