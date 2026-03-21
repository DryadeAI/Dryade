"""Tests for core/api/routes/setup.py -- Onboarding setup wizard endpoints.

Tests setup status checking, LLM key validation, and setup completion.
Uses a minimal FastAPI app with just the setup router to avoid heavy
dependency chains (sentence_transformers etc).
"""

import importlib
import json
import sys
from types import ModuleType
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

def _load__setup_mod() -> ModuleType:
    """Load setup module directly, bypassing routes __init__.py."""
    import importlib.util
    from pathlib import Path

    # Navigate from tests/unit/ up to core/api/routes/setup.py
    _core_root = Path(__file__).resolve().parent.parent.parent
    setup_path = _core_root / "core" / "api" / "routes" / "setup.py"
    spec = importlib.util.spec_from_file_location(
        "core.api.routes.setup",
        str(setup_path),
    )
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["core.api.routes.setup"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod

# Load once at module level
_setup_mod = _load__setup_mod()

# Create a lightweight test app with just the setup router
_test_app = FastAPI()
_test_app.include_router(_setup_mod.router, prefix="/api/setup", tags=["setup"])

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def _setup_config_dir(tmp_path):
    """Create a temporary config directory for setup state."""
    config_dir = tmp_path / ".dryade"
    config_dir.mkdir()
    return config_dir

@pytest.fixture
def client(_setup_config_dir):
    """Create a test client with mocked setup config path."""
    with patch.object(
        _setup_mod,
        "SETUP_STATE_PATH",
        _setup_config_dir / "setup-state.json",
    ):
        yield TestClient(_test_app)

# ---------------------------------------------------------------------------
# GET /api/setup/status
# ---------------------------------------------------------------------------

class TestSetupStatus:
    """Tests for GET /api/setup/status."""

    def test_status_unconfigured_when_no_state_file(self, client):
        """Returns configured=false when no setup state exists."""
        resp = client.get("/api/setup/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["configured"] is False
        assert "steps" in data

    def test_status_configured_when_setup_completed(self, client, _setup_config_dir):
        """Returns configured=true when setup_completed flag is set."""
        state_path = _setup_config_dir / "setup-state.json"
        state_path.write_text(
            json.dumps(
                {
                    "setup_completed": True,
                    "llm_provider": "openai",
                    "llm_api_key_set": True,
                    "key_validated": True,
                }
            )
        )
        resp = client.get("/api/setup/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["configured"] is True

    def test_status_returns_step_details(self, client, _setup_config_dir):
        """Returns per-step completion status in steps object."""
        state_path = _setup_config_dir / "setup-state.json"
        state_path.write_text(
            json.dumps(
                {
                    "setup_completed": False,
                    "llm_provider": "vllm",
                    "llm_api_key_set": True,
                    "key_validated": False,
                }
            )
        )
        resp = client.get("/api/setup/status")
        assert resp.status_code == 200
        data = resp.json()
        steps = data["steps"]
        assert steps["llm_provider"] is True
        assert steps["api_key"] is True
        assert steps["key_validated"] is False

    def test_status_uses_flag_not_key_validity(self, client, _setup_config_dir):
        """Setup status checks setup_completed flag, NOT current key validity.

        This prevents blocking returning users after key rotation.
        """
        state_path = _setup_config_dir / "setup-state.json"
        state_path.write_text(
            json.dumps(
                {
                    "setup_completed": True,
                    "llm_provider": "openai",
                    "llm_api_key_set": True,
                    "key_validated": False,
                }
            )
        )
        resp = client.get("/api/setup/status")
        data = resp.json()
        assert data["configured"] is True

    def test_status_has_top_level_bools(self, client, _setup_config_dir):
        """Returns has_llm_provider and has_api_key as top-level bools."""
        state_path = _setup_config_dir / "setup-state.json"
        state_path.write_text(
            json.dumps(
                {
                    "setup_completed": False,
                    "llm_provider": "anthropic",
                    "llm_api_key_set": True,
                }
            )
        )
        resp = client.get("/api/setup/status")
        data = resp.json()
        assert data["has_llm_provider"] is True
        assert data["has_api_key"] is True

# ---------------------------------------------------------------------------
# POST /api/setup/validate-key
# ---------------------------------------------------------------------------

class TestValidateKey:
    """Tests for POST /api/setup/validate-key."""

    def test_validate_key_valid(self, client):
        """Returns valid=true with model list for valid provider+key."""
        with patch.object(_setup_mod, "_test_provider_key") as mock_test:
            mock_test.return_value = (True, ["gpt-4o", "gpt-4o-mini"], None)
            resp = client.post(
                "/api/setup/validate-key",
                json={"provider": "openai", "api_key": "sk-test-key-123"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert "gpt-4o" in data["model_list"]

    def test_validate_key_invalid(self, client):
        """Returns valid=false with error for invalid key."""
        with patch.object(_setup_mod, "_test_provider_key") as mock_test:
            mock_test.return_value = (False, [], "Invalid API key")
            resp = client.post(
                "/api/setup/validate-key",
                json={"provider": "openai", "api_key": "sk-bad-key"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert "error" in data

# ---------------------------------------------------------------------------
# POST /api/setup/complete
# ---------------------------------------------------------------------------

class TestSetupComplete:
    """Tests for POST /api/setup/complete."""

    def test_complete_missing_provider_returns_422(self, client):
        """Returns 422 when llm_provider is missing."""
        resp = client.post(
            "/api/setup/complete",
            json={"llm_api_key": "sk-test"},
        )
        assert resp.status_code == 422

    def test_complete_missing_api_key_returns_422(self, client):
        """Returns 422 when llm_api_key is missing."""
        resp = client.post(
            "/api/setup/complete",
            json={"llm_provider": "openai"},
        )
        assert resp.status_code == 422

    def test_complete_valid_data_persists(self, client, _setup_config_dir):
        """Persists config and sets setup_completed=true."""
        resp = client.post(
            "/api/setup/complete",
            json={
                "llm_provider": "openai",
                "llm_api_key": "sk-test-key-123",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

        # Verify state was persisted
        state_path = _setup_config_dir / "setup-state.json"
        assert state_path.exists()
        state = json.loads(state_path.read_text())
        assert state["setup_completed"] is True
        assert state["llm_provider"] == "openai"

    def test_complete_with_optional_fields(self, client, _setup_config_dir):
        """Accepts optional fields like llm_endpoint and preferences."""
        resp = client.post(
            "/api/setup/complete",
            json={
                "llm_provider": "vllm",
                "llm_api_key": "not-needed",
                "llm_endpoint": "http://localhost:8000/v1",
                "preferences": {"theme": "dark"},
            },
        )
        assert resp.status_code == 200

        state_path = _setup_config_dir / "setup-state.json"
        state = json.loads(state_path.read_text())
        assert state["setup_completed"] is True
        assert state["llm_provider"] == "vllm"

    def test_complete_prevents_wizard_from_showing_again(self, client, _setup_config_dir):
        """Once setup_completed is true, wizard should never show again."""
        # Complete setup
        client.post(
            "/api/setup/complete",
            json={
                "llm_provider": "openai",
                "llm_api_key": "sk-test",
            },
        )
        # Check status
        resp = client.get("/api/setup/status")
        data = resp.json()
        assert data["configured"] is True
