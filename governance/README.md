# Governance scaffold

The governance package captures audit, lineage, and reporting primitives. The
module content is intentionally lightweight so teams can wire their preferred
providers without reworking imports elsewhere in the codebase.

- `audit.py` exposes spine classes for immutable ledger entries.
- `lineage.py` defines placeholder OpenLineage emitters.
- `reports.py` sketches reporting hooks for Grafana or downstream BI tooling.
