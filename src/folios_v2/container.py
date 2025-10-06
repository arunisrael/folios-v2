"""Service container wiring application components."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from folios_v2.config import AppSettings
from folios_v2.orchestration import LifecycleEngine, RequestOrchestrator, StrategyCoordinator
from folios_v2.persistence import UnitOfWork
from folios_v2.persistence.sqlite import create_sqlite_unit_of_work_factory
from folios_v2.providers import ProviderRegistry
from folios_v2.providers.anthropic import ANTHROPIC_PLUGIN
from folios_v2.providers.gemini import GEMINI_PLUGIN
from folios_v2.providers.openai import OPENAI_PLUGIN
from folios_v2.runtime import BatchRuntime, CliRuntime
from folios_v2.scheduling import HolidayCalendar, WeekdayLoadBalancer
from folios_v2.screeners import ScreenerError, ScreenerService
from folios_v2.screeners.providers import FMPScreener, FinnhubScreener

UnitOfWorkFactory = Callable[[], UnitOfWork]


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ServiceContainer:
    """Aggregates lazily constructed services with shared configuration."""

    settings: AppSettings
    provider_registry: ProviderRegistry
    screener_service: ScreenerService
    unit_of_work_factory: UnitOfWorkFactory
    load_balancer: WeekdayLoadBalancer
    holiday_calendar: HolidayCalendar
    strategy_coordinator: StrategyCoordinator
    request_orchestrator: RequestOrchestrator
    lifecycle_engine: LifecycleEngine
    batch_runtime: BatchRuntime
    cli_runtime: CliRuntime


def _ensure_sqlite_directory(database_url: str) -> None:
    if not database_url.startswith("sqlite"):
        return
    try:
        _, path = database_url.split(":///", maxsplit=1)
    except ValueError:
        return
    db_path = Path(path).expanduser()
    db_path.parent.mkdir(parents=True, exist_ok=True)


def build_container(settings: AppSettings | None = None) -> ServiceContainer:
    """Construct the primary service container."""

    resolved_settings = settings or AppSettings.from_env()
    artifacts_root: Path = resolved_settings.artifacts_root.expanduser().resolve()
    artifacts_root.mkdir(parents=True, exist_ok=True)

    registry = ProviderRegistry()
    registry.register(OPENAI_PLUGIN, override=True)
    registry.register(GEMINI_PLUGIN, override=True)
    registry.register(ANTHROPIC_PLUGIN, override=True)

    screener_service = ScreenerService()
    if resolved_settings.finnhub_api_key:
        try:
            screener_service.register(
                FinnhubScreener(token=resolved_settings.finnhub_api_key),
                override=True,
            )
        except ScreenerError as exc:  # pragma: no cover - defensive path
            logger.warning("Unable to register Finnhub screener: %s", exc)
    if resolved_settings.fmp_api_key:
        try:
            screener_service.register(
                FMPScreener(token=resolved_settings.fmp_api_key),
                override=True,
            )
        except ScreenerError as exc:  # pragma: no cover - defensive path
            logger.warning("Unable to register FMP screener: %s", exc)

    _ensure_sqlite_directory(resolved_settings.database_url)
    unit_of_work_factory = create_sqlite_unit_of_work_factory(resolved_settings.database_url)
    load_balancer = WeekdayLoadBalancer()
    holiday_calendar = HolidayCalendar()

    strategy_coordinator = StrategyCoordinator(
        unit_of_work_factory,
        load_balancer,
        holiday_calendar,
    )
    request_orchestrator = RequestOrchestrator(
        unit_of_work_factory,
        registry,
        artifacts_root,
        screener_service=screener_service,
        logger=logger,
    )
    lifecycle_engine = LifecycleEngine(unit_of_work_factory)
    batch_runtime = BatchRuntime()
    cli_runtime = CliRuntime()

    return ServiceContainer(
        settings=resolved_settings,
        provider_registry=registry,
        screener_service=screener_service,
        unit_of_work_factory=unit_of_work_factory,
        load_balancer=load_balancer,
        holiday_calendar=holiday_calendar,
        strategy_coordinator=strategy_coordinator,
        request_orchestrator=request_orchestrator,
        lifecycle_engine=lifecycle_engine,
        batch_runtime=batch_runtime,
        cli_runtime=cli_runtime,
    )


__all__ = ["ServiceContainer", "build_container"]
