"""Custom Provider CRUD API Routes.

Endpoints for user-defined OpenAI-compatible provider management.
Custom providers appear alongside built-in providers in the Settings page.
"""

import logging
import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.agents.llm import clear_llm_cache
from core.auth.dependencies import get_current_user, get_db
from core.database.models import CustomProvider, ModelConfig, ProviderApiKey
from core.providers import PROVIDER_REGISTRY

logger = logging.getLogger(__name__)

router = APIRouter()

VALID_CAPABILITIES = {"llm", "embedding", "audio_asr", "audio_tts", "vision"}

# ============================================================================
# Request/Response Models
# ============================================================================

class CustomProviderCreate(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=128)
    base_url: str = Field(..., min_length=1, max_length=512)
    requires_api_key: bool = False
    capabilities: list[str] = Field(..., min_length=1)

class CustomProviderUpdate(BaseModel):
    display_name: str | None = Field(None, min_length=1, max_length=128)
    base_url: str | None = Field(None, min_length=1, max_length=512)
    requires_api_key: bool | None = None
    capabilities: list[str] | None = Field(None, min_length=1)

class CustomProviderResponse(BaseModel):
    id: int
    slug: str
    display_name: str
    base_url: str
    requires_api_key: bool
    capabilities: list[str]
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True

# ============================================================================
# Helpers
# ============================================================================

def _slugify(name: str) -> str:
    """Generate a URL-safe slug from a display name."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug[:32] or "custom"

def _validate_capabilities(capabilities: list[str]) -> list[str]:
    invalid = set(capabilities) - VALID_CAPABILITIES
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid capabilities: {sorted(invalid)}. Valid: {sorted(VALID_CAPABILITIES)}",
        )
    return capabilities

def _to_response(cp: CustomProvider) -> CustomProviderResponse:
    return CustomProviderResponse(
        id=cp.id,
        slug=cp.slug,
        display_name=cp.display_name,
        base_url=cp.base_url,
        requires_api_key=cp.requires_api_key,
        capabilities=cp.capabilities or [],
        created_at=cp.created_at.isoformat() if cp.created_at else "",
        updated_at=cp.updated_at.isoformat() if cp.updated_at else "",
    )

# ============================================================================
# Endpoints
# ============================================================================

@router.post("", response_model=CustomProviderResponse, status_code=status.HTTP_201_CREATED)
async def create_custom_provider(
    request: CustomProviderCreate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a custom OpenAI-compatible provider."""
    _validate_capabilities(request.capabilities)

    slug = _slugify(request.display_name)

    # Reject collision with built-in providers
    if slug in PROVIDER_REGISTRY:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Slug '{slug}' conflicts with a built-in provider. Choose a different name.",
        )

    # Check for user-level slug collision, append suffix if needed
    base_slug = slug
    suffix = 1
    while (
        db.query(CustomProvider)
        .filter(CustomProvider.user_id == user["sub"], CustomProvider.slug == slug)
        .first()
    ):
        suffix += 1
        slug = f"{base_slug[:28]}-{suffix}"

    cp = CustomProvider(
        user_id=user["sub"],
        slug=slug,
        display_name=request.display_name,
        base_url=request.base_url.rstrip("/"),
        requires_api_key=request.requires_api_key,
        capabilities=request.capabilities,
    )
    db.add(cp)
    db.commit()
    db.refresh(cp)

    logger.info(f"Created custom provider: slug={slug}, user={user['sub']}")
    return _to_response(cp)

@router.get("", response_model=list[CustomProviderResponse])
async def list_custom_providers(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List user's custom providers."""
    rows = (
        db.query(CustomProvider)
        .filter(CustomProvider.user_id == user["sub"])
        .order_by(CustomProvider.display_name)
        .all()
    )
    return [_to_response(cp) for cp in rows]

@router.patch("/{slug}", response_model=CustomProviderResponse)
async def update_custom_provider(
    slug: str,
    request: CustomProviderUpdate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a custom provider. Slug stays stable."""
    cp = (
        db.query(CustomProvider)
        .filter(CustomProvider.user_id == user["sub"], CustomProvider.slug == slug)
        .first()
    )
    if not cp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Custom provider not found"
        )

    if request.display_name is not None:
        cp.display_name = request.display_name
    if request.base_url is not None:
        cp.base_url = request.base_url.rstrip("/")
    if request.requires_api_key is not None:
        cp.requires_api_key = request.requires_api_key
    if request.capabilities is not None:
        _validate_capabilities(request.capabilities)
        cp.capabilities = request.capabilities

    db.commit()
    db.refresh(cp)
    clear_llm_cache()

    return _to_response(cp)

@router.delete("/{slug}", status_code=status.HTTP_200_OK)
async def delete_custom_provider(
    slug: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a custom provider and clean up references."""
    cp = (
        db.query(CustomProvider)
        .filter(CustomProvider.user_id == user["sub"], CustomProvider.slug == slug)
        .first()
    )
    if not cp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Custom provider not found"
        )

    # Clear ModelConfig references
    config = db.query(ModelConfig).filter(ModelConfig.user_id == user["sub"]).first()
    if config:
        for provider_field in [
            "llm_provider",
            "embedding_provider",
            "asr_provider",
            "tts_provider",
            "vision_provider",
        ]:
            if getattr(config, provider_field, None) == slug:
                setattr(config, provider_field, None)
                model_field = provider_field.replace("_provider", "_model")
                if hasattr(config, model_field):
                    setattr(config, model_field, None)
                endpoint_field = provider_field.replace("_provider", "_endpoint")
                if hasattr(config, endpoint_field):
                    setattr(config, endpoint_field, None)

    # Delete API keys for this provider
    db.query(ProviderApiKey).filter(
        ProviderApiKey.user_id == user["sub"],
        ProviderApiKey.provider == slug,
    ).delete()

    db.delete(cp)
    db.commit()
    clear_llm_cache()

    logger.info(f"Deleted custom provider: slug={slug}, user={user['sub']}")
    return {"status": "deleted", "slug": slug}
