# Copyright (c) 2025-2026 Dryade SAS
# Licensed under the Dryade Enterprise Edition License. See LICENSE_EE.md.
"""Plugin System for Dryade.

Provides plugin discovery, loading, and lifecycle management.
Plugins can register extensions with the ExtensionRegistry.
"""

import asyncio
import functools
import importlib.util
import json
import logging
import sys
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib.metadata import entry_points
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import parse as parse_version

# Import from unified exception hierarchy
from core.exceptions import PluginConflictError, PluginValidationError, PluginVersionError

if TYPE_CHECKING:
    from collections.abc import Awaitable

# Type variable for decorator return type
F = TypeVar("F", bound=Callable)

logger = logging.getLogger(__name__)

# =============================================================================
# EE Plugin Security (conditional import)
# =============================================================================
# Community users without the EE module get zero plugins loaded.
# This is correct — community users don't have PM pushing allowlists.

try:
    from core.ee.plugin_security_ee import (
        _allowlist_cache_lock,
        _compute_dryadepkg_hash,
        _compute_dryadepkg_hash_sha3,
        _compute_plugin_hash,
        _compute_plugin_hash_sha3,
        _derive_plugin_key,
        _get_plugin_encryption_key,
        _load_allowlist,
        _verify_ui_bundle,
        reload_allowlist,
        validate_before_load,
        verify_dryadepkg_hash,
        verify_plugin_hash,
    )

    _HAS_PLUGIN_SECURITY = True
except ImportError:
    _HAS_PLUGIN_SECURITY = False
    _allowlist_cache_lock = threading.Lock()
    _load_allowlist = None  # type: ignore[assignment]
    reload_allowlist = None  # type: ignore[assignment]
    validate_before_load = None  # type: ignore[assignment]
    verify_plugin_hash = None  # type: ignore[assignment]
    verify_dryadepkg_hash = None  # type: ignore[assignment]
    _verify_ui_bundle = None  # type: ignore[assignment]
    _compute_plugin_hash = None  # type: ignore[assignment]
    _compute_plugin_hash_sha3 = None  # type: ignore[assignment]
    _compute_dryadepkg_hash = None  # type: ignore[assignment]
    _compute_dryadepkg_hash_sha3 = None  # type: ignore[assignment]
    _derive_plugin_key = None  # type: ignore[assignment]
    _get_plugin_encryption_key = None  # type: ignore[assignment]
    logger.info(
        "Plugin security module not available — no plugins will load "
        "(community mode: PM not present)"
    )

# =============================================================================
# Plugin Health API Data Classes
# =============================================================================

@dataclass
class PluginHealthCheck:
    """Definition of a plugin health check.

    Plugins return these from get_health_checks() to register their
    dependencies with the health monitoring system.

    Attributes:
        name: Unique identifier for this check within the plugin
        category: 'critical', 'important', or 'optional'
        check_fn: Async callable that returns (healthy: bool, message: str, latency_ms: float|None)
        description: Human-readable description of what this check verifies
        timeout_seconds: Maximum time to wait for check (default 5s)
    """

    name: str
    category: str  # 'critical', 'important', 'optional'
    check_fn: Callable[[], "Awaitable[tuple[bool, str, float | None]]"]
    description: str = ""
    timeout_seconds: float = 5.0

@dataclass
class ManageableComponent:
    """Definition of a manageable plugin component.

    Plugins return these from get_manageable_components() to expose
    state that can be monitored or managed through the API.

    Attributes:
        name: Unique identifier for this component within the plugin
        type: Component type ('cache', 'connection', 'queue', 'worker', etc.)
        description: Human-readable description
        actions: List of action names this component supports (e.g., ['clear', 'stats', 'restart'])
        get_status_fn: Optional async callable to get current status
        execute_action_fn: Optional async callable to execute an action
    """

    name: str
    type: str  # 'cache', 'connection', 'queue', 'worker', 'storage', etc.
    description: str = ""
    actions: list[str] = field(default_factory=list)
    get_status_fn: Callable[[], "Awaitable[dict[str, Any]]"] | None = None
    execute_action_fn: Callable[[str], "Awaitable[dict[str, Any]]"] | None = None

# PluginValidationError is imported from core.exceptions for backward compatibility

def validate_execution[F: Callable](func: F) -> F:
    """Decorator to validate plugin access before each execution.

    Checks for _validate_access method on self and calls it before proceeding.
    Works with both async and sync methods.

    Args:
        func: Method to wrap with validation

    Returns:
        Wrapped method that validates before execution

    Raises:
        PluginValidationError: If validation fails
    """

    @functools.wraps(func)
    async def async_wrapper(self, *args, **kwargs):
        if hasattr(self, "_validate_access"):
            allowed, reason = self._validate_access()
            if not allowed:
                logger.error(f"Plugin {self.name} validation failed: {reason}")
                raise PluginValidationError(self.name, reason)
        return await func(self, *args, **kwargs)

    @functools.wraps(func)
    def sync_wrapper(self, *args, **kwargs):
        if hasattr(self, "_validate_access"):
            allowed, reason = self._validate_access()
            if not allowed:
                logger.error(f"Plugin {self.name} validation failed: {reason}")
                raise PluginValidationError(self.name, reason)
        return func(self, *args, **kwargs)

    if asyncio.iscoroutinefunction(func):
        return async_wrapper  # type: ignore
    return sync_wrapper  # type: ignore

def _get_core_version() -> str:
    """Get current core version.

    Returns:
        Version string from package metadata, or "1.0.0" as fallback
    """
    try:
        from importlib.metadata import version

        return version("dryade-core")
    except Exception:
        return "1.0.0"  # Fallback

