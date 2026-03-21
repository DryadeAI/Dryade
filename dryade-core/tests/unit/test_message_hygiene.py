# Tests for core.services.message_hygiene (migrated from plugin Phase 222).

"""Unit tests for message hygiene business logic."""

import pytest

from core.services.message_hygiene import (
    cleanup_orphaned_tool_results,
    deduplicate_messages,
    ensure_tool_call_ids,
    extract_tool_calls,
    get_conversation_stats,
    sanitize_conversation,
    truncate_messages,
    validate_message_sequence,
)

@pytest.mark.unit
class TestCleanupOrphanedToolResults:
    """Test cleanup_orphaned_tool_results removes orphaned tool results."""

    def test_removes_orphaned_tool_result(self):
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "tool", "tool_call_id": "orphan_id", "content": "result"},
        ]
        cleaned = cleanup_orphaned_tool_results(messages)
        assert len(cleaned) == 1
        assert cleaned[0]["role"] == "user"

    def test_keeps_matched_tool_result(self):
        messages = [
            {"role": "assistant", "tool_calls": [{"id": "tc_1", "function": {"name": "foo"}}]},
            {"role": "tool", "tool_call_id": "tc_1", "content": "result"},
        ]
        cleaned = cleanup_orphaned_tool_results(messages)
        assert len(cleaned) == 2

    def test_preserves_non_tool_messages(self):
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
        ]
        cleaned = cleanup_orphaned_tool_results(messages)
        assert len(cleaned) == 3

@pytest.mark.unit
class TestEnsureToolCallIds:
    """Test ensure_tool_call_ids assigns IDs to tool calls missing them."""

    def test_assigns_id_to_missing(self):
        messages = [
            {"role": "assistant", "tool_calls": [{"function": {"name": "foo"}}]},
        ]
        result = ensure_tool_call_ids(messages)
        tc_id = result[0]["tool_calls"][0]["id"]
        assert tc_id.startswith("tc_")
        assert len(tc_id) > 3

    def test_preserves_existing_id(self):
        messages = [
            {
                "role": "assistant",
                "tool_calls": [{"id": "existing_id", "function": {"name": "foo"}}],
            },
        ]
        result = ensure_tool_call_ids(messages)
        assert result[0]["tool_calls"][0]["id"] == "existing_id"

    def test_unique_ids_assigned(self):
        messages = [
            {
                "role": "assistant",
                "tool_calls": [
                    {"function": {"name": "foo"}},
                    {"function": {"name": "bar"}},
                ],
            },
        ]
        result = ensure_tool_call_ids(messages)
        ids = [tc["id"] for tc in result[0]["tool_calls"]]
        assert len(set(ids)) == 2  # unique

@pytest.mark.unit
class TestValidateMessageSequence:
    """Test validate_message_sequence detects broken sequences."""

    def test_valid_sequence_no_errors(self):
        messages = [
            {"role": "system", "content": "System"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
        ]
        errors = validate_message_sequence(messages)
        assert errors == []

    def test_system_not_first(self):
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "system", "content": "System"},
        ]
        errors = validate_message_sequence(messages)
        assert any("System message" in e for e in errors)

    def test_orphaned_tool_result_detected(self):
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "tool", "tool_call_id": "missing_tc", "content": "result"},
        ]
        errors = validate_message_sequence(messages)
        assert any("Orphaned" in e for e in errors)

    def test_duplicate_tool_call_id_detected(self):
        messages = [
            {"role": "assistant", "tool_calls": [{"id": "dup_id"}]},
            {"role": "assistant", "tool_calls": [{"id": "dup_id"}]},
        ]
        errors = validate_message_sequence(messages)
        assert any("Duplicate" in e for e in errors)

@pytest.mark.unit
class TestSanitizeConversation:
    """Test sanitize_conversation full pipeline."""

    def test_sanitize_fixes_ids_and_removes_orphans(self):
        messages = [
            {"role": "assistant", "tool_calls": [{"function": {"name": "foo"}}]},
            {"role": "tool", "tool_call_id": "orphan_id", "content": "orphaned"},
        ]
        result = sanitize_conversation(messages)
        # The assistant's tool call now has an ID, but the orphan is still orphaned
        # because its tool_call_id doesn't match the newly assigned ID
        assert len(result) == 1
        assert result[0]["role"] == "assistant"

@pytest.mark.unit
class TestDeduplicateMessages:
    """Test deduplicate_messages removes consecutive duplicates."""

    def test_removes_consecutive_duplicates(self):
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
        ]
        result = deduplicate_messages(messages)
        assert len(result) == 2

    def test_keeps_non_consecutive_duplicates(self):
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
            {"role": "user", "content": "Hello"},
        ]
        result = deduplicate_messages(messages)
        assert len(result) == 3

    def test_empty_list(self):
        assert deduplicate_messages([]) == []

@pytest.mark.unit
class TestTruncateMessages:
    """Test truncate_messages."""

    def test_no_truncation_when_under_limit(self):
        messages = [{"role": "user", "content": f"msg{i}"} for i in range(5)]
        result = truncate_messages(messages, max_messages=10)
        assert len(result) == 5

    def test_truncates_keeping_system(self):
        messages = [{"role": "system", "content": "sys"}] + [
            {"role": "user", "content": f"msg{i}"} for i in range(10)
        ]
        result = truncate_messages(messages, max_messages=5, keep_system=True)
        assert len(result) == 5
        assert result[0]["role"] == "system"

@pytest.mark.unit
class TestGetConversationStats:
    """Test get_conversation_stats returns correct counts."""

    def test_correct_counts(self):
        messages = [
            {"role": "system", "content": "System"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!", "tool_calls": [{"id": "tc1"}]},
            {"role": "tool", "tool_call_id": "tc1", "content": "result"},
        ]
        stats = get_conversation_stats(messages)
        assert stats["total_messages"] == 4
        assert stats["user_messages"] == 1
        assert stats["assistant_messages"] == 1
        assert stats["system_messages"] == 1
        assert stats["tool_messages"] == 1
        assert stats["tool_calls"] == 1
        assert stats["total_content_length"] > 0

@pytest.mark.unit
class TestExtractToolCalls:
    """Test extract_tool_calls."""

    def test_extracts_tool_calls_from_assistant(self):
        messages = [
            {"role": "user", "content": "Hello"},
            {
                "role": "assistant",
                "tool_calls": [
                    {"id": "tc1", "function": {"name": "search"}},
                    {"id": "tc2", "function": {"name": "read"}},
                ],
            },
        ]
        result = extract_tool_calls(messages)
        assert len(result) == 2
        assert result[0]["tool_name"] == "search"
        assert result[1]["tool_name"] == "read"
        assert result[0]["message_index"] == 1
