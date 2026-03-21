"""Plugin Management API Endpoints.

Provides endpoints to list, query, and manage loaded plugins.
Includes UI bundle serving with integrity verification.
Includes check-for-updates proxy and update-status endpoints for the
marketplace-to-PM delivery pipeline (Phase 164.4).
"""

from __future__ import annotations

import hashlib
import inspect
import json
import logging
import os
import shutil
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from core.auth.dependencies import get_current_user
from core.config import get_settings
from core.ee.plugins_ee import get_plugin_manager as _get_plugin_manager
from core.extensions.pipeline import get_extension_registry
from core.slots import SlotName, slot_registry
from core.slots.models import SlotRegistration


def get_plugin_manager():
    """Get the plugin manager."""
    return _get_plugin_manager()

# Port PM listens on for manual trigger (POST /check-updates)
_PM_TRIGGER_PORT = 9472

logger = logging.getLogger(__name__)

# Some plugins register multiple pipeline extensions under different names.
_PLUGIN_EXTENSION_ALIASES: dict[str, list[str]] = {
    # safety plugin registers two pipeline extensions
    "safety": ["input_validation", "output_sanitization"],
}

def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.resolve().relative_to(base.resolve())
        return True
    except Exception:
        return False

def _safe_extract_zip(zf: zipfile.ZipFile, dest_dir: Path) -> None:
    dest_dir = dest_dir.resolve()
    for member in zf.infolist():
        member_path = Path(member.filename)
        # Reject absolute paths and parent traversal.
        if member_path.is_absolute() or ".." in member_path.parts:
            raise ValueError(f"Unsafe zip member path: {member.filename}")
        target_path = (dest_dir / member.filename).resolve()
        if not _is_relative_to(target_path, dest_dir):
            raise ValueError(f"Zip member escapes destination: {member.filename}")
        zf.extract(member, dest_dir)

def _safe_extract_tar(tf: tarfile.TarFile, dest_dir: Path) -> None:
    dest_dir = dest_dir.resolve()
    for member in tf.getmembers():
        member_path = Path(member.name)
        if member_path.is_absolute() or ".." in member_path.parts:
            raise ValueError(f"Unsafe tar member path: {member.name}")
        target_path = (dest_dir / member.name).resolve()
        if not _is_relative_to(target_path, dest_dir):
            raise ValueError(f"Tar member escapes destination: {member.name}")
    tf.extractall(dest_dir)

def _get_effective_enabled(plugin_name: str) -> bool:
    """Best-effort enabled value for a plugin name.

    For pipeline extensions, this maps to ExtensionRegistry state. For other plugins,
    it reflects an in-memory override (if set) or defaults to True.
    """
    manager = get_plugin_manager()
    registry = get_extension_registry()

    ext_names = _PLUGIN_EXTENSION_ALIASES.get(plugin_name, [plugin_name])
    ext_states: list[bool] = []
    for ext_name in ext_names:
        ext = registry.get(ext_name)
        if ext is not None:
            ext_states.append(bool(ext.enabled))

    if ext_states:
        return all(ext_states)

    override = manager.get_enabled_override(plugin_name)
    if override is not None:
        return bool(override)

    return True

def _set_effective_enabled(plugin_name: str, enabled: bool) -> list[str]:
    """Set enabled state for a plugin (best-effort).

    Returns:
        List of extension names that were updated.
    """
    manager = get_plugin_manager()
    registry = get_extension_registry()

    updated: list[str] = []
    ext_names = _PLUGIN_EXTENSION_ALIASES.get(plugin_name, [plugin_name])
    for ext_name in ext_names:
        ext = registry.get(ext_name)
        if ext is not None:
            ext.enabled = enabled
            updated.append(ext_name)

    if not updated:
        manager.set_enabled_override(plugin_name, enabled)

    return updated

class PluginInfo(BaseModel):
    """Plugin information response."""

    name: str
    version: str
    description: str
    loaded: bool = True
    enabled: bool = True
    has_ui: bool = False
    icon: str | None = None

class PluginListResponse(BaseModel):
    """Response for listing all plugins."""

    plugins: list[PluginInfo]
    count: int

class PluginDetailResponse(BaseModel):
    """Response for plugin details."""

    name: str
    version: str
    description: str
    loaded: bool = True
    registered: bool = True
    enabled: bool = True
    api_paths: list[str] | None = None

class PluginToggleRequest(BaseModel):
    """Request model for enabling/disabling a plugin."""

    enabled: bool = Field(..., description="True to enable, false to disable")

