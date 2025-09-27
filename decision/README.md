# Decision

The decision stage governs how proposed analyses become approved actions while
maintaining a durable audit trail.

## Responsibilities

- Classify decisions by criticality (Type 1 irreversible vs Type 2 reversible).
- Evaluate policy guardrails, conflicts of interest, and compliance rules.
- Capture rationale, alternatives, evidence references, and reviewer comments.
- Emit `Decision.Recorded` events and tasks for execution or additional review.

## Inputs & outputs

- **Inputs:** `Reasoning.AnalysisProposed` events, organisational policy
  catalogues, risk registers, and user roles.
- **Outputs:** `Decision.Recorded` events, approval tasks, escalation alerts,
  and ledger entries stored in the decision database.
- **Shared contracts:** Define schemas in `common/contracts/decision.py`
  (placeholder) and describe workflows in `docs/quality-gates.md`.

## Components

- Policy engine with rule packs (RBAC, regulatory, ethical) and evaluation logs.
- Approval workflow service supporting serial and parallel reviews with SLAs.
- Decision ledger storing structured records and linking evidence attachments.
- Notification adapters for email, chat, and incident management tools.

## Observability

- Metrics: approval cycle time, policy violation rate, blocker aging.
- Traces: follow decision ID through evaluation, approvals, and task creation.
- Logs: include reviewer actions, overrides, and rationale snapshots.

## Backlog

- Finalise ledger schema and publish migrations/example fixtures.
- Implement simulation mode for training reviewers without live impact.
- Extend risk scoring models and document thresholds in `docs/quality-gates.md`.
