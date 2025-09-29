# Decision

The decision stage governs how proposed analyses become approved actions while
maintaining a durable audit trail.

## Responsibilities

- Evaluate proposed analyses, attach rationale, and decide whether the action
  can auto-approve or requires additional review.
- Capture alternative options, policy metadata, and approval placeholders.
- Emit `DecisionRecorded` events that downstream execution consumes.

## Inputs & outputs

- **Inputs:** `ReasoningAnalysisProposed` events plus optional actor metadata.
- **Outputs:** `DecisionRecorded` events with status, rationale, alternatives,
  optional approval tasks, and policy check metadata.
- **Shared contracts:** `common/contracts/decision.py` defines
  `DecisionRecorded` and `ApprovalTask`. Document workflow updates in
  `docs/quality-gates.md`.

## Components

- `DecisionService` exposes a deterministic policy stub that approves when
  recommendations contain follow-up actions and otherwise flags the decision
  for review.
- `DecisionConfig` carries the policy engine name so future engines can share
  the contract without breaking downstream consumers.
- Policy check metadata records the engine identifier and insight counts for
  monitoring without enforcing complex guardrails yet.

## Observability

- Extend monitoring once richer policy engines ship; today the stage emits
  `decision.insight_count` via the monitoring service.

## Backlog

- Finalise ledger persistence, approval workflows, and policy evaluation when
  the dedicated service splits out.
- Implement simulation mode for training reviewers without live impact.
- Extend risk scoring models and document thresholds in `docs/quality-gates.md`.
