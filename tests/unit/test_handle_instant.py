"""Tests for InstantHandler (INSTANT tier path).

Covers InstantHandler.handle(), feature flag gating, and tier dispatch
wiring in TierDispatcher.handle().
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from core.extensions.events import ChatEvent
from core.orchestrator.handlers.complex_handler import TierDispatcher
from core.orchestrator.handlers.instant_handler import InstantHandler

def _make_context(**kwargs):
    """Create a mock ExecutionContext."""
    ctx = MagicMock()
    ctx.conversation_id = kwargs.get("conversation_id", "test-conv-1")
    ctx.user_id = kwargs.get("user_id", "test-user-1")
    ctx.metadata = kwargs.get(
        "metadata",
        {
            "orchestration_mode": "adaptive",
            "memory_enabled": True,
            "reasoning_visibility": "summary",
            "event_visibility": "named-steps",
        },
    )
    return ctx

class TestHandleInstant:
    """Direct tests for InstantHandler.handle()."""

    @pytest.mark.asyncio
    async def test_streams_tokens_and_emits_complete(self):
        """InstantHandler.handle streams tokens and ends with complete."""
        handler = InstantHandler()
        context = _make_context()

        # Mock _stream_llm to call on_token with content, then return
        async def mock_stream_llm(
            messages, on_token=None, on_thinking=None, cancel_event=None, merge_thinking=False
        ):
            if on_token:
                on_token("Hello! I'm Dryade.")
            return ("Hello! I'm Dryade.", "", 5)

        with patch(
            "core.orchestrator.thinking.OrchestrationThinkingProvider._stream_llm",
            side_effect=mock_stream_llm,
        ):
            events = []
            async for event in handler.handle("hello", context):
                events.append(event)

        # Should have at least a complete event
        event_types = [e.type for e in events]
        assert "complete" in event_types, f"Missing complete event. Got: {event_types}"

        # Complete event should have the response
        complete_events = [e for e in events if e.type == "complete"]
        assert len(complete_events) == 1
        assert "Dryade" in complete_events[0].content

    @pytest.mark.asyncio
    async def test_includes_conversation_history(self):
        """InstantHandler.handle passes history from context.metadata to LLM."""
        handler = InstantHandler()
        context = _make_context(
            metadata={
                "orchestration_mode": "adaptive",
                "memory_enabled": True,
                "reasoning_visibility": "summary",
                "event_visibility": "named-steps",
                "history": [
                    {"role": "user", "content": "My name is Alice"},
                    {"role": "assistant", "content": "Hello Alice!"},
                ],
            }
        )

        captured_messages = []

        async def mock_stream_llm(
            messages, on_token=None, on_thinking=None, cancel_event=None, merge_thinking=False
        ):
            captured_messages.extend(messages)
            return ("Hi Alice!", "", 3)

        with patch(
            "core.orchestrator.thinking.OrchestrationThinkingProvider._stream_llm",
            side_effect=mock_stream_llm,
        ):
            events = []
            async for event in handler.handle("hello again", context):
                events.append(event)

        # Check that history was included in messages
        roles = [m["role"] for m in captured_messages]
        assert "system" in roles
        assert roles.count("user") >= 2  # history user + current user
        assert "assistant" in roles  # history assistant

    @pytest.mark.asyncio
    async def test_history_budget_cap(self):
        """History is capped at 2000 chars."""
        handler = InstantHandler()
        # Create history that exceeds budget
        long_history = [
            {"role": "user", "content": "x" * 1500},
            {"role": "assistant", "content": "y" * 1500},
            {"role": "user", "content": "z" * 100},
        ]
        context = _make_context(
            metadata={
                "orchestration_mode": "adaptive",
                "event_visibility": "named-steps",
                "history": long_history,
            }
        )

        captured_messages = []

        async def mock_stream_llm(
            messages, on_token=None, on_thinking=None, cancel_event=None, merge_thinking=False
        ):
            captured_messages.extend(messages)
            return ("response", "", 2)

        with patch(
            "core.orchestrator.thinking.OrchestrationThinkingProvider._stream_llm",
            side_effect=mock_stream_llm,
        ):
            async for _ in handler.handle("hi", context):
                pass

        # Should not include all 3100 chars of history
        history_chars = sum(
            len(m.get("content", ""))
            for m in captured_messages
            if m["role"] != "system" and m.get("content") != "hi"
        )
        assert history_chars <= 2100  # budget + some tolerance

class TestFeatureFlagGating:
    """Test that DRYADE_TIER_INSTANT_ENABLED gates the INSTANT path."""

    @pytest.mark.asyncio
    async def test_instant_disabled_by_default(self):
        """With no env var, INSTANT messages go through COMPLEX path."""
        handler = TierDispatcher()
        context = _make_context()

        # Remove env var if set
        os.environ.pop("DRYADE_TIER_INSTANT_ENABLED", None)

        with (
            patch("core.adapters.registry.get_registry") as mock_reg,
            patch(
                "core.orchestrator.orchestrator.DryadeOrchestrator", autospec=False
            ) as mock_orch_cls,
        ):
            # Set up registry mock
            mock_reg.return_value.list_agents.return_value = []

            # Set up orchestrator mock for COMPLEX path
            mock_result = MagicMock()
            mock_result.needs_escalation = False
            mock_result.success = True
            mock_result.output = "complex response"
            mock_result.partial_results = []
            mock_result.reasoning = None
            mock_result.streamed = False

            mock_orch_instance = MagicMock()
            mock_orch_instance.thinking = MagicMock()
            mock_orch_instance.thinking._on_cost_event = None
            mock_orch_instance.agents.list_agents.return_value = []
            mock_orch_cls.return_value = mock_orch_instance

            # Mock orchestrate to return result via queue sentinel
            async def mock_orchestrate(**kwargs):
                return mock_result

            mock_orch_instance.orchestrate = mock_orchestrate

            # Verify handle() does NOT call InstantHandler.handle
            with patch.object(handler._instant, "handle") as mock_instant:
                events = []
                async for event in handler.handle("hello", context):
                    events.append(event)

                # _instant.handle should NOT have been called
                mock_instant.assert_not_called()

    @pytest.mark.asyncio
    async def test_instant_enabled_routes_to_handle_instant(self):
        """With DRYADE_TIER_INSTANT_ENABLED=true, INSTANT goes to InstantHandler."""
        handler = TierDispatcher()
        context = _make_context()

        os.environ["DRYADE_TIER_INSTANT_ENABLED"] = "true"
        try:
            with patch("core.adapters.registry.get_registry") as mock_reg:
                mock_reg.return_value.list_agents.return_value = []

                # Mock InstantHandler.handle to yield a complete event
                async def mock_handle_instant(msg, ctx, stream=True):
                    yield ChatEvent(type="complete", content="instant response")

                with patch.object(handler._instant, "handle", side_effect=mock_handle_instant):
                    events = []
                    async for event in handler.handle("hello", context):
                        events.append(event)

                    # Should have called _instant.handle
                    event_types = [e.type for e in events]
                    assert "complete" in event_types
        finally:
            os.environ.pop("DRYADE_TIER_INSTANT_ENABLED", None)
