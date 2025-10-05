"""Provider plugin contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from folios_v2.domain import ExecutionMode, ProviderId

from .exceptions import UnsupportedModeError
from .models import (
    CliResult,
    DownloadResult,
    ExecutionTaskContext,
    PollResult,
    ProviderThrottle,
    SerializeResult,
    SubmitResult,
)


@runtime_checkable
class RequestSerializer(Protocol):
    """Serializes canonical request payloads into provider-specific artifacts."""

    async def serialize(self, ctx: ExecutionTaskContext) -> SerializeResult: ...


@runtime_checkable
class ResultParser(Protocol):
    """Parses provider output into the canonical schema."""

    async def parse(self, ctx: ExecutionTaskContext) -> Mapping[str, Any]: ...


@runtime_checkable
class BatchExecutor(Protocol):
    """Executes batch-oriented provider workflows."""

    async def submit(self, ctx: ExecutionTaskContext, payload: SerializeResult) -> SubmitResult: ...

    async def poll(self, ctx: ExecutionTaskContext, provider_job_id: str) -> PollResult: ...

    async def download(self, ctx: ExecutionTaskContext, provider_job_id: str) -> DownloadResult: ...


@runtime_checkable
class CliExecutor(Protocol):
    """Executes provider logic via a local CLI command."""

    async def run(
        self,
        ctx: ExecutionTaskContext,
        payload: SerializeResult | None = None,
    ) -> CliResult: ...


@dataclass(slots=True)
class ProviderPlugin:
    """Declarative description of a provider integration."""

    provider_id: ProviderId
    display_name: str
    supports_batch: bool
    supports_cli: bool
    default_mode: ExecutionMode
    throttle: ProviderThrottle
    parser: ResultParser
    serializer: RequestSerializer | None = None
    batch_executor: BatchExecutor | None = None
    cli_executor: CliExecutor | None = None
    config_schema: Mapping[str, Any] = field(default_factory=dict)

    def ensure_mode(self, mode: ExecutionMode) -> None:
        """Validate that the plugin supports the requested execution mode."""

        if mode is ExecutionMode.BATCH and not self.supports_batch:
            msg = f"Provider {self.provider_id} does not support batch mode"
            raise UnsupportedModeError(msg)
        if mode is ExecutionMode.CLI and not self.supports_cli:
            msg = f"Provider {self.provider_id} does not support CLI mode"
            raise UnsupportedModeError(msg)

    def requires_serializer(self, mode: ExecutionMode) -> bool:
        """Return whether the given mode requires a serializer."""

        if mode is ExecutionMode.BATCH:
            return True
        if mode is ExecutionMode.CLI:
            return self.serializer is not None
        return True

    def capability_summary(self) -> dict[str, Any]:
        """Structured summary for CLI display or logging."""

        return {
            "provider_id": self.provider_id,
            "display_name": self.display_name,
            "supports_batch": self.supports_batch,
            "supports_cli": self.supports_cli,
            "default_mode": self.default_mode,
            "throttle": {
                "max_concurrent": self.throttle.max_concurrent,
                "requests_per_minute": self.throttle.requests_per_minute,
                "cool_down_seconds": self.throttle.cool_down_seconds,
            },
        }
