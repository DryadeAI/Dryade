"""Model Configuration API Routes.

Endpoints for per-user model configuration and API key management.

Target: ~200 LOC
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.auth.dependencies import get_current_user, get_db
from core.crypto import decrypt_key, encrypt_key, get_key_prefix
from core.database.models import ModelConfig, ProviderApiKey
from core.providers import PROVIDER_REGISTRY

router = APIRouter()

# ============================================================================
# Request/Response Models
# ============================================================================

class ModelConfigResponse(BaseModel):
    """User model configuration response."""

    llm_provider: str | None = None
    llm_model: str | None = None
    llm_endpoint: str | None = None
    embedding_provider: str | None = None
    embedding_model: str | None = None
    embedding_endpoint: str | None = None
    asr_provider: str | None = None
    asr_model: str | None = None
    asr_endpoint: str | None = None
    tts_provider: str | None = None
    tts_model: str | None = None
    vision_provider: str | None = None
    vision_model: str | None = None
    llm_inference_params: dict | None = None
    vision_inference_params: dict | None = None
    audio_inference_params: dict | None = None
    embedding_inference_params: dict | None = None
    vllm_server_params: dict | None = None
    updated_at: datetime | None = None

    class Config:
        """Pydantic configuration for ORM mode."""

        from_attributes = True

class ModelConfigUpdate(BaseModel):
    """Model configuration update request."""

    llm_provider: str | None = None
    llm_model: str | None = None
    llm_endpoint: str | None = None
    embedding_provider: str | None = None
    embedding_model: str | None = None
    embedding_endpoint: str | None = None
    asr_provider: str | None = None
    asr_model: str | None = None
    asr_endpoint: str | None = None
    tts_provider: str | None = None
    tts_model: str | None = None
    vision_provider: str | None = None
    vision_model: str | None = None
    llm_inference_params: dict | None = None
    vision_inference_params: dict | None = None
    audio_inference_params: dict | None = None
    embedding_inference_params: dict | None = None
    vllm_server_params: dict | None = None

class ProviderInfo(BaseModel):
    """Provider information with key status."""

    id: str
    name: str
    models: list[str]
    requires_api_key: bool
    supports_custom_endpoint: bool
    has_key: bool = False

class ApiKeyCreate(BaseModel):
    """API key storage request."""

    provider: str = Field(..., description="Provider ID (e.g., 'openai', 'anthropic')")
    api_key: str = Field(..., min_length=8, description="API key to store")
    model_override: str | None = Field(None, description="Optional: key for specific model only")

class ApiKeyInfo(BaseModel):
    """API key info response (never includes full key)."""

    provider: str
    key_prefix: str
    is_global: bool
    model_override: str | None
    created_at: datetime

    class Config:
        """Pydantic configuration for ORM mode."""

        from_attributes = True

class ApiKeyTestRequest(BaseModel):
    """API key test request."""

    provider: str
    api_key: str | None = None  # If None, uses stored key

class ApiKeyTestResponse(BaseModel):
    """API key test response."""

    provider: str
    valid: bool
    message: str
    models_available: list[str] | None = None

# ============================================================================
# Configuration Endpoints
# ============================================================================

@router.get("/config", response_model=ModelConfigResponse)
async def get_config(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get user's model configuration.

    Returns the user's current model preferences or defaults if not configured.
    """
    config = db.query(ModelConfig).filter(ModelConfig.user_id == user["sub"]).first()
    if not config:
        # Return default empty config
        return ModelConfigResponse()
    return config

