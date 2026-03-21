"""Tests for VLLMResponseValidator -- 7 failure modes + repair + passthrough.

Covers:
  - Valid response passthrough (2 tests)
  - FM-1: Broken tool_calls in reasoning_content (3 tests)
  - FM-2: content=None / empty tool_calls (2 tests)
  - FM-3: Malformed JSON in tool_calls arguments (3 tests)
  - FM-4: KV cache OOM (2 tests)
  - FM-5: Partial streaming interruption (2 tests)
  - FM-6: Wrong tool selection (2 tests)
  - FM-7: Truncated response (3 tests)
  - Edge cases (3 tests)
"""

import json

from core.orchestrator.vllm_validator import VLLMResponseValidator

# ---------------------------------------------------------------------------
# Valid response passthrough
# ---------------------------------------------------------------------------

class TestValidPassthrough:
    """Valid responses should pass through without repair."""

    def test_normal_content_string(self):
        """Normal text response -> valid=True, repaired=False."""
        validator = VLLMResponseValidator()
        result = validator.validate(
            {
                "content": "The answer is 42.",
                "finish_reason": "stop",
            }
        )
        assert result.valid is True
        assert result.repaired is False
        assert result.failure_mode is None

    def test_valid_tool_calls(self):
        """Response with valid tool_calls -> valid=True, repaired=False."""
        validator = VLLMResponseValidator(available_tools=["search", "write"])
        result = validator.validate(
            {
                "content": "",
                "tool_calls": [
                    {"name": "search", "arguments": json.dumps({"q": "test"})},
                ],
                "finish_reason": "tool_calls",
            }
        )
        assert result.valid is True
        assert result.repaired is False
        assert result.failure_mode is None

# ---------------------------------------------------------------------------
# FM-1: Broken tool_calls in reasoning_content
# ---------------------------------------------------------------------------

class TestFM1ReasoningToolCalls:
    """FM-1: Tool call JSON found in reasoning_content instead of tool_calls."""

    def test_json_array_in_reasoning(self):
        """reasoning_content contains JSON tool call array -> repair."""
        validator = VLLMResponseValidator()
        result = validator.validate(
            {
                "content": "",
                "reasoning_content": '[{"name":"search","arguments":{"q":"test"}}]',
                "tool_calls": [],
            }
        )
        assert result.valid is True
        assert result.repaired is True
        assert result.repaired_tool_calls is not None
        assert len(result.repaired_tool_calls) == 1
        assert result.repaired_tool_calls[0]["name"] == "search"

    def test_tool_call_json_with_surrounding_text(self):
        """reasoning_content with tool call JSON embedded in reasoning text -> repair."""
        validator = VLLMResponseValidator()
        result = validator.validate(
            {
                "content": None,
                "reasoning_content": 'I need to search for this. [{"name":"search","arguments":{"q":"hello"}}]',
                "tool_calls": [],
            }
        )
        assert result.valid is True
        assert result.repaired is True
        assert result.repaired_tool_calls is not None
        assert result.repaired_tool_calls[0]["name"] == "search"

    def test_reasoning_without_tool_pattern(self):
        """reasoning_content with no tool call pattern -> content repair (FM-2 path), not FM-1."""
        validator = VLLMResponseValidator()
        result = validator.validate(
            {
                "content": None,
                "reasoning_content": "Let me think about this problem step by step.",
                "tool_calls": [],
            }
        )
        # No tool calls found, so this falls to FM-2 content recovery
        assert result.valid is True
        assert result.repaired is True
        assert result.repaired_content == "Let me think about this problem step by step."

# ---------------------------------------------------------------------------
# FM-2: content=None / empty tool_calls
# ---------------------------------------------------------------------------

class TestFM2ContentNone:
    """FM-2: content=None with empty or missing tool_calls."""

    def test_content_none_with_reasoning(self):
        """content=None but reasoning_content has text -> repaired_content."""
        validator = VLLMResponseValidator()
        result = validator.validate(
            {
                "content": None,
                "tool_calls": [],
                "reasoning_content": "The answer is 42",
            }
        )
        assert result.valid is True
        assert result.repaired is True
        assert result.repaired_content == "The answer is 42"

    def test_content_none_no_reasoning(self):
        """content=None, no tool_calls, no reasoning -> empty_response."""
        validator = VLLMResponseValidator()
        result = validator.validate(
            {
                "content": None,
                "tool_calls": None,
                "reasoning_content": None,
            }
        )
        assert result.valid is False
        assert result.failure_mode == "empty_response"

# ---------------------------------------------------------------------------
# FM-3: Malformed JSON in tool_calls arguments
# ---------------------------------------------------------------------------

class TestFM3MalformedJSON:
    """FM-3: tool_calls arguments contain malformed JSON."""

    def test_missing_closing_brace(self):
        """Arguments with missing closing brace -> repaired."""
        validator = VLLMResponseValidator()
        result = validator.validate(
            {
                "content": "",
                "tool_calls": [
                    {"name": "search", "arguments": '{"query": "test"'},
                ],
                "finish_reason": "tool_calls",
            }
        )
        assert result.valid is True
        assert result.repaired is True
        assert result.repaired_tool_calls is not None
        # The repaired arguments should parse as valid JSON
        args = result.repaired_tool_calls[0]["arguments"]
        parsed = json.loads(args) if isinstance(args, str) else args
        assert parsed["query"] == "test"

    def test_trailing_garbage(self):
        """Arguments with trailing garbage after valid JSON -> repaired."""
        validator = VLLMResponseValidator()
        result = validator.validate(
            {
                "content": "",
                "tool_calls": [
                    {"name": "search", "arguments": '{"query": "test"}extra garbage'},
                ],
                "finish_reason": "tool_calls",
            }
        )
        assert result.valid is True
        assert result.repaired is True
        assert result.repaired_tool_calls is not None
        args = result.repaired_tool_calls[0]["arguments"]
        parsed = json.loads(args) if isinstance(args, str) else args
        assert parsed["query"] == "test"

    def test_completely_invalid_json(self):
        """Arguments that are totally not JSON -> malformed_json failure."""
        validator = VLLMResponseValidator()
        result = validator.validate(
            {
                "content": "",
                "tool_calls": [
                    {"name": "search", "arguments": "totally not json"},
                ],
                "finish_reason": "tool_calls",
            }
        )
        assert result.valid is False
        assert result.failure_mode == "malformed_json"

