"""Executable entry point for `python -m folios_v2.cli`."""

from __future__ import annotations

from .app import app


def main() -> None:  # pragma: no cover - thin wrapper
    app()


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()
