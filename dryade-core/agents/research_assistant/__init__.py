"""Research Assistant Agent - LangChain Implementation.

Demonstrates LangChain agent with multiple MCP tool integrations for research workflows.
Uses Playwright for web browsing, Memory for knowledge persistence, and Filesystem for reports.

This agent specializes in research tasks:
- Web browsing (navigate, screenshot, click) via Playwright MCP
- Knowledge storage (entities, relations, search) via Memory MCP
- Report generation (read/write files) via Filesystem MCP

Usage:
    from agents.research_assistant import ResearchAssistantAgent, create_research_assistant_agent

    # Factory function (recommended)
    agent = create_research_assistant_agent()
    result = await agent.execute("Research the latest AI trends")

    # Direct instantiation
    agent = ResearchAssistantAgent()
    card = agent.get_card()
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from langchain_core.tools import tool

from core.adapters.langchain_adapter import LangChainAgentAdapter
from core.adapters.protocol import AgentCard, AgentFramework, AgentResult
from core.mcp.tool_wrapper import MCPToolWrapper

logger = logging.getLogger(__name__)

# Load agent configuration
def _load_config() -> dict[str, Any]:
    """Load agent configuration from YAML file."""
    config_path = Path(__file__).parent / "config.yaml"
    if config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f)
    return {}

# ============================================================================
# Playwright MCP Tools (Web Research)
# ============================================================================

@tool
def navigate_to_url(url: str) -> str:
    """Navigate browser to a URL and return page content.

    Args:
        url: The URL to navigate to.

    Returns:
        Page title and accessibility snapshot for LLM analysis.
    """
    wrapper = MCPToolWrapper("playwright", "playwright_navigate", "Navigate to URL")
    try:
        wrapper.call(url=url)
        # Get page snapshot for content
        snapshot_wrapper = MCPToolWrapper(
            "playwright", "playwright_snapshot", "Get page accessibility tree"
        )
        snapshot = snapshot_wrapper.call()
        return f"Navigated to {url}\n\nPage content:\n{snapshot}"
    except Exception as e:
        return f"Failed to navigate to {url}: {e}"

@tool
def take_screenshot(name: str = "screenshot") -> str:
    """Take screenshot of current page for visual analysis.

    Args:
        name: Name for the screenshot (optional).

    Returns:
        Confirmation that screenshot was taken.
    """
    wrapper = MCPToolWrapper("playwright", "playwright_screenshot", "Take page screenshot")
    try:
        result = wrapper.call()
        return f"Screenshot '{name}' captured successfully. {result}"
    except Exception as e:
        return f"Failed to take screenshot: {e}"

@tool
def click_element(selector: str) -> str:
    """Click an element on the page by CSS selector.

    Args:
        selector: CSS selector for the element to click.

    Returns:
        Confirmation of the click action.
    """
    wrapper = MCPToolWrapper("playwright", "playwright_click", "Click element")
    try:
        wrapper.call(selector=selector)
        return f"Clicked element: {selector}"
    except Exception as e:
        return f"Failed to click {selector}: {e}"

# ============================================================================
# Memory MCP Tools (Knowledge Graph)
# ============================================================================

@tool
def store_research_finding(
    entity_name: str,
    entity_type: str,
    observations: list[str],
) -> str:
    """Store a research finding in the knowledge graph.

    Args:
        entity_name: Unique name for the finding/entity.
        entity_type: Type of entity (e.g., 'finding', 'source', 'topic').
        observations: List of facts/observations about this entity.

    Returns:
        Confirmation that the entity was stored.
    """
    wrapper = MCPToolWrapper("memory", "create_entities", "Create knowledge entities")
    try:
        entity = {
            "name": entity_name,
            "entityType": entity_type,
            "observations": observations,
        }
        result = wrapper.call(entities=[entity])
        return f"Stored research finding '{entity_name}' ({entity_type}). {result}"
    except Exception as e:
        return f"Failed to store finding: {e}"

@tool
def search_knowledge(query: str) -> str:
    """Search stored research findings by query.

    Args:
        query: Search query string to match against entity names and observations.

    Returns:
        Matching entities from the knowledge graph.
    """
    wrapper = MCPToolWrapper("memory", "search_nodes", "Search knowledge graph")
    try:
        result = wrapper.call(query=query)
        return f"Search results for '{query}':\n{result}"
    except Exception as e:
        return f"Failed to search knowledge: {e}"

@tool
def link_findings(source: str, target: str, relation_type: str) -> str:
    """Create relationship between two research findings.

    Args:
        source: Name of the source entity.
        target: Name of the target entity.
        relation_type: Type of relationship (e.g., 'supports', 'contradicts', 'related_to').

    Returns:
        Confirmation that the relation was created.
    """
    wrapper = MCPToolWrapper("memory", "create_relations", "Create knowledge relations")
    try:
        relation = {
            "from": source,
            "to": target,
            "relationType": relation_type,
        }
        result = wrapper.call(relations=[relation])
        return f"Linked '{source}' --[{relation_type}]--> '{target}'. {result}"
    except Exception as e:
        return f"Failed to link findings: {e}"

# ============================================================================
# Filesystem MCP Tools (Reports)
# ============================================================================

@tool
def save_report(path: str, content: str) -> str:
    """Save research report to a file.

    Args:
        path: File path where the report should be saved.
        content: Content of the report to save.

    Returns:
        Confirmation that the file was saved.
    """
    wrapper = MCPToolWrapper("filesystem", "write_file", "Write file")
    try:
        wrapper.call(path=path, content=content)
        return f"Report saved to {path}"
    except Exception as e:
        return f"Failed to save report: {e}"

@tool
def read_file(path: str) -> str:
    """Read contents of a file.

    Args:
        path: File path to read.

    Returns:
        Contents of the file.
    """
    wrapper = MCPToolWrapper("filesystem", "read_file", "Read file")
    try:
        content = wrapper.call(path=path)
        return f"Contents of {path}:\n{content}"
    except Exception as e:
        return f"Failed to read file: {e}"

# ============================================================================
# Research Assistant Agent
# ============================================================================

# Collect all tools
_RESEARCH_TOOLS = [
    # Playwright (web research)
    navigate_to_url,
    take_screenshot,
    click_element,
    # Memory (knowledge graph)
    store_research_finding,
    search_knowledge,
    link_findings,
    # Filesystem (reports)
    save_report,
    read_file,
]

class ResearchAssistantAgent:
    """LangChain Research Assistant agent with multi-MCP-server integration.

    Combines web browsing (Playwright), knowledge storage (Memory), and
    file operations (Filesystem) for comprehensive research workflows.

    Attributes:
        name: Agent name for identification.
        description: Human-readable description.
        system_prompt: System prompt defining agent behavior.

    Example:
        >>> agent = ResearchAssistantAgent()
        >>> card = agent.get_card()
        >>> print(card.framework)
        AgentFramework.LANGCHAIN
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Initialize the Research Assistant agent.

        Args:
            config: Optional configuration override. Loaded from config.yaml if not provided.
        """
        self._config = config or _load_config()

        # Agent metadata
        self.name = self._config.get("name", "research_assistant")
        self.description = self._config.get(
            "description",
            "Research topics via web browsing with persistent knowledge",
        )
        self.system_prompt = (
            "You are a research assistant. Help users research topics by browsing "
            "the web, storing findings in your knowledge graph, and generating reports. "
            "When researching:\n"
            "1. Navigate to relevant URLs to gather information\n"
            "2. Store key findings as entities in the knowledge graph\n"
            "3. Link related findings to build a knowledge network\n"
            "4. Generate comprehensive reports when requested"
        )

        # Tools
        self._tools = _RESEARCH_TOOLS

        # Create the LangChain adapter
        self._adapter = self._create_adapter()

    def _create_adapter(self) -> LangChainAgentAdapter:
        """Create LangChain adapter wrapping this agent's tools."""
        # Create a simple tool-bearing agent using LangChain
        # We use a custom agent wrapper that exposes tools

        class ToolAgent:
            """Simple wrapper to hold tools for LangChain adapter."""

            def __init__(self, tools: list, system_prompt: str):
                self.tools = tools
                self.system_prompt = system_prompt

            async def ainvoke(self, inputs: dict) -> dict:
                """Invoke is handled by the adapter's execute method."""
                return {"output": "Use execute() method instead"}

        agent = ToolAgent(self._tools, self.system_prompt)
        return LangChainAgentAdapter(
            agent=agent,
            name=self.name,
            description=self.description,
        )

    def get_card(self) -> AgentCard:
        """Return agent's capability card.

        Returns:
            AgentCard with framework=LANGCHAIN and research capabilities.
        """
        return AgentCard(
            name=self.name,
            description=self.description,
            version="1.0.0",
            framework=AgentFramework.LANGCHAIN,
            capabilities=[],  # Tools exposed via get_tools()
            metadata={
                "required_servers": ["playwright", "memory", "filesystem"],
                "tool_count": len(self._tools),
            },
        )

    def get_tools(self) -> list[dict[str, Any]]:
        """Return available tools in OpenAI function format.

        Returns:
            List of tool definitions with name, description, and parameters.
        """
        return self._adapter.get_tools()

    async def execute(
        self,
        task: str,
        context: dict[str, Any] | None = None,
    ) -> AgentResult:
        """Execute a research task with graceful fallback.

        Routes tasks to appropriate MCP tools. On failure, attempts to
        use cached knowledge from Memory MCP if available.

        Args:
            task: Natural language task description.
            context: Optional execution context with additional parameters.

        Returns:
            AgentResult with status and result.

        Example:
            >>> result = await agent.execute("Research AI trends and save report")
            >>> print(result.result)
        """
        return await self.execute_with_fallback(task, context)

    async def execute_with_fallback(
        self,
        task: str,
        context: dict[str, Any] | None = None,
    ) -> AgentResult:
        """Execute task with graceful degradation on tool failures.

        Args:
            task: Research task to execute.
            context: Optional execution context.

        Returns:
            AgentResult with status, result, and metadata.
        """
        context = context or {}

        try:
            result = await self._execute_primary(task, context)
            return result
        except Exception as e:
            logger.warning(f"Primary execution failed: {e}")

            # Check for cached research on this topic
            cached = self._get_cached_result(task)
            if cached:
                return AgentResult(
                    result=cached,
                    status="partial",
                    error=f"Using cached data ({e!s})",
                    metadata={"cached": True, "agent": self.name},
                )

            # Graceful message
            return AgentResult(
                result=None,
                status="error",
                error=f"Research failed: {e!s}. Try again later.",
                metadata={"recoverable": True, "agent": self.name},
            )

    async def _execute_primary(
        self,
        task: str,
        context: dict[str, Any],
    ) -> AgentResult:
        """Execute the primary research task.

        This method routes the task to appropriate tools based on keywords.

        Args:
            task: Research task description.
            context: Execution context.

        Returns:
            AgentResult with research findings.
        """
        task_lower = task.lower()

        # Route based on task keywords
        results = []

        # Web browsing tasks
        if "browse" in task_lower or "url" in task_lower or "http" in task_lower:
            url = context.get("url")
            if url:
                result = navigate_to_url.invoke({"url": url})
                results.append(result)

        # Search existing knowledge
        if "search" in task_lower or "find" in task_lower:
            query = context.get("query", task)
            result = search_knowledge.invoke({"query": query})
            results.append(result)

        # Save report
        if "save" in task_lower or "report" in task_lower:
            path = context.get("path", "/tmp/research_report.md")
            content = context.get("content", f"# Research Report\n\nTask: {task}")
            result = save_report.invoke({"path": path, "content": content})
            results.append(result)

        # Read file
        if "read" in task_lower and "file" in task_lower:
            path = context.get("path")
            if path:
                result = read_file.invoke({"path": path})
                results.append(result)

        # Store finding
        if "store" in task_lower or "remember" in task_lower:
            entity_name = context.get("entity_name", "research_finding")
            entity_type = context.get("entity_type", "finding")
            observations = context.get("observations", [task])
            result = store_research_finding.invoke(
                {
                    "entity_name": entity_name,
                    "entity_type": entity_type,
                    "observations": observations,
                }
            )
            results.append(result)

        if results:
            return AgentResult(
                result="\n\n".join(results),
                status="ok",
                metadata={"task": task, "agent": self.name},
            )

        # Default: just search knowledge
        result = search_knowledge.invoke({"query": task})
        return AgentResult(
            result=result,
            status="ok",
            metadata={"task": task, "agent": self.name, "action": "search"},
        )

    def _get_cached_result(self, task: str) -> str | None:
        """Query Memory MCP for recent findings matching task keywords.

        Args:
            task: Task string to extract keywords from.

        Returns:
            Cached findings if found, None otherwise.
        """
        try:
            # Extract keywords from task
            keywords = task.split()[:5]  # First 5 words as query
            query = " ".join(keywords)

            wrapper = MCPToolWrapper("memory", "search_nodes", "Search cached findings")
            result = wrapper.call(query=query)

            if result and result.strip() and "[]" not in result:
                return f"[Cached findings for '{query}']\n{result}"

            return None
        except Exception as e:
            logger.debug(f"Cache lookup failed: {e}")
            return None

    def supports_streaming(self) -> bool:
        """Check if agent supports streaming output.

        Returns:
            True since LangChain supports streaming.
        """
        return self._adapter.supports_streaming()

