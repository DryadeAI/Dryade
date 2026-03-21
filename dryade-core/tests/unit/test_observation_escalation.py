"""Unit tests for observation enrichment (F-003) and leash-exceeded escalation (F-001).

Covers:
- F-003: Timeout observations include tool name and truncated arguments
- F-003: Exception observations include tool name and truncated arguments
- F-003: Long arguments are truncated to ~200 chars
- F-003: Missing tool falls back to task description
- F-001: Leash-exceeded triggers escalation with needs_escalation=True
- F-001: Escalation question includes limit details
- F-001: Escalation preserves observation history
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.adapters.protocol import (
    AgentCapabilities,
    AgentCard,
    AgentFramework,
    AgentResult,
    UniversalAgent,
)
from core.adapters.registry import AgentRegistry
from core.autonomous.leash import LeashConfig
from core.orchestrator.models import (
    FailureAction,
    OrchestrationMode,
    OrchestrationTask,
    OrchestrationThought,
)
from core.orchestrator.orchestrator import DryadeOrchestrator
from core.orchestrator.thinking import OrchestrationThinkingProvider

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class HangingAgent(UniversalAgent):
    """Agent that hangs forever (for timeout tests)."""

    def __init__(self, name: str = "hanging-agent"):
        self._name = name

    def get_card(self) -> AgentCard:
        return AgentCard(
            name=self._name,
            description="Hangs forever",
            version="1.0",
            framework=AgentFramework.CUSTOM,
        )

    async def execute(self, task, context=None):
        await asyncio.sleep(100)

    def get_tools(self):
        return []

    def capabilities(self) -> AgentCapabilities:
        return AgentCapabilities()

class ErrorAgent(UniversalAgent):
    """Agent that raises an exception."""

    def __init__(self, error: Exception, name: str = "error-agent"):
        self._name = name
        self._error = error

    def get_card(self) -> AgentCard:
        return AgentCard(
            name=self._name,
            description="Raises errors",
            version="1.0",
            framework=AgentFramework.CUSTOM,
        )

    async def execute(self, task, context=None):
        raise self._error

    def get_tools(self):
        return []

    def capabilities(self) -> AgentCapabilities:
        return AgentCapabilities()

class SuccessAgent(UniversalAgent):
    """Agent that succeeds immediately."""

    def __init__(self, name: str = "success-agent"):
        self._name = name

    def get_card(self) -> AgentCard:
        return AgentCard(
            name=self._name,
            description="Always succeeds",
            version="1.0",
            framework=AgentFramework.CUSTOM,
        )

    async def execute(self, task, context=None):
        return AgentResult(result="done", status="ok")

    def get_tools(self):
        return []

    def capabilities(self) -> AgentCapabilities:
        return AgentCapabilities()

def _make_registry(*agents: UniversalAgent) -> AgentRegistry:
    """Build a registry pre-loaded with the given agents."""
    reg = AgentRegistry()
    for a in agents:
        reg.register(a)
    return reg

# ---------------------------------------------------------------------------
# F-003: Timeout observation enrichment
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_timeout_observation_includes_tool_name():
    """Timeout error string includes [tool=X, args=...]."""
    agent = HangingAgent(name="test-agent")
    registry = _make_registry(agent)
    orchestrator = DryadeOrchestrator(
        agent_registry=registry,
    )

    task = OrchestrationTask(
        agent_name="test-agent",
        description="List files in directory",
        tool="list_directory",
        arguments={"path": "/home/user/Desktop"},
    )

    result = await orchestrator._execute_single(task, "exec-1", {}, timeout=0.1)

    assert not result.success
    assert "timed out" in result.error.lower()
    assert "[tool=list_directory" in result.error
    assert "args=" in result.error
    assert "/home/user/Desktop" in result.error

@pytest.mark.asyncio
async def test_exception_observation_includes_tool_name():
    """Exception error string includes [tool=X, args=...]."""
    agent = ErrorAgent(RuntimeError("disk full"), name="test-agent")
    registry = _make_registry(agent)
    orchestrator = DryadeOrchestrator(
        agent_registry=registry,
    )

    task = OrchestrationTask(
        agent_name="test-agent",
        description="Write a file",
        tool="write_file",
        arguments={"path": "/tmp/test.txt", "content": "hello"},
    )

    result = await orchestrator._execute_single(
        task,
        "exec-1",
        {},
    )

    assert not result.success
    assert "RuntimeError" in result.error
    assert "disk full" in result.error
    assert "[tool=write_file" in result.error
    assert "args=" in result.error

@pytest.mark.asyncio
async def test_timeout_observation_truncates_long_args():
    """Arguments longer than 200 chars are truncated."""
    agent = HangingAgent(name="test-agent")
    registry = _make_registry(agent)
    orchestrator = DryadeOrchestrator(
        agent_registry=registry,
    )

    long_value = "x" * 500
    task = OrchestrationTask(
        agent_name="test-agent",
        description="Process data",
        tool="process",
        arguments={"data": long_value},
    )

    result = await orchestrator._execute_single(task, "exec-1", {}, timeout=0.1)

    assert not result.success
    # The args_preview should be truncated at 200 chars
    # The full string representation of {"data": "xxx..."} would be >500 chars
    # After truncation, the args part should be <= 200 chars
    args_part = result.error.split("args=")[1].rstrip("]")
    assert len(args_part) <= 200

@pytest.mark.asyncio
async def test_timeout_observation_no_tool_uses_description():
    """When tool=None, description is used as tool name fallback."""
    agent = HangingAgent(name="test-agent")
    registry = _make_registry(agent)
    orchestrator = DryadeOrchestrator(
        agent_registry=registry,
    )

    task = OrchestrationTask(
        agent_name="test-agent",
        description="Analyze the document",
        tool=None,
        arguments={},
    )

    result = await orchestrator._execute_single(task, "exec-1", {}, timeout=0.1)

    assert not result.success
    assert "[tool=Analyze the document" in result.error

# ---------------------------------------------------------------------------
# F-001: Leash-exceeded escalation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_leash_exceeded_triggers_escalation():
    """Leash-exceeded returns needs_escalation=True with proper fields."""
    agent = SuccessAgent(name="test-agent")
    registry = _make_registry(agent)

    # Create thinking mock that always returns a non-final thought with a task
    thinking = MagicMock(spec=OrchestrationThinkingProvider)
    thinking._on_cost_event = None
    thinking.orchestrate_think = AsyncMock(
        return_value=OrchestrationThought(
            reasoning="I need to do more work",
            is_final=False,
            task=OrchestrationTask(
                agent_name="test-agent",
                description="Do something",
            ),
        )
    )
    thinking.failure_think = AsyncMock(
        return_value=OrchestrationThought(
            reasoning="Retry",
            is_final=False,
            failure_action=FailureAction.RETRY,
        )
    )

    # max_actions=1 means after 1 action, leash triggers
    orchestrator = DryadeOrchestrator(
        thinking_provider=thinking,
        agent_registry=registry,
        leash=LeashConfig(
            max_actions=1,
            max_tokens=None,
            max_cost_usd=None,
            max_duration_seconds=None,
            max_tool_calls=None,
        ),
    )

    result = await orchestrator.orchestrate(
        goal="Complete a multi-step task",
        mode=OrchestrationMode.ADAPTIVE,
    )

    assert not result.success
    assert result.needs_escalation is True
    assert "resource limit" in result.escalation_question
    assert result.original_goal == "Complete a multi-step task"
    assert result.partial_results is not None

@pytest.mark.asyncio
async def test_leash_exceeded_includes_limit_details():
    """Escalation question includes specific limit values."""
    agent = SuccessAgent(name="test-agent")
    registry = _make_registry(agent)

    thinking = MagicMock(spec=OrchestrationThinkingProvider)
    thinking._on_cost_event = None
    thinking.orchestrate_think = AsyncMock(
        return_value=OrchestrationThought(
            reasoning="Work to do",
            is_final=False,
            task=OrchestrationTask(
                agent_name="test-agent",
                description="Do something",
            ),
        )
    )
    thinking.failure_think = AsyncMock(
        return_value=OrchestrationThought(
            reasoning="Retry",
            is_final=False,
            failure_action=FailureAction.RETRY,
        )
    )

    orchestrator = DryadeOrchestrator(
        thinking_provider=thinking,
        agent_registry=registry,
        leash=LeashConfig(
            max_actions=1,
            max_duration_seconds=120,
            max_tokens=None,
            max_cost_usd=None,
            max_tool_calls=None,
        ),
    )

    result = await orchestrator.orchestrate(
        goal="Multi-step analysis",
        mode=OrchestrationMode.ADAPTIVE,
    )

    assert result.needs_escalation is True
    assert "max actions: 1" in result.escalation_question
    assert "max duration: 120s" in result.escalation_question

@pytest.mark.asyncio
async def test_leash_exceeded_preserves_observation_history():
    """Leash escalation result includes observation_history_data."""
    agent = SuccessAgent(name="test-agent")
    registry = _make_registry(agent)

    thinking = MagicMock(spec=OrchestrationThinkingProvider)
    thinking._on_cost_event = None
    thinking.orchestrate_think = AsyncMock(
        return_value=OrchestrationThought(
            reasoning="Work to do",
            is_final=False,
            task=OrchestrationTask(
                agent_name="test-agent",
                description="Do something",
            ),
        )
    )
    thinking.failure_think = AsyncMock(
        return_value=OrchestrationThought(
            reasoning="Retry",
            is_final=False,
            failure_action=FailureAction.RETRY,
        )
    )

    orchestrator = DryadeOrchestrator(
        thinking_provider=thinking,
        agent_registry=registry,
        leash=LeashConfig(
            max_actions=1,
            max_tokens=None,
            max_cost_usd=None,
            max_duration_seconds=None,
            max_tool_calls=None,
        ),
    )

    result = await orchestrator.orchestrate(
        goal="History preservation test",
        mode=OrchestrationMode.ADAPTIVE,
    )

    assert result.needs_escalation is True
    assert result.observation_history_data is not None
    assert isinstance(result.observation_history_data, dict)
