# Reasoning

The reasoning stage coordinates tool-assisted synthesis of retrieved evidence
into plans, analyses, and answers.

## Responsibilities

- Consume retrieval context, summarise top passages, and surface candidate
  actions.
- Maintain guardrails for hallucination detection and assumption surfacing.
- Produce structured outputs with citations and confidence signals.
- Emit `ReasoningAnalysisProposed` events for the decision stage.

## Inputs & outputs

- **Inputs:** `RetrievalContextBundle` events and optional actor metadata.
- **Outputs:** `ReasoningAnalysisProposed` events containing narratives,
  evidence links, unresolved questions, and recommended next actions.
- **Shared contracts:** `common/contracts/reasoning.py` defines the current
  schema. Extend documentation in `docs/overview.md` and `docs/model-strategy.md`.

## Components

- `ReasoningService` exposes a deterministic planner placeholder that
  summarises retrieved passages into `Insight` objects and outlines follow-up
  actions.
- `ReasoningConfig` wires planner identifiers so future agent profiles can
  inherit the same contract.
- Helper methods convert retrieved passages into insights with capped
  confidence and a one-line summary for downstream policy checks.

## Observability

- The current implementation focuses on deterministic synthesis; logging and
  evaluation harnesses will evolve alongside the model gateway workstream.

## Backlog

- Implement the canonical planner abstraction with tool calling, critique, and
  reflection loops once the model gateway lands.
- Build regression suites with golden question-answer sets and trace-based
  evaluation.
- Document safety guardrails and escalation paths in `docs/quality-gates.md`.
