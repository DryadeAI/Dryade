"""Setup API Routes.

Endpoints for the onboarding wizard: status check, LLM key validation,
and setup completion. These endpoints run without authentication since
they are needed before the user has fully configured the instance.

Target: ~120 LOC
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

logger = logging.getLogger("dryade.setup")
router = APIRouter()

# Persistent setup state file -- lives alongside other Dryade config
SETUP_STATE_PATH = Path.home() / ".dryade" / "setup-state.json"

# ============================================================================
# Request / Response Models
# ============================================================================

class SetupSteps(BaseModel):
    """Per-step completion status for the onboarding wizard."""

    llm_provider: bool = False
    api_key: bool = False
    key_validated: bool = False
    mcp_configured: bool = False
    preferences_set: bool = False

class SetupStatusResponse(BaseModel):
    """Response for GET /api/setup/status."""

    configured: bool = False
    has_llm_provider: bool = False
    has_api_key: bool = False
    steps: SetupSteps = Field(default_factory=SetupSteps)

class ValidateKeyRequest(BaseModel):
    """Request body for POST /api/setup/validate-key."""

    provider: str
    api_key: str
    endpoint: str | None = None

class ValidateKeyResponse(BaseModel):
    """Response for POST /api/setup/validate-key."""

    valid: bool
    model_list: list[str] = Field(default_factory=list)
    error: str | None = None

class SetupCompleteRequest(BaseModel):
    """Request body for POST /api/setup/complete."""

    llm_provider: str
    llm_api_key: str
    llm_endpoint: str | None = None
    mcp_servers: dict[str, Any] | None = None
    preferences: dict[str, Any] | None = None

class SetupCompleteResponse(BaseModel):
    """Response for POST /api/setup/complete."""

    status: str = "ok"

# ============================================================================
# Internal Helpers
# ============================================================================

def _read_state() -> dict[str, Any]:
    """Read setup state from disk. Returns empty dict if not found."""
    if SETUP_STATE_PATH.exists():
        try:
            return json.loads(SETUP_STATE_PATH.read_text())
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to read setup state: %s", e)
    return {}

def _write_state(state: dict[str, Any]) -> None:
    """Persist setup state to disk."""
    SETUP_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETUP_STATE_PATH.write_text(json.dumps(state, indent=2))

def _test_provider_key(
    provider: str, api_key: str, endpoint: str | None = None
) -> tuple[bool, list[str], str | None]:
    """Test an LLM provider API key by listing models.

    Returns:
        Tuple of (valid, model_list, error_message).
    """
    import httpx

    # Map provider to its API base URL and models endpoint
    provider_urls: dict[str, str] = {
        "openai": "https://api.openai.com/v1",
        "anthropic": "https://api.anthropic.com/v1",
        "groq": "https://api.groq.com/openai/v1",
        "together": "https://api.together.xyz/v1",
        "mistral": "https://api.mistral.ai/v1",
    }

    base_url = endpoint or provider_urls.get(provider)
    if not base_url:
        # For vllm/ollama, endpoint is required
        if not endpoint:
            return (False, [], f"Provider '{provider}' requires an endpoint URL")
        base_url = endpoint

    try:
        if provider == "anthropic":
            # Anthropic uses a different API pattern
            resp = httpx.get(
                f"{base_url}/models",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
                timeout=10.0,
            )
        else:
            # OpenAI-compatible providers (openai, vllm, ollama, groq, etc.)
            resp = httpx.get(
                f"{base_url}/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10.0,
            )

        if resp.status_code == 200:
            data = resp.json()
            models = [m.get("id", "") for m in data.get("data", [])]
            return (True, models, None)
        else:
            return (False, [], f"API returned status {resp.status_code}")
    except httpx.TimeoutException:
        return (False, [], "Connection timed out (10s)")
    except Exception as e:
        return (False, [], str(e))

# ============================================================================
# Endpoints
# ============================================================================

@router.get("/status", response_model=SetupStatusResponse)
async def get_setup_status() -> SetupStatusResponse:
    """Check whether initial setup has been completed.

    Returns the overall configured flag (based on setup_completed, NOT key
    validity) and per-step completion details for the wizard UI.
    """
    state = _read_state()

    has_provider = bool(state.get("llm_provider"))
    has_key = bool(state.get("llm_api_key_set"))
    key_validated = bool(state.get("key_validated"))
    mcp_configured = bool(state.get("mcp_configured"))
    preferences_set = bool(state.get("preferences_set"))

    return SetupStatusResponse(
        configured=bool(state.get("setup_completed")),
        has_llm_provider=has_provider,
        has_api_key=has_key,
        steps=SetupSteps(
            llm_provider=has_provider,
            api_key=has_key,
            key_validated=key_validated,
            mcp_configured=mcp_configured,
            preferences_set=preferences_set,
        ),
    )

@router.post("/validate-key", response_model=ValidateKeyResponse)
async def validate_key(req: ValidateKeyRequest) -> ValidateKeyResponse:
    """Validate an LLM provider API key in real time.

    Attempts a lightweight API call (list models) against the provider.
    Returns the result with model list on success or error on failure.
    """
    valid, model_list, error = await asyncio.to_thread(
        _test_provider_key, req.provider, req.api_key, req.endpoint
    )
    return ValidateKeyResponse(valid=valid, model_list=model_list, error=error)

@router.post("/complete", response_model=SetupCompleteResponse)
async def complete_setup(req: SetupCompleteRequest) -> SetupCompleteResponse:
    """Save configuration and mark setup as done.

    Validates that required fields are present, persists the config,
    and sets setup_completed=true so the wizard never shows again.
    """
    # Build persistent state
    state = _read_state()
    state.update(
        {
            "setup_completed": True,
            "llm_provider": req.llm_provider,
            "llm_api_key_set": True,
            "key_validated": True,
        }
    )

    if req.llm_endpoint:
        state["llm_endpoint"] = req.llm_endpoint
    if req.mcp_servers:
        state["mcp_configured"] = True
    if req.preferences:
        state["preferences_set"] = True
        state["preferences"] = req.preferences

    _write_state(state)
    logger.info("Setup completed: provider=%s", req.llm_provider)

    return SetupCompleteResponse(status="ok")
