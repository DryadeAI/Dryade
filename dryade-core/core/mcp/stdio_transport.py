"""Stdio Transport for MCP Servers.

Provides a transport layer for communicating with local MCP servers
via stdin/stdout using JSON-RPC 2.0 protocol.

Features:
- JSON-RPC 2.0 communication over stdin/stdout
- Server health status tracking (STOPPED/STARTING/HEALTHY/UNHEALTHY/CRASHED)
- Auto-restart on server crash (configurable)
- Retry logic for transient failures (configurable)
- Graceful degradation when server unresponsive

Example usage:
    with StdioTransport(['npx', '-y', '@modelcontextprotocol/server-memory']) as transport:
        result = transport.initialize()
        print(f"Connected to: {result.serverInfo.name}")
        print(f"Status: {transport.status}")
        tools = transport.list_tools()
        for tool in tools:
            print(f"  - {tool.name}: {tool.description}")

    # With resilience features:
    transport = StdioTransport(
        ['npx', '-y', '@modelcontextprotocol/server-memory'],
        auto_restart=True,
        max_restarts=3,
        max_retries=2,
    )
"""

from __future__ import annotations

import json
import logging
import os
import select
import subprocess
import threading
import time
from enum import Enum
from queue import Empty, Queue
from typing import Any

# Import from unified exception hierarchy
from core.exceptions import MCPTimeoutError, MCPTransportError
from core.mcp.protocol import (
    MCPErrorCode,
    MCPInitializeResult,
    MCPPrompt,
    MCPPromptsListResult,
    MCPResource,
    MCPResourceContents,
    MCPResourcesListResult,
    MCPServerCapabilities,
    MCPServerInfo,
    MCPTool,
    MCPToolCallContent,
    MCPToolCallResult,
    MCPToolInputSchema,
    MCPToolsListResult,
)

logger = logging.getLogger(__name__)

class MCPServerStatus(str, Enum):
    """Status of an MCP server process.

    Tracks the lifecycle state of the server for health monitoring
    and resilience features.
    """

    STOPPED = "stopped"  # Not running
    STARTING = "starting"  # Process started, waiting for initialize
    HEALTHY = "healthy"  # Running and responsive
    UNHEALTHY = "unhealthy"  # Running but not responding
    CRASHED = "crashed"  # Process exited unexpectedly

# MCPTransportError and MCPTimeoutError are imported from core.exceptions
# for backward compatibility

