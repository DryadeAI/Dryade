"""Skill adapter for system prompt injection.

Formats loaded skills into compact XML for agent system prompts.
"""

import logging

from core.skills.models import Skill

logger = logging.getLogger(__name__)

class MarkdownSkillAdapter:
    """Inject markdown skill instructions into agent system prompt.

    Formats skills as compact XML blocks that fit within token budgets.
    Token overhead: ~24 tokens per skill + 195 char base overhead.
    """

    BASE_OVERHEAD = 195  # Characters for skill section header (only when >= 1 skill)
    SKILL_OVERHEAD = 97  # Approximate characters per skill (excluding content)

    def format_skills_for_prompt(self, skills: list[Skill]) -> str:
        """Convert skills to compact XML for system prompt.

        Format:
        ```xml
        <available-skills>
        <skill name="skill-name">
          <description>What this skill does</description>
          <instructions>
            ... markdown instructions ...
          </instructions>
        </skill>
        </available-skills>
        ```

        Args:
            skills: List of skills to format

        Returns:
            XML-formatted skill context for system prompt
        """
        if not skills:
            return ""

        skill_blocks = []
        for skill in skills:
            # Escape XML special chars in content
            desc = self._escape_xml(skill.description)
            instructions = skill.instructions  # Keep markdown as-is

            block = (
                f'<skill name="{self._escape_xml(skill.name)}">\n'
                f"  <description>{desc}</description>\n"
                f"  <instructions>\n{instructions}\n  </instructions>\n"
                f"</skill>"
            )
            skill_blocks.append(block)

        return "<available-skills>\n" + "\n\n".join(skill_blocks) + "\n</available-skills>"

    def _escape_xml(self, text: str) -> str:
        """Escape XML special characters."""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    def estimate_token_overhead(self, skills: list[Skill]) -> int:
        """Estimate token overhead for loading skills.

        Rough estimate: 4 chars per token.

        Args:
            skills: Skills to estimate

        Returns:
            Estimated token count
        """
        if not skills:
            return 0

        total_chars = self.BASE_OVERHEAD
        for skill in skills:
            total_chars += self.SKILL_OVERHEAD
            total_chars += len(skill.name)
            total_chars += len(skill.description)
            total_chars += len(skill.instructions)

        return total_chars // 4  # Rough chars-to-tokens ratio

    def build_skill_guidance(self) -> str:
        """Return guidance text for using skills.

        Appended after skill definitions to guide LLM usage.
        """
        return (
            "\n\n## Skill Usage Guidelines\n\n"
            "When a user request matches a skill's description, follow the skill's "
            "instructions to accomplish the task. Skills provide domain-specific "
            "guidance and may reference scripts or tools in their skill directory.\n\n"
            "If multiple skills could apply, choose the most specific one. "
            "If no skill matches, proceed with general capabilities."
        )

def format_skills_for_prompt(skills: list[Skill]) -> str:
    """Convenience function to format skills for prompt.

    Args:
        skills: List of skills to format

    Returns:
        Formatted skill context string
    """
    adapter = MarkdownSkillAdapter()
    return adapter.format_skills_for_prompt(skills)
