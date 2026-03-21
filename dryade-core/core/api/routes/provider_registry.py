"""Provider Registry API Routes.

Endpoints for provider metadata access, connection testing, and model discovery.
Uses real provider connectors to validate API keys and discover available models.

Target: ~200 LOC
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.auth.dependencies import get_current_user, get_db
from core.crypto import decrypt_key
from core.database.models import CustomProvider, ProviderApiKey
from core.providers import PROVIDER_REGISTRY, get_provider
from core.providers.connectors import get_connector

logger = logging.getLogger(__name__)

router = APIRouter()

# ============================================================================
# Request/Response Models
# ============================================================================

class ProviderCapabilities(BaseModel):
    """Provider capabilities for frontend display."""

    llm: bool = False
    embedding: bool = False
    vision: bool = False
    audio_asr: bool = False
    audio_tts: bool = False

class ModelsByCapability(BaseModel):
    """Models grouped by capability."""

    llm: list[str] = []
    embedding: list[str] = []
    vision: list[str] = []
    audio_asr: list[str] = []
    audio_tts: list[str] = []

class ProviderResponse(BaseModel):
    """Provider metadata response."""

    id: str
    display_name: str
    auth_type: str
    requires_api_key: bool
    supports_custom_endpoint: bool
    capabilities: ProviderCapabilities
    has_key: bool = False
    base_url: str | None = None
    models: list[str] = []  # All models (for backward compatibility)
    models_by_capability: ModelsByCapability = ModelsByCapability()
    is_custom: bool = False

class ConnectionTestRequest(BaseModel):
    """Request to test provider connection."""

    api_key: str | None = Field(
        None, description="API key to test (if not provided, uses stored key)"
    )
    base_url: str | None = Field(None, description="Custom endpoint URL")

class ConnectionTestResponse(BaseModel):
    """Response from connection test."""

    success: bool
    message: str
    models: list[str] | None = None
    error_code: str | None = None

class ModelDiscoveryResponse(BaseModel):
    """Response from model discovery."""

    provider_id: str
    models: list[str]
    source: str  # "dynamic", "static", or "none"

# ============================================================================
# Helpers
# ============================================================================

def _custom_to_response(cp: CustomProvider, has_key: bool) -> ProviderResponse:
    """Build a ProviderResponse from a CustomProvider row."""
    capabilities = ProviderCapabilities()
    for cap_str in cp.capabilities or []:
        cap_name = cap_str.lower().replace("-", "_")
        if hasattr(capabilities, cap_name):
            setattr(capabilities, cap_name, True)

    return ProviderResponse(
        id=cp.slug,
        display_name=cp.display_name,
        auth_type="bearer_token" if cp.requires_api_key else "none",
        requires_api_key=cp.requires_api_key,
        supports_custom_endpoint=True,
        capabilities=capabilities,
        has_key=has_key,
        base_url=cp.base_url,
        models=[],
        models_by_capability=ModelsByCapability(),
        is_custom=True,
    )

def _get_custom_provider(db: Session, user_id: str, slug: str) -> CustomProvider | None:
    return (
        db.query(CustomProvider)
        .filter(CustomProvider.user_id == user_id, CustomProvider.slug == slug)
        .first()
    )

# ============================================================================
# Provider Registry Endpoints
# ============================================================================

@router.get("", response_model=list[ProviderResponse])
async def list_providers(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all providers with capabilities and key status.

    Returns metadata for all 9 providers including authentication requirements,
    capabilities (LLM, embedding, vision, etc.), and whether the user has
    stored an API key.
    """
    # Get user's stored keys
    user_keys = (
        db.query(ProviderApiKey)
        .filter(
            ProviderApiKey.user_id == user["sub"],
            ProviderApiKey.is_global == True,  # noqa: E712
        )
        .all()
    )
    keys_by_provider = {k.provider: k for k in user_keys}

    providers = []
    for provider_id, metadata in PROVIDER_REGISTRY.items():
        # Map capabilities to frontend-friendly format
        capabilities = ProviderCapabilities()
        for cap in metadata.capabilities:
            cap_name = cap.value.lower().replace("-", "_")
            if hasattr(capabilities, cap_name):
                setattr(capabilities, cap_name, True)

        # Group models by capability
        models_by_cap = ModelsByCapability()
        for model in metadata.models.values():
            for cap in model.capabilities:
                cap_name = cap.value.lower().replace("-", "_")
                if hasattr(models_by_cap, cap_name):
                    getattr(models_by_cap, cap_name).append(model.id)

        providers.append(
            ProviderResponse(
                id=metadata.id,
                display_name=metadata.display_name,
                auth_type=metadata.auth_type.value,
                requires_api_key=metadata.requires_api_key,
                supports_custom_endpoint=metadata.supports_custom_endpoint,
                capabilities=capabilities,
                has_key=provider_id in keys_by_provider,
                base_url=metadata.base_url,
                models=list(metadata.models.keys()),  # All models
                models_by_capability=models_by_cap,
            )
        )

    # Append user's custom providers
    custom_rows = db.query(CustomProvider).filter(CustomProvider.user_id == user["sub"]).all()
    for cp in custom_rows:
        providers.append(_custom_to_response(cp, cp.slug in keys_by_provider))

    return providers

