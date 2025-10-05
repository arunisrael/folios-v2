"""Provider integration-specific exceptions."""

from __future__ import annotations


class ProviderError(RuntimeError):
    """Base class for provider integration failures."""


class SerializationError(ProviderError):
    """Raised when a request payload could not be serialized."""


class ExecutionError(ProviderError):
    """Raised when execution of a task fails irrecoverably."""


class ParseError(ProviderError):
    """Raised when parsing provider output fails."""


class UnsupportedModeError(ProviderError):
    """Raised when a provider plugin does not support a requested execution mode."""
