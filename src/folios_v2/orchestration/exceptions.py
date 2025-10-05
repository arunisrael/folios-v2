"""Exceptions for orchestration and scheduling."""

from __future__ import annotations


class LifecycleError(RuntimeError):
    """Raised when a lifecycle transition fails validation."""


class InvalidTransitionError(LifecycleError):
    """Raised when an invalid lifecycle transition is requested."""

