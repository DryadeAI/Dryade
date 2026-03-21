"""Coverage-focused tests for plugin management API routes.

Targets uncovered code paths in core/api/routes/plugins.py:
- Plugin toggle (enable/disable)
- Plugin config (get/patch)
- Plugin slots
- Plugin UI manifest/bundle/styles
- Plugin install/uninstall
- Plugin stats summary
- Effective enabled state logic
- Safe archive extraction helpers

Uses unit-level mocks for plugin manager and settings.
"""

import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.api.routes.plugins import (
    _get_effective_enabled,
    _is_relative_to,
    _load_plugin_manifest,
    _safe_extract_zip,
    _set_effective_enabled,
)

class TestHelperFunctions:
    """Tests for helper functions in plugins.py."""

    def test_is_relative_to_valid(self, tmp_path):
        """Test _is_relative_to returns True for subpath."""
        child = tmp_path / "sub" / "file.txt"
        child.parent.mkdir(parents=True, exist_ok=True)
        child.touch()
        assert _is_relative_to(child, tmp_path) is True

    def test_is_relative_to_invalid(self, tmp_path):
        """Test _is_relative_to returns False for non-subpath."""
        other = Path("/tmp/other")
        assert _is_relative_to(other, tmp_path) is False

    def test_safe_extract_zip_normal(self, tmp_path):
        """Test safe zip extraction with normal entries."""
        archive_path = tmp_path / "test.zip"
        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()

        with zipfile.ZipFile(archive_path, "w") as zf:
            zf.writestr("plugin/__init__.py", "# init")
            zf.writestr("plugin/main.py", "# main")

        with zipfile.ZipFile(archive_path, "r") as zf:
            _safe_extract_zip(zf, extract_dir)

        assert (extract_dir / "plugin" / "__init__.py").exists()
        assert (extract_dir / "plugin" / "main.py").exists()

    def test_safe_extract_zip_traversal_rejected(self, tmp_path):
        """Test safe zip extraction rejects path traversal."""
        archive_path = tmp_path / "evil.zip"
        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()

        with zipfile.ZipFile(archive_path, "w") as zf:
            zf.writestr("../../../etc/passwd", "evil")

        with zipfile.ZipFile(archive_path, "r") as zf:
            with pytest.raises(ValueError, match="Unsafe zip member"):
                _safe_extract_zip(zf, extract_dir)

class TestEffectiveEnabledState:
    """Tests for _get_effective_enabled and _set_effective_enabled."""

    @patch("core.api.routes.plugins.get_plugin_manager")
    @patch("core.api.routes.plugins.get_extension_registry")
    def test_get_effective_enabled_from_extension(self, mock_ext_reg, mock_pm):
        """Test enabled state read from extension registry."""
        mock_ext = MagicMock()
        mock_ext.enabled = True
        mock_ext_reg.return_value.get.return_value = mock_ext

        assert _get_effective_enabled("test_plugin") is True

    @patch("core.api.routes.plugins.get_plugin_manager")
    @patch("core.api.routes.plugins.get_extension_registry")
    def test_get_effective_enabled_from_override(self, mock_ext_reg, mock_pm):
        """Test enabled state read from manager override when no extension."""
        mock_ext_reg.return_value.get.return_value = None
        mock_pm.return_value.get_enabled_override.return_value = False

        assert _get_effective_enabled("test_plugin") is False

    @patch("core.api.routes.plugins.get_plugin_manager")
    @patch("core.api.routes.plugins.get_extension_registry")
    def test_get_effective_enabled_default_true(self, mock_ext_reg, mock_pm):
        """Test default enabled state is True."""
        mock_ext_reg.return_value.get.return_value = None
        mock_pm.return_value.get_enabled_override.return_value = None

        assert _get_effective_enabled("test_plugin") is True

    @patch("core.api.routes.plugins.get_plugin_manager")
    @patch("core.api.routes.plugins.get_extension_registry")
    def test_get_effective_enabled_with_aliases(self, mock_ext_reg, mock_pm):
        """Test enabled state with plugin extension aliases (safety plugin)."""
        ext1 = MagicMock()
        ext1.enabled = True
        ext2 = MagicMock()
        ext2.enabled = True

        def get_ext(name):
            if name == "input_validation":
                return ext1
            if name == "output_sanitization":
                return ext2
            return None

        mock_ext_reg.return_value.get.side_effect = get_ext

        assert _get_effective_enabled("safety") is True

    @patch("core.api.routes.plugins.get_plugin_manager")
    @patch("core.api.routes.plugins.get_extension_registry")
    def test_set_effective_enabled_extension(self, mock_ext_reg, mock_pm):
        """Test setting enabled state via extension registry."""
        mock_ext = MagicMock()
        mock_ext_reg.return_value.get.return_value = mock_ext

        updated = _set_effective_enabled("test_plugin", False)
        assert len(updated) == 1
        assert mock_ext.enabled is False

    @patch("core.api.routes.plugins.get_plugin_manager")
    @patch("core.api.routes.plugins.get_extension_registry")
    def test_set_effective_enabled_override(self, mock_ext_reg, mock_pm):
        """Test setting enabled state via manager override when no extension."""
        mock_ext_reg.return_value.get.return_value = None

        updated = _set_effective_enabled("test_plugin", True)
        assert len(updated) == 0
        mock_pm.return_value.set_enabled_override.assert_called_once_with("test_plugin", True)

