"""Tests for Phase 111 streaming pipeline fixes.

Verifies:
1. Token events pass through named-steps visibility filter.
2. Token events are blocked at minimal level.
3. Token events pass through full-transparency level.
4. _stream_final_answer uses merge_thinking=True so reasoning model
   answers stream into the message bubble.
"""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure a mock litellm module is available for patching
# (litellm may not be installed in the test environment)
if "litellm" not in sys.modules:
    _mock_litellm = MagicMock()
    _mock_litellm.acompletion = AsyncMock()
    sys.modules["litellm"] = _mock_litellm

from core.orchestrator.handlers._utils import _should_emit
from core.orchestrator.thinking import OrchestrationThinkingProvider

def test_token_passes_named_steps():
    """Token events must pass the named-steps visibility filter.

    Phase 111 removed 'token' from the named-steps deny set because
    token events carry the actual answer content for COMPLEX-tier
    responses. Blocking them caused blank/incomplete answers.
    """
    assert _should_emit("token", "named-steps") is True

def test_token_blocked_at_minimal():
    """Token events must still be blocked at minimal visibility level.

    Minimal level only allows: complete, error, escalation, cancel_ack.
    Streaming tokens are not appropriate for minimal mode.
    """
    assert _should_emit("token", "minimal") is False

def test_token_passes_full_transparency():
    """Token events must pass the full-transparency visibility filter.

    Full-transparency has an empty deny set, so everything passes.
    """
    assert _should_emit("token", "full-transparency") is True

@pytest.mark.asyncio
async def test_stream_final_answer_uses_merge_thinking_true():
    """_stream_final_answer must call _stream_llm with merge_thinking=False.

    merge_thinking=False ensures reasoning tokens go to the thinking panel
    (on_thinking) and content tokens go to the chat bubble (on_token).
    This prevents reasoning from leaking into the user-visible message.
    If the model puts everything in reasoning_content, a fallback re-emits
    it as content.
    """
    provider = OrchestrationThinkingProvider()

    # Mock _stream_llm to capture the merge_thinking parameter
    mock_stream = AsyncMock(return_value=("answer text", "", 10))

    # Mock ObservationHistory
    mock_obs_history = MagicMock()
    mock_obs_history.format_for_llm.return_value = "<observations/>"

    with patch.object(provider, "_stream_llm", mock_stream):
        result = await provider._stream_final_answer(
            goal="test goal",
            observations=[],
            observation_history=mock_obs_history,
            context=None,
            on_token=lambda t: None,
            on_thinking=lambda t: None,
            cancel_event=None,
        )

    # Verify _stream_llm was called exactly once
    mock_stream.assert_called_once()

    # Verify merge_thinking=False was passed (reasoning tokens go to thinking
    # panel; content tokens go to chat bubble — prevents reasoning leak)
    call_kwargs = mock_stream.call_args
    assert call_kwargs.kwargs.get("merge_thinking") is False, (
        f"Expected merge_thinking=False, got {call_kwargs.kwargs.get('merge_thinking')}"
    )

    # Verify the return value was passed through
    assert result == ("answer text", "", 10)
