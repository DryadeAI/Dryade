"""Agent Auto-Discovery and Directory Watcher.

Scans the agents/ directory for framework projects and detects their type
using a multi-signal approach: dryade.json > marker files > import patterns.

AgentDirectoryWatcher monitors for new/changed agent directories using
watchfiles.awatch() (following the SkillWatcher pattern from core.skills.watcher).

Target: ~250 LOC
"""

import asyncio
import json
import logging
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Import guard for watchfiles (optional dependency)
try:
    from watchfiles import awatch

    WATCHFILES_AVAILABLE = True
except ImportError:
    WATCHFILES_AVAILABLE = False

# ---------------------------------------------------------------------------
# Framework detection signals
# ---------------------------------------------------------------------------

# Marker files that indicate a specific framework (checked in directory root)
FRAMEWORK_MARKERS: dict[str, str] = {
    "crew.py": "crewai",
    "crewai.yaml": "crewai",
    "graph.py": "langchain",
    "langgraph.json": "langchain",
}

# Import patterns scanned in Python source files
IMPORT_PATTERNS: dict[str, str] = {
    "from crewai": "crewai",
    "import crewai": "crewai",
    "from langchain": "langchain",
    "from langgraph": "langchain",
    "from google.adk": "adk",
    "from google.genai": "adk",
}

# Directories to always skip during scanning
_SKIP_DIRS = {"__pycache__", ".git", ".venv", "node_modules"}