def _is_production() -> bool:
    """Check if running in production environment.

    Returns:
        True if ENVIRONMENT or DRYADE_ENV is "production"
    """
    import os

    env = os.getenv("ENVIRONMENT", os.getenv("DRYADE_ENV", "development")).lower()
    return env == "production"

class PluginProtocol(ABC):
    """Base class for all Dryade plugins.

    Plugins must implement:
    - name: Unique plugin identifier
    - version: Semver version string
    - description: Human-readable description
    - core_version_constraint: SemVer range for compatible core versions
    - register(): Register extensions with the registry

    Attributes:
        name: Unique plugin identifier
        version: Plugin semver version string
        description: Human-readable description
        core_version_constraint: SemVer range for compatible core versions
                                 e.g., ">=1.0.0,<2.0.0" or ">=1.5.0"

    Example:
        class MyPlugin(PluginProtocol):
            name = "my_plugin"
            version = "1.0.0"
            description = "My custom plugin"
            core_version_constraint = ">=1.0.0,<2.0.0"

            def register(self, registry):
                registry.register(ExtensionConfig(...))
    """

    name: str
    version: str
    description: str
    core_version_constraint: str = ">=1.0.0"  # Default: any 1.x+

    @abstractmethod
    def register(self, registry) -> None:
        """Register plugin's extensions with the registry."""
        pass

    def startup(self, **kwargs) -> None:  # noqa: B027
        """Optional startup hook called after all plugins loaded.

        Args:
            app: FastAPI application instance (optional, for accessing extension points
                 like app.state.register_shareable_type)
        """
        pass

    def shutdown(self) -> None:  # noqa: B027
        """Optional shutdown hook called on application shutdown."""
        pass

    def get_health_checks(self) -> dict[str, "PluginHealthCheck"]:
        """Return health checks for this plugin's dependencies.

        Override this method to expose plugin-specific health checks.
        Each check should verify a dependency the plugin requires.

        Returns:
            Dictionary mapping check name to PluginHealthCheck.
            Empty dict if plugin has no external dependencies.

        Example:
            def get_health_checks(self):
                return {
                    "docker": PluginHealthCheck(
                        name="docker",
                        category="important",
                        check_fn=self._check_docker,
                        description="Docker daemon for sandbox execution",
                    ),
                }
        """
        return {}

    def get_manageable_components(self) -> list["ManageableComponent"]:
        """Return components this plugin exposes for monitoring/management.

        Override this method to expose plugin state that can be monitored
        or configured through the management API.

        Returns:
            List of ManageableComponent instances.
            Empty list if plugin has no manageable state.

        Example:
            def get_manageable_components(self):
                return [
                    ManageableComponent(
                        name="cache",
                        type="cache",
                        description="Semantic cache storage",
                        actions=["clear", "stats"],
                    ),
                ]
        """
        return []

def __getattr__(name):
    """Lazy re-export of EnterprisePluginProtocol from EE module."""
    if name == "EnterprisePluginProtocol":
        try:
            from core.ee.plugin_security_ee import get_enterprise_plugin_protocol

            return get_enterprise_plugin_protocol()
        except ImportError:
            return None
    raise AttributeError(f"module 'core.plugins' has no attribute {name!r}")

# PluginConflictError is imported from core.exceptions for backward compatibility

# PluginVersionError is imported from core.exceptions for backward compatibility

def get_core_version() -> str:
    """Get current core package version.

    Returns:
        Version string from package metadata, or "1.0.0" as fallback
    """
    try:
        from importlib.metadata import version

        return version("dryade-core")
    except Exception:
        return "1.0.0"  # Fallback

