"""Skills Management API Endpoints.

Provides REST endpoints for discovering, managing, and testing markdown skills.
Skills are loaded from the AgentSkills format (SKILL.md files).
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Body, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core.config import get_settings
from core.skills.adapter import MarkdownSkillAdapter
from core.skills.loader import MarkdownSkillLoader
from core.skills.models import Skill, SkillGateResult, SkillMetadata

logger = logging.getLogger(__name__)

# ============================================================================
# Request/Response Models
# ============================================================================

class SkillSummary(BaseModel):
    """Summary of a skill for listing."""

    name: str
    description: str
    emoji: str | None = None
    eligible: bool
    eligibility_reason: str | None = None
    plugin_id: str | None = None
    source: str  # "bundled", "managed", "workspace"

class SkillListResponse(BaseModel):
    """Response for listing all skills."""

    skills: list[SkillSummary]
    total: int
    eligible_count: int

class SkillDetailResponse(BaseModel):
    """Detailed skill information."""

    name: str
    description: str
    instructions: str
    metadata: SkillMetadata
    skill_dir: str
    plugin_id: str | None = None
    eligibility: SkillGateResult
    source: str

class SkillCreateRequest(BaseModel):
    """Request to create a new user skill."""

    name: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
    description: str = Field(..., min_length=1, max_length=500)
    instructions: str = Field(..., min_length=1)
    emoji: str | None = None
    os: list[str] = Field(default_factory=list)
    requires_bins: list[str] = Field(default_factory=list)
    requires_env: list[str] = Field(default_factory=list)
    requires_config: list[str] = Field(default_factory=list)

class SkillUpdateRequest(BaseModel):
    """Request to update a user skill."""

    description: str | None = None
    instructions: str | None = None
    emoji: str | None = None
    os: list[str] | None = None
    requires_bins: list[str] | None = None
    requires_env: list[str] | None = None
    requires_config: list[str] | None = None

class SkillPreviewResponse(BaseModel):
    """Preview of formatted skill for system prompt."""

    skill_name: str
    formatted_prompt: str
    token_estimate: int
    guidance: str

class SkillTestResponse(BaseModel):
    """Test response showing skill with sample input."""

    skill_name: str
    sample_task: str
    system_prompt_preview: str
    token_estimate: int

class SkillCreateResponse(BaseModel):
    """Response after creating a skill."""

    name: str
    skill_dir: str
    message: str

router = APIRouter(prefix="/api/skills", tags=["skills"])

# ============================================================================
# Helper Functions
# ============================================================================

def _get_skills_search_paths() -> tuple[list[Path], dict[str, str]]:
    """Get skill search paths and their source labels.

    Returns:
        (search_paths, source_map) where source_map maps path to "bundled", "managed", "workspace"
    """
    settings = get_settings()
    paths: list[Path] = []
    source_map: dict[str, str] = {}

    # 1. Bundled skills (from plugins directory)
    bundled_path = Path(settings.plugins_dir) / "skills"
    if bundled_path.exists():
        paths.append(bundled_path)
        source_map[str(bundled_path)] = "bundled"

    # 2. Managed skills (~/.dryade/skills/)
    managed_path = Path.home() / ".dryade" / "skills"
    if managed_path.exists():
        paths.append(managed_path)
        source_map[str(managed_path)] = "managed"

    # 3. Workspace skills (current directory)
    workspace_path = Path.cwd() / "skills"
    if workspace_path.exists():
        paths.append(workspace_path)
        source_map[str(workspace_path)] = "workspace"

    return paths, source_map

def _get_user_skills_dir() -> Path:
    """Get the user skills directory (managed skills).

    Creates the directory if it doesn't exist.
    """
    managed_path = Path.home() / ".dryade" / "skills"
    managed_path.mkdir(parents=True, exist_ok=True)
    return managed_path

def _determine_skill_source(skill_dir: str, source_map: dict[str, str]) -> str:
    """Determine the source of a skill based on its directory."""
    skill_path = Path(skill_dir)
    for search_path, source in source_map.items():
        try:
            skill_path.relative_to(search_path)
            return source
        except ValueError:
            continue
    return "unknown"

def _is_user_skill(skill_dir: str) -> bool:
    """Check if a skill is a user-managed skill (can be modified/deleted)."""
    skill_path = Path(skill_dir)
    user_skills_dir = Path.home() / ".dryade" / "skills"
    try:
        skill_path.relative_to(user_skills_dir)
        return True
    except ValueError:
        return False

def _generate_skill_md(
    name: str,
    description: str,
    instructions: str,
    emoji: str | None = None,
    os: list[str] | None = None,
    requires_bins: list[str] | None = None,
    requires_env: list[str] | None = None,
    requires_config: list[str] | None = None,
) -> str:
    """Generate SKILL.md content from parameters."""
    # Build metadata section
    metadata: dict[str, Any] = {}
    dryade_meta: dict[str, Any] = {}

    if emoji:
        dryade_meta["emoji"] = emoji
    if os:
        dryade_meta["os"] = os

    requires: dict[str, Any] = {}
    if requires_bins:
        requires["bins"] = requires_bins
    if requires_env:
        requires["env"] = requires_env
    if requires_config:
        requires["config"] = requires_config
    if requires:
        dryade_meta["requires"] = requires

    if dryade_meta:
        metadata["dryade"] = dryade_meta

    # Build frontmatter
    frontmatter = {
        "name": name,
        "description": description,
    }
    if metadata:
        frontmatter["metadata"] = metadata

    # Generate YAML frontmatter
    yaml_content = yaml.dump(
        frontmatter, default_flow_style=False, allow_unicode=True, sort_keys=False
    )

    return f"---\n{yaml_content}---\n\n{instructions}\n"

# ============================================================================
# Endpoints
# ============================================================================

@router.get("", response_model=SkillListResponse)
async def list_skills(
    include_ineligible: bool = Query(False, description="Include skills that fail gating checks"),
) -> SkillListResponse:
    """List all discovered skills with eligibility status.

    Skills are loaded from:
    1. Bundled skills (shipped with plugins)
    2. Managed skills (~/.dryade/skills/)
    3. Workspace skills (./skills/)

    Later sources override earlier ones for same-named skills.
    """
    search_paths, source_map = _get_skills_search_paths()
    loader = MarkdownSkillLoader()

    # Discover all skills (including ineligible for listing)
    skills_by_name: dict[str, tuple[Skill, SkillGateResult, str]] = {}

    for search_path in search_paths:
        if not search_path.exists():
            continue

        source = source_map.get(str(search_path), "unknown")

        for item in search_path.iterdir():
            if item.is_dir() and (item / loader.SKILL_FILE).exists():
                try:
                    skill = loader.load_skill(item)
                    gate_result = loader.check_skill_eligibility(skill)

                    # Later paths override earlier
                    skills_by_name[skill.name] = (skill, gate_result, source)
                except Exception as e:
                    logger.warning(f"Failed to load skill from {item}: {e}")

    # Build response
    summaries = []
    eligible_count = 0

    for skill, gate_result, source in skills_by_name.values():
        if gate_result.eligible:
            eligible_count += 1
        elif not include_ineligible:
            continue

        summaries.append(
            SkillSummary(
                name=skill.name,
                description=skill.description,
                emoji=skill.metadata.emoji,
                eligible=gate_result.eligible,
                eligibility_reason=gate_result.reason,
                plugin_id=skill.plugin_id,
                source=source,
            )
        )

    # Sort by name
    summaries.sort(key=lambda s: s.name)

    return SkillListResponse(
        skills=summaries,
        total=len(summaries),
        eligible_count=eligible_count,
    )

@router.get("/{name}", response_model=SkillDetailResponse)
async def get_skill(name: str) -> SkillDetailResponse:
    """Get detailed information about a specific skill."""
    search_paths, source_map = _get_skills_search_paths()
    loader = MarkdownSkillLoader()

    # Find the skill (later paths override earlier)
    found_skill: Skill | None = None
    found_source: str = "unknown"

    for search_path in search_paths:
        if not search_path.exists():
            continue

        skill_dir = search_path / name
        if skill_dir.is_dir() and (skill_dir / loader.SKILL_FILE).exists():
            try:
                found_skill = loader.load_skill(skill_dir)
                found_source = source_map.get(str(search_path), "unknown")
            except Exception as e:
                logger.warning(f"Failed to load skill {name} from {skill_dir}: {e}")

    if not found_skill:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")

    gate_result = loader.check_skill_eligibility(found_skill)

    return SkillDetailResponse(
        name=found_skill.name,
        description=found_skill.description,
        instructions=found_skill.instructions,
        metadata=found_skill.metadata,
        skill_dir=found_skill.skill_dir,
        plugin_id=found_skill.plugin_id,
        eligibility=gate_result,
        source=found_source,
    )

@router.post("", response_model=SkillCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_skill(request: SkillCreateRequest) -> SkillCreateResponse:
    """Create a new user skill.

    Creates a SKILL.md file in the managed skills directory (~/.dryade/skills/).
    """
    user_skills_dir = _get_user_skills_dir()
    skill_dir = user_skills_dir / request.name

    # Check if skill already exists
    if skill_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Skill '{request.name}' already exists",
        )

    # Create skill directory and SKILL.md
    try:
        skill_dir.mkdir(parents=True, exist_ok=False)

        skill_md_content = _generate_skill_md(
            name=request.name,
            description=request.description,
            instructions=request.instructions,
            emoji=request.emoji,
            os=request.os,
            requires_bins=request.requires_bins,
            requires_env=request.requires_env,
            requires_config=request.requires_config,
        )

        skill_md_path = skill_dir / "SKILL.md"
        skill_md_path.write_text(skill_md_content, encoding="utf-8")

        logger.info(f"Created user skill: {request.name}")

        return SkillCreateResponse(
            name=request.name,
            skill_dir=str(skill_dir),
            message=f"Skill '{request.name}' created successfully",
        )

    except Exception as e:
        # Cleanup on failure
        if skill_dir.exists():
            shutil.rmtree(skill_dir)
        logger.error(f"Failed to create skill '{request.name}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create skill: {e}",
        ) from e

@router.put("/{name}", response_model=SkillDetailResponse)
async def update_skill(name: str, request: SkillUpdateRequest) -> SkillDetailResponse:
    """Update a user skill.

    Only user-managed skills (~/.dryade/skills/) can be updated.
    """
    user_skills_dir = _get_user_skills_dir()
    skill_dir = user_skills_dir / name

    if not skill_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User skill '{name}' not found (only managed skills can be updated)",
        )

    loader = MarkdownSkillLoader()
    skill_md_path = skill_dir / "SKILL.md"

    if not skill_md_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SKILL.md not found in skill directory",
        )

    # Load current skill
    try:
        current_skill = loader.load_skill(skill_dir)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load current skill: {e}",
        ) from e

    # Apply updates
    new_description = request.description or current_skill.description
    new_instructions = request.instructions or current_skill.instructions
    new_emoji = request.emoji if request.emoji is not None else current_skill.metadata.emoji
    new_os = request.os if request.os is not None else current_skill.metadata.os
    new_bins = (
        request.requires_bins
        if request.requires_bins is not None
        else current_skill.metadata.requires.bins
    )
    new_env = (
        request.requires_env
        if request.requires_env is not None
        else current_skill.metadata.requires.env
    )
    new_config = (
        request.requires_config
        if request.requires_config is not None
        else current_skill.metadata.requires.config
    )

    # Generate updated SKILL.md
    skill_md_content = _generate_skill_md(
        name=name,
        description=new_description,
        instructions=new_instructions,
        emoji=new_emoji,
        os=new_os,
        requires_bins=new_bins,
        requires_env=new_env,
        requires_config=new_config,
    )

    # Write updated file
    try:
        skill_md_path.write_text(skill_md_content, encoding="utf-8")
        logger.info(f"Updated user skill: {name}")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to write skill file: {e}",
        ) from e

    # Return updated skill details
    updated_skill = loader.load_skill(skill_dir)
    gate_result = loader.check_skill_eligibility(updated_skill)

    return SkillDetailResponse(
        name=updated_skill.name,
        description=updated_skill.description,
        instructions=updated_skill.instructions,
        metadata=updated_skill.metadata,
        skill_dir=updated_skill.skill_dir,
        plugin_id=updated_skill.plugin_id,
        eligibility=gate_result,
        source="managed",
    )

@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_skill(name: str) -> Response:
    """Delete a user skill.

    Only user-managed skills (~/.dryade/skills/) can be deleted.
    """
    if name in {".", ".."} or "/" in name or "\\" in name:
        raise HTTPException(status_code=400, detail="Invalid skill name")

    user_skills_dir = _get_user_skills_dir()
    skill_dir = user_skills_dir / name

    # Verify path doesn't escape user skills directory
    try:
        skill_dir.resolve().relative_to(user_skills_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid skill path")

    if not skill_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User skill '{name}' not found (only managed skills can be deleted)",
        )

    try:
        shutil.rmtree(skill_dir)
        logger.info(f"Deleted user skill: {name}")
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except Exception as e:
        logger.error(f"Failed to delete skill '{name}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete skill: {e}",
        ) from e

@router.post("/{name}/preview", response_model=SkillPreviewResponse)
async def preview_skill(name: str) -> SkillPreviewResponse:
    """Preview how a skill will be formatted for system prompt injection."""
    search_paths, _ = _get_skills_search_paths()
    loader = MarkdownSkillLoader()
    adapter = MarkdownSkillAdapter()

    # Find the skill
    found_skill: Skill | None = None
    for search_path in search_paths:
        skill_dir = search_path / name
        if skill_dir.exists() and (skill_dir / loader.SKILL_FILE).exists():
            try:
                found_skill = loader.load_skill(skill_dir)
            except Exception:
                pass

    if not found_skill:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")

    # Format for preview
    formatted = adapter.format_skills_for_prompt([found_skill])
    guidance = adapter.build_skill_guidance()
    token_estimate = adapter.estimate_token_overhead([found_skill])

    return SkillPreviewResponse(
        skill_name=name,
        formatted_prompt=formatted,
        token_estimate=token_estimate,
        guidance=guidance,
    )

@router.post("/{name}/test", response_model=SkillTestResponse)
async def test_skill(
    name: str,
    sample_task: str = Body(
        "Use this skill to help me.",
        description="Sample task to test the skill with",
        embed=True,
    ),
) -> SkillTestResponse:
    """Test a skill by showing how it would appear in a system prompt with a sample task."""
    search_paths, _ = _get_skills_search_paths()
    loader = MarkdownSkillLoader()
    adapter = MarkdownSkillAdapter()

    # Find the skill
    found_skill: Skill | None = None
    for search_path in search_paths:
        skill_dir = search_path / name
        if skill_dir.exists() and (skill_dir / loader.SKILL_FILE).exists():
            try:
                found_skill = loader.load_skill(skill_dir)
            except Exception:
                pass

    if not found_skill:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")

    # Check eligibility
    gate_result = loader.check_skill_eligibility(found_skill)
    if not gate_result.eligible:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Skill '{name}' is not eligible: {gate_result.reason}",
        )

    # Build system prompt preview
    formatted = adapter.format_skills_for_prompt([found_skill])
    guidance = adapter.build_skill_guidance()
    token_estimate = adapter.estimate_token_overhead([found_skill])

    system_prompt_preview = f"""# System Prompt Preview

{formatted}
{guidance}

---
## User Task:
{sample_task}
"""

    return SkillTestResponse(
        skill_name=name,
        sample_task=sample_task,
        system_prompt_preview=system_prompt_preview,
        token_estimate=token_estimate,
    )

@router.get("/eligible/list", response_model=SkillListResponse)
async def list_eligible_skills() -> SkillListResponse:
    """List only skills that pass all gating checks.

    Convenience endpoint for getting skills ready to inject.
    """
    return await list_skills(include_ineligible=False)