class PluginConfigResponse(BaseModel):
    """Response model for plugin configuration."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    config: dict[str, Any]
    config_schema: dict[str, Any] | None = Field(default=None, alias="schema")
    note: str | None = None

class PluginErrorResponse(BaseModel):
    """Standardized error response for plugin endpoints.

    This model lives in core for reference, but plugin routes should define
    their own copy to avoid importing from core directly. This ensures plugins
    remain decoupled from core internals.
    """

    success: bool = False
    error: str
    code: str = "PLUGIN_ERROR"
    detail: str | None = None

# Cache for plugin settings schemas (keyed by plugin name).
# Schemas are static (read from dryade.json manifest) so caching is safe.
_schema_cache: dict[str, dict | None] = {}

def _load_plugin_settings_schema(plugin_name: str) -> dict | None:
    """Load settings_schema from a plugin's dryade.json manifest.

    Uses inspect to locate the plugin's source directory, then reads
    the dryade.json file and extracts the ``settings_schema`` field.
    Results are cached since schemas are static.

    Args:
        plugin_name: Name of the plugin to load schema for.

    Returns:
        The settings_schema dict if present, None otherwise.
    """
    if plugin_name in _schema_cache:
        return _schema_cache[plugin_name]

    schema: dict | None = None
    try:
        manager = get_plugin_manager()
        plugin = manager.get_plugin(plugin_name)
        if plugin is None:
            _schema_cache[plugin_name] = None
            return None

        # Locate plugin directory via its module source file
        plugin_dir = Path(inspect.getfile(type(plugin))).parent
        manifest_path = plugin_dir / "dryade.json"

        if manifest_path.is_file():
            with open(manifest_path) as f:
                manifest = json.load(f)
            schema = manifest.get("settings_schema")
    except Exception:
        logger.debug("Failed to load settings_schema for plugin '%s'", plugin_name, exc_info=True)

    _schema_cache[plugin_name] = schema
    return schema

class PluginInstallRequest(BaseModel):
    """Install request referencing a local file/directory path."""

    path: str = Field(
        ...,
        description="Local filesystem path to .zip/.tar(.gz)/.tgz archive or a plugin directory",
    )

class PluginCategoryDetail(BaseModel):
    """Category detail in plugin stats."""

    count: int
    plugins: list[str]

class PluginStatsResponse(BaseModel):
    """Response for plugin system statistics."""

    total_loaded: int
    categories: dict[str, PluginCategoryDetail]
    plugins: list[dict[str, Any]]

router = APIRouter(prefix="/api/plugins", tags=["plugins"])

# =============================================================================
# .dryadepkg Import Endpoint (Phase 178)
# =============================================================================

class InstalledPluginInfo(BaseModel):
    """Information about an installed plugin (on-disk, may or may not be loaded)."""

    name: str
    version: str | None
    type: str  # "encrypted" | "custom"
    status: str  # "loaded" | "inactive" | "error"

@router.post("/import")
async def import_plugin(
    file: UploadFile = File(...),
    force: bool = Form(False),
    current_user: Any = Depends(get_current_user),
) -> dict[str, Any]:
    """Import a .dryadepkg marketplace package into the plugins directory.

    Validates the uploaded file (ZIP structure, manifest, allowlist check),
    places it in the plugins directory, and returns import status.

    Args:
        file: Uploaded .dryadepkg file (multipart form).
        current_user: Authenticated user (JWT).

    Returns:
        200: {"status": "imported", "plugin": {"name": ..., "version": ...}, "message": ...}

    Raises:
        400: Invalid file extension, not a ZIP, or corrupt/missing manifest.
        403: Plugin not in the signed allowlist.
        413: File exceeds 100MB limit.
    """
    from core.dryadepkg_format import read_dryadepkg_manifest

    try:
        from core.ee.plugins_ee import validate_before_load
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plugin system not available (community edition)",
        )

    # Validate extension
    if not file.filename or not file.filename.endswith(".dryadepkg"):
        raise HTTPException(
            status_code=400,
            detail="File must be a .dryadepkg package",
        )

    # Read file (limit 100MB)
    content = await file.read()
    if len(content) > 100 * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail="Package exceeds 100MB limit",
        )

    # Validate ZIP magic bytes (PK\x03\x04)
    if len(content) < 4 or content[:4] != b"PK\x03\x04":
        raise HTTPException(
            status_code=400,
            detail="Invalid package: not a ZIP archive",
        )

    # Read MANIFEST.json from ZIP without decryption
    try:
        manifest = read_dryadepkg_manifest(content)
    except Exception as exc:
        logger.warning("Failed to read manifest from uploaded package: %s", exc)
        raise HTTPException(
            status_code=400,
            detail="Invalid package: cannot read MANIFEST.json",
        ) from exc

    # Validate required manifest fields
    plugin_name = manifest.get("name")
    plugin_version = manifest.get("version")
    if not plugin_name:
        raise HTTPException(
            status_code=400,
            detail="Invalid manifest: missing required 'name' field",
        )

    # Sanitize plugin name (prevent path traversal)
    if (
        "/" in plugin_name
        or "\\" in plugin_name
        or ".." in plugin_name
        or not plugin_name.replace("_", "").replace("-", "").isalnum()
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid plugin name in manifest",
        )

    # Check allowlist — plugin must be authorized
    allowed, reason = validate_before_load(plugin_name)
    if not allowed:
        logger.warning(
            "Rejected import of plugin '%s': %s (requested by %s)",
            plugin_name,
            reason,
            getattr(
                current_user,
                "email",
                current_user.get("email", "unknown")
                if isinstance(current_user, dict)
                else "unknown",
            ),
        )
        raise HTTPException(
            status_code=403,
            detail=f"Plugin not authorized: {reason}",
        )

    # Place .dryadepkg in the plugins directory (with concurrency check)
    settings = get_settings()
    plugins_dir = Path(settings.plugins_dir)
    target_dir = plugins_dir / plugin_name
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{plugin_name}.dryadepkg"

    # Check if plugin already exists — require force=true to overwrite
    if target_path.exists() and not force:
        existing_version: str | None = None
        try:
            existing_manifest = read_dryadepkg_manifest(target_path.read_bytes())
            existing_version = existing_manifest.get("version")
        except Exception:
            existing_version = "unknown (corrupt)"

        return {
            "status": "conflict",
            "plugin": {"name": plugin_name, "version": plugin_version},
            "existing_version": existing_version,
            "message": f"Plugin '{plugin_name}' v{existing_version} is already installed.",
        }

    # Atomic write: write to temp file then rename to avoid partial writes
    import tempfile

    tmp_path = None
    try:
        tmp_fd, tmp_path = tempfile.mkstemp(dir=target_dir, suffix=".dryadepkg.tmp")
        os.write(tmp_fd, content)
        os.close(tmp_fd)
        os.replace(tmp_path, target_path)
    except Exception:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

    user_email = (
        current_user.get("email", "unknown")
        if isinstance(current_user, dict)
        else getattr(current_user, "email", "unknown")
    )
    logger.info(
        "Plugin '%s' v%s imported by user '%s' (%d bytes → %s)",
        plugin_name,
        plugin_version,
        user_email,
        len(content),
        target_path,
    )

    return {
        "status": "imported",
        "plugin": {"name": plugin_name, "version": plugin_version},
        "message": "Plugin imported successfully. It will be loaded on next reload.",
    }

@router.get("/installed", response_model=list[InstalledPluginInfo])
async def list_installed_plugins(
    current_user: Any = Depends(get_current_user),
) -> list[InstalledPluginInfo]:
    """List all installed plugins with their type and status.

    Scans the plugins directory for both .dryadepkg (encrypted marketplace
    plugins) and __init__.py (custom directory plugins). Merges with the
    in-memory plugin manager state to report load status.

    Returns:
        List of InstalledPluginInfo with name, version, type, and status.
    """
    settings = get_settings()
    plugins_dir = Path(settings.plugins_dir)
    manager = get_plugin_manager()

    # Get currently loaded plugin names from the in-memory manager
    loaded_names: set[str] = {p["name"] for p in manager.list_plugins()}

    result: list[InstalledPluginInfo] = []
    seen: set[str] = set()

    def _scan_dir(scan_root: Path) -> None:
        if not scan_root.is_dir():
            return
        for entry in scan_root.iterdir():
            if not entry.is_dir():
                continue
            # Skip tier subdirectories — recurse into them
            if entry.name in _TIER_DIRS:
                _scan_dir(entry)
                continue
            plugin_name = entry.name
            if plugin_name in seen:
                continue
            seen.add(plugin_name)

            # Determine type and version
            pkg_file = entry / f"{plugin_name}.dryadepkg"
            init_file = entry / "__init__.py"

            if pkg_file.exists():
                plugin_type = "encrypted"
                # Read version from manifest (best-effort)
                try:
                    from core.dryadepkg_format import read_dryadepkg_manifest as _rdm

                    manifest_data = _rdm(pkg_file.read_bytes())
                    version = manifest_data.get("version", "unknown")
                except Exception:
                    version = "unknown"
            elif init_file.exists():
                plugin_type = "custom"
                # Try dryade.json manifest
                manifest_file = entry / "dryade.json"
                version = "unknown"
                if manifest_file.exists():
                    try:
                        manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
                        version = manifest_data.get("version", "unknown")
                    except Exception:
                        pass
            else:
                # Directory exists but has neither package nor init — skip
                continue

            status = "loaded" if plugin_name in loaded_names else "inactive"
            result.append(
                InstalledPluginInfo(
                    name=plugin_name,
                    version=version,
                    type=plugin_type,
                    status=status,
                )
            )

    _scan_dir(plugins_dir)

    # Also scan user_plugins_dir if configured and distinct
    if settings.enable_directory_plugins and settings.user_plugins_dir:
        user_dir = Path(settings.user_plugins_dir)
        if user_dir.resolve() != plugins_dir.resolve():
            _scan_dir(user_dir)

    return result

@router.post("/check-updates")
async def check_for_updates() -> dict[str, Any]:
    """Trigger PM to check for marketplace allowlist updates immediately.

    This is a core-as-proxy endpoint: it forwards a "check now" trigger to
    PM's internal port 9472. This keeps PM's internal port hidden from the
    frontend — all frontend traffic goes through core.

    Architecture note: "Core does not call PM via gRPC or any RPC."
    This endpoint is an EXCEPTION: it is NOT requesting allowlist data from PM —
    it is forwarding a user-initiated "check now" trigger. The allowlist itself
    still flows PM->core via file write. This proxy only sends a one-shot trigger.

    Returns:
        200 {"status": "checking"} if PM responded
        503 {"error": "...", "status": "unavailable"} if PM unreachable
    """
    pm_url = f"http://127.0.0.1:{_PM_TRIGGER_PORT}/check-updates"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(pm_url)
            if response.status_code == 200:
                return {"status": "checking", "message": "Plugin update check triggered"}
            else:
                logger.warning("PM trigger returned HTTP %d", response.status_code)
                return {
                    "status": "checking",
                    "message": "Update check triggered (PM status unknown)",
                }
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Plugin manager not running or not accessible",
                "status": "unavailable",
                "hint": "Start dryade-pm in poll or serve mode to enable marketplace updates",
            },
        )
    except Exception as e:
        logger.warning("Failed to trigger PM update check: %s", e)
        raise HTTPException(
            status_code=503,
            detail={
                "error": f"Failed to reach plugin manager: {e}",
                "status": "unavailable",
            },
        )

@router.get("/update-status")
async def get_update_status() -> dict[str, Any]:
    """Get the status of the last allowlist update received from PM.

    Frontend polls this to check if plugins have been updated since the
    last check. Returns timestamp and version of the last update.

    Returns:
        {"last_updated": iso_string | null, "version": int | null, "has_update": bool}
    """
    # Try to get update info from the internal API module
    try:
        try:
            from core.ee.internal_api import get_last_allowlist_update
        except ImportError:
            from core.internal_api import get_last_allowlist_update  # type: ignore[no-redef]

        update_info = get_last_allowlist_update()
    except (ImportError, AttributeError):
        update_info = None

    if update_info is None:
        return {
            "last_updated": None,
            "version": None,
            "has_update": False,
        }

    return {
        "last_updated": update_info.get("iso"),
        "version": update_info.get("version"),
        "has_update": True,
    }

@router.get("", response_model=PluginListResponse)
async def list_plugins() -> PluginListResponse:
    """List all discovered and loaded plugins."""
    manager = get_plugin_manager()
    plugins_data = manager.list_plugins()

    plugins = []
    for p in plugins_data:
        # Load manifest to get has_ui and icon
        manifest = _load_plugin_manifest(p["name"])
        has_ui = manifest.get("has_ui", False) if manifest else False
        icon = manifest.get("icon") if manifest else None

        plugins.append(
            PluginInfo(
                name=p["name"],
                version=p["version"],
                description=p["description"],
                loaded=True,
                enabled=_get_effective_enabled(p["name"]),
                has_ui=has_ui,
                icon=icon,
            )
        )

    return PluginListResponse(plugins=plugins, count=len(plugins))

@router.post("/{name}/toggle", response_model=PluginDetailResponse)
async def toggle_plugin(name: str, request: PluginToggleRequest) -> PluginDetailResponse:
    """Enable/disable a plugin at runtime (best-effort).

    Notes:
    - For pipeline extensions, this flips ExtensionRegistry enabled flags.
    - For other plugins, this records an in-memory override only.
    - Router mounting/unmounting is not supported at runtime; restart required for that.
    """
    manager = get_plugin_manager()
    plugin = manager.get_plugin(name)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")

    _set_effective_enabled(name, request.enabled)

    return PluginDetailResponse(
        name=plugin.name,
        version=plugin.version,
        description=plugin.description,
        loaded=True,
        registered=True,
        enabled=_get_effective_enabled(name),
    )

@router.get("/{name}/config", response_model=PluginConfigResponse)
async def get_plugin_config(name: str) -> PluginConfigResponse:
    """Get stored plugin configuration (best-effort, in-memory)."""
    manager = get_plugin_manager()
    plugin = manager.get_plugin(name)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")

    return PluginConfigResponse(
        name=name,
        config=manager.get_plugin_config(name),
        config_schema=_load_plugin_settings_schema(name),
        note="Config is not persisted; restart will reset it.",
    )

@router.patch("/{name}/config", response_model=PluginConfigResponse)
async def patch_plugin_config(name: str, patch: dict[str, Any] = Body(...)) -> PluginConfigResponse:
    """Patch stored plugin configuration (shallow merge)."""
    manager = get_plugin_manager()
    plugin = manager.get_plugin(name)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")

    config = manager.patch_plugin_config(name, patch)
    return PluginConfigResponse(
        name=name,
        config=config,
        config_schema=_load_plugin_settings_schema(name),
        note="Config is not persisted; restart will reset it.",
    )

@router.post("/install", status_code=status.HTTP_202_ACCEPTED)
async def install_plugin(
    file: UploadFile | None = File(default=None),
    request: PluginInstallRequest | None = None,
) -> dict[str, Any]:
    """Install a directory plugin into the configured user plugins directory.

    Supports:
    - Uploading a .zip/.tar/.tar.gz/.tgz archive
    - Referencing a local filesystem path (archive or directory)

    Security:
    - Safe extraction prevents path traversal outside the target directory.
    - Only installs into the user plugins directory (never pip installs).
    """
    settings = get_settings()
    if not (settings.enable_directory_plugins and settings.user_plugins_dir):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Directory plugins not enabled. "
                "Set DRYADE_ENABLE_DIRECTORY_PLUGINS=true and DRYADE_USER_PLUGINS_DIR."
            ),
        )

    user_dir = Path(settings.user_plugins_dir)
    user_dir.mkdir(parents=True, exist_ok=True)

    def _install_from_dir(src_dir: Path) -> dict[str, Any]:
        if not src_dir.is_dir():
            raise HTTPException(status_code=400, detail="Path is not a directory")
        dest_dir = user_dir / src_dir.name
        if dest_dir.exists():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Plugin directory already exists: {dest_dir.name}",
            )
        shutil.copytree(src_dir, dest_dir)
        return {
            "message": "Plugin directory copied (restart required to load).",
            "plugin_dir": str(dest_dir),
            "has_init": (dest_dir / "__init__.py").exists(),
            "note": "This installs directory plugins only (no pip installs).",
        }

    def _install_from_archive(archive_path: Path) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="dryade-plugin-install-") as tmpdir:
            extract_root = Path(tmpdir) / "extract"
            extract_root.mkdir(parents=True, exist_ok=True)

            lowered = archive_path.name.lower()
            if lowered.endswith(".zip"):
                with zipfile.ZipFile(archive_path, "r") as zf:
                    _safe_extract_zip(zf, extract_root)
            elif lowered.endswith((".tar", ".tar.gz", ".tgz")):
                mode = "r:gz" if lowered.endswith((".tar.gz", ".tgz")) else "r"
                with tarfile.open(archive_path, mode) as tf:
                    _safe_extract_tar(tf, extract_root)
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Unsupported archive type (expected .zip, .tar, .tar.gz, .tgz)",
                )

            candidates = [p for p in extract_root.iterdir() if p.is_dir()]
            if len(candidates) == 1:
                src_dir = candidates[0]
                dest_dir = user_dir / src_dir.name
                if dest_dir.exists():
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"Plugin directory already exists: {dest_dir.name}",
                    )
                shutil.move(str(src_dir), str(dest_dir))
                plugin_dir = dest_dir
            else:
                # If the archive doesn't have a single top-level directory, nest it under a derived name.
                derived = archive_path.stem.replace(".tar", "")
                dest_dir = user_dir / derived
                if dest_dir.exists():
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"Plugin directory already exists: {dest_dir.name}",
                    )
                dest_dir.mkdir(parents=True, exist_ok=False)
                for item in extract_root.iterdir():
                    shutil.move(str(item), str(dest_dir / item.name))
                plugin_dir = dest_dir

            return {
                "message": "Plugin installed (restart required to load).",
                "plugin_dir": str(plugin_dir),
                "has_init": (plugin_dir / "__init__.py").exists(),
                "note": "This installs directory plugins only (no pip installs).",
            }

    if file is not None:
        filename = file.filename or "upload"
        with tempfile.TemporaryDirectory(prefix="dryade-plugin-upload-") as tmpdir:
            archive_path = Path(tmpdir) / filename
            with archive_path.open("wb") as f:
                shutil.copyfileobj(file.file, f)
            return _install_from_archive(archive_path)

    if request is None:
        raise HTTPException(
            status_code=422, detail="Provide an upload file or JSON body with 'path'"
        )

    src = Path(os.path.expanduser(request.path))
    if not src.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {request.path}")

    if src.is_dir():
        return _install_from_dir(src)

    return _install_from_archive(src)

# =============================================================================
# Slot Registration Endpoints
# =============================================================================

@router.get("/slots", response_model=dict[str, list[SlotRegistration]])
async def get_all_slots() -> dict[str, list[SlotRegistration]]:
    """Get all slot registrations.

    Returns a dict mapping slot names to lists of registrations.
    Only includes slots that have at least one registration.
    """
    return slot_registry.get_all_slots()

@router.get("/slots/{slot_name}", response_model=list[SlotRegistration])
async def get_slot_registrations(slot_name: str) -> list[SlotRegistration]:
    """Get registrations for a specific slot.

    Args:
        slot_name: Name of the slot (e.g., 'workflow-sidebar')

    Returns:
        List of registrations sorted by priority

    Raises:
        HTTPException: If slot_name is not a valid slot
    """
    try:
        slot = SlotName(slot_name)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid slot name: {slot_name}. Valid slots: {[s.value for s in SlotName]}",
        )
    return slot_registry.get_slot_registrations(slot)

@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def uninstall_plugin(name: str) -> Response:
    """Uninstall a directory plugin by deleting it from the user plugins directory."""
    if name in {".", ".."} or "/" in name or "\\" in name:
        raise HTTPException(status_code=400, detail="Invalid plugin name")

    settings = get_settings()
    if not (settings.enable_directory_plugins and settings.user_plugins_dir):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Directory plugins not enabled. "
                "Set DRYADE_ENABLE_DIRECTORY_PLUGINS=true and DRYADE_USER_PLUGINS_DIR."
            ),
        )

    user_dir = Path(settings.user_plugins_dir).resolve()
    plugin_dir = (user_dir / name).resolve()
    if not _is_relative_to(plugin_dir, user_dir):
        raise HTTPException(status_code=400, detail="Invalid plugin path")
    if not plugin_dir.exists():
        raise HTTPException(status_code=404, detail=f"Directory plugin '{name}' not found")
    if not plugin_dir.is_dir():
        raise HTTPException(status_code=400, detail=f"'{name}' is not a directory plugin")

    shutil.rmtree(plugin_dir)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.get("/{name}", response_model=PluginDetailResponse)
async def get_plugin(name: str) -> PluginDetailResponse:
    """Get details for a specific plugin."""
    manager = get_plugin_manager()
    plugin = manager.get_plugin(name)

    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")

    # Load manifest to get api_paths
    manifest = _load_plugin_manifest(name)
    api_paths = manifest.get("api_paths") if manifest else None

    return PluginDetailResponse(
        name=plugin.name,
        version=plugin.version,
        description=plugin.description,
        loaded=True,
        registered=True,
        enabled=_get_effective_enabled(name),
        api_paths=api_paths,
    )

@router.get("/stats/summary", response_model=PluginStatsResponse)
async def get_plugin_stats() -> dict[str, Any]:
    """Get plugin system statistics.

    Categories are derived dynamically from plugin manifests:
    - with_ui: Plugins with UI components
    - with_api: Plugins exposing API endpoints
    """
    manager = get_plugin_manager()
    plugins = manager.list_plugins()

    # Build categories dynamically from manifest metadata
    categories: dict[str, list[str]] = {
        "with_ui": [],
        "with_api": [],
    }

    for p in plugins:
        manifest = _load_plugin_manifest(p["name"])
        if manifest:
            if manifest.get("has_ui", False):
                categories["with_ui"].append(p["name"])

            if manifest.get("api_paths"):
                categories["with_api"].append(p["name"])

    category_counts: dict[str, Any] = {}
    for cat, plugin_list in categories.items():
        category_counts[cat] = {
            "count": len(plugin_list),
            "plugins": sorted(plugin_list),
        }

    return {
        "total_loaded": len(plugins),
        "categories": category_counts,
        "plugins": plugins,
    }

_TIER_DIRS = ("starter", "team", "enterprise")

def _find_in_user_plugins(user_dir: Path, plugin_name: str, filename: str) -> Path | None:
    """Locate a file inside a plugin's directory, searching tiered then flat layouts.

    Args:
        user_dir: Root user-plugins directory (e.g. ``plugins/``).
        plugin_name: Plugin directory name (e.g. ``audio``).
        filename: File to locate inside the plugin dir (e.g. ``dryade.json``).

    Returns:
        Resolved Path if found, else None.
    """
    # Tiered first: user_dir/{starter,team,enterprise}/plugin_name/filename
    # (avoids stale flat dirs like packaging artifacts shadowing real plugin dirs)
    for tier in _TIER_DIRS:
        tiered = user_dir / tier / plugin_name / filename
        if tiered.exists():
            return tiered
    # Flat fallback: user_dir/plugin_name/filename
    flat = user_dir / plugin_name / filename
    if flat.exists():
        return flat
    return None

def _load_plugin_manifest(plugin_name: str) -> dict[str, Any] | None:
    """Load and parse a plugin's dryade.json manifest.

    Searches plugins_dir (flat then tiered), then user plugins dir (flat and tiered).

    Args:
        plugin_name: Name of the plugin

    Returns:
        Parsed manifest dictionary, or None if not found
    """
    settings = get_settings()
    plugins_dir = Path(settings.plugins_dir)

    # Search plugins_dir (flat then tiered)
    manifest_path = _find_in_user_plugins(plugins_dir, plugin_name, "dryade.json")

    if manifest_path is None:
        # Check user plugins directory if configured, skip if same as plugins_dir
        if settings.enable_directory_plugins and settings.user_plugins_dir:
            user_dir = Path(settings.user_plugins_dir)
            if user_dir.resolve() != plugins_dir.resolve():
                manifest_path = _find_in_user_plugins(user_dir, plugin_name, "dryade.json")
        if manifest_path is None:
            return None

    try:
        content = manifest_path.read_text(encoding="utf-8")
        return json.loads(content)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to load manifest for plugin '{plugin_name}': {e}")
        return None

def _get_plugin_dir(plugin_name: str) -> Path | None:
    """Get the directory path for a plugin.

    Searches plugins_dir (flat then tiered), then user plugins dir (flat + tiered).

    Args:
        plugin_name: Name of the plugin

    Returns:
        Plugin directory path, or None if not found
    """
    settings = get_settings()
    plugins_dir = Path(settings.plugins_dir)

    # Tiered layout first: plugins_dir/{starter,team,enterprise}/plugin_name
    # (avoids stale flat dirs like packaging artifacts shadowing real plugin dirs)
    for tier in _TIER_DIRS:
        tiered = plugins_dir / tier / plugin_name
        if tiered.is_dir():
            return tiered

    # Flat layout fallback: plugins_dir/plugin_name
    plugin_path = plugins_dir / plugin_name
    if plugin_path.is_dir():
        return plugin_path

    # Check user plugins directory if configured (tiered + flat), skip if same as plugins_dir
    if settings.enable_directory_plugins and settings.user_plugins_dir:
        user_dir = Path(settings.user_plugins_dir)
        if user_dir.resolve() != plugins_dir.resolve():
            # Tiered layout
            for tier in _TIER_DIRS:
                tiered = user_dir / tier / plugin_name
                if tiered.is_dir():
                    return tiered
            # Flat layout
            flat = user_dir / plugin_name
            if flat.is_dir():
                return flat

    return None

@router.get("/{name}/slots", response_model=dict[str, list[SlotRegistration]])
async def get_plugin_slots(name: str) -> dict[str, list[SlotRegistration]]:
    """Get all slot registrations for a specific plugin.

    Args:
        name: Name of the plugin

    Returns:
        Dict mapping slot names to this plugin's registrations
    """
    return slot_registry.get_plugin_slots(name)

@router.get("/{name}/ui/bundle/decrypted")
async def get_decrypted_ui_bundle(name: str) -> Response:
    """Get decrypted UI bundle for Tier 2+ plugins.

    For encrypted plugins (.dryadepkg), this endpoint:
    1. Validates the user's license/subscription
    2. Decrypts the UI bundle on the backend
    3. Returns plain JavaScript

    The decryption key never leaves the server.

    Args:
        name: Name of the plugin

    Returns:
        Plain JavaScript bundle

    Raises:
        HTTPException: If plugin not found, not encrypted, or license invalid
    """
    _settings = get_settings()
    plugin_dir = _get_plugin_dir(name)

    if plugin_dir is None:
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")

    # Check for .dryadepkg (encrypted package)
    pkg_path = plugin_dir / f"{name}.dryadepkg"
    if not pkg_path.exists():
        # Not encrypted - redirect to regular bundle endpoint
        raise HTTPException(
            status_code=400,
            detail="Plugin is not encrypted. Use /ui/bundle endpoint instead.",
        )

    # Enterprise decryption requires the EE module
    try:
        from core.ee.plugin_decrypt import decrypt_bundle  # type: ignore[import-not-found]
    except ImportError:
        raise HTTPException(
            status_code=404,
            detail="This endpoint is not available in the community edition.",
        )

    return await decrypt_bundle(name, pkg_path, _settings)

@router.get("/{name}/ui/manifest")
async def get_plugin_ui_manifest(name: str) -> dict[str, Any]:
    """Get full plugin manifest for UI loading and signature verification.

    Returns the complete plugin manifest including signature so the frontend
    can verify authenticity before loading the UI bundle.

    Args:
        name: Plugin name

    Returns:
        Full manifest dict including signature for verification

    Raises:
        404: Plugin not found or has no UI
    """
    # Verify plugin exists
    manager = get_plugin_manager()
    plugin = manager.get_plugin(name)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")

    # Load manifest
    manifest = _load_plugin_manifest(name)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"Manifest not found for plugin '{name}'")

    # Check has_ui flag
    if not manifest.get("has_ui", False):
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' does not have UI components")

    # Verify ui field exists
    if manifest.get("ui") is None:
        raise HTTPException(
            status_code=404, detail=f"Plugin '{name}' has has_ui=true but missing ui field"
        )

    # Check if plugin is encrypted (.dryadepkg exists)
    plugin_dir = _get_plugin_dir(name)
    is_encrypted = False
    if plugin_dir:
        pkg_path = plugin_dir / f"{name}.dryadepkg"
        is_encrypted = pkg_path.exists()

    # Add is_encrypted to manifest for frontend to determine bundle endpoint
    manifest["is_encrypted"] = is_encrypted

    # Return full manifest for signature verification
    return manifest

@router.get("/{name}/ui/bundle")
async def get_plugin_ui_bundle(name: str) -> Response:
    """Serve plugin UI bundle with integrity verification.

    Reads the plugin's UI bundle file and verifies its SHA-256 hash against
    the manifest's ui_bundle_hash. Uses fail-closed pattern: any verification
    error returns 500, not the bundle.

    Args:
        name: Plugin name

    Returns:
        JavaScript bundle content with Content-Type: application/javascript

    Raises:
        404: Plugin not found or has no UI
        500: Bundle file missing, unreadable, or hash mismatch (security alert)
    """
    # Verify plugin exists
    manager = get_plugin_manager()
    plugin = manager.get_plugin(name)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")

    # Load manifest
    manifest = _load_plugin_manifest(name)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"Manifest not found for plugin '{name}'")

    # Check has_ui flag
    if not manifest.get("has_ui", False):
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' does not have UI components")

    ui_manifest = manifest.get("ui")
    if ui_manifest is None:
        raise HTTPException(
            status_code=404, detail=f"Plugin '{name}' has has_ui=true but missing ui field"
        )

    # Get entry path
    entry_path = ui_manifest.get("entry")
    if not entry_path or not isinstance(entry_path, str):
        raise HTTPException(
            status_code=500,
            detail=f"Plugin '{name}' has invalid or missing ui.entry field",
        )

    # Get expected hash
    expected_hash = manifest.get("ui_bundle_hash")
    if not expected_hash or not isinstance(expected_hash, str):
        logger.error(f"SECURITY: Plugin '{name}' has no ui_bundle_hash for integrity verification")
        raise HTTPException(
            status_code=500,
            detail="Bundle integrity cannot be verified (missing hash)",
        )

    # Locate plugin directory
    plugin_dir = _get_plugin_dir(name)
    if plugin_dir is None:
        raise HTTPException(status_code=404, detail=f"Plugin directory not found for '{name}'")

    # Construct bundle path and validate it's within plugin dir
    bundle_path = (plugin_dir / entry_path).resolve()
    if not _is_relative_to(bundle_path, plugin_dir.resolve()):
        logger.error(
            f"SECURITY: Plugin '{name}' bundle path escapes plugin directory: {entry_path}"
        )
        raise HTTPException(
            status_code=500,
            detail="Invalid bundle path (security violation)",
        )

    # Read bundle file
    if not bundle_path.exists():
        logger.error(f"Plugin '{name}' bundle file not found: {bundle_path}")
        raise HTTPException(
            status_code=500,
            detail=f"Bundle file not found: {entry_path}",
        )

    try:
        bundle_content = bundle_path.read_bytes()
    except OSError as e:
        logger.error(f"Failed to read bundle for plugin '{name}': {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to read bundle file",
        ) from e

    # Compute SHA-256 hash (hex format, no prefix)
    computed_hash = hashlib.sha256(bundle_content).hexdigest()

    # Normalize expected hash (strip sha256- prefix if present)
    normalized_expected = expected_hash.replace("sha256-", "")

    # Verify hash
    if computed_hash != normalized_expected:
        logger.error(f"SECURITY ALERT: Plugin '{name}' bundle integrity verification failed")
        raise HTTPException(
            status_code=500,
            detail="Bundle integrity verification failed",
        )

    logger.debug(f"Serving verified UI bundle for plugin '{name}' ({len(bundle_content)} bytes)")

    return Response(
        content=bundle_content,
        media_type="application/javascript",
        headers={
            "X-Content-Type-Options": "nosniff",
            "X-Plugin-Name": name,
            "X-Bundle-Hash": computed_hash,
        },
    )

@router.get("/{name}/ui/styles")
async def get_plugin_ui_styles(name: str) -> Response:
    """Serve plugin UI stylesheet (optional).

    Reads the plugin's UI styles file if present. Styles are optional so a 404 is
    returned if no styles file exists rather than an error.

    Args:
        name: Plugin name

    Returns:
        CSS content with Content-Type: text/css

    Raises:
        404: Plugin not found, has no UI, or has no styles file
    """
    # Verify plugin exists
    manager = get_plugin_manager()
    plugin = manager.get_plugin(name)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")

    # Load manifest
    manifest = _load_plugin_manifest(name)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"Manifest not found for plugin '{name}'")

    # Check has_ui flag
    if not manifest.get("has_ui", False):
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' does not have UI components")

    ui_manifest = manifest.get("ui")
    if ui_manifest is None:
        raise HTTPException(
            status_code=404, detail=f"Plugin '{name}' has has_ui=true but missing ui field"
        )

    # Get styles path from manifest (optional field)
    styles_path = ui_manifest.get("styles")
    if not styles_path:
        # Styles are optional - try common default path
        styles_path = "ui/dist/styles.css"

    # Locate plugin directory
    plugin_dir = _get_plugin_dir(name)
    if plugin_dir is None:
        raise HTTPException(status_code=404, detail=f"Plugin directory not found for '{name}'")

    # Construct styles path and validate it's within plugin dir
    full_styles_path = (plugin_dir / styles_path).resolve()
    if not _is_relative_to(full_styles_path, plugin_dir.resolve()):
        logger.error(
            f"SECURITY: Plugin '{name}' styles path escapes plugin directory: {styles_path}"
        )
        raise HTTPException(
            status_code=500,
            detail="Invalid styles path (security violation)",
        )

    # Check if styles file exists (styles are optional)
    if not full_styles_path.exists():
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' has no styles file")

    try:
        styles_content = full_styles_path.read_bytes()
    except OSError as e:
        logger.error(f"Failed to read styles for plugin '{name}': {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to read styles file",
        ) from e

    logger.debug(f"Serving UI styles for plugin '{name}' ({len(styles_content)} bytes)")

    return Response(
        content=styles_content,
        media_type="text/css",
        headers={
            "X-Content-Type-Options": "nosniff",
            "X-Plugin-Name": name,
        },
    )

# =============================================================================
# PM Plugin Signing HTTP API Proxy (Phase 164.5)
#
# Architecture note: "Core does not call PM via gRPC or any RPC."
# These routes are the ONE EXCEPTION for the UI signing flow: they proxy
# user-initiated plugin management requests to PM's HTTP API on port 9472.
# The allowlist itself still flows PM->core via file write (normal path).
# These proxies ONLY work when the PM serve daemon is running.
# =============================================================================

class SignPluginRequest(BaseModel):
    """Request to sign a local plugin directory via PM."""

    plugin_dir: str

_PM_API_PORT = int(os.environ.get("DRYADE_PM_API_PORT", "9472"))
_PM_API_URL = f"http://127.0.0.1:{_PM_API_PORT}"

@router.post("/sign")
async def sign_plugin(request: SignPluginRequest) -> dict[str, Any]:
    """Proxy plugin signing request to PM daemon.

    Asks PM to sign a local plugin directory (validates manifest, computes
    hash, registers in local-plugins.json, triggers merged allowlist push).

    Returns:
        200 {"success": true, "plugin_name": "...", "hash": "sha256:..."} on success
        503 if PM daemon is not running
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(
                f"{_PM_API_URL}/plugins/sign",
                json={"plugin_dir": request.plugin_dir},
            )
            return resp.json()
        except httpx.ConnectError:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "Plugin Manager daemon is not running",
                    "hint": "Start it with: dryade-pm serve",
                },
            )
        except Exception as e:
            logger.warning("Failed to proxy plugin sign request: %s", e)
            raise HTTPException(
                status_code=503,
                detail={"error": f"Failed to reach Plugin Manager: {e}"},
            )

