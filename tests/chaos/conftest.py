"""Shared fixtures and helpers for chaos tests.

Chaos tests exercise the real DryadeOrchestrator with mocked agents
that inject specific failure modes (timeout, crash, overflow, model down).
"""

from typing import Any
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
    OrchestrationTask,
    OrchestrationThought,
)
from core.orchestrator.orchestrator import DryadeOrchestrator
from core.orchestrator.thinking import OrchestrationThinkingProvider

# ---------------------------------------------------------------------------
# StubAgent -- minimal agent for chaos testing
# ---------------------------------------------------------------------------

class StubAgent(UniversalAgent):
    """Minimal agent for chaos testing.

    Copied from tests/unit/test_failure_middleware_integration.py with
    extensions for chaos-specific needs.
    """

    def __init__(
        self,
        name: str = "chaos-agent",
        description: str = "A chaos test agent",
        result: str = "done",
        status: str = "ok",
        caps: AgentCapabilities | None = None,
        raise_on_execute: Exception | None = None,
    ):
        self._name = name
        self._description = description
        self._result = result
        self._status = status
        self._caps = caps or AgentCapabilities(
            max_retries=1,  # Minimize retries in chaos tests
            timeout_seconds=5,  # Short timeout for chaos tests
        )
        self._raise_on_execute = raise_on_execute

    def get_card(self) -> AgentCard:
        return AgentCard(
            name=self._name,
            description=self._description,
            version="1.0",
            framework=AgentFramework.CUSTOM,
        )

    async def execute(self, task: str, context: dict[str, Any] | None = None) -> AgentResult:
        if self._raise_on_execute:
            raise self._raise_on_execute
        return AgentResult(result=self._result, status=self._status)

    def get_tools(self) -> list[dict[str, Any]]:
        return []

    def capabilities(self) -> AgentCapabilities:
        return self._caps

# ---------------------------------------------------------------------------
# CountingAgent -- tracks invocations, fails for first N calls
# ---------------------------------------------------------------------------

class CountingAgent(StubAgent):
    """StubAgent variant that tracks call_count and fails for first N calls.

    Args:
        fail_until: Number of calls that should raise before succeeding.
                    0 means never fail.
        raise_on_execute: Exception to raise during failure calls.
    """

    def __init__(
        self,
        *,
        name: str = "counting-agent",
        description: str = "A counting chaos agent",
        result: str = "recovered",
        status: str = "ok",
        fail_until: int = 0,
        raise_on_execute: Exception | None = None,
        **kwargs: Any,
    ):
        super().__init__(
            name=name,
            description=description,
            result=result,
            status=status,
            raise_on_execute=None,  # We handle failures ourselves
            **kwargs,
        )
        self.fail_until = fail_until
        self._failure_exception = raise_on_execute
        self.call_count = 0

    async def execute(self, task: str, context: dict[str, Any] | None = None) -> AgentResult:
        self.call_count += 1
        if self.call_count <= self.fail_until and self._failure_exception:
            raise self._failure_exception
        return AgentResult(result=self._result, status=self._status)

# ---------------------------------------------------------------------------
# Factory functions
# ---------------------------------------------------------------------------

def make_registry(*agents: UniversalAgent) -> AgentRegistry:
    """Build a registry pre-loaded with the given agents."""
    reg = AgentRegistry()
    for a in agents:
        reg.register(a)
    return reg

def make_thinking(
    *,
    failure_action: FailureAction = FailureAction.ESCALATE,
    is_final_after_fail: bool = False,
    agent_name: str | None = None,
) -> OrchestrationThinkingProvider:
    """Return a mock-backed thinking provider for chaos tests.

    Args:
        failure_action: What action failure_think should recommend.
        is_final_after_fail: If True, failure_think returns is_final=True
            (useful for testing abort/escalate paths that end orchestration).
        agent_name: Agent name to set on failure thought (needed for RETRY).
    """
    tp = MagicMock(spec=OrchestrationThinkingProvider)
    tp._on_cost_event = None

    # orchestrate_think: always picks our test agent and assigns a task
    orchestrate_response = OrchestrationThought(
        reasoning="Chaos test: dispatching to agent",
        is_final=False,
        task=OrchestrationTask(
            agent_name=agent_name or "chaos-agent",
            description="chaos test task",
        ),
    )
    tp.orchestrate_think = AsyncMock(return_value=orchestrate_response)

    # failure_think: returns the configured failure action
    failure_thought = OrchestrationThought(
        reasoning=f"Chaos test: failure handler recommends {failure_action.value}",
        is_final=is_final_after_fail,
        failure_action=failure_action,
        escalation_question="Chaos test escalation"
        if failure_action == FailureAction.ESCALATE
        else None,
        answer="Chaos test aborted" if is_final_after_fail else None,
    )
    if failure_action == FailureAction.RETRY and agent_name:
        failure_thought.task = OrchestrationTask(
            agent_name=agent_name,
            description="retry task",
        )
    tp.failure_think = AsyncMock(return_value=failure_thought)

    return tp

def make_orchestrator(
    *,
    agents: list[UniversalAgent] | None = None,
    failure_action: FailureAction = FailureAction.ESCALATE,
    agent_name: str | None = None,
    config_overrides: dict[str, str] | None = None,
    max_actions: int = 5,
) -> DryadeOrchestrator:
    """Create a DryadeOrchestrator for chaos testing.

    Args:
        agents: List of agents to register. Defaults to a single StubAgent.
        failure_action: Default failure action for the thinking provider.
        agent_name: Agent name for thinking provider dispatching.
        config_overrides: Environment variable overrides for OrchestrationConfig.
        max_actions: Maximum actions before leash stops the orchestrator.
            Defaults to 5 to prevent infinite loops in chaos tests.
    """
    from core.autonomous.leash import LeashConfig

    if agents is None:
        agents = [StubAgent(name="chaos-agent")]

    # Determine agent name for thinking provider
    effective_name = agent_name or agents[0].get_card().name

    reg = make_registry(*agents)
    tp = make_thinking(failure_action=failure_action, agent_name=effective_name)

    leash = LeashConfig(max_actions=max_actions)
    orch = DryadeOrchestrator(thinking_provider=tp, agent_registry=reg, leash=leash)
    return orch

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Set required env vars for tests and reset failure middleware singleton."""
    monkeypatch.setenv("DRYADE_MODEL", "test-model")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    # Disable prevention checks that require a real model endpoint
    monkeypatch.setenv("DRYADE_PREVENTION_ENABLED", "false")
    # Disable failure learning (no SQLite in tests)
    monkeypatch.setenv("DRYADE_FAILURE_LEARNING_ENABLED", "false")
    # Disable middleware hooks
    monkeypatch.setenv("DRYADE_MIDDLEWARE_ENABLED", "false")
    # Disable optimization
    monkeypatch.setenv("DRYADE_OPTIMIZATION_ENABLED", "false")
    # Short timeout for chaos tests (don't wait 120s per agent call)
    monkeypatch.setenv("DRYADE_AGENT_TIMEOUT", "5")

    yield

    # Reset failure middleware singleton if it exists
    try:
        import core.orchestrator.failure_middleware as fm

        with fm._failure_pipeline_lock:
            if fm._failure_pipeline is not None:
                fm._failure_pipeline.clear()
            fm._failure_pipeline = None
    except Exception:
        pass

@pytest.fixture
def chaos_timeout() -> int:
    """Reference timeout value for chaos tests (seconds)."""
    return 30