class PluginLoader:
    """Discovers and loads plugins via entry points.

    Plugins register themselves in pyproject.toml:
    [project.entry-points."dryade.plugins"]
    plugin_name = "plugins.plugin_name.plugin:plugin"
    """

    def __init__(self):
        """Initialize plugin loader with core version."""
        self._core_version = get_core_version()
        logger.debug(f"Plugin loader initialized for core version {self._core_version}")

    def _check_version_compatibility(self, plugin: PluginProtocol) -> bool:
        """Check if plugin is compatible with core version.

        Args:
            plugin: Plugin to check

        Returns:
            True if compatible

        Raises:
            PluginVersionError: If incompatible
        """
        try:
            specifier = SpecifierSet(plugin.core_version_constraint)
            if parse_version(self._core_version) not in specifier:
                raise PluginVersionError(
                    plugin_name=plugin.name,
                    plugin_constraint=plugin.core_version_constraint,
                    core_version=self._core_version,
                )
            return True
        except InvalidSpecifier as e:
            logger.warning(
                f"Plugin '{plugin.name}' has invalid version constraint "
                f"'{plugin.core_version_constraint}': {e}"
            )
            return True  # Invalid constraint = allow (log warning)

    def discover_plugins(self) -> list[PluginProtocol]:
        """Discover plugins via entry points with graceful degradation.

        Plugins register themselves via pyproject.toml entry points:
        [project.entry-points."dryade.plugins"]
        plugin_name = "plugins.plugin_name.plugin:plugin"

        Failed plugins are logged but don't prevent other plugins from loading.
        Discovery is gated by the signed allowlist -- no allowlist means no plugins.

        Returns:
            List of successfully discovered plugin instances.
        """
        # When EE security module is available, gate by signed allowlist.
        # When absent (community), load all discovered plugins freely.
        if _HAS_PLUGIN_SECURITY:
            allowed = _load_allowlist()
            if allowed is None:
                logger.info("No plugin allowlist found. See docs.dryade.ai/plugins for setup.")
                return []
        else:
            allowed = None  # community: no allowlist gate

        plugins = []
        failed = []

        # Python 3.10+ entry points API
        try:
            discovered = entry_points(group="dryade.plugins")
        except TypeError:
            # Fallback for older Python (shouldn't happen with >=3.10)
            discovered = entry_points().get("dryade.plugins", [])

        for ep in discovered:
            try:
                # Validate before loading
                plugin_name = ep.name
                allowed, reason = validate_before_load(plugin_name)
                if not allowed:
                    logger.error(f"Plugin {plugin_name} not loaded: {reason}")
                    failed.append(plugin_name)
                    continue

                # Load the plugin instance from entry point
                plugin = ep.load()

                if isinstance(plugin, PluginProtocol):
                    # Check version compatibility
                    self._check_version_compatibility(plugin)

                    logger.info(
                        f"Loaded plugin via entry point: {plugin.name} v{plugin.version} "
                        f"(requires core {plugin.core_version_constraint}) from {ep.value}"
                    )
                    plugins.append(plugin)
                else:
                    logger.warning(
                        f"Entry point {ep.name} did not return PluginProtocol instance: "
                        f"got {type(plugin).__name__}"
                    )
                    failed.append(ep.name)

            except PluginVersionError as e:
                # Log version incompatibility but continue loading other plugins
                logger.warning(f"Plugin {ep.name} version incompatible: {e}")
                failed.append(ep.name)
            except Exception as e:
                logger.error(f"Failed to load plugin from entry point {ep.name}: {e}")
                failed.append(ep.name)

        if failed:
            logger.error(f"Failed to load {len(failed)} plugins: {failed}")

        logger.info(f"Discovered {len(plugins)} plugins via entry points")
        return plugins

    def load_plugin(self, plugin_name: str, validate: bool = True) -> PluginProtocol | None:
        """Load a specific plugin by name with graceful degradation.

        Returns None on failure instead of raising exceptions, allowing the
        system to continue operating without failed plugins.

        Args:
            plugin_name: Name of the plugin to load
            validate: Whether to validate before loading (default True)

        Returns:
            Plugin instance or None if loading fails
        """
        try:
            # Check security module availability
            if not _HAS_PLUGIN_SECURITY:
                logger.warning("Plugin security module not available — cannot load plugins")
                return None

            # Validate before loading
            if validate:
                allowed, reason = validate_before_load(plugin_name)
                if not allowed:
                    logger.warning(f"Plugin validation failed for '{plugin_name}': {reason}")
                    return None

            # Proceed with import via entry point
            try:
                discovered = entry_points(group="dryade.plugins")
            except TypeError:
                discovered = entry_points().get("dryade.plugins", [])

            for ep in discovered:
                if ep.name == plugin_name:
                    plugin = ep.load()
                    if isinstance(plugin, PluginProtocol):
                        self._check_version_compatibility(plugin)
                        return plugin
                    else:
                        logger.warning(
                            f"Entry point {ep.name} did not return PluginProtocol instance"
                        )
                        return None

            logger.warning(f"Plugin '{plugin_name}' not found in entry points")
            return None

        except PluginVersionError as e:
            logger.warning(f"Plugin '{plugin_name}' version incompatible: {e}")
            return None
        except Exception as e:
            logger.exception(f"Failed to load plugin '{plugin_name}': {e}")
            return None

