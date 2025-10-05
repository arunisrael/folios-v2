"""Shared models for provider integrations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from folios_v2.domain import ExecutionTask, Request


@dataclass(slots=True)
class ProviderThrottle:
    """Throttle policy declared by a provider plugin."""

    max_concurrent: int = 1
    requests_per_minute: int | None = None
    cool_down_seconds: float | None = None


@dataclass(slots=True)
class ExecutionTaskContext:
    """Context passed to provider executors and parsers."""

    request: Request
    task: ExecutionTask
    artifact_dir: Path
    config: Mapping[str, Any] = field(default_factory=dict)

    def with_artifact(self, relative_path: str) -> Path:
        """Resolve an artifact path relative to the task directory."""

        return self.artifact_dir.joinpath(relative_path)


@dataclass(slots=True)
class SerializeResult:
    """Description of a serialized payload prepared for submission."""

    payload_path: Path
    content_type: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SubmitResult:
    """Result from submitting a batch job."""

    provider_job_id: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PollResult:
    """Polling response from a provider."""

    completed: bool
    status: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DownloadResult:
    """Download response containing artifact location."""

    artifact_path: Path
    content_type: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CliResult:
    """Result of executing a local CLI provider."""

    exit_code: int
    stdout_path: Path | None
    stderr_path: Path | None
    metadata: Mapping[str, Any] = field(default_factory=dict)