def create_research_assistant_agent(
    config: dict[str, Any] | None = None,
) -> LangChainAgentAdapter:
    """Factory function to create a Research Assistant agent wrapped in LangChainAgentAdapter.

    Args:
        config: Optional configuration override.

    Returns:
        LangChainAgentAdapter wrapping the Research Assistant.

    Example:
        >>> agent = create_research_assistant_agent()
        >>> card = agent.get_card()
        >>> print(card.framework)
        AgentFramework.LANGCHAIN
    """
    research_agent = ResearchAssistantAgent(config=config)

    # Return adapter that wraps the research agent
    class ResearchAgentWrapper:
        """Wrapper to expose research agent through LangChain adapter interface."""

        def __init__(self, agent: ResearchAssistantAgent):
            self._agent = agent
            self.tools = agent._tools

        async def ainvoke(self, inputs: dict) -> dict:
            """Invoke the research agent."""
            task = inputs.get("input", "")
            context = {k: v for k, v in inputs.items() if k != "input"}
            result = await self._agent.execute(task, context)
            return {"output": result.result, "status": result.status}

    wrapper = ResearchAgentWrapper(research_agent)
    return LangChainAgentAdapter(
        agent=wrapper,
        name=research_agent.name,
        description=research_agent.description,
    )

__all__ = [
    "ResearchAssistantAgent",
    "create_research_assistant_agent",
]
