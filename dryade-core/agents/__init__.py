"""Agents Package.

Core reference agent implementations demonstrating multi-framework patterns.
Each agent showcases a different integration approach:

- DevOps Engineer: MCP-native (no framework overhead)
- Research Assistant: LangChain with Playwright, Memory, Filesystem MCP tools
- Code Reviewer: CrewAI-based with GitHub, Context7, Git MCP tools
- Database Analyst: LangChain/LangGraph-based with DBHub, Grafana MCP tools
- Project Manager: ADK-based (future)

Usage:
    from agents import register_core_agents
    from agents.devops_engineer import DevOpsEngineerAgent, create_devops_engineer_agent
    from agents.research_assistant import ResearchAssistantAgent, create_research_assistant_agent
    from agents.code_reviewer import CodeReviewerAgent, create_code_reviewer_agent
    from agents.database_analyst import DatabaseAnalystAgent, create_database_analyst_agent

    # Register all core agents with the adapter registry
    register_core_agents()

    # Or create individual agents
    agent = create_devops_engineer_agent()
    result = await agent.execute("Check git status")

    research = create_research_assistant_agent()
    result = await research.execute("Research AI trends", context={"url": "https://example.com"})

    reviewer = create_code_reviewer_agent()
    result = await reviewer.execute("Review PR #123")

    analyst = create_database_analyst_agent()
    result = await analyst.execute("List all tables")
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Registry of available core agents
_CORE_AGENTS: dict[str, type] = {}

def register_core_agents() -> list[str]:
    """Register all core demonstration agents.

    Called during API startup after MCP servers are configured.
    This function attempts to register each agent individually, ensuring that
    a failure in one agent's registration doesn't prevent other agents from
    being registered (graceful fallback pattern).

    Returns:
        List of registered agent names.

    Example:
        >>> registered = register_core_agents()
        >>> print(registered)
        ['devops_engineer', 'code_reviewer', 'database_analyst', 'research_assistant']
    """
    from core.adapters import register_agent

    registered: list[str] = []

    # DevOps Engineer (MCP-native)
    try:
        from agents.devops_engineer import create_devops_engineer_agent

        agent = create_devops_engineer_agent()
        register_agent(agent)
        registered.append(agent.get_card().name)
        logger.info(f"Registered core agent: {agent.get_card().name}")
    except Exception as e:
        logger.warning(f"Failed to register devops_engineer: {e}")

    # Code Reviewer (CrewAI)
    try:
        from agents.code_reviewer import create_code_reviewer_agent

        agent = create_code_reviewer_agent()
        register_agent(agent)
        registered.append(agent.get_card().name)
        logger.info(f"Registered core agent: {agent.get_card().name}")
    except Exception as e:
        logger.warning(f"Failed to register code_reviewer: {e}")

    # Database Analyst (LangChain)
    try:
        from agents.database_analyst import create_database_analyst_agent

        agent = create_database_analyst_agent()
        register_agent(agent)
        registered.append(agent.get_card().name)
        logger.info(f"Registered core agent: {agent.get_card().name}")
    except Exception as e:
        logger.warning(f"Failed to register database_analyst: {e}")

    # Research Assistant (LangChain)
    try:
        from agents.research_assistant import create_research_assistant_agent

        agent = create_research_assistant_agent()
        register_agent(agent)
        registered.append(agent.get_card().name)
        logger.info(f"Registered core agent: {agent.get_card().name}")
    except Exception as e:
        logger.warning(f"Failed to register research_assistant: {e}")

    # Project Manager (MCP-native)
    try:
        from agents.project_manager import create_project_manager_agent

        agent = create_project_manager_agent()
        register_agent(agent)
        registered.append(agent.get_card().name)
        logger.info(f"Registered core agent: {agent.get_card().name}")
    except Exception as e:
        logger.warning(f"Failed to register project_manager: {e}")

    logger.info(f"Registered {len(registered)}/5 core agents: {registered}")
    return registered

def get_available_agents() -> list[str]:
    """Get list of available core agent names.

    Returns:
        List of agent names that can be created.
    """
    return [
        "devops_engineer",
        "research_assistant",
        "code_reviewer",
        "database_analyst",
        "project_manager",
    ]

__all__ = [
    "register_core_agents",
    "get_available_agents",
]
