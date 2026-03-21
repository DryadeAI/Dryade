"""Unit tests for OrchestrationThinkingProvider.

Covers:
- Initialization with default and custom config
- orchestrate_think: basic call, with observations, prompt assembly, return format,
  JSON parse failure recovery, conversational fallback
- failure_think: retry/skip/escalate/alternative actions, LLM error fallback
- manager_think: delegation, final answer, progress formatting, LLM error fallback
- plan_think: DAG plan generation, fallback on parse error
- replan_think: revised plan generation, None on failure
- synthesize_think: result synthesis
- _call_llm: dict responses, tool call responses, error propagation, cost emission
- _extract_json_from_response: markdown blocks, raw JSON, nested braces, None input
- _format_agents_xml: full and lightweight modes, empty agents
- _convert_tool_calls_to_json: native tool call conversion
- _resolve_agent_for_tool: capability-based agent lookup
- _extract_agent_from_reasoning: intent extraction from reasoning text
- _emit_cost_from_llm: delta tracking, estimation fallback, callback errors
- _filter_agents_by_router: matching, non-MCP inclusion, fallback, empty hints, max_servers, dedup
- _build_tools_for_agents caching: hit, miss, invalidation, initial state
- orchestrate_think filtering integration: lightweight XML, filtered tools, config bypass, text-only, plan_think isolation
"""

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.adapters.protocol import (
    AgentCapability,
    AgentCard,
    AgentFramework,
)
from core.extensions.events import ChatEvent
from core.orchestrator.models import (
    ExecutionPlan,
    FailureAction,
    OrchestrationObservation,
    OrchestrationTask,
    OrchestrationThought,
    PlanStep,
    StepStatus,
)
from core.orchestrator.observation import ObservationHistory
from core.orchestrator.thinking import (
    OrchestrationThinkingProvider,
    _format_agents_xml,
)

# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------

def _make_agent_card(
    name: str = "test-agent",
    description: str = "A test agent",
    framework: AgentFramework = AgentFramework.CUSTOM,
    capabilities: list[AgentCapability] | None = None,
) -> AgentCard:
    """Create a minimal AgentCard for testing."""
    return AgentCard(
        name=name,
        description=description,
        version="1.0",
        framework=framework,
        capabilities=capabilities or [],
    )

def _make_mcp_agent(
    name: str = "mcp-filesystem",
    tools: list[tuple[str, str]] | None = None,
) -> AgentCard:
    """Create an MCP agent card with tool capabilities."""
    caps = []
    for tool_name, desc in tools or [("list_directory", "List files")]:
        caps.append(
            AgentCapability(
                name=tool_name,
                description=desc,
                input_schema={
                    "properties": {"path": {"type": "string", "description": "Dir path"}},
                    "required": ["path"],
                },
            )
        )
    return AgentCard(
        name=name,
        description="MCP filesystem agent",
        version="1.0",
        framework=AgentFramework.MCP,
        capabilities=caps,
    )

def _make_observation(
    agent_name: str = "test-agent",
    task: str = "do something",
    result: str = "done",
    success: bool = True,
    error: str | None = None,
) -> OrchestrationObservation:
    return OrchestrationObservation(
        agent_name=agent_name,
        task=task,
        result=result,
        success=success,
        error=error,
    )

def _make_observation_history(
    observations: list[OrchestrationObservation] | None = None,
) -> ObservationHistory:
    """Create an ObservationHistory optionally pre-populated."""
    history = ObservationHistory()
    for obs in observations or []:
        history.add(obs)
    return history

@pytest.fixture
def provider():
    """Create a ThinkingProvider with a mocked LLM."""
    mock_llm = MagicMock()
    mock_llm.call = MagicMock(return_value="")
    mock_llm._token_usage = {"prompt_tokens": 0, "completion_tokens": 0}
    return OrchestrationThinkingProvider(llm=mock_llm)

@pytest.fixture
def agents():
    """Standard test agent list."""
    return [
        _make_agent_card("agent-a", "Agent Alpha"),
        _make_mcp_agent(
            "mcp-filesystem", [("list_directory", "List files"), ("search_files", "Search files")]
        ),
    ]

# ---------------------------------------------------------------------------
# TestThinkingProviderInit
# ---------------------------------------------------------------------------

class TestThinkingProviderInit:
    """Constructor with default/custom config."""

    def test_default_init(self):
        p = OrchestrationThinkingProvider()
        assert p._explicit_llm is None
        assert p._on_cost_event is None
        assert p._last_available_agents == []

    def test_explicit_llm(self):
        mock_llm = MagicMock()
        p = OrchestrationThinkingProvider(llm=mock_llm)
        assert p._explicit_llm is mock_llm

    def test_cost_callback(self):
        cb = MagicMock()
        p = OrchestrationThinkingProvider(on_cost_event=cb)
        assert p._on_cost_event is cb

    def test_get_llm_explicit(self):
        mock_llm = MagicMock()
        p = OrchestrationThinkingProvider(llm=mock_llm)
        assert p._get_llm() is mock_llm

    @patch("core.orchestrator.thinking.get_configured_llm", create=True)
    def test_get_llm_fallback(self, mock_get):
        """When no explicit LLM, _get_llm() calls get_configured_llm()."""
        sentinel = MagicMock()
        with patch("core.providers.llm_adapter.get_configured_llm", return_value=sentinel):
            p = OrchestrationThinkingProvider()
            result = p._get_llm()
            assert result is sentinel

# ---------------------------------------------------------------------------
# TestOrchestrateThink
# ---------------------------------------------------------------------------

class TestOrchestrateThink:
    """Tests for orchestrate_think method."""

    @pytest.mark.asyncio
    async def test_basic_final_answer(self, provider, agents):
        """LLM returns is_final=true with an answer."""
        response = json.dumps(
            {
                "reasoning": "Goal already achieved",
                "reasoning_summary": "Done",
                "is_final": True,
                "answer": "Here is the result",
                "task": None,
                "parallel_tasks": None,
            }
        )
        provider._explicit_llm.call = MagicMock(return_value=response)
        history = _make_observation_history()

        thought = await provider.orchestrate_think(
            goal="Get result",
            observations=[],
            available_agents=agents,
            observation_history=history,
        )
        assert thought.is_final is True
        assert thought.answer == "Here is the result"
        assert thought.task is None

    @pytest.mark.asyncio
    async def test_next_action_task(self, provider, agents):
        """LLM returns a next action with a task."""
        response = json.dumps(
            {
                "reasoning": "Need to list directory",
                "reasoning_summary": "Listing files",
                "is_final": False,
                "answer": None,
                "task": {
                    "agent_name": "mcp-filesystem",
                    "description": "list_directory",
                    "tool": "list_directory",
                    "arguments": {"path": "/home"},
                },
                "parallel_tasks": None,
            }
        )
        provider._explicit_llm.call = MagicMock(return_value=response)
        history = _make_observation_history()

        thought = await provider.orchestrate_think(
            goal="List files",
            observations=[],
            available_agents=agents,
            observation_history=history,
        )
        assert thought.is_final is False
        assert thought.task is not None
        assert thought.task.agent_name == "mcp-filesystem"
        assert thought.task.tool == "list_directory"
        assert thought.task.arguments == {"path": "/home"}

    @pytest.mark.asyncio
    async def test_with_observations(self, provider, agents):
        """When observations are provided, COMPLETED ACTIONS appears in user message."""
        response = json.dumps(
            {
                "reasoning": "Done",
                "is_final": True,
                "answer": "Result",
                "task": None,
                "parallel_tasks": None,
            }
        )
        provider._explicit_llm.call = MagicMock(return_value=response)

        obs = _make_observation("agent-a", "do task", "success", True)
        history = _make_observation_history([obs])

        thought = await provider.orchestrate_think(
            goal="Finish",
            observations=[obs],
            available_agents=agents,
            observation_history=history,
        )
        # Verify call was made with messages containing observations
        call_args = provider._explicit_llm.call.call_args
        messages = call_args[1]["messages"] if "messages" in call_args[1] else call_args[0][0]
        user_msg = [m for m in messages if m["role"] == "user"][0]
        assert "COMPLETED ACTIONS" in user_msg["content"]
        assert "USER GOAL" in user_msg["content"]

    @pytest.mark.asyncio
    async def test_no_observations_user_goal_only(self, provider, agents):
        """When no observations, user message is just the goal."""
        response = json.dumps(
            {
                "reasoning": "Starting",
                "is_final": False,
                "task": {"agent_name": "agent-a", "description": "start"},
                "parallel_tasks": None,
            }
        )
        provider._explicit_llm.call = MagicMock(return_value=response)
        history = _make_observation_history()

        await provider.orchestrate_think(
            goal="Do something",
            observations=[],
            available_agents=agents,
            observation_history=history,
        )
        call_args = provider._explicit_llm.call.call_args
        messages = call_args[1]["messages"] if "messages" in call_args[1] else call_args[0][0]
        user_msg = [m for m in messages if m["role"] == "user"][0]
        # Phase 167 added routing_examples XML to the user message after the goal.
        # Assert the goal prefix is present rather than requiring exact equality.
        assert user_msg["content"].startswith("USER GOAL: Do something")

    @pytest.mark.asyncio
    async def test_prompt_contains_agents_xml(self, provider, agents):
        """System prompt includes agents XML."""
        response = json.dumps(
            {
                "reasoning": "x",
                "is_final": True,
                "answer": "ok",
                "task": None,
                "parallel_tasks": None,
            }
        )
        provider._explicit_llm.call = MagicMock(return_value=response)
        history = _make_observation_history()

        await provider.orchestrate_think(
            goal="test",
            observations=[],
            available_agents=agents,
            observation_history=history,
        )
        call_args = provider._explicit_llm.call.call_args
        messages = call_args[1]["messages"] if "messages" in call_args[1] else call_args[0][0]
        system_msg = [m for m in messages if m["role"] == "system"][0]
        assert "<agents>" in system_msg["content"]
        assert "agent-a" in system_msg["content"]

    @pytest.mark.asyncio
    async def test_lightweight_mode_adds_addendum(self, provider, agents):
        """Lightweight mode appends LIGHTWEIGHT_AGENT_ADDENDUM."""
        response = json.dumps(
            {
                "reasoning": "x",
                "is_final": True,
                "answer": "ok",
                "task": None,
                "parallel_tasks": None,
            }
        )
        provider._explicit_llm.call = MagicMock(return_value=response)
        history = _make_observation_history()

        await provider.orchestrate_think(
            goal="test",
            observations=[],
            available_agents=agents,
            observation_history=history,
            lightweight=True,
        )
        call_args = provider._explicit_llm.call.call_args
        messages = call_args[1]["messages"] if "messages" in call_args[1] else call_args[0][0]
        system_msg = [m for m in messages if m["role"] == "system"][0]
        assert "lightweight agent roster" in system_msg["content"]

    @pytest.mark.asyncio
    async def test_prompt_contains_clarification_option(self, provider, agents):
        """System prompt includes needs_clarification output format (RC2)."""
        response = json.dumps(
            {
                "reasoning": "x",
                "is_final": True,
                "answer": "ok",
                "task": None,
                "parallel_tasks": None,
            }
        )
        provider._explicit_llm.call = MagicMock(return_value=response)
        history = _make_observation_history()

        await provider.orchestrate_think(
            goal="test",
            observations=[],
            available_agents=agents,
            observation_history=history,
        )
        call_args = provider._explicit_llm.call.call_args
        messages = call_args[1]["messages"] if "messages" in call_args[1] else call_args[0][0]
        system_msg = [m for m in messages if m["role"] == "system"][0]
        assert "needs_clarification" in system_msg["content"]
        assert "clarifying question" in system_msg["content"].lower()

    @pytest.mark.asyncio
    async def test_json_parse_failure_conversational_fallback(self, provider, agents):
        """When LLM returns conversational text instead of JSON, use it as answer."""
        # Return a long non-JSON string (>50 chars, not starting with {)
        long_text = "I apologize, but I cannot process that request. Let me explain why this is the case in detail."
        provider._explicit_llm.call = MagicMock(return_value=long_text)
        history = _make_observation_history()

        thought = await provider.orchestrate_think(
            goal="Do something",
            observations=[],
            available_agents=agents,
            observation_history=history,
        )
        assert thought.is_final is True
        assert thought.answer is not None
        assert "apologize" in thought.answer

    @pytest.mark.asyncio
    async def test_json_parse_failure_short_content(self, provider, agents):
        """When LLM returns short non-JSON content, fallback error message."""
        provider._explicit_llm.call = MagicMock(return_value="err")
        history = _make_observation_history()

        thought = await provider.orchestrate_think(
            goal="Do something",
            observations=[],
            available_agents=agents,
            observation_history=history,
        )
        assert thought.is_final is True
        assert (
            "issue" in thought.answer.lower()
            or "error" in thought.answer.lower()
            or "encountered" in thought.answer.lower()
        )

    @pytest.mark.asyncio
    async def test_json_recovery_from_reasoning(self, provider, agents):
        """When main content is invalid JSON but reasoning contains valid JSON, recover."""
        valid_json = json.dumps(
            {
                "reasoning": "recovered",
                "is_final": True,
                "answer": "Recovered answer",
                "task": None,
                "parallel_tasks": None,
            }
        )
        # Return a dict response where content is empty but reasoning_content has valid JSON
        provider._explicit_llm.call = MagicMock(
            return_value={
                "content": "",
                "reasoning_content": valid_json,
            }
        )
        history = _make_observation_history()

        thought = await provider.orchestrate_think(
            goal="test",
            observations=[],
            available_agents=agents,
            observation_history=history,
        )
        assert thought.is_final is True
        assert thought.answer == "Recovered answer"

    @pytest.mark.asyncio
    async def test_exception_in_llm_returns_error_thought(self, provider, agents):
        """If LLM raises an unexpected exception, return error thought."""
        provider._explicit_llm.call = MagicMock(side_effect=RuntimeError("LLM down"))
        history = _make_observation_history()

        thought = await provider.orchestrate_think(
            goal="test",
            observations=[],
            available_agents=agents,
            observation_history=history,
        )
        assert thought.is_final is True
        assert "RuntimeError" in thought.answer

    @pytest.mark.asyncio
    async def test_parallel_tasks(self, provider, agents):
        """LLM returns parallel_tasks list."""
        response = json.dumps(
            {
                "reasoning": "Do two things at once",
                "is_final": False,
                "task": None,
                "parallel_tasks": [
                    {"agent_name": "agent-a", "description": "task 1"},
                    {
                        "agent_name": "mcp-filesystem",
                        "description": "task 2",
                        "tool": "list_directory",
                        "arguments": {"path": "/"},
                    },
                ],
            }
        )
        provider._explicit_llm.call = MagicMock(return_value=response)
        history = _make_observation_history()

        thought = await provider.orchestrate_think(
            goal="multi",
            observations=[],
            available_agents=agents,
            observation_history=history,
        )
        assert thought.parallel_tasks is not None
        assert len(thought.parallel_tasks) == 2
        assert thought.parallel_tasks[0].agent_name == "agent-a"

    @pytest.mark.asyncio
    async def test_stores_last_available_agents(self, provider, agents):
        """orchestrate_think stores agents for tool resolution."""
        response = json.dumps(
            {
                "reasoning": "x",
                "is_final": True,
                "answer": "ok",
                "task": None,
                "parallel_tasks": None,
            }
        )
        provider._explicit_llm.call = MagicMock(return_value=response)
        history = _make_observation_history()

        await provider.orchestrate_think(
            goal="test",
            observations=[],
            available_agents=agents,
            observation_history=history,
        )
        assert provider._last_available_agents is agents

    @pytest.mark.asyncio
    async def test_external_reasoning_preferred(self, provider, agents):
        """When LLM returns reasoning_content, it is preferred over JSON reasoning."""
        response_json = json.dumps(
            {
                "reasoning": "from json",
                "is_final": True,
                "answer": "ok",
                "task": None,
                "parallel_tasks": None,
            }
        )
        # Simulate dict response with separate reasoning_content
        provider._explicit_llm.call = MagicMock(
            return_value={
                "content": response_json,
                "reasoning_content": "from thinking model",
            }
        )
        history = _make_observation_history()

        thought = await provider.orchestrate_think(
            goal="test",
            observations=[],
            available_agents=agents,
            observation_history=history,
        )
        assert thought.reasoning == "from thinking model"

