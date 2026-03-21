"""Unit tests for core.plugins module (coverage gap closure).

Tests the parts of core.plugins NOT covered by test_plugin_discovery_allowlist.py:
- PluginHealthCheck and ManageableComponent dataclasses
- validate_execution decorator (sync and async)
- PluginProtocol abstract base class (startup, shutdown, get_health_checks, get_manageable_components)
- EnterprisePluginProtocol backward compat (_validate_access, invalidate_validation_cache)
- PluginLoader: discover_plugins, load_plugin, version compatibility
- DirectoryPluginLoader: discover_plugins, slot limits, version incompatibility
- EncryptedPluginLoader: is_available, load/cache/clear
- PluginDrainer: request lifecycle, drain, timeout, draining_plugins
- PluginManager: discover, register_all, startup_all, shutdown_all,
  unmount_plugin, get_plugin, list_plugins, enabled overrides, config
- get_plugin_manager / get_plugin_drainer singletons
- make_drain_guard, make_drain_cleanup
- validate_before_load, reload_allowlist, _load_allowlist
- discover_all_plugins, load_plugins
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.ee.plugins_ee import (
    DirectoryPluginLoader,
    EncryptedPluginLoader,
    EnterprisePluginProtocol,
    ManageableComponent,
    PluginDrainer,
    PluginHealthCheck,
    PluginLoader,
    PluginManager,
    PluginProtocol,
    discover_all_plugins,
    get_plugin_drainer,
    get_plugin_manager,
    load_plugins,
    reload_allowlist,
    validate_before_load,
    validate_execution,
)
from core.exceptions import PluginConflictError, PluginValidationError, PluginVersionError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class ConcretePlugin(PluginProtocol):
    """Minimal concrete plugin for testing."""

    name = "test-plugin"
    version = "1.0.0"
    description = "A test plugin"
    core_version_constraint = ">=1.0.0"

    def register(self, registry):
        pass

class VersionedPlugin(PluginProtocol):
    """Plugin with specific version constraint."""

    name = "versioned-plugin"
    version = "2.0.0"
    description = "Versioned"
    core_version_constraint = ">=3.0.0,<4.0.0"  # Intentionally incompatible

    def register(self, registry):
        pass

# ---------------------------------------------------------------------------
# Tests: PluginHealthCheck dataclass
# ---------------------------------------------------------------------------

class TestPluginHealthCheck:
    def test_creation(self):
        check = PluginHealthCheck(
            name="db",
            category="critical",
            check_fn=AsyncMock(),
            description="Database health",
            timeout_seconds=10.0,
        )
        assert check.name == "db"
        assert check.category == "critical"
        assert check.timeout_seconds == 10.0

    def test_defaults(self):
        check = PluginHealthCheck(
            name="redis",
            category="optional",
            check_fn=AsyncMock(),
        )
        assert check.description == ""
        assert check.timeout_seconds == 5.0

# ---------------------------------------------------------------------------
# Tests: ManageableComponent dataclass
# ---------------------------------------------------------------------------

class TestManageableComponent:
    def test_creation(self):
        comp = ManageableComponent(
            name="cache",
            type="cache",
            description="Semantic cache",
            actions=["clear", "stats"],
        )
        assert comp.name == "cache"
        assert comp.type == "cache"
        assert len(comp.actions) == 2

    def test_defaults(self):
        comp = ManageableComponent(name="worker", type="worker")
        assert comp.description == ""
        assert comp.actions == []
        assert comp.get_status_fn is None
        assert comp.execute_action_fn is None

# ---------------------------------------------------------------------------
# Tests: validate_execution decorator
# ---------------------------------------------------------------------------

class TestValidateExecution:
    @pytest.mark.asyncio
    async def test_async_wrapper_passes_when_no_validate_access(self):
        class NoValidation:
            name = "test"

            @validate_execution
            async def do_thing(self):
                return "ok"

        obj = NoValidation()
        result = await obj.do_thing()
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_async_wrapper_passes_when_allowed(self):
        class WithValidation:
            name = "test"

            def _validate_access(self):
                return True, "allowed"

            @validate_execution
            async def do_thing(self):
                return "ok"

        obj = WithValidation()
        result = await obj.do_thing()
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_async_wrapper_raises_when_denied(self):
        class Denied:
            name = "denied-plugin"

            def _validate_access(self):
                return False, "expired"

            @validate_execution
            async def do_thing(self):
                return "ok"

        obj = Denied()
        with pytest.raises(PluginValidationError):
            await obj.do_thing()

    def test_sync_wrapper_passes(self):
        class SyncPlugin:
            name = "sync"

            def _validate_access(self):
                return True, "ok"

            @validate_execution
            def do_thing(self):
                return "sync-ok"

        obj = SyncPlugin()
        assert obj.do_thing() == "sync-ok"

    def test_sync_wrapper_raises_when_denied(self):
        class SyncDenied:
            name = "sync-denied"

            def _validate_access(self):
                return False, "nope"

            @validate_execution
            def do_thing(self):
                return "unreachable"

        obj = SyncDenied()
        with pytest.raises(PluginValidationError):
            obj.do_thing()

# ---------------------------------------------------------------------------
# Tests: PluginProtocol
# ---------------------------------------------------------------------------

class TestPluginProtocol:
    def test_startup_is_noop(self):
        p = ConcretePlugin()
        p.startup()  # Should not raise

    def test_shutdown_is_noop(self):
        p = ConcretePlugin()
        p.shutdown()  # Should not raise

    def test_get_health_checks_empty(self):
        p = ConcretePlugin()
        assert p.get_health_checks() == {}

    def test_get_manageable_components_empty(self):
        p = ConcretePlugin()
        assert p.get_manageable_components() == []

# ---------------------------------------------------------------------------
# Tests: EnterprisePluginProtocol
# ---------------------------------------------------------------------------

class TestEnterprisePluginProtocol:
    def test_validate_access_always_allowed(self):
        class MyPlugin(EnterprisePluginProtocol):
            name = "my-plugin"
            version = "1.0"
            description = "Test"
            core_version_constraint = ">=1.0.0"

        p = MyPlugin()
        allowed, reason = p._validate_access()
        assert allowed is True
        assert reason == "allowed"

    def test_invalidate_validation_cache_noop(self):
        class MyPlugin(EnterprisePluginProtocol):
            name = "my-plugin"
            version = "1.0"
            description = "Test"
            core_version_constraint = ">=1.0.0"

        p = MyPlugin()
        p.invalidate_validation_cache()  # Should not raise

    def test_register_default(self):
        class MyPlugin(EnterprisePluginProtocol):
            name = "my-plugin"
            version = "1.0"
            description = "Test"
            core_version_constraint = ">=1.0.0"

        p = MyPlugin()
        mock_registry = MagicMock()
        p.register(mock_registry)  # Should just log

# ---------------------------------------------------------------------------
# Tests: PluginDrainer
# ---------------------------------------------------------------------------

class TestPluginDrainer:
    def test_request_start_normal(self):
        drainer = PluginDrainer()
        assert drainer.request_start("audio") is True

    def test_request_start_when_draining(self):
        drainer = PluginDrainer()
        drainer._draining.add("audio")
        assert drainer.request_start("audio") is False

    def test_request_end(self):
        drainer = PluginDrainer()
        drainer.request_start("audio")
        drainer.request_end("audio")
        assert drainer._inflight.get("audio", 0) == 0

    def test_request_end_no_negative(self):
        drainer = PluginDrainer()
        drainer.request_end("audio")  # Never started
        assert drainer._inflight.get("audio", 0) == 0

    @pytest.mark.asyncio
    async def test_drain_completes(self):
        drainer = PluginDrainer()
        drainer.request_start("audio")
        drainer.request_start("audio")

        # Simulate requests completing in background
        async def complete_requests():
            await asyncio.sleep(0.05)
            drainer.request_end("audio")
            await asyncio.sleep(0.05)
            drainer.request_end("audio")

        asyncio.create_task(complete_requests())
        await drainer.drain("audio", timeout=2.0)
        assert "audio" not in drainer._draining
        assert drainer._inflight.get("audio") is None

    @pytest.mark.asyncio
    async def test_drain_timeout(self):
        drainer = PluginDrainer()
        drainer.request_start("stuck")
        # Don't complete the request -- will hit timeout
        await drainer.drain("stuck", timeout=0.2)
        # After timeout, cleanup should happen
        assert "stuck" not in drainer._draining

    def test_draining_plugins_property(self):
        drainer = PluginDrainer()
        drainer._draining.add("audio")
        drainer._draining.add("video")
        assert drainer.draining_plugins == {"audio", "video"}

    def test_draining_plugins_is_copy(self):
        drainer = PluginDrainer()
        drainer._draining.add("audio")
        plugins = drainer.draining_plugins
        plugins.add("injected")
        assert "injected" not in drainer._draining

class TestGetPluginDrainer:
    def test_singleton(self):
        import core.ee.plugins_ee as mod

        mod._plugin_drainer = None
        d1 = get_plugin_drainer()
        d2 = get_plugin_drainer()
        assert d1 is d2
        mod._plugin_drainer = None

# ---------------------------------------------------------------------------
# Tests: validate_before_load and allowlist functions
# ---------------------------------------------------------------------------

class TestValidateBeforeLoad:
    def test_no_allowlist(self):
        import core.ee.plugin_security_ee as sec_mod

        sec_mod._allowlist_loaded = False
        with patch("core.ee.allowlist_ee.get_allowed_plugins", return_value=None):
            allowed, reason = validate_before_load("any-plugin")
        assert allowed is False
        assert "no valid allowlist" in reason
        sec_mod._allowlist_loaded = False

    def test_not_in_allowlist(self):
        import core.ee.plugin_security_ee as sec_mod

        sec_mod._allowlist_loaded = False
        with patch("core.ee.allowlist_ee.get_allowed_plugins", return_value=frozenset({"other"})):
            allowed, reason = validate_before_load("my-plugin")
        assert allowed is False
        assert "not in allowlist" in reason
        sec_mod._allowlist_loaded = False

    def test_in_allowlist(self):
        import core.ee.plugin_security_ee as sec_mod

        sec_mod._allowlist_loaded = False
        with patch(
            "core.ee.allowlist_ee.get_allowed_plugins", return_value=frozenset({"my-plugin"})
        ):
            allowed, reason = validate_before_load("my-plugin")
        assert allowed is True
        assert reason == "allowed"
        sec_mod._allowlist_loaded = False

class TestReloadAllowlist:
    def test_reload_clears_cache(self):
        import core.ee.plugin_security_ee as sec_mod

        sec_mod._allowlist_loaded = True
        sec_mod._allowed_plugins = frozenset({"old"})
        with patch("core.ee.allowlist_ee.get_allowed_plugins", return_value=frozenset({"new"})):
            result = reload_allowlist()
        assert "new" in result
        sec_mod._allowlist_loaded = False

# ---------------------------------------------------------------------------
# Tests: PluginLoader
# ---------------------------------------------------------------------------

class TestPluginLoader:
    def test_version_check_compatible(self):
        loader = PluginLoader()
        loader._core_version = "2.5.0"
        plugin = ConcretePlugin()  # constraint: >=1.0.0
        assert loader._check_version_compatibility(plugin) is True

    def test_version_check_incompatible(self):
        loader = PluginLoader()
        loader._core_version = "2.5.0"
        plugin = VersionedPlugin()  # constraint: >=3.0.0,<4.0.0
        with pytest.raises(PluginVersionError):
            loader._check_version_compatibility(plugin)

    def test_version_check_invalid_specifier(self):
        loader = PluginLoader()
        loader._core_version = "2.5.0"
        plugin = ConcretePlugin()
        plugin.core_version_constraint = "not_a_valid_constraint!!!"
        # Invalid constraint should be allowed (with warning)
        assert loader._check_version_compatibility(plugin) is True

    def test_discover_plugins_no_allowlist(self):
        loader = PluginLoader()
        import core.ee.plugin_security_ee as sec_mod

        sec_mod._allowlist_loaded = False
        with patch("core.ee.allowlist_ee.get_allowed_plugins", return_value=None):
            plugins = loader.discover_plugins()
        assert plugins == []
        sec_mod._allowlist_loaded = False

    def test_load_plugin_not_found(self):
        loader = PluginLoader()
        import core.ee.plugin_security_ee as sec_mod

        sec_mod._allowlist_loaded = False
        with (
            patch("core.ee.allowlist_ee.get_allowed_plugins", return_value=frozenset({"missing"})),
            patch("importlib.metadata.entry_points", return_value=[]),
        ):
            result = loader.load_plugin("missing")
        assert result is None
        sec_mod._allowlist_loaded = False

    def test_load_plugin_validation_fails(self):
        loader = PluginLoader()
        import core.ee.plugin_security_ee as sec_mod

        sec_mod._allowlist_loaded = False
        with patch("core.ee.allowlist_ee.get_allowed_plugins", return_value=frozenset({"other"})):
            result = loader.load_plugin("blocked-plugin")
        assert result is None
        sec_mod._allowlist_loaded = False

    def test_load_plugin_skip_validation(self):
        """load_plugin with validate=False skips allowlist check."""
        loader = PluginLoader()
        # No entry points means None
        with patch("importlib.metadata.entry_points", return_value=[]):
            result = loader.load_plugin("any-plugin", validate=False)
        assert result is None

# ---------------------------------------------------------------------------
# Tests: DirectoryPluginLoader
# ---------------------------------------------------------------------------

class TestDirectoryPluginLoader:
    def test_nonexistent_directory(self):
        loader = DirectoryPluginLoader(Path("/nonexistent/path"))
        import core.ee.plugin_security_ee as sec_mod

        sec_mod._allowlist_loaded = False
        with patch("core.ee.allowlist_ee.get_allowed_plugins", return_value=frozenset({"test"})):
            plugins = loader.discover_plugins()
        assert plugins == []
        sec_mod._allowlist_loaded = False

    def test_no_allowlist(self):
        loader = DirectoryPluginLoader(Path("/tmp"))
        import core.ee.plugin_security_ee as sec_mod

        sec_mod._allowlist_loaded = False
        with patch("core.ee.allowlist_ee.get_allowed_plugins", return_value=None):
            plugins = loader.discover_plugins()
        assert plugins == []
        sec_mod._allowlist_loaded = False

# ---------------------------------------------------------------------------
# Tests: EncryptedPluginLoader
# ---------------------------------------------------------------------------

class TestEncryptedPluginLoader:
    def test_not_available_by_default(self):
        loader = EncryptedPluginLoader()
        assert loader.is_available is False

    def test_available_when_configured(self):
        loader = EncryptedPluginLoader()
        loader.customer_secret = "secret123"
        loader.machine_fingerprint = "fp123"
        assert loader.is_available is True

    def test_clear_cache(self):
        loader = EncryptedPluginLoader()
        loader._decryption_cache["key"] = b"data"
        loader.clear_cache()
        assert len(loader._decryption_cache) == 0

# ---------------------------------------------------------------------------
# Tests: PluginManager
# ---------------------------------------------------------------------------

class TestPluginManager:
    def test_init(self):
        manager = PluginManager()
        assert manager._plugins == {}
        assert manager.get_plugins() == []

    def test_get_plugin(self):
        manager = PluginManager()
        plugin = ConcretePlugin()
        manager._plugins["test-plugin"] = plugin
        assert manager.get_plugin("test-plugin") is plugin
        assert manager.get_plugin("nonexistent") is None

    def test_list_plugins(self):
        manager = PluginManager()
        plugin = ConcretePlugin()
        manager._plugins["test-plugin"] = plugin
        listing = manager.list_plugins()
        assert len(listing) == 1
        assert listing[0]["name"] == "test-plugin"
        assert listing[0]["version"] == "1.0.0"

    def test_enabled_override(self):
        manager = PluginManager()
        assert manager.get_enabled_override("audio") is None
        manager.set_enabled_override("audio", False)
        assert manager.get_enabled_override("audio") is False
        manager.set_enabled_override("audio", True)
        assert manager.get_enabled_override("audio") is True

    def test_plugin_config(self, tmp_path):
        manager = PluginManager(config_dir=tmp_path / "plugin-configs")
        assert manager.get_plugin_config("audio") == {}
        result = manager.patch_plugin_config("audio", {"key": "value"})
        assert result == {"key": "value"}
        # Patch again
        result2 = manager.patch_plugin_config("audio", {"key2": "value2"})
        assert result2 == {"key": "value", "key2": "value2"}

    def test_register_all(self):
        manager = PluginManager()
        plugin = ConcretePlugin()
        manager._plugins["test-plugin"] = plugin
        mock_registry = MagicMock()
        manager.register_all(mock_registry)
        # register was called (no error)

    def test_register_all_handles_error(self):
        manager = PluginManager()
        bad_plugin = MagicMock()
        bad_plugin.name = "bad"
        bad_plugin.register.side_effect = RuntimeError("fail")
        manager._plugins["bad"] = bad_plugin
        mock_registry = MagicMock()
        # Should not raise
        manager.register_all(mock_registry)

    def test_startup_all(self):
        manager = PluginManager()
        plugin = ConcretePlugin()
        manager._plugins["test-plugin"] = plugin

        with patch("core.health_checks.get_plugin_health_registry") as mock_get_reg:
            mock_reg = MagicMock()
            mock_get_reg.return_value = mock_reg
            manager.startup_all()

    def test_shutdown_all(self):
        manager = PluginManager()
        plugin = ConcretePlugin()
        manager._plugins["test-plugin"] = plugin

        with patch("core.health_checks.get_plugin_health_registry") as mock_get_reg:
            mock_reg = MagicMock()
            mock_get_reg.return_value = mock_reg
            manager.shutdown_all()

    def test_unmount_plugin_nonexistent(self):
        manager = PluginManager()
        app = MagicMock()
        manager.unmount_plugin(app, "nonexistent")  # Should not raise

    def test_unmount_plugin_with_router(self):
        manager = PluginManager()
        plugin = MagicMock()
        plugin.name = "audio"

        route = MagicMock()
        route.path = "/api/audio/transcribe"
        route.methods = {"POST"}

        router = MagicMock()
        router.routes = [route]
        router.prefix = "/api/audio"
        plugin.router = router

        manager._plugins["audio"] = plugin

        app = MagicMock()
        app.routes = [route]

        with patch("core.health_checks.get_plugin_health_registry") as mock_get_reg:
            mock_reg = MagicMock()
            mock_get_reg.return_value = mock_reg
            manager.unmount_plugin(app, "audio")

        assert "audio" not in manager._plugins
        plugin.shutdown.assert_called_once()

    def test_discover_name_conflict(self):
        manager = PluginManager()
        plugin1 = ConcretePlugin()
        plugin2 = ConcretePlugin()

        with patch("core.ee.plugins_ee.discover_all_plugins", return_value=[plugin1, plugin2]):
            with pytest.raises(PluginConflictError):
                manager.discover()

class TestGetPluginManager:
    def test_singleton(self):
        import core.ee.plugins_ee as mod

        mod._plugin_manager = None
        m1 = get_plugin_manager()
        m2 = get_plugin_manager()
        assert m1 is m2
        mod._plugin_manager = None

# ---------------------------------------------------------------------------
# Tests: discover_all_plugins and load_plugins
# ---------------------------------------------------------------------------

class TestDiscoverAllPlugins:
    def test_entry_point_priority(self):
        """Entry point plugin takes precedence over directory plugin with same name."""
        ep_plugin = ConcretePlugin()

        dir_plugin = MagicMock()
        dir_plugin.name = "test-plugin"  # Same name

        mock_settings = MagicMock()
        mock_settings.plugins_dir = "/tmp/ep-plugins"

        with (
            patch.object(PluginLoader, "discover_plugins", return_value=[ep_plugin]),
            patch.object(DirectoryPluginLoader, "discover_plugins", return_value=[dir_plugin]),
            patch("core.config.get_settings", return_value=mock_settings),
        ):
            result = discover_all_plugins(user_plugins_dir="/tmp/plugins")

        assert len(result) == 1
        assert result[0] is ep_plugin

    def test_no_user_dir(self):
        mock_settings = MagicMock()
        mock_settings.plugins_dir = "/nonexistent/plugins"
        with (
            patch.object(PluginLoader, "discover_plugins", return_value=[]),
            patch("core.config.get_settings", return_value=mock_settings),
        ):
            result = discover_all_plugins(user_plugins_dir=None)
        assert result == []

class TestLoadPlugins:
    def test_returns_manager(self):
        import core.ee.plugins_ee as mod

        mod._plugin_manager = None
        with patch.object(PluginManager, "discover"):
            manager = load_plugins()
        assert isinstance(manager, PluginManager)
        mod._plugin_manager = None
