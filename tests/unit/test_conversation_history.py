"""Unit tests for conversation history wiring (Phase 86.3).

Tests cover:
- History fetch in route_request: injection, dedup, empty, failure tolerance
- History consumption in orchestrate_think: budget, ordering, empty cases
"""

import json
from unittest.mock import MagicMock, patch

import pytest

# Pre-load the router module. The core.orchestrator.__init__ imports
# DryadeOrchestrator which pulls in sentence_transformers (not installed
# in unit-test environment). We catch the error so that the submodules
# that loaded successfully (router, handlers, models) stay in sys.modules
# and are importable for all tests.
try:
    import core.orchestrator.router  # noqa: F401
except (ImportError, ModuleNotFoundError):
    pass

try:
    import core.orchestrator.thinking  # noqa: F401
except (ImportError, ModuleNotFoundError):
    pass

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def collect_events(gen):
    """Collect all events from an async generator."""
    events = []
    async for event in gen:
        events.append(event)
    return events

async def _get_context_from_route_request(
    history_return_value=None,
    history_side_effect=None,
    mode_override=None,
    enable_thinking=False,
    user_llm_config=None,
    crew_id=None,
    leash_preset=None,
):
    """Call route_request, intercept the ExecutionContext passed to router.route().

    Patches both get_router().route and get_recent_history to control behavior.
    Returns the captured ExecutionContext.
    """
    captured_ctx = None

    async def capture_route(message, context, stream=True):
        nonlocal captured_ctx
        captured_ctx = context
        return
        yield  # make it an async generator  # noqa: E501

    with (
        patch("core.orchestrator.router.get_router") as mock_get,
        patch("core.services.conversation.get_recent_history") as mock_history,
    ):
        mock_router = MagicMock()
        mock_router.route = capture_route
        mock_get.return_value = mock_router

        if history_side_effect is not None:
            mock_history.side_effect = history_side_effect
        else:
            mock_history.return_value = history_return_value or []

        from core.orchestrator.router import route_request

        gen = route_request(
            message="yes",
            conversation_id="conv-test",
            user_id="user-1",
            mode_override=mode_override,
            enable_thinking=enable_thinking,
            user_llm_config=user_llm_config,
            crew_id=crew_id,
            leash_preset=leash_preset,
        )
        # Consume the generator
        async for _ in gen:
            pass

    assert captured_ctx is not None, "route_request did not call router.route()"
    return captured_ctx

# ---------------------------------------------------------------------------
# TestHistoryFetchInRouteRequest
# ---------------------------------------------------------------------------

class TestHistoryFetchInRouteRequest:
    """Tests for the history fetch logic in route_request()."""

    @pytest.mark.asyncio
    async def test_history_injected_into_metadata(self):
        """History from get_recent_history is injected into context.metadata.

        Mock get_recent_history to return 4 messages (the last being a user msg).
        Assert context.metadata["history"] has 3 messages (last user msg deduped).
        """
        raw_history = [
            {"role": "user", "content": "first question"},
            {"role": "assistant", "content": "first answer"},
            {"role": "user", "content": "follow-up"},
            {"role": "assistant", "content": "follow-up answer"},
        ]

        # Last message is assistant, so no dedup -- all 4 kept
        # Wait, re-read: route_request checks raw_history[-1]["role"] == "user"
        # Here last is assistant, so history = raw_history (all 4)
        ctx = await _get_context_from_route_request(history_return_value=raw_history)

        assert "history" in ctx.metadata
        assert len(ctx.metadata["history"]) == 4

    @pytest.mark.asyncio
    async def test_history_dedup_drops_last_user_message(self):
        """When the last message in history is role='user', it's dropped.

        The current user message was already persisted to DB before route_request,
        so the last user message in the fetched history is a duplicate.
        """
        raw_history = [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "response"},
            {"role": "user", "content": "yes"},  # This is the current message
        ]

        ctx = await _get_context_from_route_request(history_return_value=raw_history)

        assert len(ctx.metadata["history"]) == 2
        assert ctx.metadata["history"][0]["content"] == "first"
        assert ctx.metadata["history"][1]["content"] == "response"

    @pytest.mark.asyncio
    async def test_history_no_dedup_when_last_is_assistant(self):
        """When the last message is role='assistant', all messages are kept."""
        raw_history = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]

        ctx = await _get_context_from_route_request(history_return_value=raw_history)

        assert len(ctx.metadata["history"]) == 2
        assert ctx.metadata["history"][0]["content"] == "hello"
        assert ctx.metadata["history"][1]["content"] == "hi"

    @pytest.mark.asyncio
    async def test_history_empty_when_no_conversation(self):
        """When get_recent_history returns [], metadata history is []."""
        ctx = await _get_context_from_route_request(history_return_value=[])

        assert ctx.metadata["history"] == []

    @pytest.mark.asyncio
    async def test_history_fetch_failure_is_nonfatal(self):
        """When get_recent_history raises, history is [] (no crash)."""
        ctx = await _get_context_from_route_request(
            history_side_effect=Exception("DB error"),
        )

        assert ctx.metadata["history"] == []

# ---------------------------------------------------------------------------
# TestHistoryConsumptionInOrchestrate
# ---------------------------------------------------------------------------

