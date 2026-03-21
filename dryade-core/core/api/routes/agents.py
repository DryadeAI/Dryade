"""Agent Routes - Agent discovery and invocation via adapter registry.

All agents are accessed through the universal adapter interface.
Includes setup wizard endpoint for first-run configuration guidance
and ZIP upload for remote agent distribution.
Target: ~200 LOC
"""

import logging
import re
import shutil
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel, Field

from core.adapters import AgentCard
from core.adapters import get_agent as adapter_get_agent
from core.adapters import list_agents as adapter_list_agents
from core.api.models.openapi import response_with_errors
from core.mcp.setup_wizard import check_agent_setup, get_setup_instructions

try:
    from core.extensions import get_cost_tracker
except ImportError:
    get_cost_tracker = None

logger = logging.getLogger(__name__)

router = APIRouter()

# Response Models
class AgentInfo(BaseModel):
    """Information about a registered agent."""

    name: str = Field(..., description="Unique agent identifier")
    description: str = Field(..., description="Human-readable agent description")
    tools: list[str] = Field(..., description="List of tool names available to this agent")
    framework: str = Field(
        "crewai", description="Agent framework (crewai, langchain, adk, a2a, mcp, custom)"
    )
    version: str = Field("1.0.0", description="Agent version")
    role: str | None = Field(None, description="Agent's role (what it is)")
    goal: str | None = Field(None, description="Agent's goal (what it does)")

class ToolInfo(BaseModel):
    """Information about a tool available to an agent."""

    name: str = Field(..., description="Tool identifier")
    description: str = Field(..., description="What the tool does")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Tool parameter schema")

class InvokeRequest(BaseModel):
    """Request to execute a task with an agent."""

    task: str = Field(..., description="Task description for the agent to execute", min_length=1)
    tool: str | None = Field(None, description="Explicit MCP tool name to invoke")
    arguments: dict[str, Any] | None = Field(None, description="Tool arguments for MCP agents")
    context: dict[str, Any] | None = Field(
        None, description="Additional context for task execution"
    )

class InvokeResponse(BaseModel):
    """Response from agent task execution."""

    result: str = Field(..., description="Agent's output from task execution")
    agent: str = Field(..., description="Name of the agent that executed the task")
    tool_calls: list[dict[str, Any]] = Field(
        default_factory=list, description="Tools invoked during execution"
    )
    execution_time_ms: float = Field(..., description="Execution time in milliseconds", ge=0)
    tokens_used: int = Field(0, description="Total tokens used during execution")
    cost: float = Field(0.0, description="Estimated cost in USD")

class UploadResponse(BaseModel):
    """Response from agent ZIP upload."""

    name: str = Field(..., description="Registered agent name")
    framework: str = Field(..., description="Detected framework")
    status: str = Field(..., description="Registration status")

def _card_to_agent_info(card: AgentCard) -> AgentInfo:
    """Convert AgentCard to AgentInfo response model."""
    tools = [cap.name for cap in card.capabilities] if card.capabilities else []
    # CrewAI agents store role in name, goal in description
    # Other frameworks may store in metadata
    role = card.metadata.get("role") or card.name
    goal = card.metadata.get("goal") or card.description
    return AgentInfo(
        name=card.name,
        description=card.description,
        tools=tools,
        framework=card.framework.value if card.framework else "crewai",
        version=card.version,
        role=role,
        goal=goal,
    )

@router.get(
    "",
    response_model=list[AgentInfo],
    summary="List all agents",
)
async def list_agents() -> list[AgentInfo]:
    """List all registered agents with their capabilities.

    Returns agents from all loaded domains including their tools and framework info.
    """
    cards = adapter_list_agents()
    agents = [_card_to_agent_info(card) for card in cards]
    return agents

# ---------------------------------------------------------------------------
# Agent ZIP Upload
# ---------------------------------------------------------------------------

# Default agents directory (from config, resolves correctly in Docker and host)
from core.config import get_settings as _get_settings

_AGENTS_DIR = Path(_get_settings().agents_dir)

# Safe filename pattern: alphanumeric, hyphens, underscores only
_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")

def _safe_extract_zip(zip_path: Path, dest: Path) -> None:
    """Securely extract a ZIP file, protecting against path traversal.

    Validates that all extracted paths stay within the destination directory.

    Args:
        zip_path: Path to the ZIP file.
        dest: Destination directory.

    Raises:
        HTTPException: If ZIP contains path traversal attempts or is invalid.
    """
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for info in zf.infolist():
                # Normalize and check for path traversal
                member_path = Path(dest / info.filename).resolve()
                if not str(member_path).startswith(str(dest.resolve())):
                    raise HTTPException(
                        status_code=400,
                        detail=f"ZIP contains path traversal: {info.filename}",
                    )
                # Skip directories (they get created by extract)
                if info.is_dir():
                    continue
                # Reject excessively large files (50MB per file)
                if info.file_size > 50 * 1024 * 1024:
                    raise HTTPException(
                        status_code=400,
                        detail=f"File too large in ZIP: {info.filename} ({info.file_size} bytes)",
                    )
            zf.extractall(dest)
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Invalid ZIP file")

