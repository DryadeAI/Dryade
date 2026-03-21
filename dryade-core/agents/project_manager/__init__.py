"""Project Manager Agent.

Simple MCP-native agent for task creation and escalation handling.
Designed for workflow integration to handle escalation scenarios.
"""

from __future__ import annotations

import logging
from typing import Any

from core.adapters.protocol import (
    AgentCapability,
    AgentCard,
    AgentFramework,
    AgentResult,
    UniversalAgent,
)

logger = logging.getLogger(__name__)

class ProjectManagerAgent(UniversalAgent):
    """MCP-native Project Manager agent.

    Handles escalation tasks by creating GitHub issues or posting comments.
    Falls back to formatted output if MCP tools are unavailable.
    """

    def __init__(self):
        """Initialize project manager agent."""
        self._card = AgentCard(
            name="project_manager",
            description="Creates tasks and manages escalations for review issues",
            version="1.0.0",
            framework=AgentFramework.MCP,
            capabilities=[
                AgentCapability(
                    name="create_escalation",
                    description="Create escalation task or issue",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "description": "Issue title"},
                            "body": {"type": "string", "description": "Issue body"},
                            "labels": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Issue labels",
                            },
                        },
                        "required": ["title"],
                    },
                ),
                AgentCapability(
                    name="post_comment",
                    description="Post comment on PR or issue",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "body": {"type": "string", "description": "Comment body"},
                            "pr_number": {"type": "integer", "description": "PR number"},
                        },
                        "required": ["body"],
                    },
                ),
            ],
            tools=[],  # Tools added dynamically from MCP
            metadata={
                "version": "1.0.0",
                "mcp_servers": ["github"],
            },
        )
        self._tools: dict[str, Any] = {}
        self._initialized = False

    def get_card(self) -> AgentCard:
        """Return agent card."""
        return self._card

    def get_tools(self) -> list[dict[str, Any]]:
        """Return available tools in OpenAI function format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "create_escalation",
                    "description": "Create escalation task or issue",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "description": "Issue title"},
                            "body": {"type": "string", "description": "Issue body"},
                            "labels": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Issue labels",
                            },
                        },
                        "required": ["title"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "post_comment",
                    "description": "Post comment on PR or issue",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "body": {"type": "string", "description": "Comment body"},
                            "pr_number": {"type": "integer", "description": "PR number"},
                        },
                        "required": ["body"],
                    },
                },
            },
        ]

    def _ensure_initialized(self) -> bool:
        """Lazy initialization - load MCP tools on first use."""
        if self._initialized:
            return True

        try:
            from core.mcp import get_registry

            registry = get_registry()

            # Try to get GitHub tools
            try:
                self._tools["create_issue"] = registry.get_tool("github", "create_issue")
                self._tools["create_pr_comment"] = registry.get_tool(
                    "github", "create_or_update_pr_comment"
                )
            except Exception:
                logger.debug("GitHub MCP tools not available - using fallback mode")

            self._initialized = True
            return True

        except Exception as e:
            logger.warning(f"Failed to initialize MCP tools: {e}")
            self._initialized = True  # Mark as initialized to avoid retry loops
            return True

    async def execute(self, task: str, context: dict[str, Any] | None = None) -> AgentResult:
        """Execute task with context.

        Args:
            task: Task description
            context: Execution context with owner, repo, pr_number, etc.

        Returns:
            AgentResult with execution output
        """
        context = context or {}
        self._ensure_initialized()

        task_lower = task.lower()
        logger.info(f"[PROJECT_MANAGER] Executing task: {task}")

        try:
            # Extract context values
            owner = context.get("owner")
            repo = context.get("repo")
            pr_number = context.get("pr_number")

            # Get any previous review results from context
            security_review = context.get("security_review", "")
            fetch_pr = context.get("fetch_pr", "")

            # Create escalation task/issue
            if "escalate" in task_lower or "create" in task_lower or "task" in task_lower:
                title = "[ESCALATION] Code Review Requires Senior Review"
                body = self._format_escalation_body(
                    task=task,
                    security_review=security_review,
                    fetch_pr=fetch_pr,
                    pr_number=pr_number,
                    owner=owner,
                    repo=repo,
                )

                # Try MCP tool if available
                if "create_issue" in self._tools and owner and repo:
                    try:
                        result = self._tools["create_issue"].call(
                            owner=owner,
                            repo=repo,
                            title=title,
                            body=body,
                            labels=["needs-review", "escalation", "high-priority"],
                        )
                        return AgentResult(
                            result=f"Created escalation issue: {result}",
                            status="ok",
                            metadata={"type": "github_issue", "owner": owner, "repo": repo},
                        )
                    except Exception as e:
                        logger.warning(f"GitHub create_issue failed: {e}")

                # Fallback: return formatted escalation message
                return AgentResult(
                    result=f"ESCALATION REQUIRED\n\nTitle: {title}\n\n{body}",
                    status="ok",
                    metadata={"type": "escalation_message", "needs_manual_action": True},
                )

            # Post comment
            if "comment" in task_lower or "notify" in task_lower:
                comment_body = self._format_comment(task, context)

                if "create_pr_comment" in self._tools and owner and repo and pr_number:
                    try:
                        result = self._tools["create_pr_comment"].call(
                            owner=owner,
                            repo=repo,
                            pr_number=int(pr_number),
                            body=comment_body,
                        )
                        return AgentResult(
                            result=f"Posted comment: {result}",
                            status="ok",
                            metadata={"type": "pr_comment", "pr_number": pr_number},
                        )
                    except Exception as e:
                        logger.warning(f"GitHub create_pr_comment failed: {e}")

                return AgentResult(
                    result=f"COMMENT:\n\n{comment_body}",
                    status="ok",
                    metadata={"type": "comment_message", "needs_manual_action": True},
                )

            # Default: treat as escalation
            return await self.execute(f"escalate: {task}", context)

        except Exception as e:
            logger.error(f"[PROJECT_MANAGER] Execution failed: {e}")
            return AgentResult(
                result=f"Execution failed: {str(e)}",
                status="error",
                error=str(e),
                metadata={"error": str(e)},
            )

    def _format_escalation_body(
        self,
        task: str,
        security_review: str,
        fetch_pr: str,
        pr_number: str | None,
        owner: str | None,
        repo: str | None,
    ) -> str:
        """Format escalation issue body."""
        lines = [
            "## Escalation Details",
            "",
            f"**Task:** {task}",
            "",
        ]

        if pr_number and owner and repo:
            lines.extend(
                [
                    f"**PR:** https://github.com/{owner}/{repo}/pull/{pr_number}",
                    "",
                ]
            )

        if security_review:
            lines.extend(
                [
                    "## Security Review Results",
                    "",
                    str(security_review)[:1000],
                    "",
                ]
            )

        if fetch_pr:
            lines.extend(
                [
                    "## PR Details",
                    "",
                    str(fetch_pr)[:500],
                    "",
                ]
            )

        lines.extend(
            [
                "## Action Required",
                "",
                "- [ ] Senior developer review required",
                "- [ ] Address security concerns",
                "- [ ] Verify risk assessment",
                "",
                "---",
                "*This issue was created automatically by the code review pipeline.*",
            ]
        )

        return "\n".join(lines)

    def _format_comment(self, task: str, context: dict[str, Any]) -> str:
        """Format PR comment."""
        lines = [
            "## Automated Review Notification",
            "",
            f"**Action:** {task}",
            "",
        ]

        if context.get("security_review"):
            lines.extend(
                [
                    "### Security Review",
                    str(context["security_review"])[:500],
                    "",
                ]
            )

        return "\n".join(lines)

def create_project_manager_agent() -> ProjectManagerAgent:
    """Factory function to create project manager agent.

    Returns:
        Configured ProjectManagerAgent instance.
    """
    return ProjectManagerAgent()