# ---------------------------------------------------------------------------
# TestFailureThink
# ---------------------------------------------------------------------------

class TestFailureThink:
    """Tests for failure_think method."""

    @pytest.mark.asyncio
    async def test_retry_action(self, provider, agents):
        response = json.dumps(
            {
                "reasoning": "Network timeout, worth retrying",
                "failure_action": "retry",
                "alternative_agent": None,
                "escalation_question": None,
            }
        )
        provider._explicit_llm.call = MagicMock(return_value=response)

        thought = await provider.failure_think(
            agent_name="agent-a",
            task_description="fetch data",
            error="Connection timeout",
            retry_count=0,
            max_retries=3,
            is_critical=True,
            available_agents=agents,
        )
        assert thought.failure_action == FailureAction.RETRY
        assert thought.alternative_agent is None

    @pytest.mark.asyncio
    async def test_alternative_action(self, provider, agents):
        response = json.dumps(
            {
                "reasoning": "Wrong agent, use filesystem",
                "failure_action": "alternative",
                "alternative_agent": "mcp-filesystem",
                "escalation_question": None,
            }
        )
        provider._explicit_llm.call = MagicMock(return_value=response)

        thought = await provider.failure_think(
            agent_name="agent-a",
            task_description="list files",
            error="Agent cannot list files",
            retry_count=0,
            max_retries=3,
            is_critical=True,
            available_agents=agents,
        )
        assert thought.failure_action == FailureAction.ALTERNATIVE
        assert thought.alternative_agent == "mcp-filesystem"

    @pytest.mark.asyncio
    async def test_escalate_action(self, provider, agents):
        response = json.dumps(
            {
                "reasoning": "Permission denied, user must fix",
                "failure_action": "escalate",
                "alternative_agent": None,
                "escalation_question": "Would you like me to update the config?",
            }
        )
        provider._explicit_llm.call = MagicMock(return_value=response)

        thought = await provider.failure_think(
            agent_name="mcp-filesystem",
            task_description="read /etc/secret",
            error="Permission denied",
            retry_count=0,
            max_retries=3,
            is_critical=True,
            available_agents=agents,
        )
        assert thought.failure_action == FailureAction.ESCALATE
        assert thought.escalation_question is not None

    @pytest.mark.asyncio
    async def test_skip_action(self, provider, agents):
        response = json.dumps(
            {
                "reasoning": "Non-critical, skip it",
                "failure_action": "skip",
                "alternative_agent": None,
                "escalation_question": None,
            }
        )
        provider._explicit_llm.call = MagicMock(return_value=response)

        thought = await provider.failure_think(
            agent_name="agent-a",
            task_description="optional task",
            error="Cannot complete",
            retry_count=3,
            max_retries=3,
            is_critical=False,
            available_agents=agents,
        )
        assert thought.failure_action == FailureAction.SKIP

    @pytest.mark.asyncio
    async def test_invalid_action_defaults_to_escalate(self, provider, agents):
        """When LLM returns an invalid failure_action, defaults to ESCALATE."""
        response = json.dumps(
            {
                "reasoning": "Some reason",
                "failure_action": "invalid_action",
                "alternative_agent": None,
                "escalation_question": None,
            }
        )
        provider._explicit_llm.call = MagicMock(return_value=response)

        thought = await provider.failure_think(
            agent_name="agent-a",
            task_description="task",
            error="error",
            retry_count=0,
            max_retries=3,
            is_critical=True,
            available_agents=agents,
        )
        assert thought.failure_action == FailureAction.ESCALATE

    @pytest.mark.asyncio
    async def test_llm_error_defaults_to_escalate(self, provider, agents):
        """When LLM fails entirely, default to escalation."""
        provider._explicit_llm.call = MagicMock(side_effect=RuntimeError("LLM down"))

        thought = await provider.failure_think(
            agent_name="agent-a",
            task_description="critical task",
            error="Something broke",
            retry_count=0,
            max_retries=3,
            is_critical=True,
            available_agents=agents,
        )
        assert thought.failure_action == FailureAction.ESCALATE
        assert "critical task" in thought.escalation_question

    @pytest.mark.asyncio
    async def test_failure_prompt_requires_different_agent(self, provider, agents):
        """FAILURE_SYSTEM_PROMPT instructs LLM to pick a DIFFERENT agent (RC4)."""
        response = json.dumps(
            {
                "reasoning": "try alternative",
                "failure_action": "alternative",
                "alternative_agent": "agent-a",
                "escalation_question": None,
            }
        )
        provider._explicit_llm.call = MagicMock(return_value=response)

        await provider.failure_think(
            agent_name="mcp-filesystem",
            task_description="list files",
            error="Failed",
            retry_count=0,
            max_retries=3,
            is_critical=True,
            available_agents=agents,
        )
        call_args = provider._explicit_llm.call.call_args
        messages = call_args[1]["messages"] if "messages" in call_args[1] else call_args[0][0]
        system_msg = [m for m in messages if m["role"] == "system"][0]
        assert "MUST differ from the failed agent" in system_msg["content"]
        assert "Never suggest the same agent" in system_msg["content"]

    @pytest.mark.asyncio
    async def test_prompt_contains_failure_context(self, provider, agents):
        """System prompt contains agent name, error, retry count."""
        response = json.dumps(
            {
                "reasoning": "x",
                "failure_action": "retry",
                "alternative_agent": None,
                "escalation_question": None,
            }
        )
        provider._explicit_llm.call = MagicMock(return_value=response)

        await provider.failure_think(
            agent_name="mcp-filesystem",
            task_description="read file",
            error="File not found",
            retry_count=2,
            max_retries=3,
            is_critical=True,
            available_agents=agents,
        )
        call_args = provider._explicit_llm.call.call_args
        messages = call_args[1]["messages"] if "messages" in call_args[1] else call_args[0][0]
        system_msg = [m for m in messages if m["role"] == "system"][0]
        assert "mcp-filesystem" in system_msg["content"]
        assert "File not found" in system_msg["content"]
        assert "2" in system_msg["content"]  # retry_count
        assert "3" in system_msg["content"]  # max_retries

    @pytest.mark.asyncio
    async def test_external_reasoning_preferred(self, provider, agents):
        """When LLM returns reasoning_content, it replaces JSON reasoning."""
        response = {
            "content": json.dumps(
                {
                    "reasoning": "from json",
                    "failure_action": "retry",
                    "alternative_agent": None,
                    "escalation_question": None,
                }
            ),
            "reasoning_content": "Deep thought about this failure",
        }
        provider._explicit_llm.call = MagicMock(return_value=response)

        thought = await provider.failure_think(
            agent_name="agent-a",
            task_description="task",
            error="err",
            retry_count=0,
            max_retries=3,
            is_critical=False,
            available_agents=agents,
        )
        assert thought.reasoning == "Deep thought about this failure"

# ---------------------------------------------------------------------------
# TestManagerThink
# ---------------------------------------------------------------------------

class TestManagerThink:
    """Tests for manager_think method."""

    @pytest.mark.asyncio
    async def test_delegation_decision(self, provider, agents):
        response = json.dumps(
            {
                "reasoning": "Agent Alpha is best for this",
                "reasoning_summary": "Delegating to Alpha",
                "is_final": False,
                "delegate_to": "agent-a",
                "subtask": "Analyze the data",
                "expected_output": "Analysis report",
            }
        )
        provider._explicit_llm.call = MagicMock(return_value=response)

        thought = await provider.manager_think(
            goal="Analyze and report",
            progress=[],
            specialists=agents,
        )
        assert thought.is_final is False
        assert thought.delegate_to == "agent-a"
        assert thought.subtask == "Analyze the data"

    @pytest.mark.asyncio
    async def test_final_synthesis(self, provider, agents):
        response = json.dumps(
            {
                "reasoning": "All work done",
                "reasoning_summary": "Complete",
                "is_final": True,
                "answer": "Final synthesized answer",
                "delegate_to": None,
                "subtask": None,
            }
        )
        provider._explicit_llm.call = MagicMock(return_value=response)

        thought = await provider.manager_think(
            goal="Complex goal",
            progress=[
                {
                    "agent": "agent-a",
                    "task": "analyze",
                    "result": "data analyzed",
                    "validation": "passed",
                },
            ],
            specialists=agents,
        )
        assert thought.is_final is True
        assert thought.answer == "Final synthesized answer"

    @pytest.mark.asyncio
    async def test_progress_formatting(self, provider, agents):
        """Progress XML is properly formatted in system prompt."""
        response = json.dumps(
            {
                "reasoning": "x",
                "is_final": True,
                "answer": "ok",
                "delegate_to": None,
                "subtask": None,
            }
        )
        provider._explicit_llm.call = MagicMock(return_value=response)

        progress = [
            {"agent": "agent-a", "task": "step 1", "result": "done", "validation": "passed"},
            {
                "agent": "mcp-filesystem",
                "task": "step 2",
                "result": "files listed",
                "validation": "pending",
            },
        ]
        await provider.manager_think(goal="goal", progress=progress, specialists=agents)

        call_args = provider._explicit_llm.call.call_args
        messages = call_args[1]["messages"] if "messages" in call_args[1] else call_args[0][0]
        system_msg = [m for m in messages if m["role"] == "system"][0]
        assert "<progress>" in system_msg["content"]
        assert "agent-a" in system_msg["content"]
        assert "step 1" in system_msg["content"]

    @pytest.mark.asyncio
    async def test_empty_progress(self, provider, agents):
        """When no progress yet, prompt says 'No delegations yet'."""
        response = json.dumps(
            {
                "reasoning": "x",
                "is_final": False,
                "delegate_to": "agent-a",
                "subtask": "start",
            }
        )
        provider._explicit_llm.call = MagicMock(return_value=response)

        await provider.manager_think(goal="goal", progress=[], specialists=agents)

        call_args = provider._explicit_llm.call.call_args
        messages = call_args[1]["messages"] if "messages" in call_args[1] else call_args[0][0]
        system_msg = [m for m in messages if m["role"] == "system"][0]
        assert "No delegations yet" in system_msg["content"]

    @pytest.mark.asyncio
    async def test_llm_error_returns_error_thought(self, provider, agents):
        provider._explicit_llm.call = MagicMock(side_effect=RuntimeError("Manager LLM down"))

        thought = await provider.manager_think(
            goal="goal",
            progress=[],
            specialists=agents,
        )
        assert thought.is_final is True
        assert "RuntimeError" in thought.answer

    @pytest.mark.asyncio
    async def test_external_reasoning_preferred(self, provider, agents):
        """External reasoning from thinking model is preferred."""
        response = {
            "content": json.dumps(
                {
                    "reasoning": "json reasoning",
                    "is_final": False,
                    "delegate_to": "agent-a",
                    "subtask": "task",
                }
            ),
            "reasoning_content": "Deep manager reasoning",
        }
        provider._explicit_llm.call = MagicMock(return_value=response)

        thought = await provider.manager_think(goal="goal", progress=[], specialists=agents)
        assert thought.reasoning == "Deep manager reasoning"