class TestLoadPluginManifest:
    """Tests for _load_plugin_manifest."""

    @patch("core.api.routes.plugins.get_settings")
    def test_load_manifest_not_found(self, mock_settings):
        """Test returns None when manifest file doesn't exist."""
        mock_settings.return_value.plugins_dir = "/nonexistent"
        mock_settings.return_value.enable_directory_plugins = False
        mock_settings.return_value.user_plugins_dir = None

        result = _load_plugin_manifest("nonexistent_plugin")
        assert result is None

    @patch("core.api.routes.plugins.get_settings")
    def test_load_manifest_success(self, mock_settings, tmp_path):
        """Test successfully loading a valid manifest."""
        plugin_dir = tmp_path / "test_plugin"
        plugin_dir.mkdir()
        manifest = {"name": "test_plugin", "version": "1.0.0", "has_ui": True}
        (plugin_dir / "dryade.json").write_text(json.dumps(manifest))

        mock_settings.return_value.plugins_dir = str(tmp_path)
        mock_settings.return_value.enable_directory_plugins = False
        mock_settings.return_value.user_plugins_dir = None

        result = _load_plugin_manifest("test_plugin")
        assert result is not None
        assert result["name"] == "test_plugin"
        assert result["has_ui"] is True

    @patch("core.api.routes.plugins.get_settings")
    def test_load_manifest_invalid_json(self, mock_settings, tmp_path):
        """Test returns None for invalid JSON manifest."""
        plugin_dir = tmp_path / "bad_plugin"
        plugin_dir.mkdir()
        (plugin_dir / "dryade.json").write_text("{invalid json")

        mock_settings.return_value.plugins_dir = str(tmp_path)
        mock_settings.return_value.enable_directory_plugins = False
        mock_settings.return_value.user_plugins_dir = None

        result = _load_plugin_manifest("bad_plugin")
        assert result is None

    @patch("core.api.routes.plugins.get_settings")
    def test_load_manifest_user_plugins_dir(self, mock_settings, tmp_path):
        """Test loading manifest from user plugins directory."""
        user_dir = tmp_path / "user_plugins"
        plugin_dir = user_dir / "custom_plugin"
        plugin_dir.mkdir(parents=True)
        manifest = {"name": "custom_plugin", "version": "2.0.0"}
        (plugin_dir / "dryade.json").write_text(json.dumps(manifest))

        mock_settings.return_value.plugins_dir = str(tmp_path / "system")
        mock_settings.return_value.enable_directory_plugins = True
        mock_settings.return_value.user_plugins_dir = str(user_dir)

        result = _load_plugin_manifest("custom_plugin")
        assert result is not None
        assert result["version"] == "2.0.0"

