"""Tests for factory JSON truncation repair.

Covers edge cases in _repair_truncated_json() and _extract_json() for:
- Truncation mid-string value (unclosed quotes)
- Truncation mid-array (missing ])
- Truncation mid-nested object (multiple unclosed })
- Truncation after key but before value (trailing :)
- Trailing comma before repair
- Pipeline graceful degradation on failure
- Structured logging on truncation events

TDD: written before implementation improvements.
"""

import json
import logging
from unittest.mock import patch

import pytest

from core.factory._llm import _extract_json, _repair_truncated_json

# ---------------------------------------------------------------------------
# _repair_truncated_json — low-level repair function
# ---------------------------------------------------------------------------

class TestRepairTruncatedJsonBasic:
    """Basic repair scenarios that the current implementation already handles."""

    def test_complete_json_returned_as_is(self):
        """A complete JSON object is returned unchanged."""
        text = '{"key": "value"}'
        result = _repair_truncated_json(text)
        assert result == text

    def test_simple_truncation_mid_key(self):
        """Truncation after the last complete top-level object."""
        text = '{"key": "value"} some trailing garbage'
        result = _repair_truncated_json(text)
        assert result == '{"key": "value"}'

    def test_no_json_returns_none(self):
        """No valid JSON object returns None."""
        text = "not json at all"
        result = _repair_truncated_json(text)
        assert result is None

    def test_empty_string_returns_none(self):
        """Empty input returns None."""
        result = _repair_truncated_json("")
        assert result is None

    def test_nested_objects_complete(self):
        """Complete nested object is recovered."""
        text = '{"outer": {"inner": "val"}} extra'
        result = _repair_truncated_json(text)
        assert result == '{"outer": {"inner": "val"}}'

class TestRepairTruncatedJsonMidString:
    """Truncation mid-string value (unclosed quotes)."""

    def test_truncation_mid_string_value(self):
        """Input: {"key": "value truncated mid-str
        Expected: recover the last complete object (or None if none).
        Current behavior: should return None (no complete top-level object).
        The improved repair should detect the unclosed string and attempt to close it.
        """
        text = '{"key": "value truncated mid-str'
        # With improved repair: should try to close the string and the object.
        result = _repair_truncated_json(text)
        # Improved: returns a parseable JSON string, not None
        assert result is not None
        parsed = json.loads(result)
        assert "key" in parsed

    def test_truncation_mid_string_with_escaped_quote(self):
        """Truncation mid-string that contains an escaped quote."""
        text = '{"key": "value with \\"escape\\" and then truncated mid'
        result = _repair_truncated_json(text)
        assert result is not None
        parsed = json.loads(result)
        assert "key" in parsed

    def test_truncation_after_complete_string_but_missing_brace(self):
        """{"key": "complete value" — trailing } missing."""
        text = '{"key": "complete value"'
        result = _repair_truncated_json(text)
        assert result is not None
        parsed = json.loads(result)
        assert parsed["key"] == "complete value"

    def test_truncation_mid_string_in_nested_key(self):
        """Truncation mid-string inside a nested value."""
        text = '{"outer": {"inner": "truncated'
        result = _repair_truncated_json(text)
        # Improved: closes nested string + nested obj + outer obj
        assert result is not None
        parsed = json.loads(result)
        assert "outer" in parsed

class TestRepairTruncatedJsonMidArray:
    """Truncation mid-array (missing ])."""

    def test_truncation_mid_array_empty(self):
        """{"arr": [} — array opened but not closed."""
        text = '{"arr": ['
        result = _repair_truncated_json(text)
        # Improved: closes array and object
        assert result is not None
        parsed = json.loads(result)
        assert "arr" in parsed
        assert isinstance(parsed["arr"], list)

    def test_truncation_mid_array_with_items(self):
        """{"arr": ["a", "b", "c} — array truncated mid-items."""
        text = '{"arr": ["a", "b", "c'
        result = _repair_truncated_json(text)
        assert result is not None
        parsed = json.loads(result)
        # Should have at least the "arr" key
        assert "arr" in parsed

    def test_truncation_after_complete_array_item(self):
        """{"arr": ["a", "b"} — missing ] and }."""
        text = '{"arr": ["a", "b"'
        result = _repair_truncated_json(text)
        assert result is not None
        parsed = json.loads(result)
        assert "arr" in parsed

    def test_nested_array_of_objects(self):
        """{"arr": [{"x": 1}, {"y": 2} — last } closes inner, outer } missing."""
        text = '{"arr": [{"x": 1}, {"y": 2}'
        result = _repair_truncated_json(text)
        # Depending on repair strategy: at minimum, should not raise
        # and should return parseable JSON
        assert result is not None
        parsed = json.loads(result)
        assert "arr" in parsed

