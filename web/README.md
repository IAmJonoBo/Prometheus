# Prometheus web workspace

This directory hosts the Next.js scaffolding for the Prometheus collaboration
UI. It is intentionally minimal so engineers can layer in authentication,
collaboration, and visualisation features without re-running `create-next-app`.

## Getting started

1. Install dependencies (choose any Node package manager):

   ```bash
   pnpm install
   # or
   npm install
   ```

2. Launch the dev server:

   ```bash
   pnpm dev
   ```

3. During development, run the Python API (`poetry run prometheus-api`) and the
   infrastructure stack (`docker compose up` inside `infra/`) so UI fetches can
   target realistic backends.

## Project structure

- `app/` — App Router entrypoints (layout, global styles, root page).
- `next.config.mjs` — Next.js configuration (strict mode, server actions).
- `tsconfig.json` — TypeScript configuration tuned for strict mode.
- `types/` — Temporary ambient declarations until real dependencies and types
  are installed.

## Next steps

- Replace the placeholder ambient types with actual `node_modules` once the UI
  dependencies are installed.
- Introduce state management (`@tanstack/react-query`, Zustand) and design
  system components.
- Wire API calls to `/v1/pipeline/run` and upcoming retrieval/monitoring
  endpoints.
