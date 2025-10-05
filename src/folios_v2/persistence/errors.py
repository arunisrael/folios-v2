"""Custom persistence exceptions."""

from __future__ import annotations


class RepositoryError(RuntimeError):
    """Base class for persistence layer errors."""


class NotFoundError(RepositoryError):
    """Raised when a requested entity is missing."""


class ConcurrencyError(RepositoryError):
    """Raised when optimistic concurrency fails."""
