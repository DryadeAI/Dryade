"""Tests for plan executor content-based refusal detection."""

import pytest

from core.api.routes.plans import REFUSAL_PATTERNS

@pytest.mark.unit
class TestRefusalPatterns:
    """Verify REFUSAL_PATTERNS catches known failure text."""

    @pytest.mark.parametrize(
        "text,expected_match",
        [
            ("I can't complete this task because the tool is not available", True),
            ("I'm unable to access the required function", True),
            ("I don't have access to the tool set", True),
            ("The function not found in available tools", True),
            ("I'm sorry, but I cannot complete this request", True),
            ("tool set I have access to does not include capella_trace", True),
            ("Successfully created 5 elements in the model", False),
            ("Found 12 requirements across 3 layers", False),
            ("Session opened: abc-123", False),
        ],
    )
    def test_refusal_pattern_detection(self, text, expected_match):
        text_lower = text.lower()
        matched = any(p in text_lower for p in REFUSAL_PATTERNS)
        assert matched == expected_match

    def test_patterns_are_lowercase(self):
        """All patterns must be lowercase for case-insensitive matching."""
        for p in REFUSAL_PATTERNS:
            assert p == p.lower(), f"Pattern '{p}' is not lowercase"

    def test_patterns_list_not_empty(self):
        """REFUSAL_PATTERNS must contain at least 10 patterns."""
        assert len(REFUSAL_PATTERNS) >= 10

    def test_case_insensitive_matching(self):
        """Matching works regardless of input casing."""
        text = "I CAN'T DO THIS TASK"
        text_lower = text.lower()
        matched = any(p in text_lower for p in REFUSAL_PATTERNS)
        assert matched is True

    def test_partial_sentence_match(self):
        """Patterns match within longer sentences."""
        text = "After analyzing the request, I am unable to proceed because the model is closed."
        text_lower = text.lower()
        matched = any(p in text_lower for p in REFUSAL_PATTERNS)
        assert matched is True

    def test_success_output_not_matched(self):
        """Normal success output should not trigger refusal detection."""
        success_outputs = [
            "Created element LogicalFunction_001 in Logical Architecture",
            "Traced 15 requirements from SA to LA successfully",
            "Schema: 4 layers, 22 element types, 8 relationship types",
            "Model saved to /workspace/project.capella",
            "Exported 3 diagrams as PNG files",
        ]
        for output in success_outputs:
            text_lower = output.lower()
            matched = any(p in text_lower for p in REFUSAL_PATTERNS)
            assert matched is False, f"False positive on: {output}"
