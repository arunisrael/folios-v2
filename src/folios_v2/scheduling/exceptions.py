"""Scheduling-specific errors."""

from __future__ import annotations


class SchedulingError(RuntimeError):
    """Raised when scheduling cannot compute a valid result."""
