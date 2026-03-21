"""Few-shot example library for routing prompt injection.

Phase 115.4: Provides curated examples of user messages paired with
expected tool calls, formatted as XML for injection into routing prompts.
Helps weaker models understand the expected tool-calling pattern.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass

logger = logging.getLogger(__name__)

__all__ = [
    "FewShotExample",
    "FewShotLibrary",
    "get_few_shot_library",
]

@dataclass
class FewShotExample:
    """A single curated routing example."""

    user_message: str
    expected_tool: str
    expected_arguments: dict
    category: str  # agent_creation | mcp_server | tool_creation | config

# ─── Curated examples ────────────────────────────────────────────────────────

_CURATED_EXAMPLES: list[FewShotExample] = [
    # agent_creation (Phase 167: updated to use unified `create` tool with artifact_type)
    FewShotExample(
        user_message="Create a websearch agent that can look things up online",
        expected_tool="create",
        expected_arguments={
            "goal": "Create a web search agent that can query search engines",
            "artifact_type": "agent",
            "name": "websearch",
        },
        category="agent_creation",
    ),
    FewShotExample(
        user_message="Make a code review agent for my Python projects",
        expected_tool="create",
        expected_arguments={
            "goal": "Create an agent that reviews Python code for quality and security issues",
            "artifact_type": "agent",
            "name": "code_reviewer",
        },
        category="agent_creation",
    ),
    # mcp_server
    FewShotExample(
        user_message="Add a postgres MCP server so I can query my database",
        expected_tool="add_mcp_server",
        expected_arguments={
            "name": "postgres",
            "transport": "stdio",
        },
        category="mcp_server",
    ),
    FewShotExample(
        user_message="Add a filesystem MCP server for my documents folder",
        expected_tool="add_mcp_server",
        expected_arguments={
            "name": "filesystem",
            "transport": "stdio",
        },
        category="mcp_server",
    ),
    # tool_creation (Phase 167: updated to use unified `create` tool with artifact_type)
    FewShotExample(
        user_message="Create a CSV parser tool that can read and analyze spreadsheet data",
        expected_tool="create",
        expected_arguments={
            "goal": "Create a CSV parser tool that can read and analyze spreadsheet data",
            "artifact_type": "tool",
            "name": "csv_parser",
        },
        category="tool_creation",
    ),
    FewShotExample(
        user_message="Make a web scraper tool for extracting content from websites",
        expected_tool="create",
        expected_arguments={
            "goal": "Create a web scraper tool for extracting content from websites",
            "artifact_type": "tool",
            "name": "web_scraper",
        },
        category="tool_creation",
    ),
    # config
    FewShotExample(
        user_message="Increase the agent timeout to 5 minutes",
        expected_tool="modify_config",
        expected_arguments={
            "key": "agent_timeout",
            "value": 300,
        },
        category="config",
    ),
    FewShotExample(
        user_message="Disable the router filter so all tools are always available",
        expected_tool="modify_config",
        expected_arguments={
            "key": "router_filter_enabled",
            "value": False,
        },
        category="config",
    ),
]

class FewShotLibrary:
    """Searchable library of curated few-shot routing examples.

    Used by routing strategies to inject examples into prompts,
    helping weaker models understand expected tool-calling patterns.
    """

    def __init__(self):
        self._examples: list[FewShotExample] = list(_CURATED_EXAMPLES)

    def get_examples(self, category: str | None = None, limit: int = 3) -> list[FewShotExample]:
        """Get few-shot examples, optionally filtered by category.

        Args:
            category: Optional category filter (e.g. "agent_creation").
            limit: Maximum number of examples to return.

        Returns:
            List of FewShotExample up to the limit.
        """
        if category:
            filtered = [e for e in self._examples if e.category == category]
            return filtered[:limit]
        return self._examples[:limit]

    def format_for_prompt(self, examples: list[FewShotExample]) -> str:
        """Format examples as XML for prompt injection.

        Args:
            examples: List of FewShotExample to format.

        Returns:
            XML string with routing examples.
        """
        if not examples:
            return ""

        lines = ["<routing_examples>"]
        for ex in examples:
            lines.append("  <example>")
            lines.append(f"    <user>{ex.user_message}</user>")
            lines.append(f"    <tool>{ex.expected_tool}</tool>")
            lines.append(f"    <arguments>{json.dumps(ex.expected_arguments)}</arguments>")
            lines.append("  </example>")
        lines.append("</routing_examples>")
        return "\n".join(lines)

    def add_from_metric(
        self,
        user_message: str,
        tool_called: str,
        arguments: dict,
        category: str,
    ) -> None:
        """Add a new example from observed routing metrics.

        Reserved for Phase 115.5 autonomous optimization pipeline.
        Present now for API completeness.

        Args:
            user_message: The user message that triggered the tool call.
            tool_called: The tool that was called.
            arguments: The arguments passed to the tool.
            category: The category for this example.
        """
        self._examples.append(
            FewShotExample(
                user_message=user_message,
                expected_tool=tool_called,
                expected_arguments=arguments,
                category=category,
            )
        )

# Singleton pattern with double-checked locking
_few_shot_library: FewShotLibrary | None = None
_few_shot_library_lock = threading.Lock()

def get_few_shot_library() -> FewShotLibrary:
    """Get or create singleton FewShotLibrary instance."""
    global _few_shot_library
    if _few_shot_library is None:
        with _few_shot_library_lock:
            if _few_shot_library is None:
                _few_shot_library = FewShotLibrary()
    return _few_shot_library