class TestRepairTruncatedJsonNestedObjects:
    """Truncation mid-nested object (multiple unclosed })."""

    def test_double_nested_truncation(self):
        """{"a": {"b": {"c": "val"} — two closing braces missing."""
        text = '{"a": {"b": {"c": "val"'
        result = _repair_truncated_json(text)
        assert result is not None
        parsed = json.loads(result)
        assert "a" in parsed

    def test_triple_nested_truncation(self):
        """Three levels deep, truncated at innermost value."""
        text = '{"l1": {"l2": {"l3": {"l4": "deep'
        result = _repair_truncated_json(text)
        assert result is not None
        parsed = json.loads(result)
        assert "l1" in parsed

    def test_sibling_fields_after_nested(self):
        """Complete nested object + incomplete sibling field."""
        text = '{"a": {"x": 1}, "b": {"y": 2'
        result = _repair_truncated_json(text)
        assert result is not None
        parsed = json.loads(result)
        # At minimum "a" is complete; "b" may or may not be included
        assert "a" in parsed

class TestRepairTruncatedJsonTrailingColon:
    """Truncation after key but before value (trailing :)."""

    def test_trailing_colon_only(self):
        """{"key": — key present but no value at all."""
        text = '{"key":'
        result = _repair_truncated_json(text)
        # Improved: handle gracefully — either return the key with null or return None
        # The key invariant: if not None, result must be valid JSON
        if result is not None:
            parsed = json.loads(result)
            assert isinstance(parsed, dict)

    def test_trailing_colon_with_space(self):
        """{"key": — key present with space but no value."""
        text = '{"key": '
        result = _repair_truncated_json(text)
        if result is not None:
            parsed = json.loads(result)
            assert isinstance(parsed, dict)

    def test_complete_field_then_trailing_colon(self):
        """{"a": 1, "b": — first field complete, second key present but no value."""
        text = '{"a": 1, "b":'
        result = _repair_truncated_json(text)
        if result is not None:
            parsed = json.loads(result)
            assert isinstance(parsed, dict)
            # At minimum, the complete field should be present
            assert "a" in parsed

class TestRepairTruncatedJsonTrailingComma:
    """Trailing comma before repair."""

    def test_trailing_comma_in_object(self):
        """{"a": 1, "b": 2, — trailing comma, object not closed."""
        text = '{"a": 1, "b": 2,'
        result = _repair_truncated_json(text)
        assert result is not None
        parsed = json.loads(result)
        assert parsed["a"] == 1
        assert parsed["b"] == 2

    def test_trailing_comma_in_array(self):
        """{"arr": [1, 2, 3, — trailing comma in array."""
        text = '{"arr": [1, 2, 3,'
        result = _repair_truncated_json(text)
        assert result is not None
        parsed = json.loads(result)
        assert "arr" in parsed

    def test_trailing_comma_after_nested_object(self):
        """{"a": {"x": 1}, — trailing comma after nested object."""
        text = '{"a": {"x": 1},'
        result = _repair_truncated_json(text)
        assert result is not None
        parsed = json.loads(result)
        assert "a" in parsed
        assert parsed["a"]["x"] == 1

    def test_multiple_trailing_commas_cleaned(self):
        """Already-complete JSON with trailing comma before } should still recover."""
        text = '{"a": 1, "b": 2,}'
        result = _repair_truncated_json(text)
        # Should clean trailing comma and parse successfully
        assert result is not None
        parsed = json.loads(result)
        assert parsed["a"] == 1

    def test_trailing_comma_with_whitespace(self):
        """{"a": 1,   } — trailing comma + whitespace before closing brace."""
        text = '{"a": 1,   }'
        result = _repair_truncated_json(text)
        assert result is not None
        parsed = json.loads(result)
        assert parsed["a"] == 1

# ---------------------------------------------------------------------------
# _extract_json — higher-level extraction + repair integration
# ---------------------------------------------------------------------------

