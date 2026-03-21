"""Command API Routes - Slash command discovery and execution endpoints.

Target: ~100 LOC
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from core.auth.dependencies import get_current_user
from core.commands import get_command, get_registry, list_commands

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/commands", tags=["commands"])

# Request/Response Models
class CommandInfo(BaseModel):
    """Information about a registered command."""

    name: str = Field(..., description="Command name (without / prefix)")
    description: str = Field(..., description="Human-readable description")

class CommandListResponse(BaseModel):
    """List of available commands."""

    commands: list[CommandInfo] = Field(..., description="List of command info")

class CommandExecuteRequest(BaseModel):
    """Request to execute a command."""

    args: dict[str, Any] = Field(default_factory=dict, description="Command arguments")

class CommandExecuteResponse(BaseModel):
    """Response from command execution."""

    status: str = Field(..., description="Execution status (ok/error)")
    result: Any = Field(None, description="Command result")
    error: str | None = Field(None, description="Error message if status=error")

class CommandNotFoundResponse(BaseModel):
    """Response when command is not found."""

    error: str = Field(..., description="Error message")
    suggestions: list[str] = Field(default_factory=list, description="Similar command names")

@router.get(
    "",
    response_model=CommandListResponse,
    summary="List available commands",
)
async def get_commands() -> CommandListResponse:
    """List all available slash commands.

    Returns commands registered in the system with their names and descriptions.
    """
    commands = list_commands()
    return CommandListResponse(
        commands=[CommandInfo(name=c["name"], description=c["description"]) for c in commands]
    )

@router.post(
    "/{command_name}/execute",
    response_model=CommandExecuteResponse,
    responses={
        404: {"model": CommandNotFoundResponse, "description": "Command not found"},
        400: {"description": "Invalid arguments"},
        500: {"description": "Execution error"},
    },
    summary="Execute a command",
)
async def execute_command(
    command_name: str,
    request: CommandExecuteRequest,
    current_user: dict = Depends(get_current_user),
) -> CommandExecuteResponse:
    """Execute a specific slash command.

    Validates the command exists, then executes with provided arguments.
    Context includes user_id from JWT token for audit logging.

    Args:
        command_name: Name of command to execute (without / prefix)
        request: Command arguments
        current_user: Authenticated user from JWT

    Returns:
        Command execution result

    Raises:
        404: Command not found (includes suggestions for typos)
        400: Invalid arguments
        500: Execution error
    """
    # Lookup command
    command = get_command(command_name)
    if command is None:
        registry = get_registry()
        suggestions = registry.suggest_similar(command_name)
        suggestion_msg = ""
        if suggestions:
            suggestion_msg = f" Did you mean: {', '.join(suggestions)}?"
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": f"Command '{command_name}' not found.{suggestion_msg}",
                "suggestions": suggestions,
            },
        )

    # Build execution context
    context = {
        "user_id": current_user.get("sub") or current_user.get("user_id"),
        "username": current_user.get("username"),
    }

    logger.info(f"Executing command /{command_name} for user {context.get('user_id')}")

    # Execute command
    try:
        result = await command.execute(request.args, context)
        return CommandExecuteResponse(status="ok", result=result)
    except ValueError as e:
        # Invalid arguments
        logger.warning(f"Invalid arguments for /{command_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to parse command. Check command syntax: /command [args]",
        ) from e
    except RuntimeError as e:
        # Execution error (e.g., agent/flow not found)
        logger.exception(f"Execution error for /{command_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to execute command. Verify command handler configuration.",
        ) from e
    except Exception as e:
        # Unexpected error
        logger.exception(f"Unexpected error executing /{command_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Command execution failed. Please check logs or try again.",
        ) from e