@router.get("/{provider_id}", response_model=ProviderResponse)
async def get_provider_details(
    provider_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get details for a specific provider.

    Returns metadata including capabilities and whether user has stored a key.
    """
    metadata = get_provider(provider_id)

    # Fall back to custom provider
    if not metadata:
        cp = _get_custom_provider(db, user["sub"], provider_id)
        if not cp:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Provider not found: {provider_id}",
            )
        has_key = (
            db.query(ProviderApiKey)
            .filter(
                ProviderApiKey.user_id == user["sub"],
                ProviderApiKey.provider == provider_id,
                ProviderApiKey.is_global == True,  # noqa: E712
            )
            .first()
        ) is not None
        return _custom_to_response(cp, has_key)

    # Built-in provider
    stored_key = (
        db.query(ProviderApiKey)
        .filter(
            ProviderApiKey.user_id == user["sub"],
            ProviderApiKey.provider == provider_id,
            ProviderApiKey.is_global == True,  # noqa: E712
        )
        .first()
    )

    capabilities = ProviderCapabilities()
    for cap in metadata.capabilities:
        cap_name = cap.value.lower().replace("-", "_")
        if hasattr(capabilities, cap_name):
            setattr(capabilities, cap_name, True)

    models_by_cap = ModelsByCapability()
    for model in metadata.models.values():
        for cap in model.capabilities:
            cap_name = cap.value.lower().replace("-", "_")
            if hasattr(models_by_cap, cap_name):
                getattr(models_by_cap, cap_name).append(model.id)

    return ProviderResponse(
        id=metadata.id,
        display_name=metadata.display_name,
        auth_type=metadata.auth_type.value,
        requires_api_key=metadata.requires_api_key,
        supports_custom_endpoint=metadata.supports_custom_endpoint,
        capabilities=capabilities,
        has_key=stored_key is not None,
        base_url=metadata.base_url,
        models=list(metadata.models.keys()),
        models_by_capability=models_by_cap,
    )

# ============================================================================
# Connection Testing Endpoints
# ============================================================================

@router.post("/{provider_id}/test", response_model=ConnectionTestResponse)
async def test_provider_connection(
    provider_id: str,
    request: ConnectionTestRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Test connection to a provider using real API call.

    If api_key is not provided in request, uses stored key.
    For local providers (Ollama, vLLM), tests connectivity to the endpoint.
    For cloud providers, validates API key with real provider API call.

    Returns success status, message, and available models if connection succeeds.
    """
    metadata = get_provider(provider_id)
    custom_provider = None

    if not metadata:
        custom_provider = _get_custom_provider(db, user["sub"], provider_id)
        if not custom_provider:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Provider not found: {provider_id}",
            )

    # Get connector (built-in or dynamic for custom)
    custom_base_url = custom_provider.base_url if custom_provider else None
    connector = get_connector(provider_id, custom_base_url=custom_base_url)
    if not connector:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"Connection testing not implemented for provider: {provider_id}",
        )

    # Get API key to test
    requires_key = (
        custom_provider.requires_api_key if custom_provider else metadata.requires_api_key
    )
    api_key = request.api_key
    if not api_key and requires_key:
        stored = (
            db.query(ProviderApiKey)
            .filter(
                ProviderApiKey.user_id == user["sub"],
                ProviderApiKey.provider == provider_id,
                ProviderApiKey.is_global == True,  # noqa: E712
            )
            .first()
        )
        if stored:
            api_key = decrypt_key(stored.key_encrypted)
        else:
            return ConnectionTestResponse(
                success=False,
                message="No API key provided and no stored key found",
                error_code="no_api_key",
            )

    # Use custom base_url if provided, otherwise provider default
    if custom_provider:
        base_url = request.base_url or custom_provider.base_url
    else:
        base_url = request.base_url or metadata.base_url

    result = await connector.test_connection(api_key=api_key, base_url=base_url)

    return ConnectionTestResponse(
        success=result.success,
        message=result.message,
        models=result.models,
        error_code=result.error_code,
    )