class DirectoryPluginLoader:
    """Discovers plugins from a directory.

    Scans a directory for Python modules containing PluginProtocol instances.
    Each plugin must have a module-level `plugin` variable of type PluginProtocol.

    Directory structure expected:
        user_plugins/
            my_plugin/
                __init__.py  # Contains: plugin = MyPlugin()
                plugin.py    # Optional: actual plugin implementation
    """

    def __init__(self, plugins_dir: Path | str):
        """Initialize directory plugin loader.

        Args:
            plugins_dir: Path to directory containing plugin subdirectories
        """
        self.plugins_dir = Path(plugins_dir)
        self._core_version = get_core_version()

    def _check_version_compatibility(self, plugin: PluginProtocol) -> bool:
        """Check if plugin is compatible with core version.

        Args:
            plugin: Plugin to check

        Returns:
            True if compatible

        Raises:
            PluginVersionError: If incompatible
        """
        try:
            specifier = SpecifierSet(plugin.core_version_constraint)
            if parse_version(self._core_version) not in specifier:
                raise PluginVersionError(
                    plugin_name=plugin.name,
                    plugin_constraint=plugin.core_version_constraint,
                    core_version=self._core_version,
                )
            return True
        except InvalidSpecifier as e:
            logger.warning(
                f"Plugin '{plugin.name}' has invalid version constraint "
                f"'{plugin.core_version_constraint}': {e}"
            )
            return True  # Invalid constraint = allow (log warning)

    # Known tier directory names used in the tiered plugin layout
    # (plugins/{starter,team,enterprise}/plugin_name/).
    TIER_DIRS = frozenset({"starter", "team", "enterprise"})

    @staticmethod
    def _ensure_plugins_package() -> None:
        """Ensure a synthetic 'plugins' package exists in sys.modules.

        Plugins use absolute imports like ``from plugins.audio.stt import ...``.
        For these to resolve, ``sys.modules["plugins"]`` must be a package.
        """
        if "plugins" not in sys.modules:
            import types

            pkg = types.ModuleType("plugins")
            pkg.__path__ = []  # namespace package
            pkg.__package__ = "plugins"
            sys.modules["plugins"] = pkg

    @staticmethod
    def _ensure_tier_package(tier: str) -> None:
        """Ensure a synthetic 'plugins.<tier>' package exists in sys.modules."""
        key = f"plugins.{tier}"
        if key not in sys.modules:
            import types

            pkg = types.ModuleType(key)
            pkg.__path__ = []
            pkg.__package__ = key
            sys.modules[key] = pkg

    def _collect_plugin_dirs(self) -> list[tuple[Path, str | None]]:
        """Collect plugin directories, supporting both flat and tiered layouts.

        Flat layout — plaintext:
            plugins_dir/my_plugin/__init__.py

        Flat layout — encrypted marketplace:
            plugins_dir/my_plugin/my_plugin.dryadepkg

        Tiered layout (same as PM scanner):
            plugins_dir/starter/audio/__init__.py
            plugins_dir/team/devops_sre/__init__.py
            plugins_dir/enterprise/finance/__init__.py
            plugins_dir/enterprise/finance/finance.dryadepkg  (encrypted)

        When tier directories are present, non-tier top-level directories
        (e.g. ``tools/``, ``shared/``) are skipped — they are utility packages,
        not plugins.

        Returns:
            List of (plugin_dir, tier_name) tuples.  tier_name is None for
            flat-layout plugins.
        """
        results: list[tuple[Path, str | None]] = []
        has_tiers = False
        for item in self.plugins_dir.iterdir():
            if item.is_dir() and item.name in self.TIER_DIRS:
                has_tiers = True
                # Tier directory — scan one level deeper for actual plugins
                for sub in item.iterdir():
                    if sub.is_dir() and (
                        (sub / "__init__.py").exists() or (sub / f"{sub.name}.dryadepkg").exists()
                    ):
                        results.append((sub, item.name))

        if not has_tiers:
            # Flat layout — scan top-level dirs directly
            for item in self.plugins_dir.iterdir():
                if item.is_dir() and (
                    (item / "__init__.py").exists() or (item / f"{item.name}.dryadepkg").exists()
                ):
                    results.append((item, None))

        return results

    def discover_plugins(self, skip_names: set[str] | None = None) -> list[PluginProtocol]:
        """Discover plugins from directory with graceful degradation.

        Supports both flat and tiered (starter/team/enterprise) layouts.
        Failed plugins are logged but don't prevent other plugins from loading.
        Discovery is gated by the signed allowlist -- no allowlist means no plugins.
        Custom plugin slot limits from v2 allowlist tier metadata are enforced.

        Args:
            skip_names: Optional set of plugin names to silently skip (e.g. already
                loaded via entry points). Avoids noisy warnings on misconfigured dirs.

        Returns:
            List of successfully discovered plugin instances.
        """
        # Check security module availability first
        if not _HAS_PLUGIN_SECURITY:
            logger.info("Plugin security module not available — no plugins will load.")
            return []

        # Check allowlist first - no allowlist = no plugins
        allowed = _load_allowlist()
        if allowed is None:
            logger.info("No plugin allowlist found. See docs.dryade.ai/plugins for setup.")
            return []

        # Check custom plugin slot limit from tier metadata
        from core.ee.allowlist_ee import get_tier_metadata

        tier_meta = get_tier_metadata()
        custom_limit = tier_meta.custom_plugin_slots if tier_meta else 0
        # 0 means unlimited
        custom_loaded = 0

        plugins = []
        failed = []
        if not self.plugins_dir.exists():
            logger.debug(f"User plugins directory not found: {self.plugins_dir}")
            return plugins

        for item, tier in self._collect_plugin_dirs():
            plugin_name = item.name

            # Skip plugins already loaded via entry points
            if skip_names and plugin_name in skip_names:
                logger.debug(
                    f"Skipping directory plugin '{plugin_name}' (already loaded via entry point)"
                )
                continue

            try:
                # Enforce custom plugin slot limit (0 = unlimited)
                if custom_limit > 0 and custom_loaded >= custom_limit:
                    logger.warning(
                        f"Custom plugin slot limit reached ({custom_limit}), "
                        f"skipping remaining directory plugins"
                    )
                    break

                # Validate before loading — allowlist gate
                allowed, reason = validate_before_load(plugin_name)
                if not allowed:
                    logger.error(f"Plugin {plugin_name} not loaded: {reason}")
                    failed.append(plugin_name)
                    continue

                # Determine plugin type: encrypted marketplace vs plaintext custom
                pkg_path = item / f"{plugin_name}.dryadepkg"
                is_encrypted = pkg_path.exists()

                if is_encrypted:
                    # ── Encrypted marketplace plugin path ──────────────────────
                    # Hash verification: compare .dryadepkg file hash against allowlist
                    if not verify_dryadepkg_hash(plugin_name, pkg_path):
                        logger.error(
                            "Encrypted plugin '%s' not loaded: .dryadepkg hash mismatch",
                            plugin_name,
                        )
                        failed.append(plugin_name)
                        continue

                    # Get per-plugin encryption key (HKDF from master secret)
                    encryption_key = _get_plugin_encryption_key(plugin_name)
                    if encryption_key is None:
                        logger.warning(
                            "Encrypted plugin '%s' skipped: DRYADE_ENCRYPTION_SECRET not set",
                            plugin_name,
                        )
                        # Silently skip — not a load failure, just missing config
                        continue

                    try:
                        from core.encrypted_loader import SecurityError, load_encrypted_plugin

                        module = load_encrypted_plugin(pkg_path, encryption_key)
                        plugin = getattr(module, "plugin", None)
                        if isinstance(plugin, PluginProtocol):
                            # Tag as encrypted marketplace plugin so route mounting
                            # knows to wrap through the encrypted bridge.
                            plugin._dryadepkg_encrypted = True  # type: ignore[attr-defined]
                            plugins.append(plugin)
                            custom_loaded += 1
                            logger.info(
                                "Loaded encrypted plugin: %s v%s from %s",
                                plugin.name,
                                plugin.version,
                                pkg_path.name,
                            )
                        else:
                            logger.warning(
                                "Encrypted plugin '%s' has no PluginProtocol instance", plugin_name
                            )
                            failed.append(plugin_name)
                    except SecurityError as e:
                        # Blocked plugins are invisible
                        logger.warning(
                            "Encrypted plugin '%s' failed signature check: %s", plugin_name, e
                        )
                        failed.append(plugin_name)
                    except Exception as e:
                        logger.error("Failed to load encrypted plugin '%s': %s", plugin_name, e)
                        failed.append(plugin_name)

                else:
                    # ── Plaintext custom plugin path (existing behavior) ────────
                    # Verify plugin code hash (plugin code authenticity)
                    # Runs after allowlist name check passes, before any code is imported.
                    if not verify_plugin_hash(plugin_name, item):
                        logger.error(
                            f"Plugin {plugin_name} not loaded: hash mismatch "
                            "(code tampered or not in plugin_hashes)"
                        )
                        failed.append(plugin_name)
                        continue

                    # Check has_ui bundle integrity (strict fail-closed)
                    manifest_path = item / "dryade.json"
                    if manifest_path.exists():
                        try:
                            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
                            if manifest_data.get("has_ui", False):
                                if not _verify_ui_bundle(item, manifest_data):
                                    logger.error(
                                        "Plugin '%s' not loaded: has_ui=true but bundle missing "
                                        "or hash mismatch. Run: dryade build-plugins && dryade-pm push",
                                        plugin_name,
                                    )
                                    failed.append(plugin_name)
                                    continue
                        except (json.JSONDecodeError, OSError) as e:
                            logger.warning(
                                "Plugin '%s': failed to read dryade.json: %s", plugin_name, e
                            )
                            # Manifest unreadable but allowlist+hash passed — still load Python backend

                    plugin = self._load_plugin_from_directory(item, tier=tier)
                    if plugin:
                        plugins.append(plugin)
                        custom_loaded += 1
                    else:
                        failed.append(plugin_name)
            except PluginVersionError as e:
                # Log version incompatibility but continue loading other plugins
                logger.warning(f"Plugin {plugin_name} version incompatible: {e}")
                failed.append(plugin_name)
            except Exception as e:
                logger.error(f"Failed to load plugin from {item}: {e}")
                failed.append(plugin_name)

        if failed:
            logger.error(f"Failed to load {len(failed)} directory plugins: {failed}")

        logger.info(f"Discovered {len(plugins)} plugins from directory {self.plugins_dir}")
        return plugins

    def _load_plugin_from_directory(
        self, plugin_dir: Path, *, tier: str | None = None
    ) -> PluginProtocol | None:
        """Load a single plugin from directory.

        Args:
            plugin_dir: Path to plugin directory containing __init__.py
            tier: Optional tier name (starter/team/enterprise) for module namespacing.

        Returns:
            Plugin instance or None if not found/invalid

        Raises:
            PluginVersionError: If plugin version is incompatible
        """
        # Use "plugins.<name>" namespace to avoid shadowing real packages (e.g., "vllm")
        # and to match the absolute import convention used inside plugins
        # (e.g. "from plugins.document_processor.agent import ...").
        module_name = f"plugins.{plugin_dir.name}"

        # Ensure the synthetic "plugins" package exists so absolute imports resolve.
        self._ensure_plugins_package()

        # For tiered layout, also register a tier-qualified alias
        # (plugins.team.audio) for debugging, but the primary name is plugins.audio.
        tier_alias = f"plugins.{tier}.{plugin_dir.name}" if tier else None
        if tier:
            self._ensure_tier_package(tier)

        spec = importlib.util.spec_from_file_location(
            module_name,
            plugin_dir / "__init__.py",
            submodule_search_locations=[str(plugin_dir)],
        )
        if spec is None or spec.loader is None:
            return None

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        if tier_alias:
            sys.modules[tier_alias] = module
        spec.loader.exec_module(module)

        plugin = getattr(module, "plugin", None)

        # Fallback: if __init__.py doesn't expose `plugin`, try plugin.py directly.
        # Many plugins define the instance in plugin.py but forget to re-export
        # from __init__.py.
        if not isinstance(plugin, PluginProtocol):
            plugin_py = plugin_dir / "plugin.py"
            if plugin_py.exists():
                sub_module_name = f"{module_name}.plugin"
                sub_spec = importlib.util.spec_from_file_location(sub_module_name, plugin_py)
                if sub_spec and sub_spec.loader:
                    sub_module = importlib.util.module_from_spec(sub_spec)
                    sys.modules[sub_module_name] = sub_module
                    sub_spec.loader.exec_module(sub_module)
                    plugin = getattr(sub_module, "plugin", None)

        if isinstance(plugin, PluginProtocol):
            # Check version compatibility
            self._check_version_compatibility(plugin)

            logger.info(
                f"Loaded directory plugin: {plugin.name} v{plugin.version} "
                f"(requires core {plugin.core_version_constraint})"
            )
            return plugin
        else:
            logger.warning(f"No PluginProtocol instance found in {plugin_dir}")
            return None