@router.post(
    "/upload",
    response_model=UploadResponse,
    responses=response_with_errors(400, 409, 500),
    summary="Upload agent as ZIP",
)
async def upload_agent(file: UploadFile) -> UploadResponse:
    """Upload a ZIP file containing an agent project.

    The ZIP is securely extracted, validated (must contain at least one .py file),
    and placed in the agents/ directory. Auto-discovery then detects the framework
    and registers the agent.

    The agent name is derived from the ZIP filename (sanitized).
    """
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="File must be a .zip archive")

    # Derive agent name from ZIP filename
    raw_name = file.filename.rsplit(".zip", 1)[0]
    # Sanitize: replace spaces/dots with underscores, strip non-alnum
    sanitized = re.sub(r"[^a-zA-Z0-9_-]", "_", raw_name).strip("_")
    if not sanitized or not _SAFE_NAME_RE.match(sanitized):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid agent name derived from filename: '{raw_name}'",
        )

    agent_name = sanitized.lower()
    target_dir = _AGENTS_DIR / agent_name

    if target_dir.exists():
        raise HTTPException(
            status_code=409,
            detail=f"Agent directory '{agent_name}' already exists",
        )

    tmp_dir = None
    try:
        # Save uploaded file to temp location
        tmp_dir = Path(tempfile.mkdtemp(prefix="dryade_agent_"))
        zip_path = tmp_dir / "upload.zip"

        content = await file.read()
        zip_path.write_bytes(content)

        # Extract to temp staging directory
        staging_dir = tmp_dir / "staging"
        staging_dir.mkdir()
        _safe_extract_zip(zip_path, staging_dir)

        # If ZIP contains a single top-level directory, use its contents
        entries = list(staging_dir.iterdir())
        if len(entries) == 1 and entries[0].is_dir():
            staging_dir = entries[0]

        # Validate: must have at least one .py file
        py_files = list(staging_dir.glob("*.py"))
        if not py_files:
            raise HTTPException(
                status_code=400,
                detail="ZIP must contain at least one .py file at the root level",
            )

        # Move to agents directory
        shutil.copytree(staging_dir, target_dir)

        # Auto-discover and register
        from core.adapters.auto_discovery import AgentAutoDiscovery

        discovery = AgentAutoDiscovery(_AGENTS_DIR)
        framework = discovery.detect_framework(target_dir)

        registered = discovery.discover_and_register()

        if agent_name in registered:
            return UploadResponse(
                name=agent_name,
                framework=framework,
                status="registered",
            )
        else:
            return UploadResponse(
                name=agent_name,
                framework=framework,
                status="extracted_but_not_registered",
            )

    except HTTPException:
        # Clean up target dir on validation error
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
        raise
    except Exception as e:
        # Clean up target dir on unexpected error
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
        logger.exception(f"Failed to upload agent: {e}")
        raise HTTPException(status_code=500, detail="Failed to process agent upload") from e
    finally:
        # Always clean up temp directory
        if tmp_dir and tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)

@router.get(
    "/{name}",
    response_model=AgentInfo,
    responses=response_with_errors(404),
    summary="Get agent details",
)
async def get_agent(name: str) -> AgentInfo:
    """Get details for a specific agent.

    Returns agent information including available tools and framework.
    """
    agent = adapter_get_agent(name)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")
    return _card_to_agent_info(agent.get_card())

@router.get(
    "/{name}/tools",
    response_model=list[ToolInfo],
    responses=response_with_errors(404),
    summary="Get agent tools",
)
async def get_agent_tools(name: str) -> list[ToolInfo]:
    """Get tools available to an agent.

    Returns detailed information about each tool including parameter schemas.
    """
    agent = adapter_get_agent(name)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")

    card = agent.get_card()
    return [
        ToolInfo(name=cap.name, description=cap.description, parameters=cap.input_schema or {})
        for cap in card.capabilities or []
    ]

