"""Provider plugin registry."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from folios_v2.domain import ExecutionMode, ProviderId

from .base import ProviderPlugin
from .exceptions import UnsupportedModeError


@dataclass(slots=True)
class ProviderRegistry:
    """Runtime registry mapping provider identifiers to plugins."""

    _plugins: dict[ProviderId, ProviderPlugin] = field(default_factory=dict)

    def register(self, plugin: ProviderPlugin, *, override: bool = False) -> None:
        if not override and plugin.provider_id in self._plugins:
            existing = self._plugins[plugin.provider_id]
            msg = f"Provider {plugin.provider_id} already registered ({existing.display_name})"
            raise ValueError(msg)
        self._plugins[plugin.provider_id] = plugin

    def get(self, provider_id: ProviderId) -> ProviderPlugin:
        try:
            return self._plugins[provider_id]
        except KeyError as exc:  # pragma: no cover - defensive guard
            msg = f"Unknown provider {provider_id}"
            raise KeyError(msg) from exc

    def list_plugins(self) -> Iterable[ProviderPlugin]:
        return tuple(self._plugins.values())

    def supports(self, provider_id: ProviderId, mode: ExecutionMode) -> bool:
        try:
            plugin = self.get(provider_id)
        except KeyError:
            return False
        if mode is ExecutionMode.BATCH:
            return plugin.supports_batch
        if mode is ExecutionMode.CLI:
            return plugin.supports_cli
        return plugin.supports_batch or plugin.supports_cli

    def require(self, provider_id: ProviderId, mode: ExecutionMode) -> ProviderPlugin:
        plugin = self.get(provider_id)
        try:
            plugin.ensure_mode(mode)
        except UnsupportedModeError as exc:
            raise UnsupportedModeError(str(exc)) from exc
        return plugin


registry = ProviderRegistry()


def register_plugin(plugin: ProviderPlugin, *, override: bool = False) -> None:
    """Register a plugin on the global registry."""

    registry.register(plugin, override=override)


__all__ = ["ProviderRegistry", "register_plugin", "registry"]