# ============================================================================
# Model Discovery Endpoints
# ============================================================================

@router.get("/{provider_id}/models", response_model=ModelDiscoveryResponse)
async def discover_provider_models(
    provider_id: str,
    endpoint: str | None = None,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Discover available models for a provider.

    For cloud providers with static model lists (OpenAI, Anthropic, Google),
    returns the predefined model list from the registry.

    For local providers (Ollama, vLLM), dynamically queries the provider
    endpoint to discover installed/available models.

    For providers requiring API keys, uses stored key if available.

    Args:
        provider_id: Provider identifier
        endpoint: Optional custom endpoint URL (for local providers)
    """
    metadata = get_provider(provider_id)
    custom_provider = None

    if not metadata:
        custom_provider = _get_custom_provider(db, user["sub"], provider_id)
        if not custom_provider:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Provider not found: {provider_id}",
            )

    # Get connector (built-in or dynamic for custom)
    custom_base_url = custom_provider.base_url if custom_provider else None
    connector = get_connector(provider_id, custom_base_url=custom_base_url)

    if connector:
        # Get API key if needed
        requires_key = (
            custom_provider.requires_api_key if custom_provider else metadata.requires_api_key
        )
        api_key = None
        if requires_key:
            stored = (
                db.query(ProviderApiKey)
                .filter(
                    ProviderApiKey.user_id == user["sub"],
                    ProviderApiKey.provider == provider_id,
                    ProviderApiKey.is_global == True,  # noqa: E712
                )
                .first()
            )
            if stored:
                api_key = decrypt_key(stored.key_encrypted)

        # Use custom endpoint or provider/custom default
        if custom_provider:
            base_url = endpoint or custom_provider.base_url
        else:
            base_url = endpoint or metadata.base_url

        try:
            models = await connector.discover_models(api_key=api_key, base_url=base_url)
            if models:
                return ModelDiscoveryResponse(
                    provider_id=provider_id,
                    models=models,
                    source="dynamic",
                )
        except Exception:
            pass

    # Fall back to static models from the registry
    if metadata and metadata.models:
        static_models = list(metadata.models.keys())
        if static_models:
            return ModelDiscoveryResponse(
                provider_id=provider_id,
                models=static_models,
                source="static",
            )

    return ModelDiscoveryResponse(
        provider_id=provider_id,
        models=[],
        source="none",
    )
