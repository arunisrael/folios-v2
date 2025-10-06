"""Request orchestration service."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from folios_v2.domain import (
    ExecutionMode,
    ExecutionTask,
    LifecycleState,
    ProviderId,
    Request,
    RequestId,
    RequestPriority,
    RequestType,
    Strategy,
    TaskId,
)
from folios_v2.persistence import UnitOfWork
from folios_v2.providers import ProviderRegistry
from folios_v2.screeners import ScreenerError, ScreenerResult, ScreenerService
from folios_v2.utils import ensure_utc

from .prompt_builder import build_research_prompt

UnitOfWorkFactory = Callable[[], UnitOfWork]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class RequestOrchestrator:
    """Creates provider-bound requests and bootstraps execution tasks."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        registry: ProviderRegistry,
        artifacts_root: Path,
        *,
        screener_service: ScreenerService | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._registry = registry
        self._artifacts_root = artifacts_root
        self._screener_service = screener_service
        self._logger = logger or logging.getLogger(__name__)

    async def enqueue_request(
        self,
        strategy: Strategy,
        *,
        provider_id: ProviderId,
        request_type: RequestType,
        mode: ExecutionMode,
        priority: RequestPriority = RequestPriority.NORMAL,
        scheduled_for: datetime | None = None,
        metadata: Mapping[str, str] | None = None,
    ) -> tuple[Request, ExecutionTask]:
        self._registry.require(provider_id, mode)
        request_id = RequestId(uuid4())
        task_id = TaskId(uuid4())
        scheduled_ts = ensure_utc(scheduled_for) if scheduled_for else None

        strategy_for_prompt, screener_result = await self._prepare_strategy(strategy)

        prompt = build_research_prompt(
            strategy_for_prompt,
            mode=mode,
            screener_candidates=screener_result.symbols if screener_result else None,
        )

        base_metadata = {
            "strategy_name": strategy_for_prompt.name,
            "provider": provider_id.value,
            "request_type": request_type.value,
            "strategy_prompt": prompt,
            "output_schema": "investment_analysis_v1",
        }
        if screener_result is not None:
            base_metadata.update(
                {
                    "screener_provider": screener_result.provider.value,
                    "screener_candidates": ",".join(screener_result.symbols),
                    "screener_filters": json.dumps(screener_result.filters),
                    "screener_refreshed_at": screener_result.fetched_at.isoformat(),
                    "screener_candidate_count": str(len(screener_result.symbols)),
                }
            )
        if metadata is not None:
            base_metadata.update(metadata)

        request = Request(
            id=request_id,
            strategy_id=strategy_for_prompt.id,
            provider_id=provider_id,
            mode=mode,
            request_type=request_type,
            priority=priority,
            lifecycle_state=LifecycleState.PENDING,
            metadata=base_metadata,
            scheduled_for=scheduled_ts,
        )

        artifacts_dir = self._artifacts_root / str(request_id) / str(task_id)
        task = ExecutionTask(
            id=task_id,
            request_id=request_id,
            sequence=1,
            mode=mode,
            lifecycle_state=LifecycleState.PENDING,
            metadata={"artifact_dir": str(artifacts_dir)},
        )

        async with self._uow_factory() as uow:
            if strategy_for_prompt is not strategy:
                await uow.strategy_repository.upsert(strategy_for_prompt)
            await uow.request_repository.add(request)
            await uow.task_repository.add(task)
            await uow.commit()

        return request, task

    async def _prepare_strategy(
        self,
        strategy: Strategy,
    ) -> tuple[Strategy, ScreenerResult | None]:
        if self._screener_service is None or strategy.screener is None:
            return strategy, None

        try:
            result = await self._screener_service.run(strategy.screener)
        except ScreenerError as exc:
            self._logger.warning(
                "Screener run failed for strategy %s: %s",
                strategy.id,
                exc,
            )
            return strategy, None

        if result.symbols and tuple(result.symbols) != strategy.tickers:
            updated = strategy.model_copy(
                update={
                    "tickers": tuple(result.symbols),
                    "updated_at": _utc_now(),
                }
            )
            self._logger.info(
                "Refreshed screener for strategy %s via %s (%d candidates)",
                strategy.id,
                result.provider.value,
                len(result.symbols),
            )
            return updated, result

        return strategy, result


__all__ = ["RequestOrchestrator"]
