# Prometheus desktop workspace

This directory contains a minimal Tauri shell that will eventually wrap the web
experience for offline-first deployments. The scaffold keeps configuration in
Rust so the desktop app can reuse the Next.js UI under `../web`.

## Requirements

- Rust 1.74+
- `pnpm` (or npm/Yarn) for the web frontend
- `cargo install tauri-cli`

## Development loop

1. Install web dependencies and start the dev server inside `../web`.
2. From this directory run `pnpm tauri dev` or `cargo tauri dev` to launch the
   desktop shell pointed at `http://localhost:3000`.
3. When building distributables, run `pnpm tauri build` (this calls the web
   `build` script before bundling).

The configuration disables bundling by default (`bundle.active = false`). Enable
it once signing certificates and OS packaging requirements are in place.