# ---------------------------------------------------------------------------
# FM-4: KV cache OOM
# ---------------------------------------------------------------------------

class TestFM4KVCacheOOM:
    """FM-4: KV cache / GPU memory errors (HTTP 500)."""

    def test_kv_cache_error(self):
        """HTTP 500 with 'KV cache' in error -> kv_cache_oom."""
        validator = VLLMResponseValidator()
        result = validator.validate(
            {
                "http_status": 500,
                "error": "vLLM error: KV cache is full, cannot allocate new blocks",
            }
        )
        assert result.valid is False
        assert result.failure_mode == "kv_cache_oom"

    def test_out_of_memory_error(self):
        """HTTP 500 with 'out of memory' -> kv_cache_oom."""
        validator = VLLMResponseValidator()
        result = validator.validate(
            {
                "http_status": 500,
                "error": "CUDA out of memory. Tried to allocate 2.00 GiB",
            }
        )
        assert result.valid is False
        assert result.failure_mode == "kv_cache_oom"

# ---------------------------------------------------------------------------
# FM-5: Partial streaming interruption
# ---------------------------------------------------------------------------

class TestFM5StreamInterrupted:
    """FM-5: Streaming response interrupted before completion."""

    def test_no_finish_reason(self):
        """Content present but finish_reason=None -> stream_interrupted."""
        validator = VLLMResponseValidator()
        result = validator.validate(
            {
                "content": "The answer is",
                "finish_reason": None,
            }
        )
        assert result.valid is False
        assert result.failure_mode == "stream_interrupted"

    def test_normal_finish(self):
        """Content with finish_reason='stop' -> valid."""
        validator = VLLMResponseValidator()
        result = validator.validate(
            {
                "content": "The answer is complete.",
                "finish_reason": "stop",
            }
        )
        assert result.valid is True
        assert result.repaired is False

# ---------------------------------------------------------------------------
# FM-6: Wrong tool selection
# ---------------------------------------------------------------------------

class TestFM6WrongTool:
    """FM-6: Tool calls reference tools not in available_tools."""

    def test_nonexistent_tool(self):
        """Tool name not in available_tools -> wrong_tool."""
        validator = VLLMResponseValidator(available_tools=["search", "write"])
        result = validator.validate(
            {
                "content": "",
                "tool_calls": [
                    {"name": "nonexistent_tool", "arguments": "{}"},
                ],
                "finish_reason": "tool_calls",
            }
        )
        assert result.valid is False
        assert result.failure_mode == "wrong_tool"

    def test_valid_tool_name(self):
        """Tool name in available_tools -> valid."""
        validator = VLLMResponseValidator(available_tools=["search", "write"])
        result = validator.validate(
            {
                "content": "",
                "tool_calls": [
                    {"name": "search", "arguments": '{"q": "test"}'},
                ],
                "finish_reason": "tool_calls",
            }
        )
        assert result.valid is True
        assert result.repaired is False

# ---------------------------------------------------------------------------
# FM-7: Truncated response
# ---------------------------------------------------------------------------

class TestFM7Truncated:
    """FM-7: Response truncated mid-token with unclosed brackets."""

    def test_unclosed_brace(self):
        """JSON-like content with unclosed brace -> truncated."""
        validator = VLLMResponseValidator()
        result = validator.validate(
            {
                "content": '{"action": "search", "arg',
                "finish_reason": "length",
            }
        )
        assert result.valid is False
        assert result.failure_mode == "truncated"

    def test_normal_text_ending(self):
        """Normal complete text -> valid (not truncated)."""
        validator = VLLMResponseValidator()
        result = validator.validate(
            {
                "content": "The answer is complete.",
                "finish_reason": "stop",
            }
        )
        assert result.valid is True

    def test_unclosed_bracket(self):
        """JSON-like content with unclosed bracket -> truncated."""
        validator = VLLMResponseValidator()
        result = validator.validate(
            {
                "content": '[{"name":"tool"',
                "finish_reason": "length",
            }
        )
        assert result.valid is False
        assert result.failure_mode == "truncated"

# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_empty_response_dict(self):
        """Empty response dict {} -> empty_response."""
        validator = VLLMResponseValidator()
        result = validator.validate({})
        assert result.valid is False
        assert result.failure_mode == "empty_response"

    def test_non_oom_api_error(self):
        """Response with error key (not OOM-related) -> api_error."""
        validator = VLLMResponseValidator()
        result = validator.validate(
            {
                "error": "Model not found: llama-99b",
                "http_status": 404,
            }
        )
        assert result.valid is False
        assert result.failure_mode == "api_error"

    def test_no_available_tools_skips_fm6(self):
        """Validator with no available_tools skips FM-6 tool name check."""
        validator = VLLMResponseValidator()  # No available_tools
        result = validator.validate(
            {
                "content": "",
                "tool_calls": [
                    {"name": "any_tool_name", "arguments": '{"q": "test"}'},
                ],
                "finish_reason": "tool_calls",
            }
        )
        # Without available_tools, FM-6 check is skipped -> valid
        assert result.valid is True
        assert result.repaired is False
