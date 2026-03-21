"""Tests for CrewAI adapter Action/ActionInput interception."""

import pytest

from core.adapters.crewai_adapter import CrewAIAgentAdapter

@pytest.mark.unit
class TestParseActionResponse:
    """Test _parse_action_response helper."""

    def _make_adapter(self):
        """Create adapter with mock agent (bypass CrewAI import)."""
        adapter = object.__new__(CrewAIAgentAdapter)
        adapter._name = "test"
        return adapter

    def test_parses_valid_action_with_json_args(self):
        adapter = self._make_adapter()
        result = adapter._parse_action_response(
            'Action: capella_list\nAction Input: {"type": "Requirement", "layer": "OA"}'
        )
        assert result is not None
        assert result[0] == "capella_list"
        assert result[1] == {"type": "Requirement", "layer": "OA"}

    def test_parses_action_with_string_arg(self):
        adapter = self._make_adapter()
        result = adapter._parse_action_response(
            "Action: capella_open\nAction Input: /path/to/model.aird"
        )
        assert result is not None
        assert result[0] == "capella_open"
        assert result[1] == {"input": "/path/to/model.aird"}

    def test_returns_none_for_normal_text(self):
        adapter = self._make_adapter()
        result = adapter._parse_action_response("I found 5 requirements in the model.")
        assert result is None

    def test_returns_none_for_empty_string(self):
        adapter = self._make_adapter()
        assert adapter._parse_action_response("") is None

    def test_case_insensitive_action_keyword(self):
        adapter = self._make_adapter()
        result = adapter._parse_action_response(
            'action: capella_trace\naction input: {"session_id": "abc"}'
        )
        assert result is not None
        assert result[0] == "capella_trace"

    def test_handles_extra_whitespace(self):
        adapter = self._make_adapter()
        result = adapter._parse_action_response(
            '  Action:   capella_coverage  \n  Action Input:   {"session_id": "x"}  '
        )
        assert result is not None
        assert result[0] == "capella_coverage"
