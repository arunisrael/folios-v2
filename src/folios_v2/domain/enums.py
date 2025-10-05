"""Enumerations used across the Folios v2 domain layer."""

from __future__ import annotations

from enum import StrEnum


class ProviderId(StrEnum):
    """Identifiers for supported AI research providers."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    CUSTOM = "custom"


class ExecutionMode(StrEnum):
    """Execution channels available for provider interactions."""

    BATCH = "batch"
    CLI = "cli"
    HYBRID = "hybrid"


class RequestType(StrEnum):
    """High-level intent of a request in the weekly lifecycle."""

    RESEARCH = "research"
    EXECUTION = "execution"
    EMAIL_DIGEST = "email_digest"


class LifecycleState(StrEnum):
    """State machine shared by requests and execution tasks."""

    PENDING = "pending"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    AWAITING_RESULTS = "awaiting_results"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class RequestPriority(StrEnum):
    """Relative priority for scheduling work."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class DigestType(StrEnum):
    """Digest variants supported by notifications."""

    SUNDAY_OUTLOOK = "sunday_outlook"
    FRIDAY_RECAP = "friday_recap"


class StrategyStatus(StrEnum):
    """Lifecycle status for strategies."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    DRAFT = "draft"


class StrategyRunStatus(StrEnum):
    """Aggregated status for a weekly strategy run."""

    PLANNED = "planned"
    RESEARCH_SCHEDULED = "research_scheduled"
    RESEARCH_COMPLETE = "research_complete"
    EXECUTION_SCHEDULED = "execution_scheduled"
    EXECUTION_COMPLETE = "execution_complete"
    FAILED = "failed"


class DeliveryState(StrEnum):
    """Delivery lifecycle for email digests and notifications."""

    PENDING = "pending"
    SENDING = "sending"
    DELIVERED = "delivered"
    FAILED = "failed"
