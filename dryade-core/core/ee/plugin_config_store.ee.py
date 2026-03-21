# Copyright (c) 2025-2026 Dryade SAS
# Licensed under the Dryade Enterprise Edition License. See LICENSE_EE.md.
"""Persistent plugin configuration storage (Enterprise Edition).

Stores per-plugin configuration as individual JSON files in a config directory.
Replaces the in-memory dict approach so settings persist across core restarts.

Default location: ~/.dryade/plugin-configs/{plugin_name}.json
"""

import json
import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_DIR = Path.home() / ".dryade" / "plugin-configs"

class PluginConfigStore:
    """File-backed plugin configuration store.

    Each plugin gets its own JSON file. Writes are atomic (temp file + rename)
    to prevent corruption on crash. Thread-safe via a per-instance lock.
    """

    def __init__(
        self,
        plugin_name_or_dir: str | Path | None = None,
        *,
        config_dir: Path | None = None,
    ) -> None:
        """Initialize the config store.

        Args:
            plugin_name_or_dir: Either a plugin name (str) for bound access,
                or a Path to a config directory, or None for defaults.
            config_dir: Explicit config directory (keyword-only, for tests).

        When initialized with a plugin name, ``get()`` and ``patch()`` can be
        called without the plugin_name argument (auto-bound).
        """
        self._bound_name: str | None = None
        if config_dir is not None:
            self._config_dir = config_dir
        elif isinstance(plugin_name_or_dir, str) and "/" not in plugin_name_or_dir:
            self._bound_name = plugin_name_or_dir
            self._config_dir = _DEFAULT_CONFIG_DIR
        elif isinstance(plugin_name_or_dir, Path):
            self._config_dir = plugin_name_or_dir
        else:
            self._config_dir = _DEFAULT_CONFIG_DIR
        self._lock = threading.Lock()

    def _config_path(self, plugin_name: str) -> Path:
        """Return the JSON file path for a plugin."""
        return self._config_dir / f"{plugin_name}.json"

    def get(self, plugin_name: str | None = None) -> dict[str, Any]:
        """Get configuration for a plugin.

        Returns empty dict if plugin has no config or file is corrupt.
        Always returns a copy -- mutations don't affect stored data.

        Args:
            plugin_name: Unique plugin identifier. Uses bound name if omitted.

        Returns:
            Plugin configuration dict, or {} if missing/corrupt.
        """
        plugin_name = plugin_name or self._bound_name
        if not plugin_name:
            return {}
        config_file = self._config_path(plugin_name)
        if not config_file.exists():
            return {}

        try:
            with open(config_file) as f:
                data = json.load(f)
            if not isinstance(data, dict):
                logger.warning("Plugin config for '%s' is not a dict, returning empty", plugin_name)
                return {}
            return dict(data)  # Return a copy
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Corrupt or unreadable config for plugin '%s': %s", plugin_name, e)
            return {}

    def patch(self, plugin_name: str | dict | None = None, updates: dict[str, Any] | None = None) -> dict[str, Any]:
        """Merge updates into a plugin's configuration.

        Creates the config directory and file if they don't exist.
        Uses atomic file writes (write to temp, rename) to prevent corruption.

        Args:
            plugin_name: Unique plugin identifier. Uses bound name if omitted.
                Can also pass a dict as first arg when using bound name.
            updates: Key-value pairs to merge into existing config.

        Returns:
            The merged configuration dict.
        """
        if updates is None and isinstance(plugin_name, dict):
            updates = plugin_name
            plugin_name = self._bound_name
        else:
            plugin_name = plugin_name or self._bound_name
        if not plugin_name or updates is None:
            return {}
        with self._lock:
            current = self.get(plugin_name)
            current.update(updates)

            # Ensure directory exists
            self._config_dir.mkdir(parents=True, exist_ok=True)

            # Atomic write: write to temp file in same dir, then rename
            config_file = self._config_path(plugin_name)
            fd, tmp_path = tempfile.mkstemp(
                dir=self._config_dir, suffix=".tmp", prefix=f".{plugin_name}_"
            )
            try:
                with os.fdopen(fd, "w") as f:
                    json.dump(current, f, indent=2)
                os.replace(tmp_path, config_file)
            except Exception:
                # Clean up temp file on failure
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise

            return dict(current)  # Return a copy
