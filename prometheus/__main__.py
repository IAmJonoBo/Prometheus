"""Executable module shim for the Prometheus CLI."""

from __future__ import annotations

from .cli import main as cli_main


def main(argv: list[str] | None = None) -> int:
    """Delegate to the Typer-powered CLI."""

    return cli_main(argv)


if __name__ == "__main__":  # pragma: no cover - manual entrypoint
    raise SystemExit(main())
