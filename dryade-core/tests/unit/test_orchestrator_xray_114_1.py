"""Regression tests for X-Ray 114.1 orchestrator bug fixes.

BUG-002: failure_think receives list[AgentCard] (not list[str]) on agent-not-found path
BUG-006: Timeout retry with identical params forces ESCALATE instead of blind retry
BUG-007: Escalation fallback message uses action.description when escalation_question is missing
"""

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
from core.orchestrator.models import (
    FailureAction,
    OrchestrationObservation,
    OrchestrationTask,
    OrchestrationThought,
)
from core.orchestrator.orchestrator import DryadeOrchestrator
from core.orchestrator.thinking import OrchestrationThinkingProvider

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class StubAgent(UniversalAgent):
    """Minimal agent for testing."""

    def __init__(
        self,
        name: str = "test-agent",
        description: str = "A test agent",
        result: str = "done",
        status: str = "ok",
        caps: AgentCapabilities | None = None,
        raise_on_execute: Exception | None = None,
    ):
        self._name = name
        self._description = description
        self._result = result
        self._status = status
        self._caps = caps or AgentCapabilities()
        self._raise_on_execute = raise_on_execute

    def get_card(self) -> AgentCard:
        return AgentCard(
            name=self._name,
            description=self._description,
            version="1.0",
            framework=AgentFramework.CUSTOM,
        )

    async def execute(self, task, context=None):
        if self._raise_on_execute:
            raise self._raise_on_execute
        return AgentResult(result=self._result, status=self._status)

    def get_tools(self):
        return []

    def capabilities(self) -> AgentCapabilities:
        return self._caps

def _make_registry(*agents: UniversalAgent) -> AgentRegistry:
    """Build a registry pre-loaded with the given agents."""
    reg = AgentRegistry()
    for a in agents:
        reg.register(a)
    return reg

# ---------------------------------------------------------------------------
# BUG-002: failure_think receives list[AgentCard] on agent-not-found path
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestBug002FailureThinkReceivesAgentCards:
    """BUG-002 regression: agent-not-found is now handled by Tier 1 classifier.

    FailureClassifier intercepts "agent not found" deterministically
    (TOOL_NOT_FOUND -> ESCALATE), so failure_think is NOT called. The original BUG-002
    (failure_think receiving list[str] instead of list[AgentCard]) is structurally
    impossible when the classifier handles it at Tier 1.
    """

    async def test_agent_not_found_handled_by_tier1_classifier(self):
        """When an agent is not found, the Tier 1 FailureClassifier handles it
        deterministically (TOOL_NOT_FOUND -> ESCALATE) without calling failure_think."""
        # Setup: registry with one agent, but task references a different agent
        existing_agent = StubAgent(name="existing-agent", description="I exist")
        registry = _make_registry(existing_agent)

        # Mock thinking provider — failure_think should NOT be called
        thinking = MagicMock(spec=OrchestrationThinkingProvider)
        thinking._on_cost_event = None
        thinking.failure_think = AsyncMock()

        orch = DryadeOrchestrator(
            thinking_provider=thinking,
            agent_registry=registry,
        )

        # Execute with a task that references a non-existent agent
        available_agents = [existing_agent.get_card()]
        task = OrchestrationTask(
            agent_name="nonexistent-agent",
            description="Do something",
        )
        result = await orch._execute_with_retry(
            task=task,
            execution_id="test-exec",
            context={},
            available_agents=available_agents,
        )

        # Tier 1 classifier handles it — failure_think NOT called (zero LLM cost)
        thinking.failure_think.assert_not_awaited()

        # Result should indicate failure with ESCALATE action from classifier
        assert result.success is False
        assert result.failure_thought is not None
        assert result.failure_thought.failure_action == FailureAction.ESCALATE

# ---------------------------------------------------------------------------
# BUG-006: Timeout forces escalation on retry
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestBug006TimeoutBlocksBlindRetry:
    """BUG-006 regression: timeout with identical params must force ESCALATE."""

    async def test_timeout_forces_escalation_instead_of_retry(self):
        """When an agent times out and the LLM says RETRY, the orchestrator
        should block the retry (since params are identical) and force ESCALATE."""
        # Setup: agent that times out
        timeout_agent = StubAgent(
            name="slow-agent",
            description="I time out",
            raise_on_execute=TimeoutError("Execution timed out after 30 seconds"),
        )
        registry = _make_registry(timeout_agent)

        # Mock thinking to return RETRY on failure
        thinking = MagicMock(spec=OrchestrationThinkingProvider)
        thinking._on_cost_event = None
        retry_thought = OrchestrationThought(
            reasoning="Let's retry",
            is_final=False,
            failure_action=FailureAction.RETRY,
        )
        thinking.failure_think = AsyncMock(return_value=retry_thought)

        orch = DryadeOrchestrator(
            thinking_provider=thinking,
            agent_registry=registry,
        )

        available_agents = [timeout_agent.get_card()]
        task = OrchestrationTask(
            agent_name="slow-agent",
            description="Do something slow",
            tool="some_tool",
        )

        result = await orch._execute_with_retry(
            task=task,
            execution_id="test-exec",
            context={},
            available_agents=available_agents,
        )

        # The result should have been escalated, not retried
        assert result.success is False
        assert result.failure_thought is not None
        assert result.failure_thought.failure_action == FailureAction.ESCALATE
        assert "timed out" in result.failure_thought.escalation_question.lower()

        # Only 1 execution attempt should have been made (no blind retries)
        # failure_think is called once for the first failure, then BUG-006 blocks retry
        assert thinking.failure_think.await_count == 1

    async def test_non_timeout_error_allows_retry(self):
        """Non-timeout errors should still be allowed to retry normally."""
        # Setup: agent that fails with a non-timeout error
        error_agent = StubAgent(
            name="error-agent",
            description="I error out",
            raise_on_execute=ValueError("Something went wrong"),
        )
        registry = _make_registry(error_agent)

        # Mock thinking to return RETRY then ESCALATE
        thinking = MagicMock(spec=OrchestrationThinkingProvider)
        thinking._on_cost_event = None
        thinking.failure_think = AsyncMock(
            side_effect=[
                OrchestrationThought(
                    reasoning="Let's retry",
                    is_final=False,
                    failure_action=FailureAction.RETRY,
                ),
                OrchestrationThought(
                    reasoning="Give up now",
                    is_final=False,
                    failure_action=FailureAction.ESCALATE,
                    escalation_question="Still failing, what now?",
                ),
            ]
        )

        orch = DryadeOrchestrator(
            thinking_provider=thinking,
            agent_registry=registry,
        )

        available_agents = [error_agent.get_card()]
        task = OrchestrationTask(
            agent_name="error-agent",
            description="Do something broken",
        )

        result = await orch._execute_with_retry(
            task=task,
            execution_id="test-exec",
            context={},
            available_agents=available_agents,
        )

        # For non-timeout errors, retry should be allowed
        # failure_think should be called at least 2 times (first retry, then escalate)
        assert thinking.failure_think.await_count == 2
        assert result.success is False

