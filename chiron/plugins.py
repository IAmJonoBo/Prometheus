"""Chiron Plugin System - Foundation for extensibility.

This module provides a plugin system that allows third-party extensions to integrate
with the Chiron subsystem. Plugins can extend dependency management, packaging,
remediation, and other Chiron capabilities.

Plugin Types Supported:
- Dependency analyzers (custom dependency scanners)
- Packaging hooks (pre/post packaging actions)
- Remediation strategies (custom fix strategies)
- Export formats (custom output formats)

Example Plugin:

    from chiron.plugins import ChironPlugin, PluginMetadata

    class MyPlugin(ChironPlugin):
        @property
        def metadata(self) -> PluginMetadata:
            return PluginMetadata(
                name="my-plugin",
                version="1.0.0",
                description="My custom Chiron extension"
            )

        def initialize(self, config: dict) -> None:
            # Plugin initialization logic
            pass
"""

from __future__ import annotations

import abc
import importlib
import importlib.metadata
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PluginMetadata:
    """Metadata describing a Chiron plugin."""

    name: str
    version: str
    description: str
    author: str = ""
    requires: tuple[str, ...] = ()
    entry_point: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Plugin name cannot be empty")
        if not self.version:
            raise ValueError("Plugin version cannot be empty")


class ChironPlugin(abc.ABC):
    """Base class for all Chiron plugins.

    Plugins extend Chiron functionality by implementing this interface.
    """

    @property
    @abc.abstractmethod
    def metadata(self) -> PluginMetadata:
        """Return plugin metadata."""
        ...

    def initialize(self, config: dict[str, Any]) -> None:
        """Initialize the plugin with configuration.

        Args:
            config: Plugin configuration dictionary
        """
        pass

    def cleanup(self) -> None:
        """Clean up plugin resources."""
        pass


@dataclass
class PluginRegistry:
    """Registry for managing Chiron plugins."""

    _plugins: dict[str, ChironPlugin] = field(default_factory=dict)
    _initialized: set[str] = field(default_factory=set)

    def register(self, plugin: ChironPlugin) -> None:
        """Register a plugin.

        Args:
            plugin: Plugin instance to register

        Raises:
            ValueError: If plugin name conflicts with existing plugin
        """
        metadata = plugin.metadata
        if metadata.name in self._plugins:
            raise ValueError(f"Plugin '{metadata.name}' is already registered")

        logger.info(f"Registering plugin: {metadata.name} v{metadata.version}")
        self._plugins[metadata.name] = plugin

    def get(self, name: str) -> ChironPlugin | None:
        """Get a plugin by name.

        Args:
            name: Plugin name

        Returns:
            Plugin instance or None if not found
        """
        return self._plugins.get(name)

    def list_plugins(self) -> list[PluginMetadata]:
        """List all registered plugins.

        Returns:
            List of plugin metadata
        """
        return [plugin.metadata for plugin in self._plugins.values()]

    def initialize_plugin(self, name: str, config: dict[str, Any]) -> None:
        """Initialize a registered plugin.

        Args:
            name: Plugin name
            config: Plugin configuration

        Raises:
            KeyError: If plugin not found
        """
        if name not in self._plugins:
            raise KeyError(f"Plugin '{name}' not found")

        if name in self._initialized:
            logger.warning(f"Plugin '{name}' already initialized")
            return

        logger.info(f"Initializing plugin: {name}")
        plugin = self._plugins[name]
        plugin.initialize(config)
        self._initialized.add(name)

    def cleanup_all(self) -> None:
        """Clean up all initialized plugins."""
        for name in self._initialized:
            plugin = self._plugins[name]
            try:
                plugin.cleanup()
            except Exception as exc:
                logger.error(f"Error cleaning up plugin '{name}': {exc}")
        self._initialized.clear()


# Global plugin registry
_registry = PluginRegistry()


def register_plugin(plugin: ChironPlugin) -> None:
    """Register a plugin with the global registry.

    Args:
        plugin: Plugin instance to register
    """
    _registry.register(plugin)


def get_plugin(name: str) -> ChironPlugin | None:
    """Get a plugin from the global registry.

    Args:
        name: Plugin name

    Returns:
        Plugin instance or None if not found
    """
    return _registry.get(name)


def list_plugins() -> list[PluginMetadata]:
    """List all registered plugins.

    Returns:
        List of plugin metadata
    """
    return _registry.list_plugins()


def discover_plugins(entry_point_group: str = "chiron.plugins") -> list[ChironPlugin]:
    """Discover and load plugins from entry points.

    Args:
        entry_point_group: Entry point group name

    Returns:
        List of discovered plugin instances
    """
    plugins = []

    try:
        entry_points = importlib.metadata.entry_points()
        if hasattr(entry_points, "select"):
            # Python 3.10+
            group = entry_points.select(group=entry_point_group)
        else:
            # Python 3.9
            group = entry_points.get(entry_point_group, [])

        for ep in group:
            try:
                plugin_class = ep.load()
                plugin = plugin_class()
                plugins.append(plugin)
                logger.info(f"Discovered plugin: {ep.name}")
            except Exception as exc:
                logger.error(f"Failed to load plugin '{ep.name}': {exc}")
    except Exception as exc:
        logger.error(f"Error discovering plugins: {exc}")

    return plugins


def initialize_plugins(config: dict[str, dict[str, Any]]) -> None:
    """Initialize all registered plugins with configuration.

    Args:
        config: Dictionary mapping plugin names to their configuration
    """
    for plugin_name in _registry._plugins:
        plugin_config = config.get(plugin_name, {})
        try:
            _registry.initialize_plugin(plugin_name, plugin_config)
        except Exception as exc:
            logger.error(f"Failed to initialize plugin '{plugin_name}': {exc}")


__all__ = [
    "ChironPlugin",
    "PluginMetadata",
    "PluginRegistry",
    "register_plugin",
    "get_plugin",
    "list_plugins",
    "discover_plugins",
    "initialize_plugins",
]