class StdioTransport:
    """Transport for communicating with MCP servers via stdio.

    Uses JSON-RPC 2.0 protocol over stdin/stdout for bidirectional
    communication with local MCP server processes.

    Handles server-initiated requests (like roots/list) automatically.

    Args:
        command: Command line to start the MCP server process.
        timeout: Default timeout for requests in seconds.
        startup_delay: Time to wait after starting server before initialize.
        env: Additional environment variables for the server process.
    """

    def __init__(
        self,
        command: list[str],
        timeout: float = float(os.getenv("DRYADE_MCP_TIMEOUT", "120")),
        startup_delay: float = 2.0,
        env: dict[str, str] | None = None,
        auto_restart: bool = False,
        max_restarts: int = 3,
        restart_delay: float = 1.0,
        max_retries: int = 2,
        retry_delay: float = 0.5,
    ):
        self.command = command
        self.timeout = timeout
        self.startup_delay = startup_delay
        self.env = env or {}

        # Resilience configuration
        self.auto_restart = auto_restart
        self.max_restarts = max_restarts
        self.restart_delay = restart_delay
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        self._process: subprocess.Popen | None = None
        self._message_id = 0
        self._pending_responses: dict[int | str, Queue] = {}
        self._reader_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._running = False
        self._lock = threading.Lock()

        # Server status tracking
        self._status: MCPServerStatus = MCPServerStatus.STOPPED
        self._restart_count: int = 0
        self._last_health_check: float | None = None
        self._consecutive_failures: int = 0

        # Server info from initialize
        self.server_info: MCPServerInfo | None = None
        self.capabilities: MCPServerCapabilities | None = None
        self.protocol_version: str = ""

    @property
    def status(self) -> MCPServerStatus:
        """Get the current status of the server.

        Checks if the process is still alive before returning status.
        If status was HEALTHY or STARTING but process died, returns CRASHED.
        """
        # Check if process is still running
        if (
            self._process is not None
            and self._process.poll() is not None
            and self._status in (MCPServerStatus.HEALTHY, MCPServerStatus.STARTING)
        ):
            # Process exited unexpectedly
            self._status = MCPServerStatus.CRASHED
        return self._status

    @property
    def is_alive(self) -> bool:
        """Check if the server process is currently running.

        Returns:
            True if the process exists and is running, False otherwise.
        """
        if self._process is None:
            return False
        return self._process.poll() is None

    def __enter__(self) -> StdioTransport:
        """Start the transport as a context manager."""
        self.start()
        self.initialize()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Stop the transport when exiting context."""
        self.stop()

    def _next_id(self) -> int:
        """Generate the next message ID."""
        with self._lock:
            self._message_id += 1
            return self._message_id

    def start(self) -> None:
        """Start the MCP server process."""
        if self._process is not None:
            raise MCPTransportError("Transport already started")

        # Build environment
        process_env = {**os.environ, **self.env}
        process_env["NODE_OPTIONS"] = "--no-warnings"

        try:
            logger.debug(f"Starting MCP server: {' '.join(self.command)}")
            self._status = MCPServerStatus.STARTING
            self._process = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # Line buffered
                env=process_env,
            )

            self._running = True

            # Start background reader thread
            self._reader_thread = threading.Thread(
                target=self._reader_loop,
                daemon=True,
            )
            self._reader_thread.start()

            # Start stderr drain thread to prevent buffer deadlock
            self._stderr_thread = threading.Thread(
                target=self._stderr_drain_loop,
                daemon=True,
            )
            self._stderr_thread.start()

            # Wait for server to be ready
            time.sleep(self.startup_delay)

            # Check if process crashed during startup
            if self._process.poll() is not None:
                stderr = self._process.stderr.read() if self._process.stderr else ""
                self._status = MCPServerStatus.CRASHED
                raise MCPTransportError(f"Server process exited during startup: {stderr}")

        except FileNotFoundError as e:
            self._status = MCPServerStatus.STOPPED
            raise MCPTransportError(f"Command not found: {self.command[0]}") from e
        except MCPTransportError:
            # Re-raise transport errors without wrapping
            raise
        except Exception as e:
            self._running = False
            self._status = MCPServerStatus.STOPPED
            if self._process:
                self._process.terminate()
                self._process = None
            raise MCPTransportError(f"Failed to start server: {e}") from e

    def stop(self) -> None:
        """Stop the MCP server process."""
        self._running = False

        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()
            finally:
                self._process = None

        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=1.0)

        if self._stderr_thread and self._stderr_thread.is_alive():
            self._stderr_thread.join(timeout=1.0)

        self._status = MCPServerStatus.STOPPED

    def _check_and_restart(self) -> None:
        """Check if the server has crashed and attempt restart if enabled.

        Called at the start of send_request() to ensure the server is running.

        Raises:
            MCPTransportError: If server crashed and max restarts exceeded,
                or if auto_restart is disabled.
        """
        if self._process is None:
            raise MCPTransportError("Transport not started")

        # Check if process is still running
        if self._process.poll() is None:
            return  # Process is alive, nothing to do

        # Process has crashed
        logger.warning(f"MCP server process crashed (exit code: {self._process.returncode})")
        self._status = MCPServerStatus.CRASHED

        if not self.auto_restart:
            raise MCPTransportError("Server process crashed")

        if self._restart_count >= self.max_restarts:
            raise MCPTransportError(f"Server crashed, max restarts ({self.max_restarts}) exceeded")

        # Attempt restart
        self._restart_count += 1
        logger.warning(
            f"Auto-restarting MCP server (attempt {self._restart_count}/{self.max_restarts})"
        )

        # Clean up and restart
        self.stop()
        time.sleep(self.restart_delay)
        self.start()
        self.initialize()

        # Reset consecutive failures after successful restart
        self._consecutive_failures = 0

    def restart(self) -> None:
        """Manually restart the server process.

        Stops the current process (if running) and starts a fresh one.
        Resets the restart counter.
        """
        logger.info("Manually restarting MCP server")
        self._restart_count = 0
        self.stop()
        self.start()
        self.initialize()

    def reset_restart_count(self) -> None:
        """Reset the restart counter.

        Can be used by external code (e.g., registry) to reset the counter
        after scheduled maintenance or health checks.
        """
        self._restart_count = 0

    def _reader_loop(self) -> None:
        """Background loop that reads responses from the server."""
        if not self._process or not self._process.stdout:
            return

        while self._running:
            try:
                # Use select with timeout to allow checking _running flag
                ready, _, _ = select.select([self._process.stdout], [], [], 0.1)
                if not ready:
                    continue

                line = self._process.stdout.readline()
                if not line:
                    # Process closed stdout
                    break

                line = line.strip()
                if not line:
                    continue
                # Filter non-JSON lines (e.g., npx download banners, npm progress)
                if not line.startswith("{"):
                    logger.debug(f"Skipping non-JSON line from server: {line[:120]}")
                    continue

                try:
                    message = json.loads(line)
                    self._handle_message(message)
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse JSON from server: {e}")
                    continue

            except Exception as e:
                if self._running:
                    logger.error(f"Reader loop error: {e}")
                break

    def _stderr_drain_loop(self) -> None:
        """Drain stderr from the server process to prevent buffer deadlock.

        Reads stderr line by line and logs at debug level.
        If the buffer fills (64KB default), the server process blocks on writes,
        causing a deadlock. This thread prevents that.
        """
        try:
            while self._running and self._process and self._process.stderr:
                line = self._process.stderr.readline()
                if not line:
                    break
                line = line.strip()
                if line:
                    logger.debug(f"MCP server stderr: {line}")
        except Exception:
            # Best effort -- don't crash the drain thread
            pass

    def _handle_message(self, message: dict) -> None:
        """Handle an incoming message from the server."""
        # Check if this is a server-initiated request (has method, no result)
        if "method" in message and "result" not in message:
            self._handle_server_request(message)
            return

        # This is a response to one of our requests
        msg_id = message.get("id")
        if msg_id is not None and msg_id in self._pending_responses:
            queue = self._pending_responses[msg_id]
            queue.put(message)

    def _handle_server_request(self, message: dict) -> None:
        """Handle a request initiated by the server."""
        method = message.get("method", "")
        request_id = message.get("id")

        logger.debug(f"Server request: {method}")

        response: dict

        if method == "roots/list":
            # Return empty roots list
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"roots": []},
            }

        elif method == "sampling/createMessage":
            # We don't support sampling
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": MCPErrorCode.METHOD_NOT_FOUND,
                    "message": "Sampling not supported",
                },
            }

        else:
            # Unknown method
            logger.warning(f"Unknown server request method: {method}")
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": MCPErrorCode.METHOD_NOT_FOUND,
                    "message": f"Method not supported: {method}",
                },
            }

        self._send_raw(response)

    def _send_raw(self, message: dict) -> None:
        """Send a raw JSON-RPC message without waiting for response."""
        if not self._process or not self._process.stdin:
            raise MCPTransportError("Transport not started")

        try:
            msg_str = json.dumps(message)
            logger.debug(f">>> {msg_str[:200]}...")
            self._process.stdin.write(msg_str + "\n")
            self._process.stdin.flush()
        except Exception as e:
            raise MCPTransportError(f"Failed to send message: {e}") from e

    def _is_retryable_error(self, error: Exception) -> bool:
        """Determine if an error is transient and can be retried.

        Args:
            error: The exception that occurred.

        Returns:
            True if the error is transient and should be retried.
        """
        # Timeout errors are retryable
        if isinstance(error, MCPTimeoutError):
            return True

        # Transport errors with INTERNAL_ERROR that look like pipe issues
        if isinstance(error, MCPTransportError):
            # Non-retryable error codes
            non_retryable_codes = {
                MCPErrorCode.METHOD_NOT_FOUND,
                MCPErrorCode.INVALID_PARAMS,
                MCPErrorCode.INVALID_REQUEST,
                MCPErrorCode.PARSE_ERROR,
            }
            if error.code in non_retryable_codes:
                return False

            # Check if it's a pipe/connection error (transient)
            error_msg = str(error).lower()
            if "pipe" in error_msg or "broken" in error_msg:
                return True

        return False

    def _send_request_no_retry(
        self,
        method: str,
        params: dict | None = None,
        timeout: float | None = None,
    ) -> dict:
        """Send a JSON-RPC request without retry logic.

        Used internally for operations that should not be retried
        (e.g., initialize handshake).

        Args:
            method: The RPC method name.
            params: Optional parameters for the method.
            timeout: Optional timeout override in seconds.

        Returns:
            The response result dictionary.

        Raises:
            MCPTransportError: If communication fails.
            MCPTimeoutError: If the request times out.
        """
        if not self._process:
            raise MCPTransportError("Transport not started")

        request_id = self._next_id()
        response_queue: Queue = Queue()

        # Register for response
        self._pending_responses[request_id] = response_queue

        try:
            # Build and send request
            request = {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
            }
            if params is not None:
                request["params"] = params

            self._send_raw(request)

            # Wait for response
            actual_timeout = timeout if timeout is not None else self.timeout
            try:
                response = response_queue.get(timeout=actual_timeout)
            except Empty:
                raise MCPTimeoutError(f"Timeout waiting for response to {method}") from None

            # Check for error
            if "error" in response:
                error = response["error"]
                raise MCPTransportError(
                    error.get("message", "Unknown error"),
                    error.get("code", MCPErrorCode.INTERNAL_ERROR),
                )

            return response.get("result", {})

        finally:
            # Clean up pending response
            self._pending_responses.pop(request_id, None)

    def send_request(
        self,
        method: str,
        params: dict | None = None,
        timeout: float | None = None,
    ) -> dict:
        """Send a JSON-RPC request and wait for the response.

        Includes auto-restart check and retry logic for transient failures.

        Args:
            method: The RPC method name.
            params: Optional parameters for the method.
            timeout: Optional timeout override in seconds.

        Returns:
            The response result dictionary.

        Raises:
            MCPTransportError: If communication fails after all retries.
            MCPTimeoutError: If the request times out after all retries.
        """
        # Check for crash and potentially auto-restart
        self._check_and_restart()

        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                result = self._send_request_no_retry(method, params, timeout)

                # Success - reset counters
                self._restart_count = 0
                self._consecutive_failures = 0
                self._last_health_check = time.time()

                return result

            except (MCPTransportError, MCPTimeoutError) as e:
                last_error = e
                self._consecutive_failures += 1

                # Check if we should retry
                if not self._is_retryable_error(e):
                    # Non-retryable error, raise immediately
                    raise

                if attempt < self.max_retries:
                    logger.warning(
                        f"Request to {method} failed (attempt {attempt + 1}/{self.max_retries + 1}): {e}"
                    )
                    time.sleep(self.retry_delay)

                    # Check for crash before retry
                    try:
                        self._check_and_restart()
                    except MCPTransportError:
                        # Can't restart, re-raise original error
                        raise last_error from None

        # All retries exhausted
        if last_error is not None:
            raise last_error
        raise MCPTransportError("Request failed after all retries")

    def send_notification(self, method: str, params: dict | None = None) -> None:
        """Send a JSON-RPC notification (no response expected).

        Args:
            method: The notification method name.
            params: Optional parameters for the notification.
        """
        notification = {
            "jsonrpc": "2.0",
            "method": method,
        }
        if params is not None:
            notification["params"] = params

        self._send_raw(notification)

    # ========================================================================
    # High-level MCP methods
    # ========================================================================

    def initialize(self) -> MCPInitializeResult:
        """Perform MCP initialization handshake.

        This must be called before using other methods.
        Sets status to HEALTHY on success, UNHEALTHY on failure.

        Returns:
            MCPInitializeResult with server info and capabilities.

        Raises:
            MCPTransportError: If handshake fails.
            MCPTimeoutError: If server doesn't respond.
        """
        params = {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "roots": {"listChanged": True},
                "sampling": {},
            },
            "clientInfo": {
                "name": "dryade-mcp-client",
                "version": "1.0.0",
            },
        }

        try:
            result = self._send_request_no_retry("initialize", params)
        except (MCPTransportError, MCPTimeoutError):
            self._status = MCPServerStatus.UNHEALTHY
            raise

        # Parse result into typed structure
        self.protocol_version = result.get("protocolVersion", "")

        server_info = result.get("serverInfo")
        if server_info:
            self.server_info = MCPServerInfo(
                name=server_info.get("name", ""),
                version=server_info.get("version", ""),
            )

        caps = result.get("capabilities", {})
        self.capabilities = MCPServerCapabilities(
            tools=caps.get("tools"),
            resources=caps.get("resources"),
            prompts=caps.get("prompts"),
            logging=caps.get("logging"),
        )

        # Send initialized notification
        self.send_notification("notifications/initialized")

        # Mark as healthy after successful handshake
        self._status = MCPServerStatus.HEALTHY
        self._last_health_check = time.time()

        return MCPInitializeResult(
            protocolVersion=self.protocol_version,
            capabilities=self.capabilities,
            serverInfo=self.server_info,
        )

    def list_tools(self) -> list[MCPTool]:
        """List available tools from the server.

        Returns:
            List of MCPTool definitions.
        """
        result = self.send_request("tools/list")
        tools_result = MCPToolsListResult(
            tools=[
                MCPTool(
                    name=t.get("name", ""),
                    description=t.get("description", ""),
                    inputSchema=MCPToolInputSchema(
                        type=t.get("inputSchema", {}).get("type", "object"),
                        properties=t.get("inputSchema", {}).get("properties", {}),
                        required=t.get("inputSchema", {}).get("required", []),
                    ),
                )
                for t in result.get("tools", [])
            ],
            nextCursor=result.get("nextCursor"),
        )
        return tools_result.tools

    def call_tool(self, name: str, arguments: dict | None = None) -> MCPToolCallResult:
        """Call a tool on the server.

        Args:
            name: The tool name.
            arguments: Arguments to pass to the tool.

        Returns:
            MCPToolCallResult with the tool output.
        """
        params = {"name": name}
        if arguments is not None:
            params["arguments"] = arguments

        result = self.send_request("tools/call", params)

        return MCPToolCallResult(
            content=[
                MCPToolCallContent(
                    type=c.get("type", "text"),
                    text=c.get("text"),
                    data=c.get("data"),
                    mimeType=c.get("mimeType"),
                )
                for c in result.get("content", [])
            ],
            isError=result.get("isError", False),
        )

    def list_resources(self) -> list[MCPResource]:
        """List available resources from the server.

        Returns:
            List of MCPResource definitions.
        """
        result = self.send_request("resources/list")
        resources_result = MCPResourcesListResult(
            resources=[
                MCPResource(
                    uri=r.get("uri", ""),
                    name=r.get("name", ""),
                    description=r.get("description", ""),
                    mimeType=r.get("mimeType"),
                )
                for r in result.get("resources", [])
            ],
            nextCursor=result.get("nextCursor"),
        )
        return resources_result.resources

    def read_resource(self, uri: str) -> MCPResourceContents:
        """Read a resource from the server.

        Args:
            uri: The resource URI.

        Returns:
            MCPResourceContents with the resource data.
        """
        result = self.send_request("resources/read", {"uri": uri})
        contents = result.get("contents", [{}])[0]

        return MCPResourceContents(
            uri=contents.get("uri", uri),
            mimeType=contents.get("mimeType"),
            text=contents.get("text"),
            blob=contents.get("blob"),
        )

    def list_prompts(self) -> list[MCPPrompt]:
        """List available prompts from the server.

        Returns:
            List of MCPPrompt definitions.
        """
        result = self.send_request("prompts/list")
        prompts_result = MCPPromptsListResult(
            prompts=[
                MCPPrompt(
                    name=p.get("name", ""),
                    description=p.get("description", ""),
                    arguments=p.get("arguments", []),
                )
                for p in result.get("prompts", [])
            ],
            nextCursor=result.get("nextCursor"),
        )
        return prompts_result.prompts

    def get_prompt(self, name: str, arguments: dict | None = None) -> dict:
        """Get a prompt from the server.

        Args:
            name: The prompt name.
            arguments: Arguments to fill the prompt template.

        Returns:
            Dict with 'description' and 'messages' keys.
        """
        params = {"name": name}
        if arguments is not None:
            params["arguments"] = arguments

        return self.send_request("prompts/get", params)