# Enterprise encrypted plugin loader (conditional import)
try:
    from core.ee.encrypted_loader import ENCRYPTED_PLUGIN_EXTENSION, EncryptedPluginLoader
except ImportError:
    EncryptedPluginLoader = None  # Enterprise feature
    ENCRYPTED_PLUGIN_EXTENSION = ".pye"

# =============================================================================
# Plugin Drainer (graceful hot-reload)
# =============================================================================

class PluginDrainer:
    """Track in-flight requests per plugin and drain on revocation.

    Used during hot-reload: when a plugin is revoked from the allowlist,
    new requests are rejected (403) while in-flight requests finish.
    After drain completes, routes are unmounted (404).

    Usage:
        drainer = get_plugin_drainer()
        if not drainer.request_start("audio"):
            return 403  # plugin is draining
        try:
            # handle request
        finally:
            drainer.request_end("audio")
    """

    def __init__(self):
        """Initialize drainer with empty state."""
        self._inflight: dict[str, int] = {}
        self._draining: set[str] = set()
        self._lock = threading.Lock()

    def request_start(self, plugin_name: str) -> bool:
        """Track request start. Returns False if plugin is draining (reject with 403).

        Args:
            plugin_name: Name of the plugin handling this request.

        Returns:
            True if request may proceed, False if plugin is draining.
        """
        with self._lock:
            if plugin_name in self._draining:
                return False
            self._inflight[plugin_name] = self._inflight.get(plugin_name, 0) + 1
            return True

    def request_end(self, plugin_name: str) -> None:
        """Track request completion.

        Args:
            plugin_name: Name of the plugin that handled this request.
        """
        with self._lock:
            if plugin_name in self._inflight:
                self._inflight[plugin_name] = max(0, self._inflight[plugin_name] - 1)

    async def drain(self, plugin_name: str, timeout: float = 5.0) -> None:
        """Drain in-flight requests with timeout, then signal completion.

        Marks the plugin as draining (new requests rejected with 403),
        waits for in-flight requests to complete, then cleans up.

        Args:
            plugin_name: Name of the plugin to drain.
            timeout: Maximum seconds to wait for in-flight requests (default 5.0).
        """
        with self._lock:
            self._draining.add(plugin_name)
        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            with self._lock:
                if self._inflight.get(plugin_name, 0) <= 0:
                    break
            if asyncio.get_event_loop().time() >= deadline:
                logger.warning(f"Drain timeout for plugin {plugin_name}, forcing unmount")
                break
            await asyncio.sleep(0.1)
        with self._lock:
            self._draining.discard(plugin_name)
            # Clean up in-flight counter
            self._inflight.pop(plugin_name, None)

    @property
    def draining_plugins(self) -> set[str]:
        """Get set of currently draining plugin names."""
        with self._lock:
            return set(self._draining)