@router.post(
    "/{name}/invoke",
    response_model=InvokeResponse,
    responses=response_with_errors(404, 500),
    summary="Execute task with agent",
)
async def invoke_agent(name: str, request: InvokeRequest) -> InvokeResponse:
    """Execute a task with a specific agent.

    The agent will use its available tools to complete the task.
    Returns the result along with execution metrics.
    """
    agent = adapter_get_agent(name)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")

    start_time = time.time()

    try:
        # Merge tool + arguments into context for MCP agents
        ctx = dict(request.context or {})
        if request.tool:
            ctx["tool"] = request.tool
        if request.arguments:
            ctx["arguments"] = request.arguments
        result = await agent.execute(request.task, ctx)
        execution_time = (time.time() - start_time) * 1000

        # Check if agent execution failed
        if result.status == "error":
            raise HTTPException(status_code=500, detail=result.error or "Agent execution failed")

        # Get cost metrics for this execution from cost_tracker
        tokens_used = 0
        cost = 0.0
        if get_cost_tracker is not None:
            try:
                tracker = get_cost_tracker()
                recent_records = tracker.get_records(limit=10)
                execution_records = [r for r in recent_records if r.get("agent") == name]
                tokens_used = sum(
                    r.get("input_tokens", 0) + r.get("output_tokens", 0) for r in execution_records
                )
                cost = sum(r.get("cost_usd", 0.0) for r in execution_records)
            except Exception:
                pass  # Cost tracking unavailable

        return InvokeResponse(
            result=str(result.result) if result.result else "",
            agent=name,
            tool_calls=result.metadata.get("tool_calls", []),
            execution_time_ms=execution_time,
            tokens_used=tokens_used,
            cost=cost,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to execute agent task for '{name}': {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to execute agent task. Check agent availability and input format.",
        ) from e

@router.get(
    "/{name}/describe",
    responses=response_with_errors(404),
    summary="Get A2A agent card",
)
async def describe_agent(name: str) -> dict[str, Any]:
    """Get full agent description in A2A-compatible format.

    Returns the complete AgentCard with all metadata and capabilities.
    """
    agent = adapter_get_agent(name)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")
    return agent.get_card().model_dump()

# Agent -> required MCP servers mapping
_AGENT_SERVER_MAP: dict[str, list[str]] = {
    # Core agents
    "devops_engineer": ["git", "filesystem", "github"],
    "code_reviewer": ["github", "context7", "git"],
    "database_analyst": ["dbhub", "grafana"],
    "research_assistant": ["playwright", "memory", "filesystem"],
    # Plugin agents
    "excel_analyst": ["document-ops", "dbhub"],
    "kpi_monitor": ["grafana", "dbhub"],
    "document_processor": ["pdf-reader", "document-ops"],
    "project_manager": ["linear", "github", "memory"],
    "compliance_auditor": ["filesystem", "pdf-reader", "memory"],
    "sales_intelligence": ["playwright", "memory"],
}

def _get_required_servers(agent_name: str) -> list[str]:
    """Get required MCP servers for an agent from config."""
    return _AGENT_SERVER_MAP.get(agent_name, [])

class SetupInstruction(BaseModel):
    """Setup instruction for a missing MCP server."""

    server: str = Field(..., description="MCP server name")
    reason: str = Field(..., description="Reason this server is required")
    name: str = Field(..., description="Display name")
    description: str = Field(..., description="What the server provides")
    package: str = Field(..., description="NPM package name")
    env_vars: list[str] = Field(default_factory=list, description="Required environment variables")
    setup_steps: list[str] = Field(default_factory=list, description="Setup instructions")
    verification_command: str | None = Field(None, description="Command to verify setup")
    docs_url: str | None = Field(None, description="Documentation URL")

class SetupStatus(BaseModel):
    """Setup status for an agent."""

    ready: bool = Field(..., description="Whether agent is ready to use")
    missing: list[dict[str, str]] = Field(
        default_factory=list, description="Missing server configurations"
    )
    setup_url: str | None = Field(None, description="URL to setup page")
    instructions: list[SetupInstruction] = Field(
        default_factory=list, description="Setup instructions for missing servers"
    )

@router.get(
    "/{name}/setup",
    response_model=SetupStatus,
    responses=response_with_errors(404),
    summary="Check agent setup status",
)
async def check_agent_setup_status(name: str) -> SetupStatus:
    """Check if agent has required MCP servers configured.

    Returns setup status and instructions for any missing configuration.
    This endpoint powers the setup wizard for first-run agent configuration.
    """
    agent = adapter_get_agent(name)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")

    # Get required servers from agent config mapping
    required_servers = _get_required_servers(name)

    setup_status = check_agent_setup(name, required_servers)

    # Build response with setup instructions for missing servers
    instructions: list[SetupInstruction] = []
    if not setup_status["ready"]:
        for missing in setup_status["missing"]:
            server_info = get_setup_instructions(missing["server"])
            instructions.append(
                SetupInstruction(
                    server=missing["server"],
                    reason=missing.get("reason", "required"),
                    name=server_info.get("name", missing["server"]),
                    description=server_info.get("description", ""),
                    package=server_info.get("package", ""),
                    env_vars=server_info.get("env_vars", []),
                    setup_steps=server_info.get("setup_steps", []),
                    verification_command=server_info.get("verification_command"),
                    docs_url=server_info.get("docs_url"),
                )
            )

    return SetupStatus(
        ready=setup_status["ready"],
        missing=setup_status["missing"],
        setup_url=setup_status.get("setup_url"),
        instructions=instructions,
    )
