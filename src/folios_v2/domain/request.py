"""Request and execution task domain models."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import UUID

from pydantic import Field, field_validator

from .base import DomainModel
from .enums import ExecutionMode, LifecycleState, ProviderId, RequestPriority, RequestType
from .types import JsonMapping, RequestId, TaskId


def utc_now() -> datetime:
    return datetime.now(UTC)


class RequestPayloadRef(DomainModel):
    """Reference to a serialized request payload stored on disk or blob storage."""

    uri: str
    content_type: str = "application/json"
    bytes_estimate: int | None = None


class Request(DomainModel):
    """Unified lifecycle entry representing research/execution/email work."""

    id: RequestId
    strategy_id: UUID
    provider_id: ProviderId
    mode: ExecutionMode
    request_type: RequestType
    priority: RequestPriority = RequestPriority.NORMAL
    lifecycle_state: LifecycleState = LifecycleState.PENDING
    payload_ref: RequestPayloadRef | None = None
    metadata: Mapping[str, str] = Field(default_factory=dict)
    scheduled_for: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @field_validator("scheduled_for", "started_at", "completed_at", mode="before")
    @classmethod
    def ensure_timezone(cls, value: datetime | str | None) -> datetime | None:
        if value is None:
            return value
        if isinstance(value, str):
            # Support ISO strings persisted in storage
            if value.endswith("Z"):
                value = value.replace("Z", "+00:00")
            value = datetime.fromisoformat(value)
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class ExecutionTask(DomainModel):
    """Concrete task executed via batch or CLI runtime."""

    id: TaskId
    request_id: RequestId
    sequence: int
    mode: ExecutionMode
    lifecycle_state: LifecycleState
    scheduled_for: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    provider_job_id: str | None = None
    cli_exit_code: int | None = None
    stdout_path: str | None = None
    stderr_path: str | None = None
    artifact_path: str | None = None
    attempt: int = 1
    max_attempts: int = 3
    error: str | None = None
    metadata: JsonMapping = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @field_validator("scheduled_for", "started_at", "completed_at", mode="before")
    @classmethod
    def ensure_timezone(cls, value: datetime | str | None) -> datetime | None:
        if value is None:
            return value
        if isinstance(value, str):
            # Support ISO strings persisted in storage
            if value.endswith("Z"):
                value = value.replace("Z", "+00:00")
            value = datetime.fromisoformat(value)
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class RequestLogEntry(DomainModel):
    """Audit log entry for request/task transitions."""

    request_id: RequestId
    task_id: TaskId | None = None
    previous_state: LifecycleState | None = None
    next_state: LifecycleState
    message: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    attributes: Mapping[str, str] = Field(default_factory=dict)