def discover_all_plugins(user_plugins_dir: Path | str | None = None) -> list[PluginProtocol]:
    """Discover plugins from entry points, plugins_dir, and optional user directory.

    Priority order: entry points > plugins_dir > user_plugins_dir.
    If same plugin name exists at a higher-priority source, lower-priority
    versions are skipped.

    Args:
        user_plugins_dir: Optional directory for user plugins

    Returns:
        Combined list of discovered plugins
    """
    from core.config import get_settings

    plugins = {}

    # 1. Entry points (highest priority)
    entry_point_loader = PluginLoader()
    for plugin in entry_point_loader.discover_plugins():
        plugins[plugin.name] = plugin

    # 2. plugins_dir (tiered layout: plugins/{starter,team,enterprise}/...)
    settings = get_settings()
    plugins_dir = Path(settings.plugins_dir)
    if plugins_dir.is_dir():
        dir_loader = DirectoryPluginLoader(plugins_dir)
        for plugin in dir_loader.discover_plugins(skip_names=set(plugins.keys())):
            if plugin.name in plugins:
                logger.warning(
                    f"Directory plugin '{plugin.name}' conflicts with entry point plugin, skipping"
                )
            else:
                plugins[plugin.name] = plugin

    # 3. user_plugins_dir (if configured and different from plugins_dir)
    if user_plugins_dir:
        user_dir = Path(user_plugins_dir).resolve()
        if user_dir != plugins_dir.resolve():
            dir_loader = DirectoryPluginLoader(user_plugins_dir)
            for plugin in dir_loader.discover_plugins(skip_names=set(plugins.keys())):
                if plugin.name in plugins:
                    logger.warning(
                        f"Directory plugin '{plugin.name}' conflicts with higher-priority plugin, skipping"
                    )
                else:
                    plugins[plugin.name] = plugin

    return list(plugins.values())

