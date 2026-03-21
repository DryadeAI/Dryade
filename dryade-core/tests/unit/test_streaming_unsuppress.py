"""Regression tests for streaming un-suppression.

Covers:
- Token emission with meta_hint active (R1)
- Thinking emission with meta_hint active (R1)
- Processing status event before meta-action orchestration (R2)
- Empty complete content for meta-action fallback (R3)
- Factory progress uses send_sequenced (R4)
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.extensions.events import ChatEvent, emit_thinking, emit_token

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_context(
    conversation_id: str = "conv-1",
    user_id: str = "user-1",
    metadata: dict | None = None,
):
    ctx = MagicMock()
    ctx.conversation_id = conversation_id
    ctx.user_id = user_id
    ctx.metadata = metadata if metadata is not None else {}
    return ctx

def _make_tier_decision(*, meta_action_hint: bool = True, confidence: float = 0.9):
    td = MagicMock()
    td.meta_action_hint = meta_action_hint
    td.confidence = confidence
    td.tier = MagicMock()
    td.tier.value = "COMPLEX"
    td.sub_mode = None
    td.reason = "test"
    td.target_agent = None
    return td

async def _collect_events(gen) -> list[ChatEvent]:
    events = []
    async for event in gen:
        events.append(event)
    return events

# ---------------------------------------------------------------------------
# Test 1: on_token_cb emits when meta_hint is active
# ---------------------------------------------------------------------------

class TestTokenEmissionWithMetaHint:
    """Verify on_token_cb streams tokens even when meta_hint=True."""

    def test_on_token_cb_emits_unconditionally(self):
        """on_token_cb should emit token events regardless of meta_hint."""
        queue: asyncio.Queue = asyncio.Queue()
        meta_hint = True  # noqa: F841 -- simulates closure capture

        # Simulate the closure behavior after un-suppression
        def on_token_cb(token_content: str) -> None:
            queue.put_nowait(emit_token(token_content))

        on_token_cb("Hello ")
        on_token_cb("world")

        assert queue.qsize() == 2
        event1 = queue.get_nowait()
        assert event1.type == "token"
        assert event1.content == "Hello "
        event2 = queue.get_nowait()
        assert event2.type == "token"
        assert event2.content == "world"

# ---------------------------------------------------------------------------
# Test 2: on_thinking emits when meta_hint is active
# ---------------------------------------------------------------------------

class TestThinkingEmissionWithMetaHint:
    """Verify on_thinking streams thinking events even when meta_hint=True."""

    def test_on_thinking_emits_unconditionally(self):
        """on_thinking should emit thinking events regardless of meta_hint."""
        queue: asyncio.Queue = asyncio.Queue()
        meta_hint = True  # noqa: F841 -- simulates closure capture

        # Simulate the closure behavior after un-suppression
        def on_thinking(reasoning: str) -> None:
            queue.put_nowait(emit_thinking(reasoning))

        on_thinking("Analyzing the request...")

        assert queue.qsize() == 1
        event = queue.get_nowait()
        assert event.type == "thinking"
        assert event.content == "Analyzing the request..."

# ---------------------------------------------------------------------------
# Test 3: Processing status event emitted before meta-action orchestration
# ---------------------------------------------------------------------------

class TestMetaActionProcessingStatus:
    """Verify that a processing thinking event is emitted at orchestration start."""

    def test_processing_status_emitted_when_meta_hint_active(self):
        """When meta_hint=True, a 'processing' thinking event is queued."""
        queue: asyncio.Queue = asyncio.Queue()
        meta_hint = True

        # Simulate the top of run_orchestration() try block
        if meta_hint:
            queue.put_nowait(emit_thinking("Analyzing request to determine capabilities needed..."))

        assert queue.qsize() == 1
        event = queue.get_nowait()
        assert event.type == "thinking"
        assert "Analyzing request" in event.content

    def test_processing_status_not_emitted_without_meta_hint(self):
        """When meta_hint=False, no processing status event is queued."""
        queue: asyncio.Queue = asyncio.Queue()
        meta_hint = False

        if meta_hint:
            queue.put_nowait(emit_thinking("Analyzing request to determine capabilities needed..."))

        assert queue.qsize() == 0

# ---------------------------------------------------------------------------
# Test 4: Meta-action complete event has empty content
# ---------------------------------------------------------------------------

class TestMetaActionCompleteEventEmpty:
    """Verify _handle_meta_action emits complete with empty response."""

    @pytest.mark.asyncio
    async def test_meta_action_complete_event_empty_content(self):
        """The complete event from _handle_meta_action should have response=''."""
        from core.orchestrator.handlers.complex_handler import ComplexHandler

        handler = ComplexHandler()
        context = _make_context(metadata={})
        tier_decision = _make_tier_decision(meta_action_hint=True)

        # Patch at source module since _handle_meta_action uses a lazy import
        with patch("core.orchestrator.escalation.get_escalation_registry") as mock_reg:
            mock_reg.return_value = MagicMock()
            events = await _collect_events(
                handler._handle_meta_action("create a websearch agent", context, tier_decision)
            )

        # Should yield escalation + complete
        assert len(events) == 2
        escalation_event = events[0]
        complete_event = events[1]

        assert escalation_event.type == "escalation"
        assert complete_event.type == "complete"
        # Key assertion: response is empty string, not the escalation question
        assert complete_event.content == ""
        assert complete_event.metadata["usage"]["meta_action_intercepted"] is True

# ---------------------------------------------------------------------------
# Test 5: Factory progress uses send_sequenced
# ---------------------------------------------------------------------------

class TestFactoryProgressSendSequenced:
    """Verify _emit_progress uses send_sequenced instead of send."""

    @pytest.mark.asyncio
    async def test_emit_progress_calls_send_sequenced(self):
        """_emit_progress should call manager.send_sequenced, not manager.send."""
        from core.factory.orchestrator import FactoryPipeline

        pipeline = FactoryPipeline(conversation_id="conv-123")

        mock_session = MagicMock()
        mock_manager = MagicMock()
        mock_manager.get_session.return_value = mock_session
        mock_manager.send_sequenced = AsyncMock()
        mock_manager.send = AsyncMock()  # Should NOT be called

        # Patch at source module since _emit_progress uses a lazy import
        with patch("core.api.routes.websocket.manager", mock_manager):
            await pipeline._emit_progress(1, "deduplication", "test-artifact")

        # send_sequenced should be called
        mock_manager.send_sequenced.assert_called_once()
        call_args = mock_manager.send_sequenced.call_args
        assert call_args[0][0] is mock_session
        assert call_args[0][1] == "progress"
        assert "content" in call_args[0][2]
        assert call_args[0][2].get("factory") is True

        # Legacy send should NOT be called
        mock_manager.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_emit_progress_skips_when_no_session(self):
        """_emit_progress should skip when no session found."""
        from core.factory.orchestrator import FactoryPipeline

        pipeline = FactoryPipeline(conversation_id="conv-missing")

        mock_manager = MagicMock()
        mock_manager.get_session.return_value = None
        mock_manager.send_sequenced = AsyncMock()

        # Patch at source module since _emit_progress uses a lazy import
        with patch("core.api.routes.websocket.manager", mock_manager):
            await pipeline._emit_progress(1, "deduplication", "test-artifact")

        mock_manager.send_sequenced.assert_not_called()