class TestExtractJsonTruncationIntegration:
    """Integration tests for _extract_json when input is truncated."""

    def test_extract_json_valid(self):
        """Clean JSON parses normally."""
        result = _extract_json('{"key": "val"}')
        assert result == {"key": "val"}

    def test_extract_json_thinks_stripped(self):
        """<think>...</think> stripped before parse."""
        result = _extract_json('<think>reasoning here</think>{"key": "val"}')
        assert result == {"key": "val"}

    def test_extract_json_code_fence(self):
        """Markdown code fence stripped."""
        result = _extract_json('```json\n{"key": "val"}\n```')
        assert result == {"key": "val"}

    def test_extract_json_truncated_with_think_tag(self):
        """Truncated JSON after <think> block is repaired."""
        text = '<think>some reasoning</think>{"key": "value", "other": "truncated'
        result = _extract_json(text)
        assert "key" in result

    def test_extract_json_truncated_with_trailing_comma(self):
        """Trailing comma in otherwise complete JSON is repaired."""
        text = '{"a": 1, "b": 2,'
        result = _extract_json(text)
        assert result["a"] == 1
        assert result["b"] == 2

    def test_extract_json_truncated_nested_object(self):
        """Multi-level nested truncation is repaired."""
        text = '{"config": {"name": "test", "options": {"timeout": 30'
        result = _extract_json(text)
        assert "config" in result

    def test_extract_json_truncated_mid_array(self):
        """Truncation inside an array field is handled."""
        text = '{"tags": ["python", "fastapi"'
        result = _extract_json(text)
        assert "tags" in result

    def test_extract_json_complete_json_unaffected(self):
        """Complete valid JSON is not modified by repair path."""
        original = {"a": 1, "b": [1, 2, 3], "c": {"d": "e"}}
        result = _extract_json(json.dumps(original))
        assert result == original

    def test_extract_json_unrepairable_raises(self):
        """Completely invalid/empty input raises JSONDecodeError."""
        with pytest.raises(json.JSONDecodeError):
            _extract_json("not json at all, no braces")

    def test_extract_json_unrepairable_empty_raises(self):
        """Empty input raises JSONDecodeError."""
        with pytest.raises(json.JSONDecodeError):
            _extract_json("")

# ---------------------------------------------------------------------------
# Logging: structured logging on truncation events
# ---------------------------------------------------------------------------

class TestTruncationLogging:
    """Verify structured logging when truncation repair is attempted."""

    def test_warning_logged_on_truncation_repair(self, caplog):
        """A warning is logged when JSON is repaired from truncation."""
        truncated = '{"key": "value", "other": "truncated'
        with caplog.at_level(logging.WARNING, logger="core.factory._llm"):
            result = _extract_json(truncated)
        assert "truncat" in caplog.text.lower()
        assert result is not None

    def test_no_warning_for_valid_json(self, caplog):
        """No warning logged for valid JSON."""
        with caplog.at_level(logging.WARNING, logger="core.factory._llm"):
            _extract_json('{"key": "value"}')
        # No truncation warning should appear
        assert "truncat" not in caplog.text.lower()

    def test_warning_includes_size_info(self, caplog):
        """Truncation warning should include recovered vs original size info."""
        truncated = '{"key": "value", "another_key": "another truncated value here'
        with caplog.at_level(logging.WARNING, logger="core.factory._llm"):
            result = _extract_json(truncated)
        # Check that some size or ratio info is logged
        # Current implementation logs "recovered X/Y chars"
        log_text = caplog.text
        assert result is not None
        # If repair succeeded, the warning should mention chars or size
        if result:
            assert any(word in log_text.lower() for word in ["char", "bytes", "truncat", "repair"])

# ---------------------------------------------------------------------------
# Pipeline graceful degradation
# ---------------------------------------------------------------------------

class TestPipelineGracefulDegradation:
    """Verify the pipeline handles JSON repair failure gracefully."""

    @pytest.mark.asyncio
    async def test_call_llm_json_returns_partial_on_repair_failure(self):
        """When JSON repair fails, call_llm_json raises JSONDecodeError (documented behavior).

        The pipeline caller is responsible for handling this and returning
        a partial result rather than crashing.
        """
        from core.factory._llm import call_llm_json

        with patch("core.factory._llm.call_llm", return_value="not json at all"):
            with pytest.raises(json.JSONDecodeError):
                await call_llm_json("some prompt")

    @pytest.mark.asyncio
    async def test_call_llm_json_succeeds_with_truncated_json(self):
        """call_llm_json succeeds when JSON is truncated but repairable."""
        from core.factory._llm import call_llm_json

        truncated = '{"name": "test", "description": "truncated'
        with patch("core.factory._llm.call_llm", return_value=truncated):
            result = await call_llm_json("some prompt")
        assert "name" in result
        assert result["name"] == "test"

    @pytest.mark.asyncio
    async def test_call_llm_json_succeeds_with_trailing_comma(self):
        """call_llm_json succeeds when JSON has trailing comma from truncation."""
        from core.factory._llm import call_llm_json

        trailing_comma = '{"a": 1, "b": 2,'
        with patch("core.factory._llm.call_llm", return_value=trailing_comma):
            result = await call_llm_json("some prompt")
        assert result["a"] == 1
        assert result["b"] == 2

    @pytest.mark.asyncio
    async def test_call_llm_json_logs_warning_on_truncation(self, caplog):
        """call_llm_json logs a warning when truncation repair is needed."""
        from core.factory._llm import call_llm_json

        truncated = '{"key": "val", "other": "truncated str'
        with patch("core.factory._llm.call_llm", return_value=truncated):
            with caplog.at_level(logging.WARNING, logger="core.factory._llm"):
                result = await call_llm_json("some prompt")
        assert "truncat" in caplog.text.lower()
        assert result is not None