class PluginManager:
    """Manages plugin lifecycle and registration.

    Usage:
        manager = PluginManager()
        manager.discover()
        manager.register_all(registry)
        manager.startup_all()
        # ... application runs ...
        manager.shutdown_all()
    """

    def __init__(self, config_dir: Path | None = None):
        """Initialize plugin manager with empty plugin registry.

        Args:
            config_dir: Optional directory for persistent plugin configs.
                        Defaults to ~/.dryade/plugin-configs/.
        """
        self._plugins: dict[str, PluginProtocol] = {}
        self._loader = PluginLoader()
        # In-memory plugin management state (best-effort, non-persistent).
        self._enabled_overrides: dict[str, bool] = {}
        # Persistent plugin config -- survives core restarts
        from core.ee.plugin_config_store_ee import PluginConfigStore

        self._config_store = PluginConfigStore(config_dir=config_dir)
        self._lock = threading.Lock()
        # Encrypted bridge (lazy-initialized when encrypted plugins are present)
        self._bridge: Any | None = None

    def discover(self, user_plugins_dir: Path | str | None = None) -> None:
        """Discover plugins and check for conflicts.

        Args:
            user_plugins_dir: Optional directory for user plugins

        Raises:
            PluginConflictError: If two plugins have the same route or name
        """
        plugins = discover_all_plugins(user_plugins_dir)

        # Check for name conflicts
        seen_names = {}
        for plugin in plugins:
            if plugin.name in seen_names:
                existing = seen_names[plugin.name]
                raise PluginConflictError(
                    f"Plugin name conflict: '{plugin.name}' defined by both "
                    f"'{existing.__class__.__module__}' and "
                    f"'{plugin.__class__.__module__}'"
                )
            seen_names[plugin.name] = plugin

        # Check for route conflicts (if plugins have router attribute)
        # Routes are identified by (path, method) tuple - same path with different methods is valid
        seen_routes: dict[tuple[str, str], str] = {}
        for plugin in plugins:
            router = getattr(plugin, "router", None)
            if router:
                # Get route paths from router
                for route in getattr(router, "routes", []):
                    path = getattr(route, "path", None)
                    methods = getattr(route, "methods", set())
                    if path:
                        for method in methods:
                            route_key = (path, method)
                            if route_key in seen_routes:
                                raise PluginConflictError(
                                    f"Route conflict: '{method} {path}' registered by both "
                                    f"'{seen_routes[route_key]}' and '{plugin.name}'"
                                )
                            seen_routes[route_key] = plugin.name

        with self._lock:
            self._plugins = {p.name: p for p in plugins}
        logger.info(f"Discovered {len(plugins)} plugins (no conflicts)")

    def register_all(self, registry) -> None:
        """Register all plugins with the extension registry.

        Args:
            registry: ExtensionRegistry instance
        """
        with self._lock:
            snapshot = list(self._plugins.items())
        for name, plugin in snapshot:
            try:
                plugin.register(registry)
                logger.info(f"Registered plugin: {name}")
            except Exception as e:
                logger.error(f"Failed to register plugin {name}: {e}")

    def startup_all(self, app=None) -> None:
        """Run startup hooks for all plugins and register health checks.

        Args:
            app: FastAPI application instance (passed to plugins that accept it)
        """
        import inspect

        from core.health_checks import get_plugin_health_registry

        health_registry = get_plugin_health_registry()

        with self._lock:
            snapshot = list(self._plugins.items())
        for name, plugin in snapshot:
            try:
                sig = inspect.signature(plugin.startup)
                if "app" in sig.parameters or any(
                    p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
                ):
                    plugin.startup(app=app)
                else:
                    plugin.startup()
                logger.debug(f"Started plugin: {name}")

                # Register plugin health checks
                health_checks = plugin.get_health_checks()
                for check in health_checks.values():
                    health_registry.register(name, check)
                if health_checks:
                    logger.debug(
                        f"Registered {len(health_checks)} health checks for plugin: {name}"
                    )

            except Exception as e:
                logger.error(f"Failed to start plugin {name}: {e}")

    def shutdown_all(self) -> None:
        """Run shutdown hooks for all plugins and unregister health checks."""
        from core.health_checks import get_plugin_health_registry

        health_registry = get_plugin_health_registry()

        with self._lock:
            snapshot = list(self._plugins.items())
        for name, plugin in snapshot:
            try:
                # Unregister health checks first
                health_registry.unregister(name)

                plugin.shutdown()
                logger.debug(f"Stopped plugin: {name}")
            except Exception as e:
                logger.error(f"Failed to stop plugin {name}: {e}")

    def unmount_plugin(self, app, plugin_name: str) -> None:
        """Unmount a plugin's routes and run shutdown hook.

        Removes plugin routes from the app, unregisters health checks,
        runs the plugin shutdown hook, and removes from internal registry.

        Args:
            app: FastAPI application instance.
            plugin_name: Name of the plugin to unmount.
        """
        from core.health_checks import get_plugin_health_registry

        with self._lock:
            plugin = self._plugins.get(plugin_name)
        if not plugin:
            return

        # Unregister health checks
        health_registry = get_plugin_health_registry()
        health_registry.unregister(plugin_name)

        # Remove routes from app (slow operation -- outside lock)
        router = getattr(plugin, "router", None)
        if router:
            plugin_paths = set()
            prefix_val = getattr(router, "prefix", "") or ""
            # When the router prefix doesn't start with /api, core mounts
            # it with an extra prefix="/api" (see main.py plugin mounting).
            # We must match the actual app-level paths for removal.
            extra_prefix = "" if prefix_val.startswith("/api") else "/api"
            for route in getattr(router, "routes", []):
                path = getattr(route, "path", None)
                if path:
                    # Route paths already include the router prefix (FastAPI
                    # bakes it in at definition time), so don't add it again.
                    plugin_paths.add(extra_prefix + path)
            app.router.routes = [
                r for r in app.router.routes if getattr(r, "path", None) not in plugin_paths
            ]
            # Clear OpenAPI schema cache so removed routes disappear from /docs
            app.openapi_schema = None

        # Run shutdown hook (slow operation -- outside lock)
        try:
            plugin.shutdown()
        except Exception as e:
            logger.error(f"Shutdown hook failed for plugin {plugin_name}: {e}")

        # Remove from registry
        with self._lock:
            self._plugins.pop(plugin_name, None)
        logger.info(f"Unmounted plugin: {plugin_name}")

    def get_plugin(self, name: str) -> PluginProtocol | None:
        """Get plugin by name."""
        with self._lock:
            return self._plugins.get(name)

    def get_plugins(self) -> list[PluginProtocol]:
        """Return loaded plugin instances."""
        with self._lock:
            return list(self._plugins.values())

    def list_plugins(self) -> list[dict]:
        """List all loaded plugins with metadata."""
        with self._lock:
            return [
                {"name": p.name, "version": p.version, "description": p.description}
                for p in self._plugins.values()
            ]

    def is_encrypted_plugin(self, name: str) -> bool:
        """Return True if the named plugin is an encrypted marketplace plugin.

        Encrypted plugins are loaded from .dryadepkg files and have their routes
        obfuscated through the EncryptedPluginBridge.

        Args:
            name: Plugin name.

        Returns:
            True if plugin is encrypted, False for custom (plaintext) plugins.
        """
        with self._lock:
            plugin = self._plugins.get(name)
        return bool(plugin and getattr(plugin, "_dryadepkg_encrypted", False))

    def get_bridge(self):
        """Get or create the EncryptedPluginBridge singleton.

        The bridge key is derived from the JWT secret so that session keys
        are deterministic per server instance.

        Returns:
            EncryptedPluginBridge instance (lazy-initialized on first call).
        """
        if self._bridge is not None:
            return self._bridge

        if _HAS_PLUGIN_SECURITY:
            from core.ee.plugin_security_ee import _derive_bridge_key
            from core.encrypted_bridge import EncryptedPluginBridge

            bridge_key = _derive_bridge_key()
            self._bridge = EncryptedPluginBridge(bridge_key)
            return self._bridge

        raise RuntimeError("Plugin security module not available — cannot create bridge")

    def get_enabled_override(self, name: str) -> bool | None:
        """Get an in-memory enabled override for a plugin, if any."""
        with self._lock:
            return self._enabled_overrides.get(name)

    def set_enabled_override(self, name: str, enabled: bool) -> None:
        """Set an in-memory enabled override for a plugin."""
        with self._lock:
            self._enabled_overrides[name] = enabled

    def get_plugin_config(self, name: str) -> dict[str, Any]:
        """Get persistent config for a plugin (defaults to empty dict)."""
        return self._config_store.get(name)

    def patch_plugin_config(self, name: str, patch: dict[str, Any]) -> dict[str, Any]:
        """Shallow-merge a config patch into the persistent plugin config."""
        return self._config_store.patch(name, patch)

