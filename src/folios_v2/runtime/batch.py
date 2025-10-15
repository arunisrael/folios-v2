"""Async batch execution runtime."""

from __future__ import annotations

import asyncio

from folios_v2.domain import ExecutionMode
from folios_v2.providers import ProviderPlugin, SerializationError
from folios_v2.providers.exceptions import ExecutionError
from folios_v2.providers.models import (
    DownloadResult,
    ExecutionTaskContext,
    PollResult,
    SerializeResult,
    SubmitResult,
)

from .models import BatchExecutionOutcome


class BatchRuntime:
    """Coordinates batch submission → polling → download for a single task."""

    def __init__(self, *, poll_interval_seconds: float = 15.0, max_polls: int = 60) -> None:
        self._poll_interval_seconds = poll_interval_seconds
        self._max_polls = max_polls

    async def serialize(
        self,
        plugin: ProviderPlugin,
        ctx: ExecutionTaskContext,
    ) -> SerializeResult:
        """Serialize the request payload for later submission."""

        plugin.ensure_mode(ExecutionMode.BATCH)
        if plugin.serializer is None:
            msg = f"Provider {plugin.provider_id} lacks a serializer for batch mode"
            raise SerializationError(msg)
        return await plugin.serializer.serialize(ctx)

    async def submit(
        self,
        plugin: ProviderPlugin,
        ctx: ExecutionTaskContext,
        payload: SerializeResult | None = None,
    ) -> SubmitResult:
        """Submit a batch job without polling."""

        plugin.ensure_mode(ExecutionMode.BATCH)
        if plugin.batch_executor is None:
            msg = f"Provider {plugin.provider_id} lacks a batch executor"
            raise ExecutionError(msg)
        if payload is None:
            payload = await self.serialize(plugin, ctx)
        return await plugin.batch_executor.submit(ctx, payload)

    async def poll_once(
        self,
        plugin: ProviderPlugin,
        ctx: ExecutionTaskContext,
        provider_job_id: str,
    ) -> PollResult:
        """Poll a batch job exactly once."""

        plugin.ensure_mode(ExecutionMode.BATCH)
        if plugin.batch_executor is None:
            msg = f"Provider {plugin.provider_id} lacks a batch executor"
            raise ExecutionError(msg)
        return await plugin.batch_executor.poll(ctx, provider_job_id)

    async def download(
        self,
        plugin: ProviderPlugin,
        ctx: ExecutionTaskContext,
        provider_job_id: str,
    ) -> DownloadResult:
        """Download the completed batch results."""

        plugin.ensure_mode(ExecutionMode.BATCH)
        if plugin.batch_executor is None:
            msg = f"Provider {plugin.provider_id} lacks a batch executor"
            raise ExecutionError(msg)
        return await plugin.batch_executor.download(ctx, provider_job_id)

    async def run(self, plugin: ProviderPlugin, ctx: ExecutionTaskContext) -> BatchExecutionOutcome:
        plugin.ensure_mode(ExecutionMode.BATCH)
        payload = await self.serialize(plugin, ctx)
        submit_result = await self.submit(plugin, ctx, payload)
        poll_history: list[PollResult] = []

        provider_job_id = submit_result.provider_job_id
        for _ in range(self._max_polls):
            poll_result = await self.poll_once(plugin, ctx, provider_job_id)
            poll_history.append(poll_result)
            if poll_result.completed:
                break
            await asyncio.sleep(self._poll_interval_seconds)
        else:  # pragma: no cover - defensive guard
            msg = f"Provider job {provider_job_id} did not complete within poll budget"
            raise ExecutionError(msg)

        download_result = await self.download(plugin, ctx, provider_job_id)
        return BatchExecutionOutcome(
            submit_result=submit_result,
            download_result=download_result,
            poll_history=poll_history,
        )


__all__ = ["BatchRuntime"]
