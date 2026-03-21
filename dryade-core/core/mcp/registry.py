"""MCP Server Registry.

Central registry for MCP server instances providing lifecycle management,
health monitoring, tool routing, and graceful shutdown.

Features:
- Thread-safe server registration and discovery
- Server lifecycle management (start/stop/restart)
- Lazy start pattern: servers auto-start on first tool call
- Tool routing across multiple servers
- Health monitoring and status tracking
- Graceful shutdown with atexit handler

Usage:
    # Singleton pattern (convenience)
    from core.mcp import get_registry, MCPServerConfig

    registry = get_registry()
    config = MCPServerConfig(name="memory", command=["npx", "-y", "@modelcontextprotocol/server-memory"])
    registry.register(config)
    registry.start("memory")
    tools = registry.list_tools("memory")

    # Instance pattern (testing, isolation)
    from core.mcp import MCPRegistry

    registry = MCPRegistry()
    # ... configure and use
"""

from __future__ import annotations

import asyncio
import atexit
import contextlib
import logging
import threading
import time
from typing import Any

# Import from unified exception hierarchy
from core.exceptions import MCPRegistryError
from core.mcp.capability_cache import get_capability_cache
from core.mcp.config import MCPServerConfig, MCPServerTransport, load_config
from core.mcp.credentials import get_credential_manager
from core.mcp.hierarchical_router import get_hierarchical_router
from core.mcp.http_transport import HttpSseTransport
from core.mcp.protocol import MCPTool, MCPToolCallResult
from core.mcp.stdio_transport import MCPServerStatus, StdioTransport
from core.mcp.tool_index import DetailLevel
from core.observability.metrics import update_mcp_server_status

logger = logging.getLogger(__name__)

# MCPRegistryError is imported from core.exceptions for backward compatibility

