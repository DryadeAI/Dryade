"""Regression tests for X-Ray 114.1 bugs: BUG-001, BUG-003, BUG-004.

BUG-001: Escalation approval patterns -- "create it", "let's do it", etc.
BUG-003: INSTANT tier reasoning leak -- merge_thinking=False with fallback.
BUG-004: Native tool call parameter defaults -- missing required params filled.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.orchestrator.escalation import is_approval_message
from core.orchestrator.thinking.provider import OrchestrationThinkingProvider

# ---------------------------------------------------------------------------
# BUG-001: Escalation approval pattern coverage
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "message,expected",
    [
        # Existing patterns (sanity check)
        ("yes", True),
        ("ok", True),
        ("go ahead", True),
        ("no", False),
        ("cancel", False),
        # NEW patterns (BUG-001 regression)
        ("create it", True),
        ("create one", True),
        ("create the agent", True),
        ("make it", True),
        ("let's do it", True),
        ("lets go", True),
        ("go for it", True),
        ("sounds good", True),
        ("that's fine", True),
        ("that's great", True),
        ("absolutely", True),
        ("definitely", True),
        ("of course", True),
        ("correct", True),
        ("exactly", True),
        ("works for me", True),
        ("right", True),
        ("affirmative", True),
        ("perfect", True),
        ("great", True),
        ("fine", True),
        ("alright", True),
        # Non-approval messages (should return None)
        ("what does that mean?", None),
        ("tell me more", None),
        ("I'm not sure about that", None),
    ],
)
def test_approval_patterns(message, expected):
    """BUG-001 regression: approval/rejection/neutral pattern recognition."""
    result = is_approval_message(message)
    assert result == expected, (
        f"is_approval_message({message!r}) = {result!r}, expected {expected!r}"
    )

# ---------------------------------------------------------------------------
# BUG-003: INSTANT tier merge_thinking=False with reasoning fallback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_instant_content_only_no_reasoning_leak():
    """BUG-003: When model produces both reasoning and content, only content is used."""
    from core.orchestrator.handlers.instant_handler import InstantHandler

    handler = InstantHandler()
    context = MagicMock()
    context.metadata = {}

    # Mock ThinkingProvider to return content + reasoning
    mock_provider = MagicMock()
    mock_provider._stream_llm = AsyncMock(return_value=("Hello user!", "internal thinking...", 5))

    with patch(
        "core.orchestrator.thinking.OrchestrationThinkingProvider",
        return_value=mock_provider,
    ):
        events = []
        async for event in handler.handle("hi", context, stream=True):
            events.append(event)

    # The complete event should contain only "Hello user!", not the reasoning
    complete_events = [e for e in events if e.type == "complete"]
    assert len(complete_events) == 1
    assert complete_events[0].content == "Hello user!"

    # Verify merge_thinking=False was passed
    call_kwargs = mock_provider._stream_llm.call_args
    assert call_kwargs.kwargs.get("merge_thinking") is False

@pytest.mark.asyncio
async def test_instant_reasoning_fallback_when_content_empty():
    """BUG-003: When model puts answer only in reasoning_content, use it as content."""
    from core.orchestrator.handlers.instant_handler import InstantHandler

    handler = InstantHandler()
    context = MagicMock()
    context.metadata = {}

    # Mock ThinkingProvider to return empty content but reasoning
    mock_provider = MagicMock()
    mock_provider._stream_llm = AsyncMock(return_value=("", "The answer is 42", 5))

    with patch(
        "core.orchestrator.thinking.OrchestrationThinkingProvider",
        return_value=mock_provider,
    ):
        events = []
        async for event in handler.handle("what is the answer?", context, stream=True):
            events.append(event)

    # The complete event should use reasoning as fallback content
    complete_events = [e for e in events if e.type == "complete"]
    assert len(complete_events) == 1
    assert complete_events[0].content == "The answer is 42"

# ---------------------------------------------------------------------------
# BUG-004: Parameter default injection for native tool calls
# ---------------------------------------------------------------------------

def test_fill_missing_git_diff_target():
    """BUG-004: git_diff with no target gets target=HEAD injected."""
    provider = OrchestrationThinkingProvider.__new__(OrchestrationThinkingProvider)
    result = provider._fill_missing_required_params("git_diff", {})
    assert result == {"target": "HEAD"}

def test_fill_preserves_existing_params():
    """BUG-004: Existing params are not overwritten by defaults."""
    provider = OrchestrationThinkingProvider.__new__(OrchestrationThinkingProvider)
    result = provider._fill_missing_required_params("git_diff", {"target": "main"})
    assert result == {"target": "main"}  # Not overwritten

def test_fill_unknown_tool_no_change():
    """BUG-004: Unknown tools pass through unchanged."""
    provider = OrchestrationThinkingProvider.__new__(OrchestrationThinkingProvider)
    result = provider._fill_missing_required_params("unknown_tool", {"foo": "bar"})
    assert result == {"foo": "bar"}

def test_fill_git_log_max_count():
    """BUG-004: git_log with no max_count gets max_count=10 injected."""
    provider = OrchestrationThinkingProvider.__new__(OrchestrationThinkingProvider)
    result = provider._fill_missing_required_params("git_log", {})
    assert result == {"max_count": 10}

def test_fill_search_files_path():
    """BUG-004: search_files with no path gets path=. injected."""
    provider = OrchestrationThinkingProvider.__new__(OrchestrationThinkingProvider)
    result = provider._fill_missing_required_params("search_files", {})
    assert result == {"path": "."}

def test_fill_list_directory_path():
    """BUG-004: list_directory with no path gets path=. injected."""
    provider = OrchestrationThinkingProvider.__new__(OrchestrationThinkingProvider)
    result = provider._fill_missing_required_params("list_directory", {})
    assert result == {"path": "."}

def test_fill_read_file_no_defaults():
    """BUG-004: read_file has no sensible defaults, passes through unchanged."""
    provider = OrchestrationThinkingProvider.__new__(OrchestrationThinkingProvider)
    result = provider._fill_missing_required_params("read_file", {"path": "/tmp/x"})
    assert result == {"path": "/tmp/x"}

def test_fill_partial_params_merged():
    """BUG-004: Only missing params are filled, existing ones preserved."""
    provider = OrchestrationThinkingProvider.__new__(OrchestrationThinkingProvider)
    result = provider._fill_missing_required_params("git_log", {"ref": "main"})
    assert result == {"ref": "main", "max_count": 10}
