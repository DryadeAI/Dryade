"""
Unit tests for file_safety plugin.

Tests cover:
1. Plugin protocol implementation
2. FileSafetyGuard record_read, was_read, can_edit
3. Path resolution and hash tracking
4. External modification detection
5. ScanResult data class
"""

import os
import tempfile

import pytest

@pytest.mark.unit
class TestFileSafetyPlugin:
    """Tests for FileSafetyPlugin protocol implementation."""

    def test_plugin_protocol_attributes(self):
        """Test plugin has required protocol attributes."""
        from plugins.file_safety.plugin import FileSafetyPlugin

        plugin = FileSafetyPlugin()
        assert plugin.name == "file_safety"
        assert plugin.version == "1.0.0"
        assert hasattr(plugin, "register")

    def test_plugin_register_adds_extension(self):
        """Test register adds file_safety extension to registry."""
        from plugins.file_safety.plugin import FileSafetyPlugin

        from core.extensions.pipeline import ExtensionRegistry

        plugin = FileSafetyPlugin()
        registry = ExtensionRegistry()
        plugin.register(registry)
        config = registry.get("file_safety")
        assert config is not None

    def test_module_plugin_instance(self):
        """Test module-level plugin instance exists."""
        from plugins.file_safety.plugin import plugin

        assert plugin is not None
        assert plugin.name == "file_safety"

@pytest.mark.unit
class TestFileSafetyGuard:
    """Tests for FileSafetyGuard core operations."""

    def test_record_read_tracks_file(self):
        """Test record_read adds file to tracked set."""
        from plugins.file_safety.scanner import FileSafetyGuard

        guard = FileSafetyGuard()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("test content")
            path = f.name
        try:
            guard.record_read(path)
            assert guard.was_read(path) is True
        finally:
            os.unlink(path)

    def test_was_read_returns_false_for_untracked(self):
        """Test was_read returns False for files not yet read."""
        from plugins.file_safety.scanner import FileSafetyGuard

        guard = FileSafetyGuard()
        assert guard.was_read("/nonexistent/file.py") is False

    @pytest.mark.asyncio
    async def test_can_edit_requires_prior_read(self):
        """Test can_edit fails if file was not read first."""
        from plugins.file_safety.scanner import FileSafetyGuard

        guard = FileSafetyGuard()
        guard._scan_enabled = False  # Disable scanning for unit test
        can_edit, reason = await guard.can_edit("/some/file.py")
        assert can_edit is False
        assert "must be read" in reason.lower()

    @pytest.mark.asyncio
    async def test_can_edit_after_read(self):
        """Test can_edit succeeds after file was read."""
        from plugins.file_safety.scanner import FileSafetyGuard

        guard = FileSafetyGuard()
        guard._scan_enabled = False
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("test content")
            path = f.name
        try:
            guard.record_read(path)
            can_edit, reason = await guard.can_edit(path)
            assert can_edit is True
            assert reason == "ok"
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_can_edit_detects_external_modification(self):
        """Test can_edit detects file changed since read."""
        from plugins.file_safety.scanner import FileSafetyGuard

        guard = FileSafetyGuard()
        guard._scan_enabled = False
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("original content")
            path = f.name
        try:
            guard.record_read(path)
            # Modify file externally
            with open(path, "w") as f:
                f.write("modified content")
            can_edit, reason = await guard.can_edit(path)
            assert can_edit is False
            assert "modified externally" in reason.lower()
        finally:
            os.unlink(path)

    def test_get_read_time(self):
        """Test get_read_time returns timestamp after read."""
        from plugins.file_safety.scanner import FileSafetyGuard

        guard = FileSafetyGuard()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("test")
            path = f.name
        try:
            assert guard.get_read_time(path) is None
            guard.record_read(path)
            assert guard.get_read_time(path) is not None
        finally:
            os.unlink(path)

    def test_clear_specific_file(self):
        """Test clearing tracking for a specific file."""
        from plugins.file_safety.scanner import FileSafetyGuard

        guard = FileSafetyGuard()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("test")
            path = f.name
        try:
            guard.record_read(path)
            assert guard.was_read(path) is True
            guard.clear(path)
            assert guard.was_read(path) is False
        finally:
            os.unlink(path)

    def test_clear_all(self):
        """Test clearing all tracked files."""
        from plugins.file_safety.scanner import FileSafetyGuard

        guard = FileSafetyGuard()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("test")
            path = f.name
        try:
            guard.record_read(path)
            guard.clear()
            assert guard.get_tracked_files() == set()
        finally:
            os.unlink(path)

@pytest.mark.unit
class TestScanResult:
    """Tests for ScanResult dataclass."""

    def test_scan_result_safe(self):
        """Test safe scan result."""
        from plugins.file_safety.scanner import ScanResult

        result = ScanResult(safe=True, scanner="test")
        assert result.safe is True
        assert result.threats == []

    def test_scan_result_unsafe(self):
        """Test unsafe scan result with threats."""
        from plugins.file_safety.scanner import ScanResult

        result = ScanResult(safe=False, threats=["Eicar-Test"], scanner="clamav")
        assert result.safe is False
        assert "Eicar-Test" in result.threats
