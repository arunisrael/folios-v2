"""Custom exceptions for the screener subsystem."""

from __future__ import annotations


class ScreenerError(RuntimeError):
    """Raised when a screener provider fails to return candidates."""


__all__ = ["ScreenerError"]
