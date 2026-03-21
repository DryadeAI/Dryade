"""Integration tests for core.extensions re-export completeness.

Tests verify that all symbols previously imported directly from plugins.*
in core/ modules are now available from core.extensions.

The core.extensions module has two categories:
1. Core exports (always available): state, context, events, pipeline
2. Optional plugin re-exports: loaded via _try_import, available only if
   the corresponding plugin is installed
"""

import subprocess
import sys
from pathlib import Path

import pytest

class TestCoreExtensionsExports:
    """Test that core.extensions exports all needed symbols."""

    # Symbols that MUST be available (core or installed plugins)
    REQUIRED_EXPORTS = [
        # From plugins.mcp.bridge (used by core/agents, core/flows, core/domains)
        "get_bridge",
        "MCPBridge",
        "create_tool_wrapper",
        # From plugins.vllm (used by core/agents/llm.py)
        "VLLMBaseLLM",
        # From plugins.cost_tracker (used by core/api)
        "get_cost_summary",
        "get_cost_tracker",
        # From plugins.sandbox (used by core/adapters, core/api/routes)
        "get_sandbox_registry",
        "get_sandbox_cache",
        "get_sandbox",
        "ToolSandbox",
        # From plugins.self_healing (used by core/api/routes, core/adapters)
        "get_all_circuit_breakers",
        "get_circuit_breaker",
        "CircuitBreaker",
        # From plugins.file_safety (used by core/api/routes/files.py)
        "get_clamav_scanner",
        "get_yara_scanner",
        "is_file_safe",
        "scan_file_combined",
        # From plugins.safety (used by core/api/middleware)
        "ValidationResult",
        # From core.clarification (core module, always available)
        "request_clarification",
        "submit_clarification",
        "has_pending_clarification",
        "ClarificationResponse",
        # From plugins.checkpoint (used by core/workflows, core/api/routes/flows.py)
        "CheckpointMixin",
        "CheckpointStore",
        # From plugins.reactflow (used by core/api/routes/flows.py)
        "flow_to_reactflow",
        "get_flow_info",
    ]

    # Optional symbols that depend on plugins which may not be installed
    OPTIONAL_EXPORTS = [
        # From plugins.semantic_cache (optional, not always installed)
        "get_semantic_cache",
        "get_cache_config",
        "SemanticCache",
        "cached_llm_call_async",
        "cached_llm_stream_async",
        # From plugins.semantic_cache.embedder (optional)
        "EmbeddingGenerator",
        # From plugins.semantic_cache (optional)
        "CacheHitMarker",
    ]

    def test_core_extensions_importable(self):
        """core.extensions module can be imported."""
        import core.extensions

        assert core.extensions is not None

    @pytest.mark.parametrize("symbol", REQUIRED_EXPORTS)
    def test_export_available(self, symbol):
        """Each required symbol is available from core.extensions."""
        from core import extensions

        assert hasattr(extensions, symbol), f"core.extensions missing export: {symbol}"

    @pytest.mark.parametrize("symbol", OPTIONAL_EXPORTS)
    def test_optional_export_available(self, symbol):
        """Optional symbols are available if their plugin is installed."""
        from core import extensions

        if not hasattr(extensions, symbol):
            pytest.skip(f"Optional plugin for {symbol} not installed")
        assert hasattr(extensions, symbol)

    def test_no_circular_imports(self):
        """Importing core.extensions doesn't cause circular imports."""
        # Clear any cached imports
        modules_to_clear = [k for k in sys.modules if k.startswith("core.extensions")]
        for mod in modules_to_clear:
            del sys.modules[mod]

        # Should import cleanly
        import core.extensions

        # Should be able to use exports
        assert hasattr(core.extensions, "emit_token")  # Core export

    def test_core_exports_always_available(self):
        """Core extension exports are always available (not plugin-dependent)."""
        from core.extensions import (
            # Pipeline
            build_pipeline,
            emit_token,
            # State management
            export_state,
        )

        # All should be callable or classes
        assert callable(export_state)
        assert callable(emit_token)
        assert callable(build_pipeline)

class TestNoDirectPluginImports:
    """Verify core/ modules don't import directly from plugins."""

    # Known legacy files that still import directly from plugins.
    # These are acceptable for now and tracked for future migration.
    KNOWN_EXCEPTIONS = {
        "core/extensions/__init__.py",  # Re-export layer itself
        "core/skills/registry.py",  # Comment/docstring reference
        "core/skills/mcp_bridge.py",  # Legacy bridge import
        "core/autonomous/chat_adapter.py",  # Legacy sandbox import
    }

    def test_no_direct_plugin_imports_in_core(self):
        """core/ modules (except known exceptions) don't import from plugins.*"""
        result = subprocess.run(
            ["grep", "-rn", "from plugins\\.", "core/", "--include=*.py"],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parent.parent),
        )

        # Filter out known exceptions
        lines = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            # Check if the file is in known exceptions
            filepath = line.split(":")[0]
            if any(filepath.endswith(exc) or exc in filepath for exc in self.KNOWN_EXCEPTIONS):
                continue
            lines.append(line)

        assert len(lines) == 0, f"Found unexpected direct plugin imports in core/: {lines}"

class TestBackwardCompatibility:
    """Test backward compatibility of the migration."""

    def test_existing_core_imports_work(self):
        """Existing import patterns from core modules still work."""
        # These imports should work with migrated code
        # Note: core.agents.model was removed in Phase 95 (deprecated agent cleanup)
        try:
            from core.agents import llm  # noqa: F401
            from core.api.routes import chat, flows, health  # noqa: F401
            from core.orchestrator import router  # noqa: F401
        except ImportError as e:
            pytest.fail(f"Core import failed: {e}")

class TestPluginExportConsistency:
    """Test consistency of plugin re-exports."""

    def test_all_exports_in_all(self):
        """All exported symbols are listed in __all__."""
        from core import extensions

        # Get defined exports (not private)
        public_attrs = [name for name in dir(extensions) if not name.startswith("_")]

        # Check that they are in __all__
        for name in public_attrs:
            attr = getattr(extensions, name)
            # Skip modules and builtins
            if isinstance(attr, type(sys)):
                continue
            # All public symbols should be in __all__
            assert name in extensions.__all__, f"Public symbol '{name}' not in __all__"

    def test_no_duplicate_exports(self):
        """No duplicate entries in __all__."""
        from core import extensions

        all_list = extensions.__all__
        assert len(all_list) == len(set(all_list)), (
            f"Duplicate entries in __all__: {[x for x in all_list if all_list.count(x) > 1]}"
        )

class TestCacheHitMarkerExport:
    """Test that CacheHitMarker is available."""

    def test_cache_hit_marker_available(self):
        """CacheHitMarker should be exported from core.extensions if plugin installed."""
        from core import extensions

        if not hasattr(extensions, "CacheHitMarker"):
            pytest.skip("semantic_cache plugin not installed")
        assert extensions.CacheHitMarker is not None
