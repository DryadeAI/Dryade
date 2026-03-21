"""A2A Executor Bridge.

Translates A2A JSON-RPC 2.0 protocol calls into Dryade's UniversalAgent
interface. This module is consumed by the FastAPI routes in a2a_server.py.

Functions:
  - build_a2a_agent_card: Generate A2A AgentCard from registered agents
  - handle_message_send: Dispatch message/send to an agent
  - handle_message_stream: Dispatch message/stream with SSE events
  - handle_tasks_get: Retrieve a stored task
  - handle_tasks_cancel: Cancel a stored task
"""

import logging
from collections.abc import AsyncGenerator
from typing import Any
from uuid import uuid4

from core.a2a.models import A2AAgentCard, A2ASkill
from core.a2a.task_store import get_task_store
from core.adapters.registry import get_agent, get_registry

logger = logging.getLogger(__name__)

# Inverse of the client adapter's _A2A_STATE_TO_STATUS
_STATUS_TO_A2A_STATE = {
    "ok": "completed",
    "error": "failed",
    "partial": "working",
}

def build_a2a_agent_card(base_url: str) -> dict[str, Any]:
    """Generate an A2A AgentCard from all registered agents.

    Each registered agent becomes a skill in the card. The card is
    suitable for serving at /.well-known/agent.json.

    Args:
        base_url: Base URL of this Dryade instance (e.g. "https://dryade.example.com").

    Returns:
        A2A AgentCard as a dict (camelCase keys).
    """
    registry = get_registry()
    agent_cards = registry.list_agents()

    skills = []
    for card in agent_cards:
        skill = A2ASkill(
            id=card.name,
            name=card.name.replace("_", " ").title(),
            description=card.description,
            tags=[card.framework.value] + card.skills,
            examples=[cap.description for cap in card.capabilities[:3]],
        )
        skills.append(skill)

    a2a_card = A2AAgentCard(
        name="Dryade AI",
        description="Self-hosted AI orchestration platform with multi-framework agent support",
        url=f"{base_url}/a2a",
        skills=skills,
    )
    return a2a_card.model_dump(by_alias=True)

async def handle_message_send(params: dict[str, Any]) -> dict[str, Any]:
    """Handle A2A message/send: dispatch to a UniversalAgent and return a task.

    Args:
        params: JSON-RPC params with 'message' and optional 'metadata.skillId'.

    Returns:
        A2A Task dict with id, contextId, status, artifacts, kind.

    Raises:
        ValueError: If no message text, unknown skill, or no agents registered.
    """
    # Extract message text
    message = params.get("message", {})
    parts = message.get("parts", [])
    task_text = None
    for part in parts:
        if isinstance(part, dict) and part.get("text"):
            task_text = part["text"]
            break
    if not task_text:
        raise ValueError("No message text provided")

    # Resolve agent
    skill_id = params.get("metadata", {}).get("skillId")
    agent = None

    if skill_id:
        agent = get_agent(skill_id)
        if agent is None:
            raise ValueError(f"Unknown skill: {skill_id}")
    else:
        # Use first available agent
        agent_cards = get_registry().list_agents()
        if not agent_cards:
            raise ValueError("No agents registered")
        agent = get_agent(agent_cards[0].name)

    # Execute
    context: dict[str, Any] = {"a2a": True}
    if skill_id:
        context["skill_id"] = skill_id

    result = await agent.execute(task_text, context=context)

    # Map to A2A task
    a2a_state = _STATUS_TO_A2A_STATE.get(result.status, "failed")
    task_id = str(uuid4())
    context_id = str(uuid4())

    task_dict: dict[str, Any] = {
        "id": task_id,
        "contextId": context_id,
        "status": {
            "state": a2a_state,
            "message": {
                "role": "agent",
                "parts": [{"text": str(result.result) if result.result else ""}],
            },
        },
        "artifacts": [],
        "kind": "task",
    }

    # Store for later retrieval
    get_task_store().store(task_id, task_dict)

    return task_dict