class AgentAutoDiscovery:
    """Scan a directory tree for agent projects and detect their framework.

    Multi-signal detection priority:
      1. dryade.json "framework" key (authoritative)
      2. Marker files (crew.py, langgraph.json, etc.)
      3. Import patterns in __init__.py
      4. Import patterns in all root-level .py files
      5. Fallback: "custom"
    """

    def __init__(self, agents_dir: Path | str = "agents"):
        """Initialize with path to agents directory.

        Args:
            agents_dir: Root directory containing agent subdirectories.
        """
        self._agents_dir = Path(agents_dir).resolve()

    @property
    def agents_dir(self) -> Path:
        """Return the resolved agents directory path."""
        return self._agents_dir

    def scan(self) -> list[dict[str, Any]]:
        """Scan agents_dir for subdirectories and detect their framework.

        Returns:
            List of dicts with keys: name, path, framework.
            Skips directories starting with '_' or '.', and __pycache__.
        """
        results: list[dict[str, Any]] = []

        if not self._agents_dir.is_dir():
            logger.warning(f"Agents directory does not exist: {self._agents_dir}")
            return results

        for entry in sorted(self._agents_dir.iterdir()):
            if not entry.is_dir():
                continue

            dir_name = entry.name

            # Skip hidden dirs, underscore-prefixed, and known junk
            if dir_name.startswith(("_", ".")) or dir_name in _SKIP_DIRS:
                continue

            framework = self.detect_framework(entry)
            results.append(
                {
                    "name": dir_name,
                    "path": entry,
                    "framework": framework,
                }
            )

        logger.debug(f"Scanned {len(results)} agent directories in {self._agents_dir}")
        return results

    def detect_framework(self, agent_dir: Path) -> str:
        """Detect the framework used by an agent directory.

        Uses multi-signal approach with decreasing authority:
          1. dryade.json "framework" field (authoritative)
          2. Marker files in FRAMEWORK_MARKERS
          3. Import patterns in __init__.py (first 4096 bytes)
          4. Import patterns in all root .py files (first 4096 bytes each)
          5. Fallback: "custom"

        Args:
            agent_dir: Path to the agent directory.

        Returns:
            Framework string: "crewai", "langchain", "adk", or "custom".
        """
        # Signal 1: dryade.json (authoritative)
        dryade_json = agent_dir / "dryade.json"
        if dryade_json.is_file():
            try:
                data = json.loads(dryade_json.read_text(encoding="utf-8"))
                if "framework" in data:
                    fw = data["framework"]
                    logger.debug(f"{agent_dir.name}: dryade.json declares framework={fw}")
                    return fw
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Error reading {dryade_json}: {e}")

        # Signal 2: Marker files
        for marker_file, framework in FRAMEWORK_MARKERS.items():
            if (agent_dir / marker_file).is_file():
                logger.debug(f"{agent_dir.name}: marker file '{marker_file}' -> {framework}")
                return framework

        # Signal 3: Import patterns in __init__.py
        init_file = agent_dir / "__init__.py"
        if init_file.is_file():
            fw = self._scan_imports(init_file)
            if fw:
                logger.debug(f"{agent_dir.name}: __init__.py imports -> {fw}")
                return fw

        # Signal 4: Import patterns in all root-level .py files
        for py_file in sorted(agent_dir.glob("*.py")):
            if py_file.name == "__init__.py":
                continue  # Already checked above
            fw = self._scan_imports(py_file)
            if fw:
                logger.debug(f"{agent_dir.name}: {py_file.name} imports -> {fw}")
                return fw

        # Check if directory has any Python files before falling through to custom
        has_python = any(agent_dir.glob("*.py"))
        if not has_python:
            logger.debug(f"{agent_dir.name}: config-only directory (no Python files), skipping")
            return "config-only"

        # Signal 5: Fallback
        logger.debug(f"{agent_dir.name}: no framework signals detected, defaulting to 'custom'")
        return "custom"

    def _scan_imports(self, py_file: Path) -> str | None:
        """Scan a Python file for framework import patterns.

        Only reads the first 4096 bytes for efficiency.

        Args:
            py_file: Path to a .py file.

        Returns:
            Framework string if pattern found, None otherwise.
        """
        try:
            content = py_file.read_bytes()[:4096].decode("utf-8", errors="ignore")
        except OSError:
            return None

        for pattern, framework in IMPORT_PATTERNS.items():
            if pattern in content:
                return framework

        return None

    def discover_and_register(self, registry=None) -> list[str]:
        """Scan, wrap, and register all discovered agents.

        For each discovered directory, calls zero_dev.wrap_agent_directory()
        to create a UniversalAgent, then registers it with the agent registry.

        Args:
            registry: Optional AgentRegistry instance. Uses global registry if None.

        Returns:
            List of successfully registered agent names.
        """
        from core.adapters.registry import get_registry, register_agent

        if registry is None:
            registry = get_registry()

        # Lazy import to avoid circular dependency
        from core.adapters.zero_dev import wrap_agent_directory

        registered: list[str] = []
        scan_results = self.scan()

        for info in scan_results:
            name = info["name"]
            path = info["path"]
            framework = info["framework"]

            # Skip if already registered
            if name in registry:
                logger.debug(f"Agent '{name}' already registered, skipping")
                registered.append(name)
                continue

            # Skip config-only directories (no Python implementation yet)
            if framework == "config-only":
                logger.debug(f"Skipping config-only agent directory '{name}'")
                continue

            try:
                agent = wrap_agent_directory(name, path, framework)
                if agent is not None:
                    register_agent(agent)
                    registered.append(name)
                    logger.info(
                        f"Auto-discovered and registered agent: {name} (framework={framework})"
                    )
                else:
                    logger.warning(
                        f"Could not wrap agent directory '{name}' (framework={framework})"
                    )
            except Exception as e:
                logger.warning(f"Failed to register auto-discovered agent '{name}': {e}")

        # Domain-specific agents are loaded via plugins, not core auto-discovery

        logger.info(
            f"Auto-discovery complete: {len(registered)}/{len(scan_results)} directory agents registered"
        )
        return registered

