# Migrated from plugins/starter/message_hygiene/cleaner.py into core (Phase 222).

"""Message Hygiene Utilities.

- Remove orphaned tool results
- Assign IDs to tool calls lacking them
- Validate message sequence integrity

Inspired by Orchestral AI's automatic detection and removal of orphaned tool results.

Target: ~80 LOC
"""

import uuid

def cleanup_orphaned_tool_results(messages: list[dict]) -> list[dict]:
    """Remove tool results without matching tool calls.

    Args:
        messages: List of message dicts

    Returns:
        Cleaned message list
    """
    # Collect all tool call IDs from assistant messages
    tool_call_ids: set[str] = set()

    for msg in messages:
        if msg.get("role") == "assistant":
            for tc in msg.get("tool_calls", []):
                if tc.get("id"):
                    tool_call_ids.add(tc["id"])

    # Filter out orphaned tool results
    cleaned = []
    for msg in messages:
        if msg.get("role") == "tool":
            tool_call_id = msg.get("tool_call_id")
            if tool_call_id not in tool_call_ids:
                continue  # Skip orphan
        cleaned.append(msg)

    return cleaned

def ensure_tool_call_ids(messages: list[dict]) -> list[dict]:
    """Ensure all tool calls have unique IDs.

    Args:
        messages: List of message dicts

    Returns:
        Messages with all tool calls having IDs
    """
    for msg in messages:
        if msg.get("role") == "assistant":
            for tc in msg.get("tool_calls", []):
                if not tc.get("id"):
                    tc["id"] = f"tc_{uuid.uuid4().hex[:12]}"
    return messages

def validate_message_sequence(messages: list[dict]) -> list[str]:
    """Validate message sequence integrity.

    Args:
        messages: List of message dicts

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []
    seen_tool_call_ids: set[str] = set()

    for i, msg in enumerate(messages):
        role = msg.get("role")

        # System message should be first
        if role == "system" and i != 0:
            errors.append(f"System message at position {i} should be first")

        # Check for duplicate tool call IDs
        if role == "assistant":
            for tc in msg.get("tool_calls", []):
                tc_id = tc.get("id")
                if tc_id:
                    if tc_id in seen_tool_call_ids:
                        errors.append(f"Duplicate tool call ID: {tc_id}")
                    seen_tool_call_ids.add(tc_id)

        # Check for orphaned tool results
        if role == "tool":
            tool_call_id = msg.get("tool_call_id")
            if tool_call_id and tool_call_id not in seen_tool_call_ids:
                errors.append(f"Orphaned tool result at position {i}: {tool_call_id}")

    return errors

def sanitize_conversation(messages: list[dict]) -> list[dict]:
    """Full conversation sanitization pipeline.

    Applies all hygiene operations:
    1. Ensure tool call IDs
    2. Remove orphaned tool results

    Args:
        messages: List of message dicts

    Returns:
        Sanitized message list
    """
    messages = ensure_tool_call_ids(messages)
    messages = cleanup_orphaned_tool_results(messages)
    return messages

def deduplicate_messages(messages: list[dict]) -> list[dict]:
    """Remove duplicate consecutive messages.

    Args:
        messages: List of message dicts

    Returns:
        Deduplicated message list
    """
    if not messages:
        return []

    result = [messages[0]]
    for msg in messages[1:]:
        last = result[-1]
        # Skip if same role and content
        if msg.get("role") == last.get("role") and msg.get("content") == last.get("content"):
            continue
        result.append(msg)

    return result

def truncate_messages(
    messages: list[dict], max_messages: int = 100, keep_system: bool = True
) -> list[dict]:
    """Truncate message history to a maximum number.

    Keeps most recent messages and optionally preserves system message.

    Args:
        messages: List of message dicts
        max_messages: Maximum number of messages to keep
        keep_system: Whether to always keep the system message

    Returns:
        Truncated message list
    """
    if len(messages) <= max_messages:
        return messages

    if keep_system and messages and messages[0].get("role") == "system":
        system_msg = messages[0]
        # Keep system + last (max_messages - 1) messages
        return [system_msg] + messages[-(max_messages - 1) :]
    else:
        return messages[-max_messages:]

def extract_tool_calls(messages: list[dict]) -> list[dict]:
    """Extract all tool calls from messages.

    Args:
        messages: List of message dicts

    Returns:
        List of tool call dicts with message context
    """
    tool_calls = []
    for i, msg in enumerate(messages):
        if msg.get("role") == "assistant":
            for tc in msg.get("tool_calls", []):
                tool_calls.append(
                    {
                        "message_index": i,
                        "tool_call": tc,
                        "tool_name": tc.get("function", {}).get("name") or tc.get("name"),
                    }
                )
    return tool_calls

def get_conversation_stats(messages: list[dict]) -> dict:
    """Get statistics about a conversation.

    Args:
        messages: List of message dicts

    Returns:
        Statistics dict
    """
    stats = {
        "total_messages": len(messages),
        "user_messages": 0,
        "assistant_messages": 0,
        "system_messages": 0,
        "tool_messages": 0,
        "tool_calls": 0,
        "total_content_length": 0,
    }

    for msg in messages:
        role = msg.get("role")
        if role == "user":
            stats["user_messages"] += 1
        elif role == "assistant":
            stats["assistant_messages"] += 1
            stats["tool_calls"] += len(msg.get("tool_calls", []))
        elif role == "system":
            stats["system_messages"] += 1
        elif role == "tool":
            stats["tool_messages"] += 1

        content = msg.get("content", "")
        if content:
            stats["total_content_length"] += len(content)

    return stats
