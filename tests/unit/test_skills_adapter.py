"""
Unit tests for MarkdownSkillAdapter.

Tests cover:
1. Formatting skills for system prompt (XML output)
2. XML escaping for special characters
3. Token estimation
4. Guidance text generation
5. Empty skill list handling

Target: ~50 LOC
"""

import pytest

from core.skills.adapter import MarkdownSkillAdapter, format_skills_for_prompt
from core.skills.models import Skill

@pytest.fixture
def adapter():
    """Create a MarkdownSkillAdapter instance."""
    return MarkdownSkillAdapter()

@pytest.fixture
def sample_skill():
    """Create a sample skill for testing."""
    return Skill(
        name="test-skill",
        description="A skill for testing",
        instructions="# Instructions\n\nDo the thing.\n\n1. Step one\n2. Step two",
        skill_dir="/tmp/test-skill",
    )

@pytest.fixture
def skill_with_special_chars():
    """Create a skill with XML special characters."""
    return Skill(
        name="special-skill",
        description='Handles <tags> & "quotes"',
        instructions="Use <code>example</code> & format",
        skill_dir="/tmp/special",
    )

# =============================================================================
# Test: Formatting Skills
# =============================================================================

class TestFormatSkills:
    """Tests for formatting skills into XML."""

    def test_format_single_skill(self, adapter, sample_skill):
        """Test formatting a single skill."""
        result = adapter.format_skills_for_prompt([sample_skill])

        assert "<available-skills>" in result
        assert "</available-skills>" in result
        assert '<skill name="test-skill">' in result
        assert "<description>A skill for testing</description>" in result
        assert "<instructions>" in result
        assert "# Instructions" in result

    def test_format_multiple_skills(self, adapter, sample_skill):
        """Test formatting multiple skills."""
        skill2 = Skill(
            name="another-skill",
            description="Another skill",
            instructions="Other instructions",
            skill_dir="/tmp/another",
        )

        result = adapter.format_skills_for_prompt([sample_skill, skill2])

        assert '<skill name="test-skill">' in result
        assert '<skill name="another-skill">' in result
        assert result.count("<skill ") == 2

    def test_format_empty_list(self, adapter):
        """Test formatting an empty skill list returns empty string."""
        result = adapter.format_skills_for_prompt([])

        assert result == ""

    def test_preserve_markdown_instructions(self, adapter, sample_skill):
        """Test that markdown in instructions is preserved."""
        result = adapter.format_skills_for_prompt([sample_skill])

        # Markdown should be preserved (not escaped)
        assert "# Instructions" in result
        assert "1. Step one" in result

# =============================================================================
# Test: XML Escaping
# =============================================================================

class TestXMLEscaping:
    """Tests for XML special character escaping."""

    def test_escape_ampersand(self, adapter):
        """Test ampersand is escaped."""
        result = adapter._escape_xml("A & B")
        assert result == "A &amp; B"

    def test_escape_less_than(self, adapter):
        """Test less-than is escaped."""
        result = adapter._escape_xml("A < B")
        assert result == "A &lt; B"

    def test_escape_greater_than(self, adapter):
        """Test greater-than is escaped."""
        result = adapter._escape_xml("A > B")
        assert result == "A &gt; B"

    def test_escape_quotes(self, adapter):
        """Test double quotes are escaped."""
        result = adapter._escape_xml('Say "hello"')
        assert result == "Say &quot;hello&quot;"

    def test_escape_combined(self, adapter):
        """Test all special chars together."""
        result = adapter._escape_xml('<a href="x">&</a>')
        assert "&lt;" in result
        assert "&gt;" in result
        assert "&quot;" in result
        assert "&amp;" in result

    def test_skill_name_escaped_in_attribute(self, adapter, skill_with_special_chars):
        """Test that skill names with special chars are escaped in XML attribute."""
        skill = Skill(
            name='skill-with-"quotes"',
            description="Test",
            instructions="Test",
            skill_dir="/tmp/test",
        )

        result = adapter.format_skills_for_prompt([skill])

        # Name should be escaped in attribute
        assert "&quot;" in result

    def test_description_escaped(self, adapter, skill_with_special_chars):
        """Test that skill descriptions are escaped."""
        result = adapter.format_skills_for_prompt([skill_with_special_chars])

        # Description should have escaped chars
        assert "&lt;tags&gt;" in result
        assert "&amp;" in result
        assert "&quot;quotes&quot;" in result

# =============================================================================
# Test: Token Estimation
# =============================================================================

class TestTokenEstimation:
    """Tests for token overhead estimation."""

    def test_estimate_empty_list(self, adapter):
        """Test token estimate for empty skill list is 0."""
        result = adapter.estimate_token_overhead([])
        assert result == 0

    def test_estimate_single_skill(self, adapter, sample_skill):
        """Test token estimate for single skill."""
        result = adapter.estimate_token_overhead([sample_skill])

        # Should be greater than 0
        assert result > 0

        # Should account for base overhead + skill overhead + content
        expected_min = (adapter.BASE_OVERHEAD + adapter.SKILL_OVERHEAD) // 4
        assert result >= expected_min

    def test_estimate_increases_with_more_skills(self, adapter, sample_skill):
        """Test that estimate increases with more skills."""
        one_skill = adapter.estimate_token_overhead([sample_skill])

        skill2 = Skill(
            name="skill-2",
            description="Another skill",
            instructions="More instructions here",
            skill_dir="/tmp/skill2",
        )
        two_skills = adapter.estimate_token_overhead([sample_skill, skill2])

        assert two_skills > one_skill

    def test_estimate_increases_with_longer_content(self, adapter):
        """Test that estimate increases with longer instructions."""
        short_skill = Skill(
            name="short",
            description="Short",
            instructions="Do it.",
            skill_dir="/tmp/short",
        )

        long_skill = Skill(
            name="long",
            description="Long skill with much more description",
            instructions="These are very long instructions " * 100,
            skill_dir="/tmp/long",
        )

        short_estimate = adapter.estimate_token_overhead([short_skill])
        long_estimate = adapter.estimate_token_overhead([long_skill])

        assert long_estimate > short_estimate

# =============================================================================
# Test: Skill Guidance
# =============================================================================

class TestSkillGuidance:
    """Tests for skill usage guidance."""

    def test_guidance_text_not_empty(self, adapter):
        """Test that guidance text is generated."""
        result = adapter.build_skill_guidance()

        assert len(result) > 0
        assert "Skill" in result

    def test_guidance_contains_usage_instructions(self, adapter):
        """Test that guidance contains usage instructions."""
        result = adapter.build_skill_guidance()

        # Should mention how to use skills
        assert "instructions" in result.lower() or "skill" in result.lower()

# =============================================================================
# Test: Convenience Function
# =============================================================================

class TestConvenienceFunction:
    """Tests for the format_skills_for_prompt convenience function."""

    def test_convenience_function(self, sample_skill):
        """Test the module-level convenience function."""
        result = format_skills_for_prompt([sample_skill])

        assert "<available-skills>" in result
        assert '<skill name="test-skill">' in result

    def test_convenience_function_empty(self):
        """Test convenience function with empty list."""
        result = format_skills_for_prompt([])
        assert result == ""
