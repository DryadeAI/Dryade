"""E2E tests for plugin discovery and listing.

Tests that the plugin system is discoverable via the API:
- GET /api/plugins returns a structured list
- Each plugin entry has expected fields
- Plugin toggle and config endpoints respond correctly
- Non-existent plugins return 404

These tests work with the in-process TestClient approach (no real plugin files
required — they test the API contract when no plugins are loaded).
"""

import pytest

pytestmark = pytest.mark.e2e

class TestPluginDiscovery:
    """Plugin discovery and listing via the API."""

    def test_list_plugins_returns_list(self, e2e_client):
        """GET /api/plugins returns a JSON list with count."""
        resp = e2e_client.get("/api/plugins")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # Must have plugins list and count fields
        assert "plugins" in body, f"Missing 'plugins' key in response: {body}"
        assert "count" in body, f"Missing 'count' key in response: {body}"
        assert isinstance(body["plugins"], list)
        assert isinstance(body["count"], int)
        assert body["count"] == len(body["plugins"])

    def test_list_plugins_count_matches_list_length(self, e2e_client):
        """The count field must equal len(plugins)."""
        resp = e2e_client.get("/api/plugins")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["count"] == len(body["plugins"])

    def test_each_plugin_has_required_fields(self, e2e_client):
        """Every plugin entry must have name, version, description, enabled."""
        resp = e2e_client.get("/api/plugins")
        assert resp.status_code == 200, resp.text
        plugins = resp.json()["plugins"]

        for plugin in plugins:
            assert "name" in plugin, f"Plugin missing 'name': {plugin}"
            assert "version" in plugin, f"Plugin missing 'version': {plugin}"
            assert "description" in plugin, f"Plugin missing 'description': {plugin}"
            assert "enabled" in plugin, f"Plugin missing 'enabled': {plugin}"
            assert isinstance(plugin["enabled"], bool), f"Plugin 'enabled' is not bool: {plugin}"

    def test_get_nonexistent_plugin_returns_404(self, e2e_client):
        """GET /api/plugins/nonexistent-plugin returns 404."""
        resp = e2e_client.get("/api/plugins/nonexistent-plugin-xyz-123")
        assert resp.status_code == 404, resp.text

    def test_plugin_stats_endpoint_exists(self, e2e_client):
        """GET /api/plugins/stats/summary returns stats dict."""
        resp = e2e_client.get("/api/plugins/stats/summary")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "total_loaded" in body
        assert "categories" in body
        assert isinstance(body["total_loaded"], int)

    def test_plugin_slots_endpoint_exists(self, e2e_client):
        """GET /api/plugins/slots returns dict of slot registrations."""
        resp = e2e_client.get("/api/plugins/slots")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert isinstance(body, dict)

    def test_toggle_nonexistent_plugin_returns_error(self, e2e_client):
        """POST /api/plugins/nonexistent/toggle returns 404 or 400."""
        resp = e2e_client.post(
            "/api/plugins/nonexistent-plugin-xyz/toggle",
            json={"enabled": True},
        )
        assert resp.status_code in (400, 404), (
            f"Expected 400 or 404 for nonexistent plugin, got {resp.status_code}: {resp.text}"
        )

    def test_get_config_nonexistent_plugin_returns_error(self, e2e_client):
        """GET /api/plugins/nonexistent/config returns 404 or 400."""
        resp = e2e_client.get("/api/plugins/nonexistent-plugin-xyz/config")
        assert resp.status_code in (400, 404), (
            f"Expected 400 or 404, got {resp.status_code}: {resp.text}"
        )

class TestPluginSystemState:
    """Tests for plugin system invariants."""

    def test_plugins_list_is_consistent(self, e2e_client):
        """Two consecutive calls to GET /api/plugins return identical counts."""
        resp1 = e2e_client.get("/api/plugins")
        resp2 = e2e_client.get("/api/plugins")
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.json()["count"] == resp2.json()["count"]

    def test_stats_total_matches_list_count(self, e2e_client):
        """Plugin stats total_loaded equals the count in the list endpoint."""
        list_resp = e2e_client.get("/api/plugins")
        stats_resp = e2e_client.get("/api/plugins/stats/summary")
        assert list_resp.status_code == 200
        assert stats_resp.status_code == 200

        list_count = list_resp.json()["count"]
        stats_total = stats_resp.json()["total_loaded"]
        assert list_count == stats_total, (
            f"List count ({list_count}) != stats total_loaded ({stats_total})"
        )
