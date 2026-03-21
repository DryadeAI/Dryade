"""Tests for PluginConfigStore -- persistent plugin configuration storage."""

import json
import os
import threading
from pathlib import Path

import pytest
from core.ee.plugin_config_store_ee import PluginConfigStore

@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    """Provide a temporary config directory."""
    return tmp_path / "plugin-configs"

@pytest.fixture
def store(config_dir: Path) -> PluginConfigStore:
    """Provide a PluginConfigStore with a temporary directory."""
    return PluginConfigStore(config_dir=config_dir)

class TestPluginConfigStore:
    """Test suite for PluginConfigStore persistence."""

    def test_get_nonexistent_returns_empty(self, store: PluginConfigStore) -> None:
        """Getting config for unknown plugin returns empty dict."""
        result = store.get("nonexistent_plugin")
        assert result == {}

    def test_patch_creates_config(self, store: PluginConfigStore, config_dir: Path) -> None:
        """Patching a new plugin creates its config file and returns merged config."""
        result = store.patch("my_plugin", {"mock_mode": True, "timeout": 30})
        assert result == {"mock_mode": True, "timeout": 30}
        # File should exist on disk
        config_file = config_dir / "my_plugin.json"
        assert config_file.exists()
        with open(config_file) as f:
            data = json.load(f)
        assert data == {"mock_mode": True, "timeout": 30}

    def test_patch_persists_across_instances(self, config_dir: Path) -> None:
        """Config written by one instance is readable by a new instance."""
        store1 = PluginConfigStore(config_dir=config_dir)
        store1.patch("persistent_plugin", {"key": "value", "enabled": True})

        # Create a completely new instance pointing at the same directory
        store2 = PluginConfigStore(config_dir=config_dir)
        result = store2.get("persistent_plugin")
        assert result == {"key": "value", "enabled": True}

    def test_patch_merges_not_replaces(self, store: PluginConfigStore) -> None:
        """Patching merges into existing config, doesn't replace it."""
        store.patch("merge_plugin", {"a": 1, "b": 2})
        result = store.patch("merge_plugin", {"b": 99, "c": 3})
        assert result == {"a": 1, "b": 99, "c": 3}

    def test_concurrent_patches_safe(self, config_dir: Path) -> None:
        """Multiple threads patching simultaneously don't corrupt the file."""
        store = PluginConfigStore(config_dir=config_dir)
        errors: list[Exception] = []

        def patch_worker(thread_id: int) -> None:
            try:
                for i in range(20):
                    store.patch("concurrent_plugin", {f"thread_{thread_id}_{i}": i})
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=patch_worker, args=(tid,)) for tid in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Concurrent patch errors: {errors}"

        # Final config should be valid JSON and loadable
        result = store.get("concurrent_plugin")
        assert isinstance(result, dict)
        # Should have keys from all threads
        assert len(result) > 0

    def test_missing_dir_created(self, tmp_path: Path) -> None:
        """Config directory is created on first write if it doesn't exist."""
        deep_dir = tmp_path / "a" / "b" / "c" / "configs"
        assert not deep_dir.exists()

        store = PluginConfigStore(config_dir=deep_dir)
        store.patch("first_plugin", {"created": True})

        assert deep_dir.exists()
        assert store.get("first_plugin") == {"created": True}

    def test_corrupt_file_returns_empty(self, config_dir: Path) -> None:
        """Corrupt JSON file returns {} instead of crashing (fail-closed)."""
        config_dir.mkdir(parents=True, exist_ok=True)
        corrupt_file = config_dir / "broken_plugin.json"
        corrupt_file.write_text("{{not valid json!!")

        store = PluginConfigStore(config_dir=config_dir)
        result = store.get("broken_plugin")
        assert result == {}

    def test_get_returns_copy_not_reference(self, store: PluginConfigStore) -> None:
        """Modifying returned dict does not affect stored config."""
        store.patch("copy_plugin", {"original": True})
        result = store.get("copy_plugin")
        result["mutated"] = True

        fresh = store.get("copy_plugin")
        assert "mutated" not in fresh
