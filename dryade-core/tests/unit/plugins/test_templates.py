"""
Unit tests for templates plugin.

Tests cover:
1. Plugin protocol implementation
2. Plugin initialization and router
3. Plugin lifecycle (register graceful failure handling, shutdown)
"""

from unittest.mock import MagicMock

import pytest

@pytest.mark.unit
class TestTemplatesPlugin:
    """Tests for TemplatesPlugin protocol implementation."""

    def test_plugin_protocol_attributes(self):
        """Test plugin has required protocol attributes."""
        from plugins.templates.plugin import TemplatesPlugin

        plugin = TemplatesPlugin()
        assert plugin.name == "templates"
        assert plugin.version == "1.1.0"
        assert "template" in plugin.description.lower()

    def test_plugin_has_lifecycle_methods(self):
        """Test plugin has register, startup, shutdown methods."""
        from plugins.templates.plugin import TemplatesPlugin

        plugin = TemplatesPlugin()
        assert hasattr(plugin, "register")
        assert hasattr(plugin, "startup")
        assert hasattr(plugin, "shutdown")

    def test_router_initially_none(self):
        """Test router is None before register."""
        from plugins.templates.plugin import TemplatesPlugin

        plugin = TemplatesPlugin()
        assert plugin.router is None

    def test_register_handles_import_errors_gracefully(self):
        """Test register handles missing dependencies gracefully."""
        from plugins.templates.plugin import TemplatesPlugin

        plugin = TemplatesPlugin()
        registry = MagicMock()
        # register should not raise even if internal imports fail
        # (they log warnings instead)
        plugin.register(registry)

    def test_shutdown_handles_missing_deps(self):
        """Test shutdown handles missing slot_registry gracefully."""
        from plugins.templates.plugin import TemplatesPlugin

        plugin = TemplatesPlugin()
        # shutdown should not raise even without prior register
        plugin.shutdown()

    def test_module_plugin_instance(self):
        """Test module-level plugin instance exists."""
        from plugins.templates.plugin import plugin

        assert plugin is not None
        assert plugin.name == "templates"
