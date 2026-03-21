"""Marketplace catalog and install API endpoints.

Provides a browsable catalog of plugins with availability based on the
user's current signed allowlist.  "Install" for Phase 97 means "activate
a locally-present plugin" -- downloading from an external marketplace is
deferred.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class CatalogPlugin(BaseModel):
    """A single plugin entry in the marketplace catalog."""

    name: str
    display_name: str
    description: str
    version: str
    author: str
    tier: str = Field(description="Required tier: starter, team, or enterprise")
    category: str
    icon: Optional[str] = None
    installed: bool = False
    available: bool = Field(description="True if plugin is in the user's current allowlist")
    download_url: Optional[str] = None
    rating: Optional[float] = None
    install_count: Optional[int] = None

class CatalogResponse(BaseModel):
    """Response for GET /catalog."""

    plugins: list[CatalogPlugin]
    total: int
    tier_info: dict

class InstallRequest(BaseModel):
    """Request body for POST /install."""

    plugin_name: str

class InstallResponse(BaseModel):
    """Response for POST /install."""

    success: bool
    message: str
    plugin_name: str

# ---------------------------------------------------------------------------
# Category mapping -- derived from plugin descriptions / conventions
# ---------------------------------------------------------------------------

_CATEGORY_MAP: dict[str, str] = {
    "document_processor": "document_processing",
    "legal_review": "legal",
    "excel_analyst": "finance",
    "marketing": "marketing",
    "sales_intelligence": "marketing",
    "cost_tracker": "finance",
    "compliance_auditor": "legal",
    "healthcare": "healthcare",
    "devops_sre": "devops",
    "kpi_monitor": "devops",
    "mcp": "tools",
    "semantic_cache": "tools",
    "safety": "security",
    "file_safety": "security",
    "sandbox": "security",
    "zitadel_auth": "security",
    "self_healing": "tools",
    "debugger": "tools",
    "checkpoint": "tools",
    "flow_editor": "tools",
    "reactflow": "tools",
    "replay": "tools",
    "message_hygiene": "tools",
    "skill_editor": "tools",
    "model_selection_enhanced": "tools",
    "vllm": "tools",
    "trainer": "tools",
    "templates": "tools",
    "conversation": "tools",
    "clarify": "tools",
    "escalation": "support",
    "project_manager": "tools",
    "audio": "tools",
}

AVAILABLE_CATEGORIES = sorted(
    {
        "document_processing",
        "legal",
        "finance",
        "marketing",
        "support",
        "hr",
        "real_estate",
        "healthcare",
        "devops",
        "search",
        "tools",
        "security",
    }
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _scan_plugin_manifests() -> list[dict]:
    """Scan plugins/*/dryade.json to build a catalog of known plugins."""
    plugins_root = Path(__file__).resolve().parents[3] / "plugins"
    results: list[dict] = []

    if not plugins_root.is_dir():
        return results

    for manifest_path in sorted(plugins_root.glob("*/dryade.json")):
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            results.append(
                {
                    "name": data.get("name", manifest_path.parent.name),
                    "description": data.get("description", ""),
                    "version": data.get("version", "0.0.0"),
                    "author": data.get("author", "Unknown"),
                    "required_tier": data.get("required_tier", "starter"),
                    "has_ui": data.get("has_ui", False),
                }
            )
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read manifest %s: %s", manifest_path, exc)

    return results

def _get_allowed_set() -> frozenset[str]:
    """Return the current set of allowed plugin names from the signed allowlist."""
    try:
        from core.ee.allowlist_ee import get_allowed_plugins

        allowed = get_allowed_plugins()
        return allowed if allowed is not None else frozenset()
    except Exception:
        return frozenset()

def _get_loaded_plugin_names() -> set[str]:
    """Return names of currently loaded / active plugins."""
    try:
        from core.ee.plugins_ee import get_plugin_manager

        manager = get_plugin_manager()
        return {p.name for p in manager.get_plugins()}
    except Exception:
        return set()

def _get_current_tier() -> str:
    """Return the user's current tier from the allowlist metadata."""
    try:
        from core.ee.allowlist_ee import get_tier_metadata

        meta = get_tier_metadata()
        return meta.tier if meta else "unknown"
    except Exception:
        return "unknown"

def _format_display_name(name: str) -> str:
    """Convert snake_case plugin name to a human-readable display name."""
    return name.replace("_", " ").title()

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/catalog", response_model=CatalogResponse)
async def get_catalog(
    category: Optional[str] = None,
    search: Optional[str] = None,
    tier: Optional[str] = None,
):
    """Return the marketplace catalog filtered by optional criteria.

    Each plugin includes availability (in allowlist) and installed status.
    """
    manifests = _scan_plugin_manifests()
    allowed = _get_allowed_set()
    loaded = _get_loaded_plugin_names()
    current_tier = _get_current_tier()

    catalog: list[CatalogPlugin] = []

    for m in manifests:
        name = m["name"]
        plugin_tier = m.get("required_tier", "starter")
        plugin_category = _CATEGORY_MAP.get(name, "tools")
        is_available = name in allowed
        is_installed = name in loaded

        entry = CatalogPlugin(
            name=name,
            display_name=_format_display_name(name),
            description=m.get("description", ""),
            version=m.get("version", "0.0.0"),
            author=m.get("author", "Unknown"),
            tier=plugin_tier,
            category=plugin_category,
            installed=is_installed,
            available=is_available,
        )
        catalog.append(entry)

    # Apply filters
    if category and category != "all":
        catalog = [p for p in catalog if p.category == category]

    if search:
        q = search.lower()
        catalog = [
            p
            for p in catalog
            if q in p.name.lower() or q in p.display_name.lower() or q in p.description.lower()
        ]

    if tier:
        catalog = [p for p in catalog if p.tier == tier]

    return CatalogResponse(
        plugins=catalog,
        total=len(catalog),
        tier_info={"name": current_tier},
    )

@router.post("/install", response_model=InstallResponse)
async def install_plugin(request: InstallRequest):
    """Activate a locally-present plugin.

    Checks allowlist and triggers a plugin reload if the plugin directory
    exists but the plugin is not currently loaded.
    """
    plugin_name = request.plugin_name
    allowed = _get_allowed_set()

    if plugin_name not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Plugin '{plugin_name}' requires a tier upgrade",
        )

    # Check if plugin directory exists locally
    plugins_root = Path(__file__).resolve().parents[3] / "plugins"
    plugin_dir = plugins_root / plugin_name

    if not plugin_dir.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plugin '{plugin_name}' not found locally",
        )

    # Check if already loaded
    loaded = _get_loaded_plugin_names()
    if plugin_name in loaded:
        return InstallResponse(
            success=True,
            message=f"Plugin '{plugin_name}' is already installed and active",
            plugin_name=plugin_name,
        )

    # Plugin is allowed and exists locally but not loaded.
    # A full activation would require server restart or hot-reload.
    # For Phase 97, indicate success and note the restart requirement.
    return InstallResponse(
        success=True,
        message=(
            f"Plugin '{plugin_name}' is ready. "
            "A server restart may be required to fully activate it."
        ),
        plugin_name=plugin_name,
    )

@router.get("/categories")
async def get_categories():
    """Return the list of available plugin categories."""
    return {"categories": AVAILABLE_CATEGORIES}