# ---------------------------------------------------------------------------
# BUG-007: Escalation uses action description as fallback
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestBug007EscalationUsesActionDescription:
    """BUG-007 regression: escalation_question uses action.description when
    thought.escalation_question is missing."""

    async def test_escalation_uses_action_description_when_no_escalation_question(self):
        """When failure_thought has no escalation_question but the error produces
        an escalation action with a description, that description should be used."""
        # Setup: agent that doesn't exist (triggers agent-not-found path)
        existing_agent = StubAgent(name="existing-agent")
        registry = _make_registry(existing_agent)

        # Create an observation with failure_thought that has NO escalation_question
        observation = OrchestrationObservation(
            agent_name="nonexistent-agent",
            task="Do something",
            result=None,
            success=False,
            error="Agent 'nonexistent-agent' not found",
        )
        # Attach a thought with ESCALATE but no escalation_question
        observation.failure_thought = OrchestrationThought(
            reasoning="Agent not found",
            is_final=False,
            failure_action=FailureAction.ESCALATE,
            escalation_question=None,  # This is the BUG-007 scenario
        )

        thinking = MagicMock(spec=OrchestrationThinkingProvider)
        thinking._on_cost_event = None

        orch = DryadeOrchestrator(
            thinking_provider=thinking,
            agent_registry=registry,
        )

        from core.orchestrator.models import OrchestrationState

        state = OrchestrationState()

        result = await orch._handle_failure(
            observation=observation,
            context={},
            available_agents=[existing_agent.get_card()],
            state=state,
        )

        # The result should use the action description, not the generic message
        assert result.needs_escalation is True
        assert result.escalation_question is not None
        # Inline escalation detection in _handle_failure (deleted parse_escalation_action_from_response in 118.1)
        # returns a CREATE_AGENT action with a description like "No suitable agent found..."
        # The old generic message was "Task failed: {task}. How should I proceed?"
        # The new message should contain the action description or error context
        assert (
            "How should I proceed?" not in result.escalation_question
            or "Error:" in result.escalation_question
        )
        # The escalation_action should be present (CREATE_AGENT type)
        assert result.escalation_action is not None
        # CREATE_AGENT preserved for backward compat but FACTORY_CREATE is preferred
        assert result.escalation_action["action_type"] in ("create_agent", "factory_create")
        # The escalation_question should contain the action's description
        assert (
            "No suitable agent" in result.escalation_question
            or "factory" in result.escalation_question.lower()
            or result.escalation_action["description"] in result.escalation_question
        )

    async def test_escalation_with_explicit_question_uses_it(self):
        """When failure_thought has an explicit escalation_question, it should
        be used regardless of the action description."""
        existing_agent = StubAgent(name="existing-agent")
        registry = _make_registry(existing_agent)

        observation = OrchestrationObservation(
            agent_name="mcp-filesystem",
            task="Read file",
            result=None,
            success=False,
            error="Access denied - path outside allowed directories: /home/user/Desktop not in /tmp",
        )
        observation.failure_thought = OrchestrationThought(
            reasoning="Path not allowed",
            is_final=False,
            failure_action=FailureAction.ESCALATE,
            escalation_question="I need permission to access /home/user/Desktop. Allow it?",
        )

        thinking = MagicMock(spec=OrchestrationThinkingProvider)
        thinking._on_cost_event = None

        orch = DryadeOrchestrator(
            thinking_provider=thinking,
            agent_registry=registry,
        )

        from core.orchestrator.models import OrchestrationState

        state = OrchestrationState()

        result = await orch._handle_failure(
            observation=observation,
            context={},
            available_agents=[existing_agent.get_card()],
            state=state,
        )

        # The explicit escalation_question from thought should be used
        assert result.needs_escalation is True
        assert (
            result.escalation_question
            == "I need permission to access /home/user/Desktop. Allow it?"
        )
