"""Zero-Dev Agent Wrappers.

Factory functions that wrap a discovered agent directory into a
UniversalAgent without requiring manual adapter code. Each framework
handler imports from the agent directory and wraps using the correct
adapter class.

Target: ~180 LOC
"""

import importlib
import logging
import sys
from pathlib import Path
from typing import Any

from core.adapters.protocol import UniversalAgent

logger = logging.getLogger(__name__)

def wrap_agent_directory(name: str, path: Path, framework: str) -> UniversalAgent | None:
    """Wrap an agent directory as a UniversalAgent.

    Uses framework-specific logic to locate, import, and wrap the agent
    object found in the directory. Each handler attempts multiple patterns
    (e.g. create_crew(), crew, create_graph(), graph, etc.) and falls
    back gracefully.

    Args:
        name: Agent directory name (used as agent identifier).
        path: Absolute path to the agent directory.
        framework: Detected framework string ("crewai", "langchain", "adk", "custom").

    Returns:
        UniversalAgent instance, or None if wrapping failed.
    """
    handlers = {
        "crewai": _wrap_crewai,
        "langchain": _wrap_langchain,
        "adk": _wrap_adk,
        "custom": _wrap_custom,
    }

    handler = handlers.get(framework, _wrap_custom)

    try:
        return handler(name, path)
    except Exception as e:
        logger.warning(f"zero-dev: failed to wrap '{name}' (framework={framework}): {e}")
        return None

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _try_import_attr(module_path: str, attr_names: list[str]) -> Any | None:
    """Try to import a module and return the first matching attribute.

    Args:
        module_path: Dotted Python module path to import.
        attr_names: List of attribute names to try (in order).

    Returns:
        The first found attribute value, or None.
    """
    try:
        mod = importlib.import_module(module_path)
    except (ImportError, ModuleNotFoundError) as e:
        logger.debug(f"zero-dev: could not import {module_path}: {e}")
        return None

    for attr in attr_names:
        obj = getattr(mod, attr, None)
        if obj is not None:
            return obj

    return None

def _ensure_on_path(path: Path) -> None:
    """Ensure the agent directory's parent is on sys.path for imports.

    Args:
        path: Agent directory path (the parent will be added to sys.path).
    """
    parent = str(path.parent.resolve())
    if parent not in sys.path:
        sys.path.insert(0, parent)

def _read_description(path: Path) -> str:
    """Read a short description from the agent directory.

    Tries, in order: dryade.json "description", README.md first line,
    __init__.py docstring, fallback to generic.

    Args:
        path: Agent directory path.

    Returns:
        Description string.
    """
    import json

    # dryade.json
    dryade_json = path / "dryade.json"
    if dryade_json.is_file():
        try:
            data = json.loads(dryade_json.read_text(encoding="utf-8"))
            desc = data.get("description")
            if desc:
                return desc
        except (json.JSONDecodeError, OSError):
            pass

    # README first line
    readme = path / "README.md"
    if readme.is_file():
        try:
            first_line = readme.read_text(encoding="utf-8").strip().split("\n")[0]
            # Strip markdown heading markers
            return first_line.lstrip("# ").strip()
        except OSError:
            pass

    # __init__.py docstring
    init_file = path / "__init__.py"
    if init_file.is_file():
        try:
            content = init_file.read_text(encoding="utf-8")
            if content.startswith('"""') or content.startswith("'''"):
                quote = content[:3]
                end = content.find(quote, 3)
                if end > 3:
                    return content[3:end].strip().split("\n")[0]
        except OSError:
            pass

    return f"Auto-discovered agent: {path.name}"

# ---------------------------------------------------------------------------
# Framework-specific wrappers
# ---------------------------------------------------------------------------

