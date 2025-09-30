# Offline bootstrap gap analysis — 2025-10-22

## Summary
- Offline wheelhouse installation failed: `numpy==1.26.4` wheel absent for
  Python 3.13, blocking the baseline bootstrap command.
- Wheelhouse directory currently only contains `manifest.json` and
  `requirements.txt`; no actual wheels were vendored in git history.
- Baseline QA checks surfaced existing lint violations (ruff) and type-check
  gaps caused by optional dependencies missing from the offline bundle.
- Security tooling (`pip-audit`) is unavailable in the offline environment and
  needs a packaged wheel or alternative scanner.

## Evidence
- `python -m pip install --no-index --find-links vendor/wheelhouse -r
  vendor/wheelhouse/requirements.txt` → fails resolving `numpy==1.26.4` because
  the wheel is missing for Python 3.13.
- `ruff check .` → reports 5 violations in API, evaluation, observability, and
  CLI modules.
- `pyright` → reports 37 missing-import errors tied to optional extras
  (FastAPI, Typer, Prometheus client, OpenTelemetry, TemporalIO, RAG tooling).
- `pip-audit` → command not found; no offline binary available.

## Recommended next actions
1. Rebuild the wheelhouse with `INCLUDE_DEV=true` on Python 3.13 and upload the
   refreshed artefacts (target: Platform, 2025-10-25).
2. Ensure `requirements.txt` reflects the full dependency graph (main + extras)
   needed for baseline QA so offline installs succeed without poetry.
3. Package `pip-audit` (or an approved alternative) into the wheelhouse to keep
   the security gate runnable offline.
4. Document the supported Python interpreter versions in `README-dev-setup.md`
   and align the CI matrix with the wheelhouse build targets.
5. Schedule lint fixes for the `UP038`, `UP035`, and `B904` findings so the
   baseline ruff check can pass once dependencies are restored.