@router.patch("/config", response_model=ModelConfigResponse)
async def update_config(
    update: ModelConfigUpdate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update user's model configuration.

    Creates config if not exists, otherwise updates specified fields.
    Clears LLM cache to ensure changes take effect immediately.
    """
    from core.agents.llm import clear_llm_cache

    config = db.query(ModelConfig).filter(ModelConfig.user_id == user["sub"]).first()

    if not config:
        config = ModelConfig(user_id=user["sub"])
        db.add(config)

    from core.providers.inference_params import validate_params

    for key, value in update.model_dump(exclude_unset=True).items():
        # Validate and clamp inference param values
        if key.endswith("_inference_params") and value is not None:
            value = validate_params(value)
        setattr(config, key, value)

    db.commit()
    db.refresh(config)

    # Clear LLM cache so new config takes effect immediately
    clear_llm_cache()

    return config

@router.get("/provider-params")
async def get_provider_params(user: dict = Depends(get_current_user)):
    """Return provider-to-supported-params map, param specs, presets, and capability support.

    Used by the frontend to dynamically show/hide parameters based on selected provider.
    """
    from core.providers.inference_params import (
        CAPABILITY_PARAM_SUPPORT,
        PRESETS,
        VLLM_SERVER_PARAMS,
        get_param_specs_for_api,
        get_provider_params_for_api,
    )

    return {
        "provider_params": get_provider_params_for_api(),
        "param_specs": get_param_specs_for_api(),
        "presets": PRESETS,
        "capability_support": CAPABILITY_PARAM_SUPPORT,
        "vllm_server_params": {
            name: {
                "type": spec.type,
                "min": spec.min_val,
                "max": spec.max_val,
                "default": spec.default,
                "step": spec.step,
                "label": spec.label,
                "description": spec.description,
            }
            for name, spec in VLLM_SERVER_PARAMS.items()
        },
    }

# ============================================================================
# Provider Endpoints
# ============================================================================

@router.get("/providers", response_model=list[ProviderInfo])
async def list_providers(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """List supported providers with user's key status.

    Returns all supported providers with information about whether
    the user has stored an API key for each.
    """
    # Get user's stored keys
    user_keys = (
        db.query(ProviderApiKey)
        .filter(ProviderApiKey.user_id == user["sub"], ProviderApiKey.is_global == True)  # noqa: E712
        .all()
    )
    keys_by_provider = {k.provider: k for k in user_keys}

    providers = []
    for provider_id, metadata in PROVIDER_REGISTRY.items():
        # Get model IDs from registry (static) or empty list for dynamic providers
        model_ids = list(metadata.models.keys()) if metadata.models else []

        providers.append(
            ProviderInfo(
                id=provider_id,
                name=metadata.display_name,
                models=model_ids,
                requires_api_key=metadata.requires_api_key,
                supports_custom_endpoint=metadata.supports_custom_endpoint,
                has_key=provider_id in keys_by_provider,
            )
        )
    return providers

# ============================================================================
# API Key Endpoints
# ============================================================================

@router.post("/keys", response_model=ApiKeyInfo)
async def store_key(
    request: ApiKeyCreate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Store encrypted API key for a provider.

    Keys are encrypted at rest using Fernet (AES-128-CBC).
    Replaces existing key for the same provider/model combination.
    """
    # Validate provider: must be in built-in registry or user's custom providers
    if request.provider not in PROVIDER_REGISTRY:
        from core.database.models import CustomProvider

        custom = (
            db.query(CustomProvider)
            .filter(CustomProvider.user_id == user["sub"], CustomProvider.slug == request.provider)
            .first()
        )
        if not custom:
            raise HTTPException(status_code=400, detail=f"Unknown provider: {request.provider}")

    # Check for existing key
    existing = (
        db.query(ProviderApiKey)
        .filter(
            ProviderApiKey.user_id == user["sub"],
            ProviderApiKey.provider == request.provider,
            ProviderApiKey.model_override == request.model_override,
        )
        .first()
    )

    if existing:
        # Update existing key
        existing.key_encrypted = encrypt_key(request.api_key)
        existing.key_prefix = get_key_prefix(request.api_key)
        db.commit()
        db.refresh(existing)
        return existing

    # Create new key
    key_record = ProviderApiKey(
        user_id=user["sub"],
        provider=request.provider,
        key_encrypted=encrypt_key(request.api_key),
        key_prefix=get_key_prefix(request.api_key),
        is_global=request.model_override is None,
        model_override=request.model_override,
    )
    db.add(key_record)
    db.commit()
    db.refresh(key_record)
    return key_record

@router.get("/keys", response_model=list[ApiKeyInfo])
async def list_keys(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """List user's stored API keys (prefixes only, never full keys).

    Returns metadata about stored keys including provider, prefix,
    and whether it's a global or model-specific key.
    """
    keys = db.query(ProviderApiKey).filter(ProviderApiKey.user_id == user["sub"]).all()
    return keys

@router.delete("/keys/{provider}")
async def delete_key(
    provider: str,
    model_override: str | None = None,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a stored API key.

    Args:
        provider: Provider ID to delete key for
        model_override: If specified, deletes model-specific key only
    """
    query = db.query(ProviderApiKey).filter(
        ProviderApiKey.user_id == user["sub"],
        ProviderApiKey.provider == provider,
        ProviderApiKey.model_override == model_override,
    )
    key_record = query.first()

    if not key_record:
        raise HTTPException(status_code=404, detail="API key not found")

    db.delete(key_record)
    db.commit()
    return {"status": "deleted", "provider": provider}

@router.post("/test", response_model=ApiKeyTestResponse)
async def test_key(
    request: ApiKeyTestRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Test API key connectivity with provider.

    If api_key is not provided, uses the stored key for the provider.
    Makes a real API call to the provider to verify connectivity.
    Returns validation result and available models if successful.
    """
    from core.database.models import CustomProvider
    from core.providers.connectors import get_connector

    provider_metadata = PROVIDER_REGISTRY.get(request.provider)
    custom_provider = None

    if not provider_metadata:
        custom_provider = (
            db.query(CustomProvider)
            .filter(CustomProvider.user_id == user["sub"], CustomProvider.slug == request.provider)
            .first()
        )
        if not custom_provider:
            raise HTTPException(status_code=400, detail=f"Unknown provider: {request.provider}")

    # For local providers that don't require keys, return success immediately
    requires_key = (
        custom_provider.requires_api_key if custom_provider else provider_metadata.requires_api_key
    )
    if not requires_key:
        display = (
            custom_provider.display_name if custom_provider else provider_metadata.display_name
        )
        return ApiKeyTestResponse(
            provider=request.provider,
            valid=True,
            message=f"{display} does not require an API key",
            models_available=[],
        )

    # Get the key to test
    api_key = request.api_key
    if not api_key:
        stored = (
            db.query(ProviderApiKey)
            .filter(
                ProviderApiKey.user_id == user["sub"],
                ProviderApiKey.provider == request.provider,
                ProviderApiKey.is_global == True,  # noqa: E712
            )
            .first()
        )
        if not stored:
            return ApiKeyTestResponse(
                provider=request.provider,
                valid=False,
                message="No API key stored for this provider",
            )
        api_key = decrypt_key(stored.key_encrypted)

    # Real connectivity test via provider connector
    custom_base_url = custom_provider.base_url if custom_provider else None
    connector = get_connector(request.provider, custom_base_url=custom_base_url)
    if connector:
        base_url = custom_base_url or (provider_metadata.base_url if provider_metadata else None)
        result = await connector.test_connection(api_key=api_key, base_url=base_url)
        return ApiKeyTestResponse(
            provider=request.provider,
            valid=result.success,
            message=result.message,
            models_available=result.models,
        )

    return ApiKeyTestResponse(
        provider=request.provider,
        valid=True,
        message="No connector available for real test; key stored successfully",
    )