def _wrap_crewai(name: str, path: Path) -> UniversalAgent | None:
    """Wrap a CrewAI agent directory.

    Tries to find:
      1. create_crew() factory function -> Crew -> CrewDelegationAdapter
      2. crew attribute -> Crew -> CrewDelegationAdapter
      3. Fallback: CrewAIAgentAdapter with lazy config if agent config found
    """
    _ensure_on_path(path)
    description = _read_description(path)
    dir_name = path.name

    # Search modules for crew factory or instance
    search_modules = [
        f"{dir_name}",
        f"{dir_name}.__init__",
        f"{dir_name}.crew",
        f"{dir_name}.main",
    ]

    for mod_path in search_modules:
        # Try factory function first
        factory = _try_import_attr(mod_path, ["create_crew"])
        if callable(factory):
            try:
                from core.adapters.crewai_delegation import CrewDelegationAdapter

                crew = factory()
                logger.info(f"zero-dev: {name} -> CrewDelegationAdapter via create_crew()")
                return CrewDelegationAdapter(crew=crew, name=name, description=description)
            except Exception as e:
                logger.debug(f"zero-dev: create_crew() failed for {name}: {e}")

        # Try crew instance
        crew_obj = _try_import_attr(mod_path, ["crew", "Crew"])
        if crew_obj is not None and hasattr(crew_obj, "kickoff"):
            try:
                from core.adapters.crewai_delegation import CrewDelegationAdapter

                logger.info(f"zero-dev: {name} -> CrewDelegationAdapter via crew attribute")
                return CrewDelegationAdapter(crew=crew_obj, name=name, description=description)
            except Exception as e:
                logger.debug(f"zero-dev: crew wrapping failed for {name}: {e}")

    # Fallback: look for agent factory
    for mod_path in search_modules:
        factory = _try_import_attr(mod_path, [f"create_{name}_agent", "create_agent"])
        if callable(factory):
            try:
                agent = factory()
                if isinstance(agent, UniversalAgent):
                    logger.info(f"zero-dev: {name} -> existing UniversalAgent from factory")
                    return agent
            except Exception as e:
                logger.debug(f"zero-dev: agent factory failed for {name}: {e}")

    logger.warning(f"zero-dev: could not wrap crewai directory '{name}'")
    return None

def _wrap_langchain(name: str, path: Path) -> UniversalAgent | None:
    """Wrap a LangChain/LangGraph agent directory.

    Tries to find:
      1. create_graph() factory -> LangChainAgentAdapter
      2. graph attribute (CompiledStateGraph) -> LangChainAgentAdapter
      3. create_agent() factory -> LangChainAgentAdapter
      4. agent attribute (AgentExecutor) -> LangChainAgentAdapter
    """
    _ensure_on_path(path)
    description = _read_description(path)
    dir_name = path.name

    search_modules = [
        f"{dir_name}",
        f"{dir_name}.__init__",
        f"{dir_name}.graph",
        f"{dir_name}.main",
    ]

    from core.adapters.langchain_adapter import LangChainAgentAdapter

    for mod_path in search_modules:
        # Try graph factory
        factory = _try_import_attr(mod_path, ["create_graph"])
        if callable(factory):
            try:
                graph = factory()
                logger.info(f"zero-dev: {name} -> LangChainAgentAdapter via create_graph()")
                return LangChainAgentAdapter(agent=graph, name=name, description=description)
            except Exception as e:
                logger.debug(f"zero-dev: create_graph() failed for {name}: {e}")

        # Try graph instance
        graph_obj = _try_import_attr(mod_path, ["graph", "compiled_graph"])
        if graph_obj is not None and hasattr(graph_obj, "ainvoke"):
            try:
                logger.info(f"zero-dev: {name} -> LangChainAgentAdapter via graph attribute")
                return LangChainAgentAdapter(agent=graph_obj, name=name, description=description)
            except Exception as e:
                logger.debug(f"zero-dev: graph wrapping failed for {name}: {e}")

        # Try agent factory
        factory = _try_import_attr(mod_path, [f"create_{name}_agent", "create_agent"])
        if callable(factory):
            try:
                agent = factory()
                if isinstance(agent, UniversalAgent):
                    logger.info(f"zero-dev: {name} -> existing UniversalAgent from factory")
                    return agent
                # Assume it's a LangChain agent
                logger.info(f"zero-dev: {name} -> LangChainAgentAdapter via create_agent()")
                return LangChainAgentAdapter(agent=agent, name=name, description=description)
            except Exception as e:
                logger.debug(f"zero-dev: agent factory failed for {name}: {e}")

        # Try agent instance
        agent_obj = _try_import_attr(mod_path, ["agent", "executor"])
        if agent_obj is not None and (hasattr(agent_obj, "ainvoke") or hasattr(agent_obj, "run")):
            try:
                logger.info(f"zero-dev: {name} -> LangChainAgentAdapter via agent attribute")
                return LangChainAgentAdapter(agent=agent_obj, name=name, description=description)
            except Exception as e:
                logger.debug(f"zero-dev: agent wrapping failed for {name}: {e}")

    logger.warning(f"zero-dev: could not wrap langchain directory '{name}'")
    return None

