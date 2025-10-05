"""Core base classes for domain models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class DomainModel(BaseModel):
    """Immutable domain model base with strict validation."""

    model_config = ConfigDict(frozen=True, extra="forbid", validate_assignment=True)


class MutableDomainModel(BaseModel):
    """Mutable counterpart used where in-place updates are required."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)