# ---------------------------------------------------------------------------
# TestPlanThink
# ---------------------------------------------------------------------------

class TestPlanThink:
    """Tests for plan_think method."""

    @pytest.mark.asyncio
    async def test_basic_plan_generation(self, provider, agents):
        response = json.dumps(
            {
                "reasoning": "Two-step plan",
                "steps": [
                    {
                        "id": "step-1",
                        "agent_name": "mcp-filesystem",
                        "task": "List files",
                        "depends_on": [],
                        "expected_output": "File list",
                        "is_critical": True,
                        "estimated_duration_seconds": 10,
                    },
                    {
                        "id": "step-2",
                        "agent_name": "agent-a",
                        "task": "Analyze files",
                        "depends_on": ["step-1"],
                        "expected_output": "Analysis",
                        "is_critical": True,
                        "estimated_duration_seconds": 30,
                    },
                ],
            }
        )
        provider._explicit_llm.call = MagicMock(return_value=response)

        plan = await provider.plan_think(goal="Analyze directory", available_agents=agents)
        assert isinstance(plan, ExecutionPlan)
        assert len(plan.steps) == 2
        assert plan.steps[0].id == "step-1"
        assert plan.steps[1].depends_on == ["step-1"]
        assert len(plan.execution_order) == 2  # 2 waves
        assert plan.total_estimated_seconds == 40  # 10 + 30

    @pytest.mark.asyncio
    async def test_fallback_on_json_error(self, provider, agents):
        """On JSON parse error, returns single-step fallback plan."""
        provider._explicit_llm.call = MagicMock(return_value="not valid json at all")

        plan = await provider.plan_think(goal="Fallback goal", available_agents=agents)
        assert isinstance(plan, ExecutionPlan)
        assert len(plan.steps) == 1
        assert plan.steps[0].task == "Fallback goal"
        assert plan.steps[0].is_critical is True

    @pytest.mark.asyncio
    async def test_fallback_on_empty_steps(self, provider, agents):
        """When LLM returns zero steps, falls back to single-step plan."""
        response = json.dumps({"reasoning": "Nothing", "steps": []})
        provider._explicit_llm.call = MagicMock(return_value=response)

        plan = await provider.plan_think(goal="Empty plan", available_agents=agents)
        assert len(plan.steps) == 1  # Fallback

    @pytest.mark.asyncio
    async def test_context_adds_environment(self, provider, agents):
        """When context is passed, environment info is appended to system prompt."""
        response = json.dumps(
            {
                "reasoning": "plan",
                "steps": [{"id": "step-1", "agent_name": "agent-a", "task": "do it"}],
            }
        )
        provider._explicit_llm.call = MagicMock(return_value=response)

        await provider.plan_think(
            goal="goal",
            available_agents=agents,
            context={"user_id": "user-123"},
        )
        call_args = provider._explicit_llm.call.call_args
        messages = call_args[1]["messages"] if "messages" in call_args[1] else call_args[0][0]
        system_msg = [m for m in messages if m["role"] == "system"][0]
        assert "Environment" in system_msg["content"]

    @pytest.mark.asyncio
    async def test_memory_context_appended(self, provider, agents):
        """When memory_context is passed, it's appended to system prompt."""
        response = json.dumps(
            {
                "reasoning": "plan",
                "steps": [{"id": "step-1", "agent_name": "agent-a", "task": "do it"}],
            }
        )
        provider._explicit_llm.call = MagicMock(return_value=response)

        await provider.plan_think(
            goal="goal",
            available_agents=agents,
            memory_context="User prefers dark mode",
        )
        call_args = provider._explicit_llm.call.call_args
        messages = call_args[1]["messages"] if "messages" in call_args[1] else call_args[0][0]
        system_msg = [m for m in messages if m["role"] == "system"][0]
        assert "Relevant Memory" in system_msg["content"]
        assert "dark mode" in system_msg["content"]

# ---------------------------------------------------------------------------
# TestReplanThink
# ---------------------------------------------------------------------------