class AgentDirectoryWatcher:
    """Async directory watcher for agent hot-reload.

    Monitors the agents/ directory for new or changed agent projects
    using watchfiles.awatch(). Follows the SkillWatcher pattern from
    core.skills.watcher.

    Usage:
        discovery = AgentAutoDiscovery("agents")
        watcher = AgentDirectoryWatcher("agents", discovery)
        await watcher.start()
        # ... application runs ...
        await watcher.stop()
    """

    def __init__(
        self,
        agents_dir: Path | str,
        discovery: AgentAutoDiscovery,
        debounce_ms: int = 2000,
    ):
        """Initialize agent directory watcher.

        Args:
            agents_dir: Path to the agents directory.
            discovery: AgentAutoDiscovery instance for re-scanning.
            debounce_ms: Debounce interval in milliseconds for rapid changes.
        """
        self._agents_dir = Path(agents_dir).resolve()
        self._discovery = discovery
        self._debounce_ms = debounce_ms
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._running = False

    @property
    def is_running(self) -> bool:
        """Check if watcher is currently running."""
        return self._running

    async def start(self) -> None:
        """Start watching agents directory for changes.

        No-op if watchfiles is not available or watcher is already running.
        """
        if not WATCHFILES_AVAILABLE:
            logger.warning("watchfiles not installed, agent hot reload disabled")
            return

        if self._running:
            logger.debug("Agent directory watcher already running")
            return

        if not self._agents_dir.is_dir():
            logger.warning(f"Agents directory does not exist: {self._agents_dir}")
            return

        self._stop_event.clear()
        self._running = True
        self._task = asyncio.create_task(self._watch_loop())
        logger.info(f"Agent directory watcher started on {self._agents_dir}")

    async def stop(self) -> None:
        """Stop watching agents directory."""
        if not self._running:
            return

        self._stop_event.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        self._running = False
        logger.info("Agent directory watcher stopped")

    async def _watch_loop(self) -> None:
        """Main watch loop monitoring for agent directory changes."""
        try:
            async for changes in awatch(
                str(self._agents_dir),
                debounce=self._debounce_ms,
                stop_event=self._stop_event,
            ):
                # Identify affected agent directories
                affected_dirs: set[str] = set()
                for _change_type, change_path in changes:
                    # Resolve the agent directory from the changed file path
                    rel = Path(change_path).relative_to(self._agents_dir)
                    agent_dir_name = rel.parts[0] if rel.parts else None
                    if agent_dir_name and not agent_dir_name.startswith(("_", ".")):
                        affected_dirs.add(agent_dir_name)

                if affected_dirs:
                    logger.info(f"Agent directory changes detected: {affected_dirs}")
                    # Re-run discovery (will skip already-registered agents
                    # and pick up new ones)
                    try:
                        registered = self._discovery.discover_and_register()
                        logger.info(f"Re-discovery after change: {len(registered)} agents")
                    except Exception as e:
                        logger.error(f"Error during agent re-discovery: {e}")

        except asyncio.CancelledError:
            logger.debug("Agent directory watcher cancelled")
            raise
        except Exception as e:
            logger.error(f"Agent directory watcher error: {e}")
            self._running = False

# =============================================================================
# Global Watcher Management
# =============================================================================

_watcher: AgentDirectoryWatcher | None = None
_watcher_lock = threading.Lock()

def get_agent_watcher(agents_dir: str = "agents") -> AgentDirectoryWatcher:
    """Get or create global agent directory watcher.

    Args:
        agents_dir: Path to agents directory.

    Returns:
        Singleton AgentDirectoryWatcher instance.
    """
    global _watcher
    if _watcher is None:
        with _watcher_lock:
            if _watcher is None:
                discovery = AgentAutoDiscovery(agents_dir)
                _watcher = AgentDirectoryWatcher(agents_dir, discovery)
    return _watcher

async def start_agent_watcher(agents_dir: str = "agents") -> None:
    """Start the global agent directory watcher.

    Convenience function for application startup.
    """
    watcher = get_agent_watcher(agents_dir)
    await watcher.start()

async def stop_agent_watcher() -> None:
    """Stop the global agent directory watcher.

    Convenience function for application shutdown.
    """
    global _watcher
    if _watcher is not None:
        await _watcher.stop()