class TestHistoryConsumptionInOrchestrate:
    """Tests for history consumption in orchestrate_think()."""

    def _make_provider(self):
        """Create an OrchestrationThinkingProvider with a mock LLM."""
        from core.orchestrator.thinking import OrchestrationThinkingProvider

        mock_llm = MagicMock()
        provider = OrchestrationThinkingProvider(llm=mock_llm)
        return provider, mock_llm

    def _make_observation_history(self):
        """Create a mock ObservationHistory."""
        mock_oh = MagicMock()
        mock_oh.format_for_llm.return_value = "<observations>none</observations>"
        return mock_oh

    def _valid_llm_response(self):
        """Return a valid orchestration JSON response string."""
        return json.dumps(
            {
                "reasoning": "test",
                "reasoning_summary": "test",
                "is_final": True,
                "answer": "ok",
                "task": None,
                "parallel_tasks": None,
            }
        )

    @pytest.mark.asyncio
    async def test_history_messages_prepended_between_system_and_user(self):
        """History messages appear between system and user messages in LLM call.

        Expected order: [system, user("first"), assistant("reply"), user(goal)]
        """
        provider, mock_llm = self._make_provider()
        obs_history = self._make_observation_history()

        captured_messages = None

        async def capture_call_llm(messages, tools=None):
            nonlocal captured_messages
            captured_messages = messages
            return (self._valid_llm_response(), None)

        provider._call_llm = capture_call_llm

        history = [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "reply"},
        ]

        await provider.orchestrate_think(
            goal="do something",
            observations=[],
            available_agents=[],
            observation_history=obs_history,
            context={"history": history},
        )

        assert captured_messages is not None
        # Message structure: [system, user("first"), assistant("reply"), user(goal)]
        assert len(captured_messages) == 4
        assert captured_messages[0]["role"] == "system"
        assert captured_messages[1]["role"] == "user"
        assert captured_messages[1]["content"] == "first"
        assert captured_messages[2]["role"] == "assistant"
        assert captured_messages[2]["content"] == "reply"
        assert captured_messages[3]["role"] == "user"
        assert "do something" in captured_messages[3]["content"]

    @pytest.mark.asyncio
    async def test_history_budget_truncates_oldest_messages(self):
        """Messages exceeding 2000 chars budget are truncated from oldest.

        Build 5 messages with 500 chars each (total 2500). Budget is 2000.
        The oldest message should be dropped, keeping the most recent 4.
        """
        provider, mock_llm = self._make_provider()
        obs_history = self._make_observation_history()

        captured_messages = None

        async def capture_call_llm(messages, tools=None):
            nonlocal captured_messages
            captured_messages = messages
            return (self._valid_llm_response(), None)

        provider._call_llm = capture_call_llm

        # Build 5 messages, each with 500-char content
        history = []
        for i in range(5):
            role = "user" if i % 2 == 0 else "assistant"
            history.append({"role": role, "content": f"msg{i}-" + "x" * 495})

        await provider.orchestrate_think(
            goal="test budget",
            observations=[],
            available_agents=[],
            observation_history=obs_history,
            context={"history": history},
        )

        assert captured_messages is not None
        # Total messages = system + (kept history) + user
        # 5 messages * 500 chars = 2500, budget = 2000
        # The budget loop goes from most recent to oldest:
        #   msg4 (500), msg3 (500), msg2 (500), msg1 (500) = 2000 -> fits
        #   msg0 (500) would exceed -> dropped
        # So 4 history messages kept + system + user = 6
        history_msgs = [
            m for m in captured_messages if m not in [captured_messages[0], captured_messages[-1]]
        ]
        assert len(history_msgs) == 4
        # The oldest message (msg0) should be dropped
        for m in history_msgs:
            assert not m["content"].startswith("msg0-")

    @pytest.mark.asyncio
    async def test_empty_history_produces_standard_messages(self):
        """With empty history, messages list is [system, user]."""
        provider, mock_llm = self._make_provider()
        obs_history = self._make_observation_history()

        captured_messages = None

        async def capture_call_llm(messages, tools=None):
            nonlocal captured_messages
            captured_messages = messages
            return (self._valid_llm_response(), None)

        provider._call_llm = capture_call_llm

        await provider.orchestrate_think(
            goal="test empty",
            observations=[],
            available_agents=[],
            observation_history=obs_history,
            context={"history": []},
        )

        assert captured_messages is not None
        assert len(captured_messages) == 2
        assert captured_messages[0]["role"] == "system"
        assert captured_messages[1]["role"] == "user"

    @pytest.mark.asyncio
    async def test_no_context_produces_standard_messages(self):
        """With context=None, messages list is [system, user]."""
        provider, mock_llm = self._make_provider()
        obs_history = self._make_observation_history()

        captured_messages = None

        async def capture_call_llm(messages, tools=None):
            nonlocal captured_messages
            captured_messages = messages
            return (self._valid_llm_response(), None)

        provider._call_llm = capture_call_llm

        await provider.orchestrate_think(
            goal="test no context",
            observations=[],
            available_agents=[],
            observation_history=obs_history,
            context=None,
        )

        assert captured_messages is not None
        assert len(captured_messages) == 2
        assert captured_messages[0]["role"] == "system"
        assert captured_messages[1]["role"] == "user"