@router.get("/local")
async def list_local_plugins() -> dict[str, Any]:
    """List locally-signed custom plugins from PM registry.

    Returns:
        200 {"plugins": [...]} with list of locally registered custom plugins
        503 if PM daemon is not running
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"{_PM_API_URL}/plugins/local")
            return resp.json()
        except httpx.ConnectError:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "Plugin Manager daemon is not running",
                    "hint": "Start it with: dryade-pm serve",
                },
            )
        except Exception as e:
            logger.warning("Failed to proxy list local plugins request: %s", e)
            raise HTTPException(
                status_code=503,
                detail={"error": f"Failed to reach Plugin Manager: {e}"},
            )

@router.get("/bridge/session-key")
async def get_bridge_session_key(
    request: Request,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Return key material for the workbench to derive its bridge session key.

    The workbench calls this endpoint once per session to obtain the scoped
    secret it needs to replicate the server-side HMAC-SHA256 key derivation.
    The returned secret is scoped per-user and does NOT expose the raw bridge key.

    The workbench then derives the session key as:
        HMAC-SHA256(scoped_secret, "{sub}:{exp}")

    This matches the server-side derivation in EncryptedPluginBridge._extract_session_key().

    Requires: Bearer token (JWT auth).
    Returns: {secret: base64str, sub: str, exp: int}
    """
    manager = get_plugin_manager()
    bridge = manager.get_bridge()

    jwt_sub = str(user.get("sub", user.get("id", "")))
    jwt_exp = int(user.get("exp", 0))

    if not jwt_sub:
        raise HTTPException(status_code=401, detail="JWT missing subject claim")

    return bridge.get_session_key_material(jwt_sub, jwt_exp)

@router.delete("/local/{plugin_name}")
async def delete_local_plugin(plugin_name: str) -> dict[str, Any]:
    """Remove a locally-signed custom plugin via PM.

    Removes the plugin from PM's local registry and triggers a merged
    allowlist re-push so core no longer loads it.

    Returns:
        200 {"success": true} on success
        404 {"success": false, "error": "Plugin not found"} if not registered
        503 if PM daemon is not running
    """
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.delete(f"{_PM_API_URL}/plugins/local/{plugin_name}")
            return resp.json()
        except httpx.ConnectError:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "Plugin Manager daemon is not running",
                    "hint": "Start it with: dryade-pm serve",
                },
            )
        except Exception as e:
            logger.warning("Failed to proxy delete local plugin request: %s", e)
            raise HTTPException(
                status_code=503,
                detail={"error": f"Failed to reach Plugin Manager: {e}"},
            )