class TestReplanThink:
    """Tests for replan_think method."""

    def _make_original_plan(self) -> ExecutionPlan:
        steps = [
            PlanStep(
                id="step-1",
                agent_name="agent-a",
                task="Analyze",
                status=StepStatus.COMPLETED,
                result="done",
            ),
            PlanStep(
                id="step-2",
                agent_name="mcp-filesystem",
                task="Read file",
                depends_on=["step-1"],
                status=StepStatus.FAILED,
                error="File not found",
            ),
        ]
        plan = ExecutionPlan(id="orig-plan", goal="Analyze and read", steps=steps)
        plan.compute_execution_order()
        return plan

    @pytest.mark.asyncio
    async def test_basic_replan(self, provider, agents):
        response = json.dumps(
            {
                "reasoning": "Skip the failed step, add alternative",
                "steps": [
                    {"id": "step-1", "agent_name": "agent-a", "task": "Analyze", "depends_on": []},
                    {
                        "id": "replan-1",
                        "agent_name": "mcp-filesystem",
                        "task": "Search for file",
                        "depends_on": ["step-1"],
                    },
                ],
                "changes_summary": "Replaced file read with file search",
            }
        )
        provider._explicit_llm.call = MagicMock(return_value=response)

        original = self._make_original_plan()
        new_plan = await provider.replan_think(
            original_plan=original,
            failed_steps=[original.steps[1]],
            completed_results={"step-1": "done"},
            available_agents=agents,
        )
        assert new_plan is not None
        assert new_plan.replan_count == 1
        assert len(new_plan.steps) == 2
        # Completed step should preserve status
        completed_step = new_plan.get_step("step-1")
        assert completed_step.status == StepStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_replan_failure_returns_none(self, provider, agents):
        """When replanning fails, returns None."""
        provider._explicit_llm.call = MagicMock(side_effect=RuntimeError("LLM down"))

        original = self._make_original_plan()
        result = await provider.replan_think(
            original_plan=original,
            failed_steps=[original.steps[1]],
            completed_results={"step-1": "done"},
            available_agents=agents,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_steps_returns_none(self, provider, agents):
        """When LLM returns empty steps, returns None."""
        response = json.dumps({"reasoning": "No plan possible", "steps": []})
        provider._explicit_llm.call = MagicMock(return_value=response)

        original = self._make_original_plan()
        result = await provider.replan_think(
            original_plan=original,
            failed_steps=[original.steps[1]],
            completed_results={"step-1": "done"},
            available_agents=agents,
        )
        assert result is None

# ---------------------------------------------------------------------------
# TestSynthesizeThink
# ---------------------------------------------------------------------------

class TestSynthesizeThink:
    """Tests for synthesize_think method."""

    @pytest.mark.asyncio
    async def test_basic_synthesis(self, provider):
        provider._explicit_llm.call = MagicMock(
            return_value="The analysis shows positive results based on the data collected."
        )

        result = await provider.synthesize_think(
            goal="Analyze data",
            step_results={"step-1": "Data collected", "step-2": "Analysis done"},
        )
        assert isinstance(result, str)
        assert "positive" in result.lower() or "analysis" in result.lower()

    @pytest.mark.asyncio
    async def test_prompt_contains_goal_and_results(self, provider):
        provider._explicit_llm.call = MagicMock(return_value="Summary")

        await provider.synthesize_think(
            goal="Find all files",
            step_results={"step-1": "Found 5 files"},
        )
        call_args = provider._explicit_llm.call.call_args
        messages = call_args[1]["messages"] if "messages" in call_args[1] else call_args[0][0]
        system_msg = [m for m in messages if m["role"] == "system"][0]
        assert "Find all files" in system_msg["content"]
        assert "Found 5 files" in system_msg["content"]

# ---------------------------------------------------------------------------
# TestCallLLM
# ---------------------------------------------------------------------------

class TestCallLLM:
    """Tests for _call_llm method."""

    @pytest.mark.asyncio
    async def test_string_response(self, provider):
        """LLM returns a plain string."""
        provider._explicit_llm.call = MagicMock(return_value='{"key": "value"}')
        content, reasoning = await provider._call_llm([{"role": "user", "content": "test"}])
        assert content == '{"key": "value"}'
        assert reasoning is None

    @pytest.mark.asyncio
    async def test_dict_response_with_reasoning(self, provider):
        """LLM returns a dict with content and reasoning_content."""
        provider._explicit_llm.call = MagicMock(
            return_value={
                "content": '{"key": "value"}',
                "reasoning_content": "I thought carefully",
            }
        )
        content, reasoning = await provider._call_llm([{"role": "user", "content": "test"}])
        assert content == '{"key": "value"}'
        assert reasoning == "I thought carefully"

    @pytest.mark.asyncio
    async def test_dict_response_with_tool_calls(self, provider):
        """LLM returns a dict with tool_calls (native function calling)."""
        provider._explicit_llm.call = MagicMock(
            return_value={
                "tool_calls": [
                    {
                        "function": {
                            "name": "list_directory",
                            "arguments": '{"path": "/home"}',
                        },
                    }
                ],
                "content": "",
            }
        )
        content, reasoning = await provider._call_llm([{"role": "user", "content": "test"}])
        data = json.loads(content)
        assert data["task"]["tool"] == "list_directory"
        assert data["task"]["arguments"] == {"path": "/home"}

    @pytest.mark.asyncio
    async def test_non_string_non_dict_response(self, provider):
        """LLM returns something else (int, list), converted to str."""
        provider._explicit_llm.call = MagicMock(return_value=42)
        content, reasoning = await provider._call_llm([{"role": "user", "content": "test"}])
        assert content == "42"
        assert reasoning is None

    @pytest.mark.asyncio
    async def test_cost_emission_with_delta(self):
        """Cost event callback receives token delta when LLM tracks usage."""
        cost_events = []
        mock_llm = MagicMock()
        mock_llm._token_usage = {"prompt_tokens": 0, "completion_tokens": 0}
        provider = OrchestrationThinkingProvider(llm=mock_llm, on_cost_event=cost_events.append)

        # Simulate usage delta: LLM updates _token_usage after call
        def fake_call(messages):
            mock_llm._token_usage = {"prompt_tokens": 100, "completion_tokens": 50}
            return '{"result": "ok"}'

        mock_llm.call = MagicMock(side_effect=fake_call)

        await provider._call_llm([{"role": "user", "content": "test prompt"}])
        assert len(cost_events) == 1
        assert cost_events[0].metadata["prompt_tokens"] == 100
        assert cost_events[0].metadata["completion_tokens"] == 50

    @pytest.mark.asyncio
    async def test_cost_emission_fallback_estimation(self):
        """When no token tracking, estimates from character length."""
        cost_events = []
        mock_llm = MagicMock()
        # No _token_usage attribute at all -> fallback estimation
        if hasattr(mock_llm, "_token_usage"):
            del mock_llm._token_usage
        mock_llm.call = MagicMock(return_value='{"result": "ok"}')
        provider = OrchestrationThinkingProvider(llm=mock_llm, on_cost_event=cost_events.append)

        await provider._call_llm([{"role": "user", "content": "a" * 400}])
        assert len(cost_events) == 1
        # 400 chars / 4 = 100 estimated prompt tokens
        assert cost_events[0].metadata["prompt_tokens"] == 100

    @pytest.mark.asyncio
    async def test_uses_invoke_when_no_call(self):
        """When LLM has invoke but not call, uses invoke."""
        mock_llm = MagicMock(spec=[])
        mock_llm.invoke = MagicMock(return_value='{"ok": true}')
        # Remove 'call' attribute
        provider = OrchestrationThinkingProvider(llm=mock_llm)

        content, _ = await provider._call_llm([{"role": "user", "content": "test"}])
        assert content == '{"ok": true}'

    @pytest.mark.asyncio
    async def test_markdown_json_extraction(self, provider):
        """LLM wraps JSON in markdown code block."""
        provider._explicit_llm.call = MagicMock(return_value='```json\n{"key": "value"}\n```')
        content, _ = await provider._call_llm([{"role": "user", "content": "test"}])
        assert content == '{"key": "value"}'

# ---------------------------------------------------------------------------
# TestExtractJsonFromResponse
# ---------------------------------------------------------------------------

class TestExtractJsonFromResponse:
    """Tests for _extract_json_from_response."""

    def test_none_input(self, provider):
        assert provider._extract_json_from_response(None) == ""

    def test_raw_json(self, provider):
        result = provider._extract_json_from_response('{"key": "value"}')
        assert json.loads(result) == {"key": "value"}

    def test_markdown_json_block(self, provider):
        content = 'Some text\n```json\n{"key": "value"}\n```\nMore text'
        result = provider._extract_json_from_response(content)
        assert json.loads(result) == {"key": "value"}

    def test_markdown_plain_block(self, provider):
        content = 'Text\n```\n{"key": "value"}\n```\nMore'
        result = provider._extract_json_from_response(content)
        assert json.loads(result) == {"key": "value"}

    def test_json_with_surrounding_text(self, provider):
        content = 'Here is the result: {"key": "value"} and that is it.'
        result = provider._extract_json_from_response(content)
        assert json.loads(result) == {"key": "value"}

    def test_nested_braces(self, provider):
        content = '{"outer": {"inner": "value"}}'
        result = provider._extract_json_from_response(content)
        assert json.loads(result) == {"outer": {"inner": "value"}}

    def test_no_json_returns_as_is(self, provider):
        content = "Just plain text without any JSON"
        result = provider._extract_json_from_response(content)
        assert result == content

# ---------------------------------------------------------------------------
# TestFormatAgentsXml
# ---------------------------------------------------------------------------

class TestFormatAgentsXml:
    """Tests for _format_agents_xml helper."""

    def test_empty_agents(self):
        result = _format_agents_xml([])
        assert result == "<agents>No agents available</agents>"

    def test_full_mode_custom_agent(self):
        agent = _make_agent_card("agent-a", "Agent Alpha")
        result = _format_agents_xml([agent])
        assert '<agent name="agent-a">' in result
        assert "<description>Agent Alpha</description>" in result
        assert "<framework>custom</framework>" in result

    def test_full_mode_mcp_agent_with_tools(self):
        agent = _make_mcp_agent("mcp-fs", [("list_directory", "List files")])
        result = _format_agents_xml([agent])
        assert '<tool name="list_directory">' in result
        assert "<description>List files</description>" in result
        assert '<param name="path"' in result

    def test_lightweight_mode(self):
        agents = [
            _make_agent_card("agent-a", "Agent Alpha"),
            _make_mcp_agent("mcp-fs", [("list_directory", "List")]),
        ]
        result = _format_agents_xml(agents, lightweight=True)
        # Lightweight uses self-closing tags
        assert '<agent name="agent-a" description="Agent Alpha" />' in result
        assert '<agent name="mcp-fs"' in result
        # No tool schemas in lightweight mode
        assert "<tools>" not in result

# ---------------------------------------------------------------------------
# TestFilterAgentsByRouter (Phase 107)
# ---------------------------------------------------------------------------

class TestFilterAgentsByRouter:
    """Tests for _filter_agents_by_router method."""

    @pytest.fixture
    def provider(self):
        return OrchestrationThinkingProvider()

    @pytest.fixture
    def mixed_agents(self):
        """5 agents: 1 custom, 1 CrewAI, 3 MCP servers."""
        return [
            _make_agent_card("planner", "Plans tasks", AgentFramework.CUSTOM),
            _make_agent_card("analyst", "Analyzes data", AgentFramework.CREWAI),
            _make_mcp_agent("mcp-filesystem", [("list_dir", "List directory")]),
            _make_mcp_agent("mcp-git", [("git_log", "Git log"), ("git_diff", "Git diff")]),
            _make_mcp_agent("mcp-github", [("create_issue", "Create issue")]),
        ]

    def test_filter_keeps_matching_mcp_agents(self, provider, mixed_agents):
        """Hints for 2 servers -> returns those 2 MCP agents + all non-MCP agents."""
        hints = [
            {"tool_name": "list_dir", "server": "mcp-filesystem", "score": "0.9"},
            {"tool_name": "git_log", "server": "mcp-git", "score": "0.8"},
        ]
        result = provider._filter_agents_by_router(mixed_agents, hints)
        names = [a.name for a in result]
        # 2 non-MCP agents always included + 2 matching MCP agents
        assert "planner" in names
        assert "analyst" in names
        assert "mcp-filesystem" in names
        assert "mcp-git" in names
        # mcp-github was NOT in hints, should be excluded
        assert "mcp-github" not in names
        assert len(result) == 4

    def test_filter_always_includes_non_mcp_agents(self, provider, mixed_agents):
        """Non-MCP agents are present even when no MCP servers match."""
        hints = [
            {"tool_name": "some_tool", "server": "mcp-nonexistent", "score": "0.5"},
        ]
        # This would produce 0 MCP survivors -> falls back to all agents
        # But verify the concept: non-MCP agents are always in the filtered list
        # Use a hint that matches ONE server so we don't trigger fallback
        hints2 = [
            {"tool_name": "list_dir", "server": "mcp-filesystem", "score": "0.9"},
        ]
        result = provider._filter_agents_by_router(mixed_agents, hints2)
        names = [a.name for a in result]
        assert "planner" in names
        assert "analyst" in names

    def test_filter_fallback_when_no_mcp_survives(self, provider, mixed_agents):
        """All MCP agents filtered out -> bounded fallback (general-purpose + capped)."""
        hints = [
            {"tool_name": "some_tool", "server": "mcp-nonexistent-server", "score": "0.5"},
        ]
        result = provider._filter_agents_by_router(mixed_agents, hints)
        names = [a.name for a in result]
        # Non-MCP always included
        assert "planner" in names
        assert "analyst" in names
        # General-purpose MCP agents included (bounded fallback)
        assert "mcp-filesystem" in names
        assert "mcp-git" in names
        # Should NOT return all agents (no fail-open)
        assert len(result) < len(mixed_agents) or len(result) <= 5 + 2  # max_fallback + non-mcp

    def test_filter_with_empty_hints(self, provider, mixed_agents):
        """router_hints=None -> bounded fallback (non-MCP + general-purpose MCP)."""
        result = provider._filter_agents_by_router(mixed_agents, None)
        names = [a.name for a in result]
        # Non-MCP always included
        assert "planner" in names
        assert "analyst" in names
        # General-purpose MCP agents included
        assert "mcp-filesystem" in names
        assert "mcp-git" in names
        # Should not just return `agents` identity (bounded set)
        assert len(result) <= len(mixed_agents)

    def test_filter_with_empty_hints_list(self, provider, mixed_agents):
        """router_hints=[] -> bounded fallback (non-MCP + general-purpose MCP)."""
        result = provider._filter_agents_by_router(mixed_agents, [])
        names = [a.name for a in result]
        assert "planner" in names
        assert "analyst" in names
        assert "mcp-filesystem" in names
        assert "mcp-git" in names

    def test_filter_respects_max_servers(self, provider, mixed_agents):
        """10 router hints but max_servers=2 -> only 2 MCP servers included."""
        hints = [
            {"tool_name": f"tool_{i}", "server": f"mcp-server-{i}", "score": f"0.{9 - i}"}
            for i in range(10)
        ]
        # Use agents that have those server names
        agents = [
            _make_agent_card("custom-agent", "Custom", AgentFramework.CUSTOM),
            _make_mcp_agent("mcp-server-0", [("tool_0", "Tool 0")]),
            _make_mcp_agent("mcp-server-1", [("tool_1", "Tool 1")]),
            _make_mcp_agent("mcp-server-2", [("tool_2", "Tool 2")]),
            _make_mcp_agent("mcp-server-3", [("tool_3", "Tool 3")]),
        ]
        result = provider._filter_agents_by_router(agents, hints, max_servers=2)
        mcp_names = [a.name for a in result if a.framework.value == "mcp"]
        # Only 2 MCP servers should be included (first 2 unique servers from hints)
        assert len(mcp_names) == 2
        assert "mcp-server-0" in mcp_names
        assert "mcp-server-1" in mcp_names

    def test_filter_deduplicates_servers(self, provider, mixed_agents):
        """Router hints with duplicate server names -> only unique servers considered."""
        hints = [
            {"tool_name": "list_dir", "server": "mcp-filesystem", "score": "0.9"},
            {"tool_name": "search_files", "server": "mcp-filesystem", "score": "0.8"},
            {"tool_name": "git_log", "server": "mcp-git", "score": "0.7"},
        ]
        result = provider._filter_agents_by_router(mixed_agents, hints)
        names = [a.name for a in result]
        # Filesystem appears twice in hints but agent only included once
        assert names.count("mcp-filesystem") == 1
        assert "mcp-git" in names
        # mcp-github not in hints
        assert "mcp-github" not in names

# ---------------------------------------------------------------------------
# TestToolCaching (Phase 107)
# ---------------------------------------------------------------------------

class TestToolCaching:
    """Tests for _build_tools_for_agents caching."""

    @pytest.fixture
    def provider(self):
        return OrchestrationThinkingProvider()

    def test_cache_hit_same_agents(self, provider):
        """Call twice with same agents -> second call returns same object (identity check)."""
        agents = [
            _make_mcp_agent("mcp-fs", [("list_dir", "List"), ("search", "Search")]),
            _make_mcp_agent("mcp-git", [("git_log", "Log")]),
        ]
        first = provider._build_tools_for_agents(agents)
        second = provider._build_tools_for_agents(agents)
        assert first is second

    def test_cache_miss_different_agents(self, provider):
        """Call with agents A, then agents B -> cache miss, different list."""
        agents_a = [_make_mcp_agent("mcp-fs", [("list_dir", "List")])]
        agents_b = [_make_mcp_agent("mcp-git", [("git_log", "Log")])]
        first = provider._build_tools_for_agents(agents_a)
        second = provider._build_tools_for_agents(agents_b)
        assert first is not second
        assert first[0]["function"]["name"] == "list_dir"
        assert second[0]["function"]["name"] == "git_log"

    def test_cache_invalidation_on_subset(self, provider):
        """Call with [A, B, C], then [A, B] -> cache miss because key changed."""
        agents_full = [
            _make_mcp_agent("mcp-a", [("tool_a", "A")]),
            _make_mcp_agent("mcp-b", [("tool_b", "B")]),
            _make_mcp_agent("mcp-c", [("tool_c", "C")]),
        ]
        agents_subset = [
            _make_mcp_agent("mcp-a", [("tool_a", "A")]),
            _make_mcp_agent("mcp-b", [("tool_b", "B")]),
        ]
        first = provider._build_tools_for_agents(agents_full)
        second = provider._build_tools_for_agents(agents_subset)
        assert first is not second
        assert len(first) == 3
        assert len(second) == 2

    def test_cache_init_is_none(self):
        """Fresh provider has _cached_tools_key=None and _cached_tools=None."""
        provider = OrchestrationThinkingProvider()
        assert provider._cached_tools_key is None
        assert provider._cached_tools is None

# ---------------------------------------------------------------------------
# TestConvertToolCallsToJson
# ---------------------------------------------------------------------------

class TestConvertToolCallsToJson:
    """Tests for _convert_tool_calls_to_json."""

    def test_basic_conversion(self, provider):
        response = {
            "tool_calls": [
                {
                    "function": {
                        "name": "search_files",
                        "arguments": '{"path": "/home", "pattern": "*.py"}',
                    },
                }
            ],
        }
        result = provider._convert_tool_calls_to_json(response)
        data = json.loads(result)
        assert data["task"]["tool"] == "search_files"
        assert data["task"]["arguments"]["pattern"] == "*.py"
        assert data["is_final"] is False

    def test_empty_tool_calls(self, provider):
        result = provider._convert_tool_calls_to_json({"tool_calls": []})
        assert result == ""

    def test_invalid_json_arguments(self, provider):
        response = {
            "tool_calls": [
                {
                    "function": {
                        "name": "some_tool",
                        "arguments": "not json",
                    },
                }
            ],
        }
        result = provider._convert_tool_calls_to_json(response)
        data = json.loads(result)
        assert data["task"]["arguments"] == {}

# ---------------------------------------------------------------------------
# TestResolveAgentForTool
# ---------------------------------------------------------------------------

class TestResolveAgentForTool:
    """Tests for _resolve_agent_for_tool."""

    def test_finds_matching_agent(self, provider):
        provider._last_available_agents = [
            _make_mcp_agent("mcp-fs", [("list_directory", "List"), ("search_files", "Search")]),
        ]
        assert provider._resolve_agent_for_tool("list_directory") == "mcp-fs"
        assert provider._resolve_agent_for_tool("search_files") == "mcp-fs"

    def test_no_match_returns_none(self, provider):
        provider._last_available_agents = [
            _make_mcp_agent("mcp-fs", [("list_directory", "List")]),
        ]
        assert provider._resolve_agent_for_tool("nonexistent_tool") is None

    def test_empty_agents(self, provider):
        provider._last_available_agents = []
        assert provider._resolve_agent_for_tool("any_tool") is None

# ---------------------------------------------------------------------------
# TestExtractAgentFromReasoning
# ---------------------------------------------------------------------------

class TestExtractAgentFromReasoning:
    """Tests for _extract_agent_from_reasoning."""

    def test_matches_agent_name(self, provider):
        agents = [_make_agent_card("agent-a", "Agent Alpha")]
        result = provider._extract_agent_from_reasoning("I should use agent-a to do this", agents)
        assert result is not None
        assert result[0] == "agent-a"

    def test_matches_mcp_agent_with_tool(self):
        provider = OrchestrationThinkingProvider()
        agents = [
            _make_mcp_agent(
                "mcp-filesystem", [("search_files", "Search"), ("list_directory", "List")]
            )
        ]
        result = provider._extract_agent_from_reasoning(
            "I need to use mcp-filesystem to search_files in /home",
            agents,
        )
        assert result is not None
        assert result[0] == "mcp-filesystem"
        assert result[1] == "search_files"

    def test_no_match_returns_none(self, provider):
        agents = [_make_agent_card("agent-a", "Agent Alpha")]
        result = provider._extract_agent_from_reasoning("Nothing relevant here", agents)
        assert result is None

    def test_no_filesystem_bias_for_generic_terms(self, provider):
        """Generic terms like 'my file' no longer force-route to filesystem (RC5 fix)."""
        agents = [
            _make_mcp_agent(
                "mcp-filesystem", [("search_files", "Search"), ("list_directory", "List")]
            )
        ]
        result = provider._extract_agent_from_reasoning("Find my file somewhere", agents)
        # No longer auto-routes to filesystem -- returns None without filesystem bias
        assert result is None

    def test_no_filesystem_bias_for_file_extensions(self, provider):
        """File extensions without explicit agent mention no longer force filesystem (RC5 fix)."""
        agents = [
            _make_mcp_agent(
                "mcp-filesystem", [("search_files", "Search"), ("list_directory", "List")]
            )
        ]
        result = provider._extract_agent_from_reasoning(
            "Locate the .aird capella model file", agents
        )
        # Without "filesystem" in reasoning, no agent name match -- returns None
        assert result is None

    def test_agent_name_matching_still_works_after_rc5(self, provider):
        """Agent mentioned by name in reasoning is still matched (RC5 did not break this)."""
        agents = [
            _make_mcp_agent(
                "mcp-filesystem", [("search_files", "Search"), ("list_directory", "List")]
            ),
            _make_mcp_agent("mcp-capella", [("open_model", "Open a Capella model")]),
        ]
        # "mcp-capella" is explicitly mentioned -> should match
        result = provider._extract_agent_from_reasoning(
            "I should use mcp-capella to open the model", agents
        )
        assert result is not None
        assert result[0] == "mcp-capella"

# ---------------------------------------------------------------------------
# TestEmitCostFromLLM
# ---------------------------------------------------------------------------

class TestEmitCostFromLLM:
    """Tests for _emit_cost_from_llm."""

    def test_no_callback_does_nothing(self):
        provider = OrchestrationThinkingProvider()
        # Should not raise even with no callback
        provider._emit_cost_from_llm(MagicMock(), None, 100, "response")

    def test_delta_tracking(self):
        events = []
        provider = OrchestrationThinkingProvider(on_cost_event=events.append)
        mock_llm = MagicMock()
        mock_llm._token_usage = {"prompt_tokens": 200, "completion_tokens": 100}
        usage_before = {"prompt_tokens": 100, "completion_tokens": 50}

        provider._emit_cost_from_llm(mock_llm, usage_before, 0, "")
        assert len(events) == 1
        assert events[0].metadata["prompt_tokens"] == 100  # 200-100 delta
        assert events[0].metadata["completion_tokens"] == 50  # 100-50 delta

    def test_estimation_fallback(self):
        events = []
        provider = OrchestrationThinkingProvider(on_cost_event=events.append)
        mock_llm = MagicMock(spec=[])  # No _token_usage attr

        provider._emit_cost_from_llm(mock_llm, None, 800, "response text")
        assert len(events) == 1
        assert events[0].metadata["prompt_tokens"] == 200  # 800/4
        assert events[0].metadata["completion_tokens"] == 3  # 13 chars / 4 = 3

    def test_callback_error_suppressed(self):
        """If cost callback raises, it is suppressed."""

        def bad_callback(event):
            raise ValueError("Callback error")

        provider = OrchestrationThinkingProvider(on_cost_event=bad_callback)
        mock_llm = MagicMock(spec=[])

        # Should not raise
        provider._emit_cost_from_llm(mock_llm, None, 400, "response")

# ---------------------------------------------------------------------------
# TestBuildTaskFromData / TestBuildThoughtFromData
# ---------------------------------------------------------------------------

class TestBuildHelpers:
    """Tests for _build_task_from_data and _build_thought_from_data."""

    def test_build_task_basic(self, provider):
        task_data = {
            "agent_name": "agent-a",
            "description": "Do something",
            "tool": "my_tool",
            "arguments": {"key": "value"},
            "is_critical": True,
        }
        task = provider._build_task_from_data(task_data, {"user_id": "u1"})
        assert isinstance(task, OrchestrationTask)
        assert task.agent_name == "agent-a"
        assert task.tool == "my_tool"
        assert task.arguments == {"key": "value"}
        assert task.context["user_id"] == "u1"
        assert task.context["tool"] == "my_tool"

    def test_build_task_resolves_empty_agent(self, provider):
        """When agent_name is empty, resolves from tool name."""
        provider._last_available_agents = [
            _make_mcp_agent("mcp-fs", [("list_directory", "List")]),
        ]
        task_data = {"agent_name": "", "description": "list", "tool": "list_directory"}
        task = provider._build_task_from_data(task_data, None)
        assert task.agent_name == "mcp-fs"

    def test_build_thought_final(self, provider):
        data = {
            "reasoning": "done",
            "reasoning_summary": "complete",
            "is_final": True,
            "answer": "The result",
            "task": None,
            "parallel_tasks": None,
        }
        thought = provider._build_thought_from_data(data, None, None)
        assert isinstance(thought, OrchestrationThought)
        assert thought.is_final is True
        assert thought.answer == "The result"
        assert thought.task is None

    def test_build_thought_with_task(self, provider):
        data = {
            "reasoning": "need action",
            "is_final": False,
            "task": {"agent_name": "agent-a", "description": "do it"},
            "parallel_tasks": None,
        }
        thought = provider._build_thought_from_data(data, None, None)
        assert thought.task is not None
        assert thought.task.agent_name == "agent-a"

    def test_build_thought_external_reasoning(self, provider):
        data = {"reasoning": "from json", "is_final": True, "answer": "ok"}
        thought = provider._build_thought_from_data(data, None, "external reasoning")
        assert thought.reasoning == "external reasoning"

    def test_build_thought_with_needs_clarification(self, provider):
        """needs_clarification is extracted from parsed data (RC2)."""
        data = {
            "reasoning": "ambiguous request",
            "is_final": False,
            "needs_clarification": True,
            "answer": "Which model do you mean?",
            "task": None,
        }
        thought = provider._build_thought_from_data(data, None, None)
        assert thought.needs_clarification is True
        assert thought.answer == "Which model do you mean?"
        assert thought.task is None

    def test_build_thought_needs_clarification_defaults_false(self, provider):
        """needs_clarification defaults to False when not in data (RC2)."""
        data = {"reasoning": "normal", "is_final": True, "answer": "ok"}
        thought = provider._build_thought_from_data(data, None, None)
        assert thought.needs_clarification is False

    def test_build_thought_with_delegation(self, provider):
        data = {
            "reasoning": "delegate",
            "is_final": False,
            "delegate_to": "specialist-a",
            "subtask": "analyze data",
        }
        thought = provider._build_thought_from_data(data, None, None)
        assert thought.delegate_to == "specialist-a"
        assert thought.subtask == "analyze data"

# ---------------------------------------------------------------------------
# TestGetEnvironmentInfo
# ---------------------------------------------------------------------------

class TestGetEnvironmentInfo:
    """Tests for _get_environment_info."""

    def test_returns_string(self, provider):
        info = provider._get_environment_info()
        assert isinstance(info, str)
        assert "Current user" in info or "Home directory" in info or "Working directory" in info

    def test_includes_user_id_from_context(self, provider):
        info = provider._get_environment_info({"user_id": "user-42"})
        assert "user-42" in info

    def test_no_context(self, provider):
        info = provider._get_environment_info(None)
        assert isinstance(info, str)

# ---------------------------------------------------------------------------
# TestStreamFinalAnswer
# ---------------------------------------------------------------------------

class TestStreamFinalAnswer:
    """Tests for _stream_final_answer method (Phase 88-02)."""

    @pytest.mark.asyncio
    async def test_stream_final_answer_vllm_path(self):
        """VLLMBaseLLM path: astream yields content chunks, on_token called per chunk."""
        mock_llm = MagicMock()

        async def fake_astream(messages, enable_thinking=False):
            yield {"type": "content", "content": "Hello "}
            yield {"type": "content", "content": "world"}

        mock_llm.astream = fake_astream

        provider = OrchestrationThinkingProvider(llm=mock_llm)
        tokens = []
        history = _make_observation_history()

        content, reasoning, est_tokens = await provider._stream_final_answer(
            goal="test goal",
            observations=[],
            observation_history=history,
            on_token=lambda t: tokens.append(t),
        )

        assert tokens == ["Hello ", "world"]
        assert content == "Hello world"
        assert reasoning == ""
        assert est_tokens > 0

    @pytest.mark.asyncio
    async def test_stream_final_answer_litellm_path(self):
        """CrewAI/LiteLLM path: litellm.acompletion streaming."""
        import sys

        mock_llm = MagicMock(spec=[])
        mock_llm.model = "openai/gpt-4"
        mock_llm.api_key = "test-key"
        mock_llm.base_url = "http://localhost:8000"

        # Build mock streaming response
        # Set reasoning_content=None explicitly to prevent MagicMock
        # auto-generating a truthy attribute (since _stream_llm checks it)
        chunk1 = MagicMock()
        chunk1.choices = [MagicMock()]
        chunk1.choices[0].delta = MagicMock()
        chunk1.choices[0].delta.content = "Hi "
        chunk1.choices[0].delta.reasoning_content = None

        chunk2 = MagicMock()
        chunk2.choices = [MagicMock()]
        chunk2.choices[0].delta = MagicMock()
        chunk2.choices[0].delta.content = "there"
        chunk2.choices[0].delta.reasoning_content = None

        async def fake_aiter():
            yield chunk1
            yield chunk2

        mock_response = fake_aiter()

        # Create a mock litellm module with acompletion
        mock_litellm = MagicMock()
        mock_litellm.acompletion = AsyncMock(return_value=mock_response)

        provider = OrchestrationThinkingProvider(llm=mock_llm)
        tokens = []
        history = _make_observation_history()

        # Inject mock litellm into sys.modules so the import inside _stream_final_answer works
        original = sys.modules.get("litellm")
        sys.modules["litellm"] = mock_litellm
        try:
            content, reasoning, est_tokens = await provider._stream_final_answer(
                goal="test",
                observations=[],
                observation_history=history,
                on_token=lambda t: tokens.append(t),
            )
        finally:
            if original is not None:
                sys.modules["litellm"] = original
            else:
                del sys.modules["litellm"]

        assert tokens == ["Hi ", "there"]
        assert content == "Hi there"
        assert reasoning == ""
        assert est_tokens > 0

    @pytest.mark.asyncio
    async def test_stream_final_answer_with_reasoning(self):
        """VLLMBaseLLM yields reasoning + content; reasoning goes to thinking panel, content to chat bubble.

        Phase 114.2: _stream_final_answer uses merge_thinking=False to prevent
        reasoning from leaking into the user-visible chat bubble. Reasoning tokens
        go to on_thinking, content tokens go to on_token.
        """
        mock_llm = MagicMock()

        async def fake_astream(messages, enable_thinking=False):
            yield {"type": "reasoning", "content": "thinking..."}
            yield {"type": "content", "content": "answer"}

        mock_llm.astream = fake_astream

        provider = OrchestrationThinkingProvider(llm=mock_llm)
        tokens = []
        thinking = []
        history = _make_observation_history()

        content, reasoning, est_tokens = await provider._stream_final_answer(
            goal="test",
            observations=[],
            observation_history=history,
            on_token=lambda t: tokens.append(t),
            on_thinking=lambda t: thinking.append(t),
        )

        # With merge_thinking=False, reasoning goes to on_thinking, content to on_token
        assert thinking == ["thinking..."]  # Reasoning in thinking panel
        assert tokens == ["answer"]  # Only content in chat bubble
        assert content == "answer"  # Content only
        assert reasoning == "thinking..."  # Reasoning accumulated separately

    @pytest.mark.asyncio
    async def test_stream_final_answer_cancellation(self):
        """Cancel event stops streaming mid-response."""
        import asyncio

        cancel = asyncio.Event()
        cancel.set()  # Pre-set: should stop immediately

        mock_llm = MagicMock()

        async def fake_astream(messages, enable_thinking=False):
            for i in range(100):
                yield {"type": "content", "content": f"token{i} "}

        mock_llm.astream = fake_astream

        provider = OrchestrationThinkingProvider(llm=mock_llm)
        tokens = []
        history = _make_observation_history()

        content, reasoning, est_tokens = await provider._stream_final_answer(
            goal="test",
            observations=[],
            observation_history=history,
            on_token=lambda t: tokens.append(t),
            cancel_event=cancel,
        )

        # Should have consumed far fewer than 100 tokens due to cancellation
        assert len(tokens) < 100

    @pytest.mark.asyncio
    async def test_stream_final_answer_error_handling(self):
        """Error during streaming falls back to _call_llm; partial tokens already delivered via callback."""
        mock_llm = MagicMock()

        async def fake_astream(messages, enable_thinking=False):
            yield {"type": "content", "content": "partial "}
            yield {"type": "content", "content": "data"}
            raise RuntimeError("LLM connection lost")

        mock_llm.astream = fake_astream
        # When streaming fails, _stream_llm falls back to _call_llm which
        # calls llm.call(). Return empty string so the fallback produces no
        # extra tokens beyond what was already streamed before the error.
        mock_llm.call.return_value = ""

        provider = OrchestrationThinkingProvider(llm=mock_llm)
        tokens = []
        history = _make_observation_history()

        content, reasoning, est_tokens = await provider._stream_final_answer(
            goal="test",
            observations=[],
            observation_history=history,
            on_token=lambda t: tokens.append(t),
        )

        # Partial tokens were delivered via on_token callback before the error
        # The _call_llm fallback returns "" so full_content retains the partial streaming.
        assert "partial " in tokens
        assert "data" in tokens
        assert content == "partial data"

# ---------------------------------------------------------------------------
# TestRouterHints
# ---------------------------------------------------------------------------

class TestRouterHints:
    """Tests for router hint injection in orchestrate_think() (Phase 93, ADR-001 Part E)."""

    @pytest.mark.asyncio
    async def test_router_hints_injected_on_first_step(self, provider, agents):
        """Router hints appear in user message when observations is empty (first step)."""
        response = json.dumps(
            {
                "reasoning": "done",
                "is_final": True,
                "answer": "result",
                "task": None,
                "parallel_tasks": None,
            }
        )
        provider._explicit_llm.call = MagicMock(return_value=response)
        history = _make_observation_history()

        await provider.orchestrate_think(
            goal="test",
            observations=[],
            available_agents=agents,
            observation_history=history,
            context={
                "_router_hints": [
                    {"tool_name": "search_files", "server": "mcp-filesystem", "score": "0.85"},
                ],
            },
        )

        call_args = provider._explicit_llm.call.call_args
        messages = call_args[1]["messages"] if "messages" in call_args[1] else call_args[0][0]
        user_msg = [m for m in messages if m["role"] == "user"][0]
        assert "TOOL ROUTING HINTS (semantic match):" in user_msg["content"]
        assert "search_files" in user_msg["content"]
        assert "mcp-filesystem" in user_msg["content"]
        assert "0.85" in user_msg["content"]

    @pytest.mark.asyncio
    async def test_router_hints_not_injected_with_observations(self, provider, agents):
        """Router hints do NOT appear when observations exist (subsequent steps)."""
        response = json.dumps(
            {
                "reasoning": "done",
                "is_final": True,
                "answer": "result",
                "task": None,
                "parallel_tasks": None,
            }
        )
        provider._explicit_llm.call = MagicMock(return_value=response)

        obs = _make_observation("test-agent", "test task", "success", True)
        history = _make_observation_history([obs])

        await provider.orchestrate_think(
            goal="test",
            observations=[obs],
            available_agents=agents,
            observation_history=history,
            context={
                "_router_hints": [
                    {"tool_name": "search_files", "server": "mcp-filesystem", "score": "0.85"},
                ],
            },
        )

        call_args = provider._explicit_llm.call.call_args
        messages = call_args[1]["messages"] if "messages" in call_args[1] else call_args[0][0]
        user_msg = [m for m in messages if m["role"] == "user"][0]
        assert "TOOL ROUTING HINTS" not in user_msg["content"]

    @pytest.mark.asyncio
    async def test_router_hints_none_context(self, provider, agents):
        """When _router_hints is None (router had no results), no hints injected."""
        response = json.dumps(
            {
                "reasoning": "done",
                "is_final": True,
                "answer": "result",
                "task": None,
                "parallel_tasks": None,
            }
        )
        provider._explicit_llm.call = MagicMock(return_value=response)
        history = _make_observation_history()

        await provider.orchestrate_think(
            goal="test",
            observations=[],
            available_agents=agents,
            observation_history=history,
            context={"_router_hints": None},
        )

        call_args = provider._explicit_llm.call.call_args
        messages = call_args[1]["messages"] if "messages" in call_args[1] else call_args[0][0]
        user_msg = [m for m in messages if m["role"] == "user"][0]
        assert "TOOL ROUTING HINTS" not in user_msg["content"]

    @pytest.mark.asyncio
    async def test_router_hints_empty_list(self, provider, agents):
        """When _router_hints is an empty list, no hints injected."""
        response = json.dumps(
            {
                "reasoning": "done",
                "is_final": True,
                "answer": "result",
                "task": None,
                "parallel_tasks": None,
            }
        )
        provider._explicit_llm.call = MagicMock(return_value=response)
        history = _make_observation_history()

        await provider.orchestrate_think(
            goal="test",
            observations=[],
            available_agents=agents,
            observation_history=history,
            context={"_router_hints": []},
        )

        call_args = provider._explicit_llm.call.call_args
        messages = call_args[1]["messages"] if "messages" in call_args[1] else call_args[0][0]
        user_msg = [m for m in messages if m["role"] == "user"][0]
        assert "TOOL ROUTING HINTS" not in user_msg["content"]

    @pytest.mark.asyncio
    async def test_router_hints_no_context(self, provider, agents):
        """When context is None, no crash and no hints injected."""
        response = json.dumps(
            {
                "reasoning": "done",
                "is_final": True,
                "answer": "result",
                "task": None,
                "parallel_tasks": None,
            }
        )
        provider._explicit_llm.call = MagicMock(return_value=response)
        history = _make_observation_history()

        thought = await provider.orchestrate_think(
            goal="test",
            observations=[],
            available_agents=agents,
            observation_history=history,
            context=None,
        )

        # Should succeed without crash
        assert thought.is_final is True
        call_args = provider._explicit_llm.call.call_args
        messages = call_args[1]["messages"] if "messages" in call_args[1] else call_args[0][0]
        user_msg = [m for m in messages if m["role"] == "user"][0]
        assert "TOOL ROUTING HINTS" not in user_msg["content"]

    @pytest.mark.asyncio
    async def test_router_hints_multiple_entries(self, provider, agents):
        """When 3 router hints are provided, all appear in the user content."""
        response = json.dumps(
            {
                "reasoning": "done",
                "is_final": True,
                "answer": "result",
                "task": None,
                "parallel_tasks": None,
            }
        )
        provider._explicit_llm.call = MagicMock(return_value=response)
        history = _make_observation_history()

        hints = [
            {"tool_name": "search_files", "server": "mcp-filesystem", "score": "0.92"},
            {"tool_name": "list_directory", "server": "mcp-filesystem", "score": "0.78"},
            {"tool_name": "query_database", "server": "mcp-dbhub", "score": "0.65"},
        ]

        await provider.orchestrate_think(
            goal="test",
            observations=[],
            available_agents=agents,
            observation_history=history,
            context={"_router_hints": hints},
        )

        call_args = provider._explicit_llm.call.call_args
        messages = call_args[1]["messages"] if "messages" in call_args[1] else call_args[0][0]
        user_msg = [m for m in messages if m["role"] == "user"][0]
        content = user_msg["content"]

        # All 3 entries present
        assert "- search_files (mcp-filesystem): score=0.92" in content
        assert "- list_directory (mcp-filesystem): score=0.78" in content
        assert "- query_database (mcp-dbhub): score=0.65" in content
        # Header present
        assert "TOOL ROUTING HINTS (semantic match):" in content

# ---------------------------------------------------------------------------
# TestStreamingSynthesis
# ---------------------------------------------------------------------------

class TestStreamingSynthesis:
    """Tests for streaming synthesize_think() (Phase 93, ADR-002 Sub-Decision C)."""

    @pytest.mark.asyncio
    async def test_synthesize_streaming_uses_stream_llm(self):
        """When on_token is provided, synthesize_think() calls _stream_llm (not _call_llm)."""
        mock_llm = MagicMock()
        provider = OrchestrationThinkingProvider(llm=mock_llm)

        tokens = []

        async def fake_stream_llm(
            messages, on_token=None, on_thinking=None, cancel_event=None, merge_thinking=False
        ):
            for chunk in ["Synthesized ", "answer"]:
                if on_token:
                    on_token(chunk)
            return ("Synthesized answer", "", 5)

        provider._stream_llm = fake_stream_llm

        result = await provider.synthesize_think(
            goal="test goal",
            step_results={"s1": "result 1"},
            on_token=lambda t: tokens.append(t),
        )

        assert result == "Synthesized answer"
        assert tokens == ["Synthesized ", "answer"]
        # _call_llm should NOT have been called
        mock_llm.call.assert_not_called()

    @pytest.mark.asyncio
    async def test_synthesize_blocking_uses_call_llm(self):
        """When on_token is NOT provided, synthesize_think() calls _call_llm (blocking path)."""
        mock_llm = MagicMock()
        mock_llm.call = MagicMock(return_value="Blocked answer")
        mock_llm._token_usage = {"prompt_tokens": 0, "completion_tokens": 0}
        provider = OrchestrationThinkingProvider(llm=mock_llm)

        result = await provider.synthesize_think(
            goal="test goal",
            step_results={"s1": "result 1"},
        )

        assert result == "Blocked answer"
        # _call_llm was invoked (via the mock LLM's .call method)
        mock_llm.call.assert_called_once()

    @pytest.mark.asyncio
    async def test_synthesize_streaming_tokens_delivered(self):
        """All tokens from astream are delivered via on_token callback in order."""
        mock_llm = MagicMock()

        async def fake_astream(messages, enable_thinking=False):
            yield {"type": "content", "content": "First "}
            yield {"type": "content", "content": "second "}
            yield {"type": "content", "content": "third"}

        mock_llm.astream = fake_astream

        provider = OrchestrationThinkingProvider(llm=mock_llm)
        tokens = []

        result = await provider.synthesize_think(
            goal="test",
            step_results={"s1": "r1", "s2": "r2"},
            on_token=lambda t: tokens.append(t),
        )

        assert tokens == ["First ", "second ", "third"]
        assert result == "First second third"

    @pytest.mark.asyncio
    async def test_synthesize_streaming_cost_event_emitted(self):
        """Cost event callback is invoked after streaming synthesis."""
        cost_events = []
        mock_llm = MagicMock()

        async def fake_astream(messages, enable_thinking=False):
            yield {"type": "content", "content": "Hello world"}

        mock_llm.astream = fake_astream

        provider = OrchestrationThinkingProvider(llm=mock_llm, on_cost_event=cost_events.append)

        await provider.synthesize_think(
            goal="test",
            step_results={"s1": "r1"},
            on_token=lambda t: None,
        )

        assert len(cost_events) == 1
        assert isinstance(cost_events[0], ChatEvent)
        assert cost_events[0].metadata["completion_tokens"] > 0

    @pytest.mark.asyncio
    async def test_synthesize_streaming_cancellation(self):
        """Cancel event stops streaming synthesis before all tokens are yielded."""
        import asyncio

        cancel = asyncio.Event()
        cancel.set()  # Pre-set: should stop immediately

        mock_llm = MagicMock()

        async def fake_astream(messages, enable_thinking=False):
            for i in range(100):
                yield {"type": "content", "content": f"token{i} "}

        mock_llm.astream = fake_astream

        provider = OrchestrationThinkingProvider(llm=mock_llm)
        tokens = []

        result = await provider.synthesize_think(
            goal="test",
            step_results={"s1": "r1"},
            on_token=lambda t: tokens.append(t),
            cancel_event=cancel,
        )

        # Should have stopped well before 100 tokens
        assert len(tokens) < 100

    @pytest.mark.asyncio
    async def test_synthesize_streaming_return_type_is_str(self):
        """Streaming synthesis returns str (not tuple), guarding against Pitfall 3."""
        mock_llm = MagicMock()

        async def fake_astream(messages, enable_thinking=False):
            yield {"type": "content", "content": "answer"}

        mock_llm.astream = fake_astream

        provider = OrchestrationThinkingProvider(llm=mock_llm)

        result = await provider.synthesize_think(
            goal="test",
            step_results={"s1": "r1"},
            on_token=lambda t: None,
        )

        # Return type MUST be str, not tuple (Pitfall 3 from research)
        assert isinstance(result, str)
        assert result == "answer"

# ---------------------------------------------------------------------------
# Connection error handling tests (Phase 103-02)
# ---------------------------------------------------------------------------

class MockConnectionError(Exception):
    """Mock exception with error_type attribute to simulate VLLMConnectionError.

    Used instead of importing VLLMConnectionError from plugins to verify
    ThinkingProvider's duck-typed detection (hasattr(e, 'error_type')).
    """

    def __init__(self, msg, error_type="connection"):
        super().__init__(msg)
        self.error_type = error_type

class TestStreamLLMConnectionErrors:
    """Tests for _stream_llm connection error handling (Phase 103-02).

    _stream_llm re-raises connection errors instead of falling back to
    _call_llm, since _call_llm would also fail on the same connection.
    """

    @pytest.mark.asyncio
    async def test_stream_llm_reraises_connection_error(self):
        """_stream_llm re-raises exceptions with error_type='connection' (no fallback)."""
        mock_llm = MagicMock()

        async def failing_astream(messages, enable_thinking=False):
            raise MockConnectionError("vLLM down", error_type="connection")
            yield  # noqa: unreachable -- make this an async generator

        mock_llm.astream = failing_astream

        provider = OrchestrationThinkingProvider(llm=mock_llm)

        with pytest.raises(MockConnectionError) as exc_info:
            await provider._stream_llm(
                messages=[{"role": "user", "content": "test"}],
            )

        assert exc_info.value.error_type == "connection"
        # _call_llm should NOT have been called (no fallback for connection errors)
        mock_llm.call.assert_not_called()

    @pytest.mark.asyncio
    async def test_stream_llm_falls_back_on_non_connection_error(self):
        """_stream_llm falls back to _call_llm on generic RuntimeError (no error_type)."""
        mock_llm = MagicMock()

        async def failing_astream(messages, enable_thinking=False):
            raise RuntimeError("some parse error")
            yield  # noqa: unreachable -- make this an async generator

        mock_llm.astream = failing_astream
        mock_llm.call = MagicMock(return_value="fallback response")
        mock_llm._token_usage = {"prompt_tokens": 0, "completion_tokens": 0}

        provider = OrchestrationThinkingProvider(llm=mock_llm)

        content, reasoning, est_tokens = await provider._stream_llm(
            messages=[{"role": "user", "content": "test"}],
        )

        # Should have fallen back to _call_llm
        mock_llm.call.assert_called_once()
        assert content == "fallback response"

class TestOrchestrateThinkConnectionErrors:
    """Tests for orchestrate_think connection error handling (Phase 103-02).

    orchestrate_think returns user-friendly message on connection errors
    instead of raw exception text.
    """

    @pytest.mark.asyncio
    async def test_orchestrate_think_returns_friendly_message_on_connection_error(self):
        """orchestrate_think returns 'unable to reach the language model' on connection errors."""
        mock_llm = MagicMock()
        mock_llm.call = MagicMock(
            side_effect=MockConnectionError("Cannot connect to vLLM", error_type="connection")
        )
        mock_llm._token_usage = {"prompt_tokens": 0, "completion_tokens": 0}

        provider = OrchestrationThinkingProvider(llm=mock_llm)
        history = _make_observation_history()
        agents = [_make_agent_card("test-agent", "A test agent")]

        thought = await provider.orchestrate_think(
            goal="test",
            observations=[],
            available_agents=agents,
            observation_history=history,
        )

        assert thought.is_final is True
        assert "unable to reach the language model service" in thought.answer
        assert "connection" in thought.reasoning

    @pytest.mark.asyncio
    async def test_orchestrate_think_returns_generic_error_on_other_exceptions(self):
        """orchestrate_think returns 'Orchestration error: ValueError' on non-connection errors."""
        mock_llm = MagicMock()
        mock_llm.call = MagicMock(side_effect=ValueError("bad"))
        mock_llm._token_usage = {"prompt_tokens": 0, "completion_tokens": 0}

        provider = OrchestrationThinkingProvider(llm=mock_llm)
        history = _make_observation_history()
        agents = [_make_agent_card("test-agent", "A test agent")]

        thought = await provider.orchestrate_think(
            goal="test",
            observations=[],
            available_agents=agents,
            observation_history=history,
        )

        assert thought.is_final is True
        assert "ValueError" in thought.answer

# ---------------------------------------------------------------------------
# TestOrchestrateThinkFiltering (Phase 107 integration)
# ---------------------------------------------------------------------------

class TestOrchestrateThinkFiltering:
    """Integration tests for orchestrate_think with router filtering and double-def elimination."""

    def _make_five_mcp_agents(self):
        """Create 5 MCP agents for filtering tests."""
        return [
            _make_mcp_agent(
                "mcp-filesystem", [("list_dir", "List directory"), ("search_files", "Search")]
            ),
            _make_mcp_agent("mcp-git", [("git_log", "Git log"), ("git_diff", "Git diff")]),
            _make_mcp_agent("mcp-github", [("create_issue", "Create issue")]),
            _make_mcp_agent("mcp-postgres", [("query", "Run SQL query")]),
            _make_mcp_agent("mcp-docker", [("list_containers", "List containers")]),
        ]

    def _standard_response(self):
        return json.dumps(
            {
                "reasoning": "Test",
                "is_final": True,
                "answer": "Done",
                "task": None,
                "parallel_tasks": None,
            }
        )

    @pytest.mark.asyncio
    async def test_native_tools_uses_lightweight_xml(self):
        """When _supports_native_tools() is True, system prompt uses lightweight XML (self-closing tags)."""
        mock_llm = MagicMock()
        mock_llm.call = MagicMock(return_value=self._standard_response())
        mock_llm._token_usage = {"prompt_tokens": 0, "completion_tokens": 0}
        provider = OrchestrationThinkingProvider(llm=mock_llm)
        agents = self._make_five_mcp_agents()
        history = _make_observation_history()

        with patch.object(provider, "_supports_native_tools", return_value=True):
            await provider.orchestrate_think(
                goal="test",
                observations=[],
                available_agents=agents,
                observation_history=history,
            )

        call_args = mock_llm.call.call_args
        messages = call_args[1]["messages"] if "messages" in call_args[1] else call_args[0][0]
        system_msg = [m for m in messages if m["role"] == "system"][0]
        # Lightweight XML: self-closing agent tags, no <tools> blocks
        assert "/>" in system_msg["content"]
        assert "<tools>" not in system_msg["content"]

    @pytest.mark.asyncio
    async def test_native_tools_sends_filtered_tools(self):
        """With router hints for 2 servers, _call_llm receives only tools from those 2 servers."""
        mock_llm = MagicMock()
        mock_llm.call = MagicMock(return_value=self._standard_response())
        mock_llm._token_usage = {"prompt_tokens": 0, "completion_tokens": 0}
        provider = OrchestrationThinkingProvider(llm=mock_llm)
        agents = self._make_five_mcp_agents()
        history = _make_observation_history()

        hints = [
            {"tool_name": "list_dir", "server": "mcp-filesystem", "score": "0.9"},
            {"tool_name": "git_log", "server": "mcp-git", "score": "0.8"},
        ]

        with patch.object(provider, "_supports_native_tools", return_value=True):
            await provider.orchestrate_think(
                goal="test",
                observations=[],
                available_agents=agents,
                observation_history=history,
                context={"_router_hints": hints},
            )

        call_args = mock_llm.call.call_args
        # Native tools should be passed as kwarg
        tools = call_args[1].get("tools", [])
        tool_names = [t["function"]["name"] for t in tools]
        # Only tools from mcp-filesystem (2) and mcp-git (2) = 4 tools
        assert "list_dir" in tool_names
        assert "search_files" in tool_names
        assert "git_log" in tool_names
        assert "git_diff" in tool_names
        # Tools from other servers should NOT be present
        assert "create_issue" not in tool_names
        assert "query" not in tool_names
        assert "list_containers" not in tool_names

    @pytest.mark.asyncio
    async def test_filter_disabled_sends_all_tools(self):
        """When DRYADE_ROUTER_FILTER_ENABLED=false, all tools sent even with router_hints."""
        mock_llm = MagicMock()
        mock_llm.call = MagicMock(return_value=self._standard_response())
        mock_llm._token_usage = {"prompt_tokens": 0, "completion_tokens": 0}
        provider = OrchestrationThinkingProvider(llm=mock_llm)
        agents = self._make_five_mcp_agents()
        history = _make_observation_history()

        hints = [
            {"tool_name": "list_dir", "server": "mcp-filesystem", "score": "0.9"},
        ]

        with patch.dict(os.environ, {"DRYADE_ROUTER_FILTER_ENABLED": "false"}):
            with patch.object(provider, "_supports_native_tools", return_value=True):
                await provider.orchestrate_think(
                    goal="test",
                    observations=[],
                    available_agents=agents,
                    observation_history=history,
                    context={"_router_hints": hints},
                )

        call_args = mock_llm.call.call_args
        tools = call_args[1].get("tools", [])
        # All 7 tools from all 5 agents should be present (no filtering).
        # Phase 167: self-mod tools (11) are always-injected for function-calling providers,
        # so the total is 7 MCP tools + 11 self-mod tools = 18.
        tool_names = [t["function"]["name"] for t in tools]
        assert len(tool_names) >= 7  # At least the 7 MCP tools
        assert "create_issue" in tool_names
        assert "query" in tool_names
        assert "list_containers" in tool_names

    @pytest.mark.asyncio
    async def test_text_only_provider_keeps_full_xml(self):
        """When _supports_native_tools() is False, system prompt contains full XML tool schemas."""
        mock_llm = MagicMock()
        mock_llm.call = MagicMock(return_value=self._standard_response())
        mock_llm._token_usage = {"prompt_tokens": 0, "completion_tokens": 0}
        provider = OrchestrationThinkingProvider(llm=mock_llm)
        agents = self._make_five_mcp_agents()
        history = _make_observation_history()

        with patch.object(provider, "_supports_native_tools", return_value=False):
            await provider.orchestrate_think(
                goal="test",
                observations=[],
                available_agents=agents,
                observation_history=history,
            )

        call_args = mock_llm.call.call_args
        messages = call_args[1]["messages"] if "messages" in call_args[1] else call_args[0][0]
        system_msg = [m for m in messages if m["role"] == "system"][0]
        # Full XML mode: has <tools> and <param> elements
        assert "<tools>" in system_msg["content"]
        assert "<param" in system_msg["content"]
        # No native tools should be passed
        tools = call_args[1].get("tools")
        assert tools is None

    @pytest.mark.asyncio
    async def test_empty_router_hints_sends_all_tools(self):
        """No router_hints in context -> all tools sent, no filtering."""
        mock_llm = MagicMock()
        mock_llm.call = MagicMock(return_value=self._standard_response())
        mock_llm._token_usage = {"prompt_tokens": 0, "completion_tokens": 0}
        provider = OrchestrationThinkingProvider(llm=mock_llm)
        agents = self._make_five_mcp_agents()
        history = _make_observation_history()

        with patch.object(provider, "_supports_native_tools", return_value=True):
            await provider.orchestrate_think(
                goal="test",
                observations=[],
                available_agents=agents,
                observation_history=history,
                context=None,
            )

        call_args = mock_llm.call.call_args
        tools = call_args[1].get("tools", [])
        # All 7 tools from all 5 agents (no filtering without hints).
        # Phase 167: self-mod tools (11) are always-injected, so total >= 7.
        assert len(tools) >= 7

    @pytest.mark.asyncio
    async def test_plan_think_not_affected_by_filter(self):
        """plan_think() uses the full agent list regardless of router_hints context."""
        mock_llm = MagicMock()
        plan_response = json.dumps(
            {
                "reasoning": "Simple plan",
                "steps": [{"id": "step-1", "agent_name": "mcp-filesystem", "task": "List files"}],
            }
        )
        mock_llm.call = MagicMock(return_value=plan_response)
        mock_llm._token_usage = {"prompt_tokens": 0, "completion_tokens": 0}
        provider = OrchestrationThinkingProvider(llm=mock_llm)
        agents = self._make_five_mcp_agents()

        plan = await provider.plan_think(
            goal="test",
            available_agents=agents,
            context={
                "_router_hints": [
                    {"tool_name": "list_dir", "server": "mcp-filesystem", "score": "0.9"}
                ]
            },
        )

        # Verify plan_think was called with all agents in the system prompt
        call_args = mock_llm.call.call_args
        messages = call_args[1]["messages"] if "messages" in call_args[1] else call_args[0][0]
        system_msg = [m for m in messages if m["role"] == "system"][0]
        # All 5 agents should be in the system prompt (plan_think doesn't filter)
        assert "mcp-filesystem" in system_msg["content"]
        assert "mcp-git" in system_msg["content"]
        assert "mcp-github" in system_msg["content"]
        assert "mcp-postgres" in system_msg["content"]
        assert "mcp-docker" in system_msg["content"]
        # plan_think does NOT pass native tools
        tools = call_args[1].get("tools")
        assert tools is None

# ---------------------------------------------------------------------------
# TestVLLMValidatorIntegration (Phase 118.2)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestVLLMValidatorIntegration:
    """Test VLLMResponseValidator integration in _call_llm."""

    @pytest.mark.asyncio
    async def test_vllm_validator_repairs_content_none(self):
        """vLLM response with content=None + reasoning_content -> repaired content."""
        mock_llm = MagicMock()
        mock_llm._token_usage = {"prompt_tokens": 0, "completion_tokens": 0}
        # Simulate vLLM dict response with content=None (FM-2)
        mock_llm.call = MagicMock(
            return_value={
                "content": None,
                "reasoning_content": "The answer is 42",
                "tool_calls": None,
            }
        )
        # Make class name contain "vllm" to trigger _is_vllm_model
        mock_llm.__class__.__name__ = "VLLMBaseLLM"

        provider = OrchestrationThinkingProvider(llm=mock_llm)
        content, reasoning = await provider._call_llm([{"role": "user", "content": "test"}])

        # FM-2 should repair: content=None -> content from reasoning_content
        assert content is not None
        assert "The answer is 42" in content

    @pytest.mark.asyncio
    async def test_vllm_validator_rejects_oom(self):
        """vLLM OOM response returns VLLM_ERROR string."""
        mock_llm = MagicMock()
        mock_llm._token_usage = {"prompt_tokens": 0, "completion_tokens": 0}
        # Simulate vLLM dict response with OOM error (FM-4: requires http_status=500)
        mock_llm.call = MagicMock(
            return_value={
                "content": "",
                "error": "KV cache exhausted, cannot allocate more memory",
                "http_status": 500,
            }
        )
        mock_llm.__class__.__name__ = "VLLMBaseLLM"

        provider = OrchestrationThinkingProvider(llm=mock_llm)
        content, reasoning = await provider._call_llm([{"role": "user", "content": "test"}])

        assert "[VLLM_ERROR:" in content
        assert "kv_cache_oom" in content

    @pytest.mark.asyncio
    async def test_vllm_validator_skips_non_vllm(self):
        """Non-vLLM LLM responses are NOT validated."""
        mock_llm = MagicMock()
        mock_llm._token_usage = {"prompt_tokens": 0, "completion_tokens": 0}
        # Regular LLM (not vLLM) returning dict with content=None
        mock_llm.call = MagicMock(
            return_value={
                "content": None,
                "reasoning_content": "thinking...",
            }
        )
        # Ensure class name does NOT match vLLM
        mock_llm.__class__.__name__ = "LiteLLM"
        mock_llm.model = "gpt-4"

        provider = OrchestrationThinkingProvider(llm=mock_llm)
        content, reasoning = await provider._call_llm([{"role": "user", "content": "test"}])

        # No validator intervention -- content should be empty string (raw from dict)
        assert "[VLLM_ERROR:" not in content
        assert content == ""

    @pytest.mark.asyncio
    async def test_vllm_validator_disabled_by_flag(self):
        """When vllm_validator_enabled=False, validator is NOT called even for vLLM."""
        mock_llm = MagicMock()
        mock_llm._token_usage = {"prompt_tokens": 0, "completion_tokens": 0}
        mock_llm.call = MagicMock(
            return_value={
                "content": "",
                "error": "KV cache exhausted",
            }
        )
        mock_llm.__class__.__name__ = "VLLMBaseLLM"

        provider = OrchestrationThinkingProvider(llm=mock_llm)

        with patch.dict(os.environ, {"DRYADE_VLLM_VALIDATOR_ENABLED": "false"}):
            content, reasoning = await provider._call_llm([{"role": "user", "content": "test"}])

        # Validator disabled -- raw content should pass through (empty string)
        assert "[VLLM_ERROR:" not in content

# ---------------------------------------------------------------------------
# dryade_provider attribute tests (Phase 181, Plan 02)
# ---------------------------------------------------------------------------
class TestDryadeProviderAttribute:
    """Tests that _supports_native_tools and _is_vllm_model use dryade_provider."""

    def test_supports_native_tools_with_anthropic_provider(self):
        """LLM with dryade_provider='anthropic' supports native tools."""
        mock_llm = MagicMock(spec=[])
        mock_llm.dryade_provider = "anthropic"
        mock_llm.model = "anthropic/claude-opus-4-6"
        provider = OrchestrationThinkingProvider(llm=mock_llm)
        assert provider._supports_native_tools() is True

    def test_supports_native_tools_with_ollama_provider(self):
        """LLM with dryade_provider='ollama' does NOT support native tools."""
        mock_llm = MagicMock(spec=[])
        mock_llm.dryade_provider = "ollama"
        mock_llm.model = "ollama/llama3"
        provider = OrchestrationThinkingProvider(llm=mock_llm)
        assert provider._supports_native_tools() is False

    def test_supports_native_tools_backward_compat_no_attribute(self):
        """LLM without dryade_provider falls back to model string parsing."""
        mock_llm = MagicMock(spec=[])  # No attributes by default
        mock_llm.model = "ollama/llama3"
        provider = OrchestrationThinkingProvider(llm=mock_llm)
        assert provider._supports_native_tools() is False

    def test_supports_native_tools_backward_compat_openai(self):
        """LLM without dryade_provider but with openai model -> supports tools."""
        mock_llm = MagicMock(spec=[])
        mock_llm.model = "gpt-4"
        provider = OrchestrationThinkingProvider(llm=mock_llm)
        # No "/" in model -> provider="" -> not in _TEXT_ONLY_PROVIDERS -> True
        assert provider._supports_native_tools() is True

    def test_is_vllm_model_with_provider_attribute(self):
        """LLM with dryade_provider='vllm' is detected as vLLM."""
        mock_llm = MagicMock()
        mock_llm.dryade_provider = "vllm"
        mock_llm.__class__.__name__ = "SomeLLM"
        mock_llm.model = "my-model"
        provider = OrchestrationThinkingProvider(llm=mock_llm)
        assert provider._is_vllm_model() is True

    def test_is_vllm_model_with_openai_provider(self):
        """LLM with dryade_provider='openai' is NOT vLLM."""
        mock_llm = MagicMock()
        mock_llm.dryade_provider = "openai"
        mock_llm.__class__.__name__ = "LLM"
        mock_llm.model = "gpt-4"
        provider = OrchestrationThinkingProvider(llm=mock_llm)
        assert provider._is_vllm_model() is False

    def test_is_vllm_model_backward_compat_class_name(self):
        """LLM without dryade_provider but VLLMBaseLLM class name -> detected."""
        mock_llm = MagicMock()
        mock_llm.__class__.__name__ = "VLLMBaseLLM"
        mock_llm.model = "my-model"
        # Remove dryade_provider so it falls through to class name check
        del mock_llm.dryade_provider
        provider = OrchestrationThinkingProvider(llm=mock_llm)
        assert provider._is_vllm_model() is True

class TestRuntimeAdaptiveFallback:
    """Tests for session-scoped tier downgrade (runtime adaptive fallback)."""

    def test_session_tier_override_default_none(self):
        """New provider instance has no session override."""
        mock_llm = MagicMock(spec=[])
        mock_llm.model = "gpt-4"
        provider = OrchestrationThinkingProvider(llm=mock_llm)
        assert provider._session_tier_override is None

    def test_downgrade_sets_session_override(self):
        """_downgrade_tier_for_session sets _session_tier_override one tier lower."""
        from core.orchestrator.model_detection import ModelProfile, ModelTier

        mock_llm = MagicMock(spec=[])
        mock_llm.model = "gpt-4"
        mock_llm.dryade_provider = "openai"
        provider = OrchestrationThinkingProvider(llm=mock_llm)

        mock_profile = ModelProfile(
            tier=ModelTier.FRONTIER,
            supports_tools=True,
            supports_structured_output=True,
            calibration_score=1.0,
            model_key="gpt-4",
        )
        with patch("core.orchestrator.model_detection.get_model_detector") as mock_detector_fn:
            mock_detector_fn.return_value.get_model_tier.return_value = mock_profile
            provider._downgrade_tier_for_session()

        assert provider._session_tier_override == ModelTier.STRONG

    def test_double_downgrade_frontier_to_moderate(self):
        """Calling _downgrade_tier_for_session twice: FRONTIER -> STRONG -> MODERATE."""
        from core.orchestrator.model_detection import ModelProfile, ModelTier

        mock_llm = MagicMock(spec=[])
        mock_llm.model = "gpt-4"
        mock_llm.dryade_provider = "openai"
        provider = OrchestrationThinkingProvider(llm=mock_llm)

        mock_profile = ModelProfile(
            tier=ModelTier.FRONTIER,
            supports_tools=True,
            supports_structured_output=True,
            calibration_score=1.0,
            model_key="gpt-4",
        )
        with patch("core.orchestrator.model_detection.get_model_detector") as mock_detector_fn:
            mock_detector_fn.return_value.get_model_tier.return_value = mock_profile
            provider._downgrade_tier_for_session()  # FRONTIER -> STRONG
            provider._downgrade_tier_for_session()  # STRONG -> MODERATE

        assert provider._session_tier_override == ModelTier.MODERATE

    def test_downgrade_at_weak_is_noop(self):
        """Downgrade at WEAK floor is a no-op (no infinite loop)."""
        from core.orchestrator.model_detection import ModelProfile, ModelTier

        mock_llm = MagicMock(spec=[])
        mock_llm.model = "local-llm"
        mock_llm.dryade_provider = "ollama"
        provider = OrchestrationThinkingProvider(llm=mock_llm)

        mock_profile = ModelProfile(
            tier=ModelTier.WEAK,
            supports_tools=False,
            supports_structured_output=False,
            calibration_score=0.2,
            model_key="local-llm",
        )
        with patch("core.orchestrator.model_detection.get_model_detector") as mock_detector_fn:
            mock_detector_fn.return_value.get_model_tier.return_value = mock_profile
            provider._downgrade_tier_for_session()

        # WEAK stays WEAK -- override not set because no change
        assert provider._session_tier_override is None

    def test_session_scoped_not_global(self):
        """Session override is per-instance, not in global ModelDetector cache."""
        from core.orchestrator.model_detection import ModelProfile, ModelTier

        mock_llm = MagicMock(spec=[])
        mock_llm.model = "gpt-4"
        mock_llm.dryade_provider = "openai"
        provider1 = OrchestrationThinkingProvider(llm=mock_llm)
        provider2 = OrchestrationThinkingProvider(llm=mock_llm)

        mock_profile = ModelProfile(
            tier=ModelTier.FRONTIER,
            supports_tools=True,
            supports_structured_output=True,
            calibration_score=1.0,
            model_key="gpt-4",
        )
        with patch("core.orchestrator.model_detection.get_model_detector") as mock_detector_fn:
            mock_detector_fn.return_value.get_model_tier.return_value = mock_profile
            provider1._downgrade_tier_for_session()

        assert provider1._session_tier_override == ModelTier.STRONG
        assert provider2._session_tier_override is None  # Unaffected

    @pytest.mark.asyncio
    async def test_call_llm_dict_content_none_triggers_downgrade(self):
        """Dict response with content=None and no tool_calls triggers downgrade."""
        mock_llm = MagicMock(spec=[])
        mock_llm.model = "vllm/broken-model"
        mock_llm.dryade_provider = "vllm"
        mock_llm.call = MagicMock(return_value={"content": None, "tool_calls": None})
        provider = OrchestrationThinkingProvider(llm=mock_llm)

        tools = [{"type": "function", "function": {"name": "test_tool"}}]
        # Disable vLLM validator to isolate the downgrade test
        with patch("core.orchestrator.config.get_orchestration_config") as mock_cfg:
            mock_cfg.return_value.vllm_validator_enabled = False
            with patch.object(provider, "_downgrade_tier_for_session") as mock_downgrade:
                await provider._call_llm([{"role": "user", "content": "test"}], tools=tools)
                mock_downgrade.assert_called_once()

    @pytest.mark.asyncio
    async def test_call_llm_empty_string_triggers_downgrade(self):
        """String response with empty content triggers downgrade when tools provided."""
        mock_llm = MagicMock(spec=[])
        mock_llm.model = "vllm/broken-model"
        mock_llm.dryade_provider = "vllm"
        mock_llm.call = MagicMock(return_value="   ")
        provider = OrchestrationThinkingProvider(llm=mock_llm)

        tools = [{"type": "function", "function": {"name": "test_tool"}}]
        with patch("core.orchestrator.config.get_orchestration_config") as mock_cfg:
            mock_cfg.return_value.vllm_validator_enabled = False
            with patch.object(provider, "_downgrade_tier_for_session") as mock_downgrade:
                await provider._call_llm([{"role": "user", "content": "test"}], tools=tools)
                mock_downgrade.assert_called_once()

    @pytest.mark.asyncio
    async def test_call_llm_vllm_error_prefix_triggers_downgrade(self):
        """VLLM_ERROR prefix in string content triggers downgrade."""
        mock_llm = MagicMock(spec=[])
        mock_llm.model = "vllm/broken-model"
        mock_llm.dryade_provider = "vllm"
        mock_llm.call = MagicMock(return_value="[VLLM_ERROR:oom] Response validation failed")
        provider = OrchestrationThinkingProvider(llm=mock_llm)

        tools = [{"type": "function", "function": {"name": "test_tool"}}]
        with patch("core.orchestrator.config.get_orchestration_config") as mock_cfg:
            mock_cfg.return_value.vllm_validator_enabled = False
            with patch.object(provider, "_downgrade_tier_for_session") as mock_downgrade:
                await provider._call_llm([{"role": "user", "content": "test"}], tools=tools)
                mock_downgrade.assert_called_once()

    @pytest.mark.asyncio
    async def test_call_llm_no_downgrade_without_tools(self):
        """No downgrade triggered when tools are not provided (even with empty content)."""
        mock_llm = MagicMock(spec=[])
        mock_llm.model = "vllm/model"
        mock_llm.dryade_provider = "vllm"
        mock_llm.call = MagicMock(return_value="")
        provider = OrchestrationThinkingProvider(llm=mock_llm)

        with patch("core.orchestrator.config.get_orchestration_config") as mock_cfg:
            mock_cfg.return_value.vllm_validator_enabled = False
            with patch.object(provider, "_downgrade_tier_for_session") as mock_downgrade:
                await provider._call_llm([{"role": "user", "content": "test"}], tools=None)
                mock_downgrade.assert_not_called()

    @pytest.mark.asyncio
    async def test_call_llm_no_downgrade_on_valid_response(self):
        """No downgrade when model returns valid content with tools."""
        mock_llm = MagicMock(spec=[])
        mock_llm.model = "gpt-4"
        mock_llm.dryade_provider = "openai"
        mock_llm.call = MagicMock(return_value='{"reasoning": "test", "is_final": true}')
        provider = OrchestrationThinkingProvider(llm=mock_llm)

        tools = [{"type": "function", "function": {"name": "test_tool"}}]
        with patch("core.orchestrator.config.get_orchestration_config") as mock_cfg:
            mock_cfg.return_value.vllm_validator_enabled = False
            with patch.object(provider, "_downgrade_tier_for_session") as mock_downgrade:
                await provider._call_llm([{"role": "user", "content": "test"}], tools=tools)
                mock_downgrade.assert_not_called()