class MCPRegistry:
    """Central registry for MCP server instances.

    Manages server configurations, lifecycles, and tool routing.
    Provides both sync and async APIs for server management.

    Usage:
        # Singleton pattern (convenience)
        registry = get_registry()

        # Instance pattern (testing, isolation)
        registry = MCPRegistry()

    Attributes:
        _configs: Registered server configurations by name.
        _transports: Active transport instances by server name.
        _lock: Thread lock for safe concurrent access.
        _shutdown_registered: Whether atexit handler is registered.
    """

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._configs: dict[str, MCPServerConfig] = {}
        self._transports: dict[str, StdioTransport | HttpSseTransport] = {}
        self._start_times: dict[str, float] = {}  # Track server start times for cache invalidation
        self._lock = threading.RLock()
        self._shutdown_registered = False

    # ========================================================================
    # Server Registration
    # ========================================================================

    def register(self, config: MCPServerConfig) -> None:
        """Register an MCP server configuration.

        Does NOT auto-start the server. Use start() or call_tool() (lazy start)
        to begin the server process.

        Args:
            config: Server configuration to register.

        Raises:
            MCPRegistryError: If a server with the same name is already registered.

        Example:
            >>> registry = MCPRegistry()
            >>> config = MCPServerConfig(name="memory", command=["npx", "-y", "@modelcontextprotocol/server-memory"])
            >>> registry.register(config)
            >>> registry.is_registered("memory")
            True
        """
        with self._lock:
            if config.name in self._configs:
                raise MCPRegistryError(f"Server '{config.name}' is already registered")
            self._configs[config.name] = config
            logger.debug(f"Registered MCP server: {config.name}")

    def register_from_dict(self, data: dict[str, Any]) -> None:
        """Register a server from a dictionary configuration.

        Parses the dictionary using load_config() and registers the result.

        Args:
            data: Dictionary containing server configuration.

        Raises:
            MCPRegistryError: If server already registered.
            pydantic.ValidationError: If configuration is invalid.

        Example:
            >>> registry = MCPRegistry()
            >>> registry.register_from_dict({
            ...     "name": "memory",
            ...     "command": ["npx", "-y", "@modelcontextprotocol/server-memory"]
            ... })
        """
        config = load_config(data)
        self.register(config)

    def unregister(self, name: str) -> None:
        """Unregister a server by name.

        If the server is running, it will be stopped first.
        Handles both STDIO and HTTP transports appropriately.

        Args:
            name: Name of the server to unregister.

        Raises:
            MCPRegistryError: If server is not registered.

        Example:
            >>> registry = MCPRegistry()
            >>> registry.register(config)
            >>> registry.unregister("memory")
            >>> registry.is_registered("memory")
            False
        """
        with self._lock:
            if name not in self._configs:
                raise MCPRegistryError(f"Server '{name}' is not registered")

            # Stop if running
            if name in self._transports:
                try:
                    transport = self._transports[name]
                    if isinstance(transport, StdioTransport):
                        transport.stop()
                    elif isinstance(transport, HttpSseTransport):
                        transport.close_sync()
                except Exception as e:
                    logger.warning(f"Error stopping server '{name}' during unregister: {e}")
                del self._transports[name]
                if name in self._start_times:
                    del self._start_times[name]

            # Invalidate cache on unregister
            get_capability_cache().invalidate(name)
            del self._configs[name]
            logger.debug(f"Unregistered MCP server: {name}")

    def is_registered(self, name: str) -> bool:
        """Check if a server is registered.

        Args:
            name: Server name to check.

        Returns:
            True if server is registered, False otherwise.
        """
        return name in self._configs

    # ========================================================================
    # Server Discovery
    # ========================================================================

    def list_servers(self) -> list[str]:
        """List all registered server names.

        Returns:
            List of registered server names.

        Example:
            >>> registry = MCPRegistry()
            >>> registry.register(config1)
            >>> registry.register(config2)
            >>> registry.list_servers()
            ['memory', 'filesystem']
        """
        return list(self._configs.keys())

    def get_config(self, name: str) -> MCPServerConfig:
        """Get configuration for a registered server.

        Args:
            name: Server name.

        Returns:
            Server configuration.

        Raises:
            MCPRegistryError: If server is not registered.
        """
        if name not in self._configs:
            raise MCPRegistryError(f"Server '{name}' is not registered")
        return self._configs[name]

    # ========================================================================
    # Transport Factory
    # ========================================================================

    def _create_transport(self, config: MCPServerConfig) -> StdioTransport | HttpSseTransport:
        """Create appropriate transport based on config.transport type.

        For STDIO transport, creates a StdioTransport with subprocess management.
        For HTTP transport, creates an HttpSseTransport with credential integration.

        Args:
            config: Server configuration specifying transport type and settings.

        Returns:
            StdioTransport for STDIO config, HttpSseTransport for HTTP config.

        Raises:
            MCPRegistryError: If transport type is unsupported.

        Example:
            >>> config = MCPServerConfig(
            ...     name="remote-server",
            ...     command=[],
            ...     transport=MCPServerTransport.HTTP,
            ...     url="https://api.example.com/mcp",
            ... )
            >>> transport = registry._create_transport(config)
            >>> isinstance(transport, HttpSseTransport)
            True
        """
        if config.transport == MCPServerTransport.STDIO:
            return StdioTransport(
                command=config.command,
                timeout=config.timeout,
                startup_delay=config.startup_delay,
                env=config.expand_env_vars(),
                auto_restart=config.auto_restart,
                max_restarts=config.max_restarts,
            )
        elif config.transport == MCPServerTransport.HTTP:
            # Build headers with credentials if service configured
            headers = dict(config.headers)

            if config.credential_service:
                manager = get_credential_manager()
                creds = manager.get_credentials(config.credential_service)
                if creds:
                    auth_headers = config.get_auth_headers(creds)
                    headers.update(auth_headers)
                else:
                    logger.warning(
                        "No credentials found for service '%s' - "
                        "server '%s' may fail on first request",
                        config.credential_service,
                        config.name,
                    )

            return HttpSseTransport(
                url=config.url,  # type: ignore[arg-type]
                headers=headers,
                timeout=config.timeout,
            )
        else:
            raise MCPRegistryError(f"Unsupported transport type: {config.transport}")

    # ========================================================================
    # Server Lifecycle Management (Sync API)
    # ========================================================================

    def start(self, name: str) -> None:
        """Start a registered MCP server.

        Blocks until the server is ready for requests.
        Does NOT auto-start on registration; this method must be called
        explicitly, or the server will be lazy-started on first call_tool().

        Supports both STDIO (subprocess) and HTTP (remote SSE) transports.
        Registers an atexit handler on first start to ensure cleanup.

        Args:
            name: Name of the server to start.

        Raises:
            MCPRegistryError: If server is not registered or already running.
            MCPTransportError: If server fails to start.
        """
        with self._lock:
            config = self.get_config(name)

            if name in self._transports and self._transports[name].is_alive:
                logger.debug(f"Server '{name}' is already running")
                return

            # Create transport from config using factory
            transport = self._create_transport(config)

            # Start and initialize based on transport type
            if isinstance(transport, StdioTransport):
                transport.start()
                transport.initialize()
            elif isinstance(transport, HttpSseTransport):
                # HTTP transport uses async connect, run synchronously
                transport.connect_sync()

            self._transports[name] = transport
            self._start_times[name] = time.time()  # Track start time for cache invalidation
            logger.info(f"Started MCP server: {name}")
            update_mcp_server_status(name, MCPServerStatus.HEALTHY.value)

            # Register atexit handler (once)
            if not self._shutdown_registered:
                atexit.register(self.shutdown)
                self._shutdown_registered = True

    def stop(self, name: str) -> None:
        """Stop a running MCP server.

        Handles both STDIO and HTTP transports appropriately.

        Args:
            name: Name of the server to stop.

        Raises:
            MCPRegistryError: If server is not registered or not running.
        """
        with self._lock:
            if name not in self._configs:
                raise MCPRegistryError(f"Server '{name}' is not registered")

            if name not in self._transports:
                raise MCPRegistryError(f"Server '{name}' is not running")

            transport = self._transports[name]
            if isinstance(transport, StdioTransport):
                transport.stop()
            elif isinstance(transport, HttpSseTransport):
                transport.close_sync()
            del self._transports[name]
            if name in self._start_times:
                del self._start_times[name]
            # Invalidate cache on stop
            get_capability_cache().invalidate(name)
            logger.info(f"Stopped MCP server: {name}")
            update_mcp_server_status(name, MCPServerStatus.STOPPED.value)

    def is_running(self, name: str) -> bool:
        """Check if a server is currently running.

        Args:
            name: Server name to check.

        Returns:
            True if server is running and alive, False otherwise.
        """
        if name not in self._transports:
            return False
        return self._transports[name].is_alive

    def get_status(self, name: str) -> MCPServerStatus:
        """Get the current status of a server.

        Args:
            name: Server name.

        Returns:
            MCPServerStatus enum value.

        Raises:
            MCPRegistryError: If server is not registered.
        """
        if name not in self._configs:
            raise MCPRegistryError(f"Server '{name}' is not registered")

        if name not in self._transports:
            return MCPServerStatus.STOPPED

        return self._transports[name].status

    def start_all(self) -> dict[str, Exception | None]:
        """Start all registered servers that are enabled.

        Continues on individual failures for graceful degradation.

        Returns:
            Dict mapping server name to exception (None if success).

        Example:
            >>> results = registry.start_all()
            >>> for name, error in results.items():
            ...     if error:
            ...         print(f"Failed to start {name}: {error}")
        """
        results: dict[str, Exception | None] = {}

        for name, config in self._configs.items():
            if not config.enabled:
                logger.debug(f"Skipping disabled server: {name}")
                continue

            try:
                self.start(name)
                results[name] = None
            except Exception as e:
                logger.error(f"Failed to start server '{name}': {e}")
                results[name] = e

        return results

    def shutdown(self) -> None:
        """Stop all running servers gracefully.

        Called automatically via atexit handler, but can be called manually.
        Handles both STDIO and HTTP transports appropriately.
        Logs errors but continues stopping all servers.
        """
        logger.debug("Shutting down MCP registry...")

        # Get list of running servers (copy to avoid modification during iteration)
        with self._lock:
            running_servers = list(self._transports.keys())

        for name in running_servers:
            try:
                with self._lock:
                    if name in self._transports:
                        transport = self._transports[name]
                        if isinstance(transport, StdioTransport):
                            transport.stop()
                        elif isinstance(transport, HttpSseTransport):
                            transport.close_sync()
                        del self._transports[name]
                        logger.debug(f"Stopped server '{name}' during shutdown")
            except Exception as e:
                logger.warning(f"Error stopping server '{name}' during shutdown: {e}")

        logger.debug("MCP registry shutdown complete")

    # ========================================================================
    # Tool Routing (with Lazy Start)
    # ========================================================================

    def list_tools(self, server: str) -> list[MCPTool]:
        """List available tools from a server.

        Auto-starts the server if registered but not running (lazy start).
        Uses capability cache to avoid repeated fetches from the same server.

        Args:
            server: Server name.

        Returns:
            List of MCPTool definitions.

        Raises:
            MCPRegistryError: If server is not registered.
        """
        # Validate server is registered
        self.get_config(server)

        # Lazy start if not running
        if not self.is_running(server):
            logger.info(f"Auto-starting MCP server '{server}' for list_tools")
            self.start(server)

        # Check cache first (with restart detection)
        cache = get_capability_cache()
        start_time = self._start_times.get(server)
        cached = cache.get(server, server_start_time=start_time)
        if cached is not None:
            return cached

        # Cache miss - fetch from transport
        tools = self._transports[server].list_tools()

        # Cache result with server start time for restart detection
        cache.set(server, tools, server_start_time=start_time)

        return tools

    def list_all_tools(self) -> dict[str, list[MCPTool]]:
        """List tools from all currently running servers.

        Note: Only includes tools from running servers.
        Does not auto-start all servers (would be too aggressive).

        Returns:
            Dict mapping server name to list of tools.
        """
        result: dict[str, list[MCPTool]] = {}

        for name in self._transports:
            if self.is_running(name):
                try:
                    result[name] = self._transports[name].list_tools()
                except Exception as e:
                    logger.warning(f"Failed to list tools from '{name}': {e}")
                    result[name] = []

        return result

    def call_tool(
        self,
        server: str,
        tool: str,
        arguments: dict[str, Any] | None = None,
    ) -> MCPToolCallResult:
        """Execute a tool on a specific server.

        Auto-starts the server if registered but not running (lazy start).
        Logs an info message when auto-starting.

        Args:
            server: Server name.
            tool: Tool name.
            arguments: Optional arguments for the tool.

        Returns:
            MCPToolCallResult with the tool output.

        Raises:
            MCPRegistryError: If server is not registered.
            MCPTransportError: If tool call fails.
        """
        # Validate server is registered
        self.get_config(server)

        # Lazy start if not running
        if not self.is_running(server):
            logger.info(f"Auto-starting MCP server '{server}' for tool call")
            self.start(server)

        transport = self._transports[server]
        return transport.call_tool(tool, arguments)

    def find_tool(self, tool_name: str) -> tuple[str, MCPTool] | None:
        """Find which server provides a tool by name.

        Searches only running servers. Does not auto-start.

        Args:
            tool_name: Name of the tool to find.

        Returns:
            Tuple of (server_name, MCPTool) if found, None otherwise.
        """
        for server_name, transport in self._transports.items():
            if not transport.is_alive:
                continue

            try:
                tools = transport.list_tools()
                for tool in tools:
                    if tool.name == tool_name:
                        return (server_name, tool)
            except Exception as e:
                logger.warning(f"Failed to search tools in '{server_name}': {e}")

        return None

    def call_tool_by_name(
        self,
        tool: str,
        arguments: dict[str, Any] | None = None,
    ) -> MCPToolCallResult:
        """Execute a tool, auto-routing to the server that provides it.

        Note: Requires server to be running (searches running servers only).

        Args:
            tool: Tool name.
            arguments: Optional arguments for the tool.

        Returns:
            MCPToolCallResult with the tool output.

        Raises:
            MCPRegistryError: If tool is not found in any running server.
            MCPTransportError: If tool call fails.
        """
        result = self.find_tool(tool)
        if result is None:
            raise MCPRegistryError(f"Tool '{tool}' not found in any running server")

        server_name, _ = result
        return self.call_tool(server_name, tool, arguments)

    def search_tools(
        self,
        query: str,
        server_filter: str | None = None,
        top_k: int = 10,
        detail: str = "summary",
    ) -> list[dict[str, Any]]:
        """Search for tools using hierarchical routing.

        Combines semantic search (if embeddings available) with index-based
        regex search for efficient tool discovery across 1000+ tools.

        Args:
            query: Natural language query describing desired tool
            server_filter: Optional server name to restrict search
            top_k: Maximum number of results
            detail: Detail level - "name_only", "summary" (default), or "full"

        Returns:
            List of tool info dicts with name, server, score, and description.
            Detail level controls response size:
            - name_only: {name, server} only
            - summary: {name, server, description, score}
            - full: includes params and fingerprint

        Example:
            >>> registry = get_registry()
            >>> results = registry.search_tools("edit model elements")
            >>> for r in results:
            ...     print(f"{r['name']} ({r['server']}): {r['score']:.2f}")
        """
        router = get_hierarchical_router()

        if server_filter:
            route_results = router.route_to_server(query, server_filter, top_k)
        else:
            route_results = router.route(query, top_k)

        # Convert to output format based on detail level
        detail_enum = (
            DetailLevel(detail) if detail in [d.value for d in DetailLevel] else DetailLevel.SUMMARY
        )

        results = []
        for r in route_results:
            result_dict: dict[str, Any] = {
                "name": r.tool_name,
                "server": r.server,
            }

            if detail_enum != DetailLevel.NAME_ONLY:
                result_dict.update(
                    {
                        "description": r.description,
                        "score": round(r.score, 4),
                    }
                )

            if detail_enum == DetailLevel.FULL:
                result_dict.update(
                    {
                        "server_score": round(r.server_score, 4),
                        "tool_score": round(r.tool_score, 4),
                    }
                )

            results.append(result_dict)

        return results

    def validate_tool(
        self,
        tool_name: str,
        suggest_similar: bool = True,
    ) -> tuple[bool, str | None, list[str]]:
        """Validate tool exists with 'did you mean?' suggestions.

        Args:
            tool_name: Tool name to validate
            suggest_similar: Whether to suggest similar tools if not found

        Returns:
            Tuple of (exists, server_name, suggestions)
            - exists: True if tool found
            - server_name: Server providing tool, or None
            - suggestions: Similar tool names if not found

        Example:
            >>> registry = get_registry()
            >>> exists, server, suggestions = registry.validate_tool("search_fles")
            >>> if not exists:
            ...     print(f"Tool not found. Did you mean: {suggestions}")
        """
        # Check if tool exists
        result = self.find_tool(tool_name)
        if result:
            server_name, _ = result
            return (True, server_name, [])

        # Tool not found - generate suggestions
        suggestions = []
        if suggest_similar:
            # Search for similar tools
            search_results = self.search_tools(
                tool_name,
                top_k=5,
                detail="name_only",
            )
            suggestions = [r["name"] for r in search_results]

        return (False, None, suggestions)

    # ========================================================================
    # Health Monitoring
    # ========================================================================

    def get_health_summary(self) -> dict[str, Any]:
        """Get health summary for all servers.

        Returns data compatible with Health Monitoring plugin integration.

        Returns:
            Dict with structure:
            {
                "servers": {
                    "name": {
                        "status": "healthy",
                        "restart_count": 0,
                        "tool_count": 5
                    }
                },
                "total_registered": 3,
                "total_running": 2,
                "total_healthy": 2
            }
        """
        # Update Prometheus gauges when health is queried
        self.update_server_metrics()

        servers: dict[str, dict[str, Any]] = {}

        for name in self._configs:
            transport = self._transports.get(name)

            if transport is None:
                servers[name] = {
                    "status": MCPServerStatus.STOPPED.value,
                    "restart_count": 0,
                    "tool_count": 0,
                }
            else:
                tool_count = 0
                if transport.is_alive:
                    with contextlib.suppress(Exception):
                        tool_count = len(transport.list_tools())

                servers[name] = {
                    "status": transport.status.value,
                    "restart_count": transport._restart_count,
                    "tool_count": tool_count,
                }

        total_running = sum(1 for name in self._transports if self._transports[name].is_alive)
        total_healthy = sum(
            1 for name, t in self._transports.items() if t.status == MCPServerStatus.HEALTHY
        )

        return {
            "servers": servers,
            "total_registered": len(self._configs),
            "total_running": total_running,
            "total_healthy": total_healthy,
        }

    def check_health(self, name: str) -> bool:
        """Check if a specific server is healthy.

        Args:
            name: Server name.

        Returns:
            True if server is running and healthy, False otherwise.
        """
        if name not in self._transports:
            return False

        return self._transports[name].status == MCPServerStatus.HEALTHY

    def update_server_metrics(self) -> None:
        """Update Prometheus metrics for all registered servers.

        Call this periodically or after status changes to keep Prometheus gauges current.
        """
        for name in self._configs:
            transport = self._transports.get(name)

            if transport is None:
                update_mcp_server_status(name, "stopped")
            else:
                update_mcp_server_status(name, transport.status.value)

    # ========================================================================
    # Async Variants
    # ========================================================================

    async def astart(self, name: str) -> None:
        """Async variant: Start a registered MCP server.

        Args:
            name: Name of the server to start.
        """
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.start, name)

    async def astop(self, name: str) -> None:
        """Async variant: Stop a running MCP server.

        Args:
            name: Name of the server to stop.
        """
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.stop, name)

    async def astart_all(self) -> dict[str, Exception | None]:
        """Async variant: Start all enabled servers concurrently.

        Returns:
            Dict mapping server name to exception (None if success).
        """
        enabled_servers = [name for name, config in self._configs.items() if config.enabled]

        if not enabled_servers:
            return {}

        async def start_server(name: str) -> tuple[str, Exception | None]:
            try:
                await self.astart(name)
                return (name, None)
            except Exception as e:
                logger.error(f"Failed to start server '{name}': {e}")
                return (name, e)

        results = await asyncio.gather(*[start_server(name) for name in enabled_servers])

        return dict(results)

    async def ashutdown(self) -> None:
        """Async variant: Stop all running servers."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.shutdown)

    async def acall_tool(
        self,
        server: str,
        tool: str,
        arguments: dict[str, Any] | None = None,
    ) -> MCPToolCallResult:
        """Async variant: Execute a tool on a server.

        Auto-starts the server if not running (lazy start).

        Args:
            server: Server name.
            tool: Tool name.
            arguments: Optional arguments for the tool.

        Returns:
            MCPToolCallResult with the tool output.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.call_tool, server, tool, arguments)

# ============================================================================
# Global Registry (Singleton)
# ============================================================================

_registry: MCPRegistry | None = None

def get_registry() -> MCPRegistry:
    """Get the global MCP registry instance (singleton).

    For testing or isolation, create MCPRegistry() directly instead.

    Returns:
        The global MCPRegistry instance.

    Example:
        >>> registry = get_registry()
        >>> registry.register(config)
    """
    global _registry
    if _registry is None:
        _registry = MCPRegistry()
    return _registry

def reset_registry() -> None:
    """Reset the global registry (for testing).

    Shuts down any running servers and clears the singleton.
    """
    global _registry
    if _registry is not None:
        _registry.shutdown()
    _registry = None
