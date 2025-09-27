# Model Strategy

Prometheus treats model selection as a dynamic routing problem rather than a
single-provider commitment. The unified model gateway evaluates each request,
applies safety filters, chooses a provider, and tracks outcomes for continuous
improvement.

## Objectives

- Deliver grounded answers that stay within organisational policy boundaries.
- Optimise for cost, latency, and accuracy based on task type.
- Preserve portability by favouring OSS models when possible and falling back
  to hosted offerings only when required.

## Routing flow

1. Normalise the task into a structured prompt with explicit instructions,
   context snippets, and required output schema.
2. Classify the task (reasoning, extraction, generation, transformation) and
   query the capability catalog for suitable models.
3. Score candidate models using live telemetry: historical win rate, latency,
   cost, and safety incidents.
4. Apply policy constraints (data residency, sensitivity, provider allowlist).
5. Dispatch the request with guardrails (stop sequences, max tokens, tool call
   permissions) and record the decision in the model ledger.

## Evaluation loop

- Store prompts, responses, citations, and feedback signals in the evaluation
  warehouse.
- Run scheduled regression suites comparing models on golden tasks and red-team
  scenarios.
- Calibrate scores with human review, forecasting metrics (e.g., Brier scores),
  and downstream business impact measures.

## Safety controls

- Pre-flight scans detect PII and route sensitive work to approved regions.
- Output filters block disallowed content, hallucinated citations, or policy
  violations.
- Automatic retries fall back to safer but slower models when anomalies are
  detected.
- All model interactions are signed and logged for later audits.

## Provider portfolio

- OSS checkpoints (Llama, Mixtral, Mistral) served through **vLLM** for GPU
  throughput or **llama.cpp** for CPU-only and air-gapped deployments as noted
  in `docs/tech-stack.md`.
- Managed APIs (OpenAI, Anthropic, Azure OpenAI) join the routing catalog only
  when latency or accuracy demand exceeds on-prem options, subject to
  governance approval and telemetry parity.
- Specialised models for embeddings and reranking rely on
  **Sentence-Transformers** families and ms-marco cross-encoders; speech or
  vision adapters remain behind scoped plugins.

## Continuous improvement

- Drift detection monitors response quality, latency, and cost deltas by task
  type and surfaces anomalies in Prometheus/Grafana dashboards.
- A/B experiments measure new model effectiveness before broad rollout and log
  results alongside **RAGAS**, **TruLens**, and **HELM** evaluation artefacts.
- Feedback loops from decision outcomes feed into retraining, prompt tuning,
  and the model ledger, with provenance recorded via OpenLineage.
