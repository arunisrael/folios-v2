"""CLI execution runtime."""

from __future__ import annotations

from folios_v2.domain import ExecutionMode
from folios_v2.providers import ProviderPlugin, SerializationError
from folios_v2.providers.exceptions import ExecutionError
from folios_v2.providers.models import ExecutionTaskContext

from .models import CliExecutionOutcome


class CliRuntime:
    """Runs CLI-based providers for a given task."""

    def __init__(self, *, fail_on_non_zero: bool = True) -> None:
        self._fail_on_non_zero = fail_on_non_zero

    async def run(self, plugin: ProviderPlugin, ctx: ExecutionTaskContext) -> CliExecutionOutcome:
        plugin.ensure_mode(ExecutionMode.CLI)
        if plugin.cli_executor is None:
            msg = f"Provider {plugin.provider_id} lacks a CLI executor"
            raise ExecutionError(msg)

        if plugin.requires_serializer(ExecutionMode.CLI) and plugin.serializer is None:
            msg = f"Provider {plugin.provider_id} requires a serializer for CLI mode"
            raise SerializationError(msg)

        payload = None
        if plugin.serializer is not None:
            payload = await plugin.serializer.serialize(ctx)
        result = await plugin.cli_executor.run(ctx, payload)
        if self._fail_on_non_zero and result.exit_code != 0:
            msg = (
                f"CLI provider {plugin.provider_id} exited with code {result.exit_code}"
            )
            raise ExecutionError(msg)
        return CliExecutionOutcome(result=result)


__all__ = ["CliRuntime"]