async def handle_message_stream(
    params: dict[str, Any],
) -> AsyncGenerator[dict[str, Any], None]:
    """Handle A2A message/stream: yield SSE event dicts from agent streaming.

    If the agent does not support streaming, falls back to synchronous
    execution and yields a single completed event.

    Args:
        params: JSON-RPC params with 'message' and optional 'metadata.skillId'.

    Yields:
        JSON-RPC notification dicts suitable for SSE serialization.
    """
    # Extract message text
    message = params.get("message", {})
    parts = message.get("parts", [])
    task_text = None
    for part in parts:
        if isinstance(part, dict) and part.get("text"):
            task_text = part["text"]
            break
    if not task_text:
        raise ValueError("No message text provided")

    # Resolve agent
    skill_id = params.get("metadata", {}).get("skillId")
    agent = None

    if skill_id:
        agent = get_agent(skill_id)
        if agent is None:
            raise ValueError(f"Unknown skill: {skill_id}")
    else:
        agent_cards = get_registry().list_agents()
        if not agent_cards:
            raise ValueError("No agents registered")
        agent = get_agent(agent_cards[0].name)

    context: dict[str, Any] = {"a2a": True}
    if skill_id:
        context["skill_id"] = skill_id

    task_id = str(uuid4())
    context_id = str(uuid4())

    # Check streaming support
    if not agent.supports_streaming():
        # Fallback: synchronous execution, single event
        result = await agent.execute(task_text, context=context)
        a2a_state = _STATUS_TO_A2A_STATE.get(result.status, "failed")
        task_dict: dict[str, Any] = {
            "id": task_id,
            "contextId": context_id,
            "status": {
                "state": a2a_state,
                "message": {
                    "role": "agent",
                    "parts": [{"text": str(result.result) if result.result else ""}],
                },
            },
            "artifacts": [],
            "kind": "task",
        }
        get_task_store().store(task_id, task_dict)
        yield {
            "jsonrpc": "2.0",
            "result": task_dict,
        }
        return

    # Streaming execution
    yield {
        "jsonrpc": "2.0",
        "result": {
            "id": task_id,
            "contextId": context_id,
            "status": {"state": "working"},
            "kind": "task",
        },
    }

    final_text = ""
    async for event in agent.execute_stream(task_text, context=context):
        if isinstance(event, dict):
            chunk = event.get("text", event.get("message", ""))
            final_text += str(chunk)
            yield {
                "jsonrpc": "2.0",
                "result": {
                    "id": task_id,
                    "contextId": context_id,
                    "status": {
                        "state": "working",
                        "message": {
                            "role": "agent",
                            "parts": [{"text": str(chunk)}],
                        },
                    },
                    "kind": "task",
                },
            }

    # Final completed event
    task_dict = {
        "id": task_id,
        "contextId": context_id,
        "status": {
            "state": "completed",
            "message": {
                "role": "agent",
                "parts": [{"text": final_text}],
            },
        },
        "artifacts": [],
        "kind": "task",
    }
    get_task_store().store(task_id, task_dict)
    yield {"jsonrpc": "2.0", "result": task_dict}

async def handle_tasks_get(params: dict[str, Any]) -> dict[str, Any]:
    """Handle A2A tasks/get: retrieve a stored task by ID.

    Args:
        params: JSON-RPC params with 'id'.

    Returns:
        A2A Task dict.

    Raises:
        ValueError: If task not found.
    """
    task_id = params.get("id", "")
    task = get_task_store().get(task_id)
    if task is None:
        raise ValueError(f"Task not found: {task_id}")
    return task

async def handle_tasks_cancel(params: dict[str, Any]) -> dict[str, Any]:
    """Handle A2A tasks/cancel: cancel a stored task.

    Args:
        params: JSON-RPC params with 'id'.

    Returns:
        Updated A2A Task dict with canceled state.

    Raises:
        ValueError: If task not found.
    """
    task_id = params.get("id", "")
    success = get_task_store().cancel(task_id)
    if not success:
        raise ValueError(f"Task not found: {task_id}")
    task = get_task_store().get(task_id)
    return task  # type: ignore[return-value]