@pytest.mark.integration
class TestPluginEndpoints:
    """Integration tests for plugin API endpoints."""

    def test_list_plugins(self, authenticated_client):
        """Test GET /api/plugins returns list response."""
        response = authenticated_client.get("/api/plugins")
        assert response.status_code == 200
        data = response.json()
        assert "plugins" in data
        assert "count" in data
        assert isinstance(data["plugins"], list)

    def test_get_plugin_not_found(self, authenticated_client):
        """Test GET /api/plugins/{name} returns 404 for non-existent."""
        response = authenticated_client.get("/api/plugins/nonexistent_xyz_plugin")
        assert response.status_code == 404

    def test_toggle_plugin_not_found(self, authenticated_client):
        """Test POST /api/plugins/{name}/toggle returns 404."""
        response = authenticated_client.post(
            "/api/plugins/nonexistent_xyz_plugin/toggle",
            json={"enabled": True},
        )
        assert response.status_code == 404

    def test_get_plugin_config_not_found(self, authenticated_client):
        """Test GET /api/plugins/{name}/config returns 404."""
        response = authenticated_client.get("/api/plugins/nonexistent_xyz_plugin/config")
        assert response.status_code == 404

    def test_patch_plugin_config_not_found(self, authenticated_client):
        """Test PATCH /api/plugins/{name}/config returns 404."""
        response = authenticated_client.patch(
            "/api/plugins/nonexistent_xyz_plugin/config",
            json={"key": "value"},
        )
        assert response.status_code == 404

    def test_get_all_slots(self, authenticated_client):
        """Test GET /api/plugins/slots returns slot registry."""
        response = authenticated_client.get("/api/plugins/slots")
        assert response.status_code == 200
        assert isinstance(response.json(), dict)

    def test_get_slot_registrations_invalid_slot(self, authenticated_client):
        """Test GET /api/plugins/slots/{name} returns 400 for invalid slot."""
        response = authenticated_client.get("/api/plugins/slots/invalid-slot-name")
        assert response.status_code == 400
        assert "Invalid slot name" in response.json()["detail"]

    def test_get_plugin_stats(self, authenticated_client):
        """Test GET /api/plugins/stats/summary returns stats."""
        response = authenticated_client.get("/api/plugins/stats/summary")
        assert response.status_code == 200
        data = response.json()
        assert "total_loaded" in data
        assert "categories" in data

    def test_uninstall_plugin_invalid_name_slash(self, authenticated_client):
        """Test DELETE /api/plugins/{name} rejects names with slashes."""
        # Name with backslash is invalid
        response = authenticated_client.delete("/api/plugins/bad%5Cname")
        assert response.status_code == 400
        assert "Invalid plugin name" in response.json()["detail"]

    def test_get_plugin_ui_manifest_not_found(self, authenticated_client):
        """Test GET /api/plugins/{name}/ui/manifest returns 404."""
        response = authenticated_client.get("/api/plugins/nonexistent_xyz_plugin/ui/manifest")
        assert response.status_code == 404

    def test_get_plugin_ui_bundle_not_found(self, authenticated_client):
        """Test GET /api/plugins/{name}/ui/bundle returns 404."""
        response = authenticated_client.get("/api/plugins/nonexistent_xyz_plugin/ui/bundle")
        assert response.status_code == 404

    def test_get_plugin_ui_styles_not_found(self, authenticated_client):
        """Test GET /api/plugins/{name}/ui/styles returns 404."""
        response = authenticated_client.get("/api/plugins/nonexistent_xyz_plugin/ui/styles")
        assert response.status_code == 404

    def test_get_decrypted_ui_bundle_not_found(self, authenticated_client):
        """Test GET /api/plugins/{name}/ui/bundle/decrypted returns 404."""
        response = authenticated_client.get(
            "/api/plugins/nonexistent_xyz_plugin/ui/bundle/decrypted"
        )
        assert response.status_code == 404

    def test_get_plugin_slots_specific(self, authenticated_client):
        """Test GET /api/plugins/{name}/slots returns slots for plugin."""
        response = authenticated_client.get("/api/plugins/some_plugin/slots")
        assert response.status_code == 200
        assert isinstance(response.json(), dict)

    def test_install_plugin_no_body_no_file(self, authenticated_client):
        """Test POST /api/plugins/install without file or path."""
        response = authenticated_client.post("/api/plugins/install")
        # Should return 400 or 422 depending on settings/validation
        assert response.status_code in [400, 422]