def _wrap_adk(name: str, path: Path) -> UniversalAgent | None:
    """Wrap a Google ADK agent directory.

    Tries to find:
      1. create_agent() factory -> ADKAgentAdapter
      2. root_agent / agent attribute -> ADKAgentAdapter
    """
    _ensure_on_path(path)
    dir_name = path.name

    search_modules = [
        f"{dir_name}",
        f"{dir_name}.__init__",
        f"{dir_name}.agent",
        f"{dir_name}.main",
    ]

    from core.adapters.adk_adapter import ADKAgentAdapter

    for mod_path in search_modules:
        # Try factory
        factory = _try_import_attr(mod_path, ["create_agent"])
        if callable(factory):
            try:
                agent = factory()
                logger.info(f"zero-dev: {name} -> ADKAgentAdapter via create_agent()")
                return ADKAgentAdapter(agent=agent, name=name)
            except Exception as e:
                logger.debug(f"zero-dev: create_agent() failed for {name}: {e}")

        # Try instance attributes
        agent_obj = _try_import_attr(mod_path, ["root_agent", "agent"])
        if agent_obj is not None:
            try:
                logger.info(f"zero-dev: {name} -> ADKAgentAdapter via attribute")
                return ADKAgentAdapter(agent=agent_obj, name=name)
            except Exception as e:
                logger.debug(f"zero-dev: ADK agent wrapping failed for {name}: {e}")

    logger.warning(f"zero-dev: could not wrap adk directory '{name}'")
    return None

def _wrap_custom(name: str, path: Path) -> UniversalAgent | None:
    """Wrap a custom agent directory.

    Tries to find:
      1. create_agent() or create_{name}_agent() factory returning UniversalAgent
      2. Class that is a subclass of UniversalAgent
    """
    _ensure_on_path(path)
    dir_name = path.name

    search_modules = [
        f"{dir_name}",
        f"{dir_name}.__init__",
        f"{dir_name}.main",
    ]

    for mod_path in search_modules:
        # Try factory
        factory = _try_import_attr(mod_path, [f"create_{name}_agent", "create_agent"])
        if callable(factory):
            try:
                agent = factory()
                if isinstance(agent, UniversalAgent):
                    logger.info(f"zero-dev: {name} -> custom UniversalAgent from factory")
                    return agent
            except Exception as e:
                logger.debug(f"zero-dev: custom factory failed for {name}: {e}")

        # Try to find UniversalAgent subclass in module
        try:
            mod = importlib.import_module(mod_path)
            for attr_name in dir(mod):
                obj = getattr(mod, attr_name, None)
                if (
                    isinstance(obj, type)
                    and issubclass(obj, UniversalAgent)
                    and obj is not UniversalAgent
                ):
                    try:
                        instance = obj()
                        logger.info(f"zero-dev: {name} -> custom {obj.__name__} instance")
                        return instance
                    except Exception as e:
                        logger.debug(f"zero-dev: could not instantiate {obj.__name__}: {e}")
        except (ImportError, ModuleNotFoundError):
            pass

    logger.warning(f"zero-dev: could not wrap custom directory '{name}'")
    return None