# Global plugin manager singleton
_plugin_manager: PluginManager | None = None
_plugin_manager_lock = threading.Lock()

def get_plugin_manager() -> PluginManager:
    """Get or create global plugin manager."""
    global _plugin_manager
    if _plugin_manager is None:
        with _plugin_manager_lock:
            if _plugin_manager is None:
                _plugin_manager = PluginManager()
    return _plugin_manager

# Global plugin drainer singleton
_plugin_drainer: PluginDrainer | None = None
_plugin_drainer_lock = threading.Lock()

def get_plugin_drainer() -> PluginDrainer:
    """Get or create global plugin drainer.

    Returns:
        Singleton PluginDrainer instance.
    """
    global _plugin_drainer
    if _plugin_drainer is None:
        with _plugin_drainer_lock:
            if _plugin_drainer is None:
                _plugin_drainer = PluginDrainer()
    return _plugin_drainer

# =============================================================================
# Drain-aware route protection
# =============================================================================

def make_drain_guard(plugin_name: str):
    """Create a FastAPI dependency that rejects requests to draining plugins.

    Usage: app.include_router(router, dependencies=[Depends(make_drain_guard("audio"))])

    Note: Prefer make_drain_cleanup() middleware for production use -- it
    handles both request_start and request_end in a single place.

    Args:
        plugin_name: Name of the plugin to guard.

    Returns:
        Async dependency callable.
    """
    from fastapi import HTTPException
    from fastapi import Request as FastAPIRequest

    async def drain_guard(request: FastAPIRequest):
        drainer = get_plugin_drainer()
        if not drainer.request_start(plugin_name):
            raise HTTPException(status_code=403, detail="Plugin is shutting down")
        # Store plugin_name on request state so cleanup can call request_end
        request.state._drain_plugin_name = plugin_name

    return drain_guard

def make_drain_cleanup(plugin_name: str):
    """Create a middleware class that tracks request lifecycle for drain support.

    This middleware calls request_start before the handler and request_end
    after the response, even on exceptions. It returns 403 if the plugin
    is draining.

    Usage (on a sub-app or router mount):
        DrainMiddleware = make_drain_cleanup("audio")
        sub_app.add_middleware(DrainMiddleware)

    Args:
        plugin_name: Name of the plugin to protect.

    Returns:
        Starlette BaseHTTPMiddleware subclass.
    """
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request as StarletteRequest
    from starlette.responses import Response

    class DrainCleanupMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: StarletteRequest, call_next) -> Response:
            drainer = get_plugin_drainer()
            if not drainer.request_start(plugin_name):
                return Response(
                    content='{"detail":"Plugin is shutting down"}',
                    status_code=403,
                    media_type="application/json",
                )
            try:
                response = await call_next(request)
                return response
            finally:
                drainer.request_end(plugin_name)

    return DrainCleanupMiddleware

def load_plugins(user_plugins_dir: Path | str | None = None) -> PluginManager:
    """Initialize plugin system and discover plugins via entry points and directory.

    Args:
        user_plugins_dir: Optional directory for user plugins

    Returns:
        Configured PluginManager instance

    Raises:
        PluginConflictError: If plugins have naming or route conflicts
    """
    manager = get_plugin_manager()
    manager.discover(user_plugins_dir)
    return manager
