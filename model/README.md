# Model serving scaffold

This package provides the integration points for high-throughput language model
serving, CPU/offline fallbacks, and embedding pipelines. All implementations are
lightweight shims so downstream development can slot in concrete backends
without reworking the orchestrator contract.

- `config.py` exposes structured settings for model selection and tuning.
- `gateways.py` defines the runtime interfaces shared across inference engines.
- `providers/` contains concrete gateway adapters (for example, vLLM and
  llama.cpp) that currently stub behaviour with informative `NotImplemented`
  errors.
- `embeddings/` holds vectorisation utilities such as
  Sentence-Transformers loaders.

Replace the stub methods with real calls to your serving stack once hardware and
model assets are available.
