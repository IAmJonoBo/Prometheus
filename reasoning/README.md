# Reasoning

The reasoning stage coordinates tool-augmented agents that synthesize evidence
into plans, analyses, and answers.

## Responsibilities

- Decompose tasks into tool invocations, critique loops, and reflection passes.
- Maintain guardrails for hallucination detection and assumption surfacing.
- Produce structured outputs with citations and confidence signals.
- Emit `Reasoning.AnalysisProposed` events for the decision stage.

## Inputs & outputs

- **Inputs:** `Retrieval.ContextBundle` events, user intents, organisation
  policy hints, and historical decision records.
- **Outputs:** `Reasoning.AnalysisProposed` events containing narratives,
  evidence links, uncertainty notes, and recommended next actions.
- **Shared contracts:** Define schemas in `common/contracts/reasoning.py`
  (placeholder) and extend documentation in `docs/overview.md` and
  `docs/model-strategy.md`.

## Components

- Planner selecting agent profiles (e.g., analyst, devil's advocate, verifier).
- Tooling adapters (retrieval augmentation, calculators, simulators).
- Critique framework for red/green teaming and debate between agent personas.
- Score aggregator calculating forecast calibration metrics (Brier, log score).

## Observability

- Record prompt/response pairs with hashed identifiers for evaluation suites.
- Log assumption deltas and unknowns for decision-stage transparency.
- Emit latency and cost metrics per agent persona and model route.

## Backlog

- Implement the canonical planner abstraction and persist sessions for replay.
- Build regression suites with golden question-answer sets.
- Document safety guardrails and escalation paths in `docs/quality-gates.md`.
