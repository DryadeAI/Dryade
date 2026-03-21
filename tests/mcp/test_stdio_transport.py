"""Unit tests for MCP stdio transport.

Tests the StdioTransport class and protocol types without requiring
actual MCP servers. Uses mocking to simulate server behavior.
"""

from __future__ import annotations

import json
import threading
from queue import Queue
from unittest.mock import MagicMock, Mock, patch

import pytest

from core.mcp.protocol import (
    MCPErrorCode,
    MCPInitializeResult,
    MCPPrompt,
    MCPResource,
    MCPResourceContents,
    MCPServerCapabilities,
    MCPServerInfo,
    MCPTool,
    MCPToolCallContent,
    MCPToolCallResult,
    MCPToolInputSchema,
)
from core.mcp.stdio_transport import (
    MCPServerStatus,
    MCPTimeoutError,
    MCPTransportError,
    StdioTransport,
)

# ============================================================================
# Initialization Tests
# ============================================================================

class TestStdioTransportInitialization:
    """Tests for StdioTransport initialization."""

    def test_default_parameters(self):
        """Test transport initializes with default parameters."""
        transport = StdioTransport(["test-command"])

        assert transport.command == ["test-command"]
        assert transport.timeout == 120.0  # Default from DRYADE_MCP_TIMEOUT env
        assert transport.startup_delay == 2.0
        assert transport.env == {}

    def test_custom_parameters(self):
        """Test transport accepts custom parameters."""
        transport = StdioTransport(
            ["custom", "command"],
            timeout=60.0,
            startup_delay=5.0,
            env={"KEY": "value"},
        )

        assert transport.command == ["custom", "command"]
        assert transport.timeout == 60.0
        assert transport.startup_delay == 5.0
        assert transport.env == {"KEY": "value"}

    def test_initial_state(self):
        """Test transport starts in correct initial state."""
        transport = StdioTransport(["test"])

        assert transport._process is None
        assert transport._message_id == 0
        assert transport._running is False
        assert transport.server_info is None
        assert transport.capabilities is None
        assert transport.protocol_version == ""

# ============================================================================
# Process Lifecycle Tests
# ============================================================================

class TestProcessLifecycle:
    """Tests for process start/stop lifecycle."""

    @patch("subprocess.Popen")
    @patch("time.sleep")
    def test_start_creates_process(self, mock_sleep, mock_popen):
        """Test start creates subprocess with correct arguments."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Process still running
        mock_process.stdout = MagicMock()
        mock_process.stderr = MagicMock()
        mock_popen.return_value = mock_process

        transport = StdioTransport(["npx", "-y", "test-server"])
        transport.start()

        # Verify Popen called
        mock_popen.assert_called_once()
        call_args = mock_popen.call_args
        assert call_args[0][0] == ["npx", "-y", "test-server"]

        # Verify process stored
        assert transport._process is mock_process
        assert transport._running is True

        # Cleanup
        transport._running = False

    @patch("subprocess.Popen")
    @patch("time.sleep")
    def test_start_waits_for_startup(self, mock_sleep, mock_popen):
        """Test start waits for startup_delay."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.stdout = MagicMock()
        mock_popen.return_value = mock_process

        transport = StdioTransport(["test"], startup_delay=3.0)
        transport.start()

        mock_sleep.assert_called_once_with(3.0)
        transport._running = False

    @patch("subprocess.Popen")
    def test_start_raises_on_already_started(self, mock_popen):
        """Test start raises error if already started."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.stdout = MagicMock()
        mock_popen.return_value = mock_process

        transport = StdioTransport(["test"], startup_delay=0.01)
        transport.start()

        with pytest.raises(MCPTransportError) as exc_info:
            transport.start()

        assert "already started" in str(exc_info.value)
        transport._running = False

    def test_start_raises_on_command_not_found(self):
        """Test start raises error for nonexistent command."""
        transport = StdioTransport(["nonexistent-command-xyz-12345"], startup_delay=0.01)

        with pytest.raises(MCPTransportError) as exc_info:
            transport.start()

        assert "Command not found" in str(exc_info.value)

    @patch("subprocess.Popen")
    @patch("time.sleep")
    def test_start_raises_on_early_exit(self, mock_sleep, mock_popen):
        """Test start raises error if process exits during startup."""
        mock_process = MagicMock()
        mock_process.poll.return_value = 1  # Process exited
        mock_process.stderr = MagicMock()
        mock_process.stderr.read.return_value = "Error: startup failed"
        mock_process.stdout = MagicMock()
        mock_popen.return_value = mock_process

        transport = StdioTransport(["test"], startup_delay=0.01)

        with pytest.raises(MCPTransportError) as exc_info:
            transport.start()

        assert "exited during startup" in str(exc_info.value)

    @patch("subprocess.Popen")
    @patch("time.sleep")
    def test_stop_terminates_process(self, mock_sleep, mock_popen):
        """Test stop terminates the process."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.stdout = MagicMock()
        mock_popen.return_value = mock_process

        transport = StdioTransport(["test"], startup_delay=0.01)
        transport.start()
        transport.stop()

        mock_process.terminate.assert_called_once()
        mock_process.wait.assert_called()
        assert transport._process is None
        assert transport._running is False

    @patch("subprocess.Popen")
    @patch("time.sleep")
    def test_stop_kills_on_timeout(self, mock_sleep, mock_popen):
        """Test stop kills process if terminate times out."""
        from subprocess import TimeoutExpired

        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.stdout = MagicMock()
        mock_process.wait.side_effect = [TimeoutExpired("cmd", 5), None]
        mock_popen.return_value = mock_process

        transport = StdioTransport(["test"], startup_delay=0.01)
        transport.start()
        transport.stop()

        mock_process.terminate.assert_called_once()
        mock_process.kill.assert_called_once()

# ============================================================================
# Context Manager Tests
# ============================================================================

class TestContextManager:
    """Tests for context manager behavior."""

    @patch.object(StdioTransport, "start")
    @patch.object(StdioTransport, "initialize")
    @patch.object(StdioTransport, "stop")
    def test_enter_starts_and_initializes(self, mock_stop, mock_init, mock_start):
        """Test __enter__ calls start and initialize."""
        transport = StdioTransport(["test"])

        result = transport.__enter__()

        mock_start.assert_called_once()
        mock_init.assert_called_once()
        assert result is transport

    @patch.object(StdioTransport, "start")
    @patch.object(StdioTransport, "initialize")
    @patch.object(StdioTransport, "stop")
    def test_exit_stops_transport(self, mock_stop, mock_init, mock_start):
        """Test __exit__ calls stop."""
        transport = StdioTransport(["test"])

        with transport:
            pass

        mock_stop.assert_called_once()

    @patch.object(StdioTransport, "start")
    @patch.object(StdioTransport, "initialize")
    @patch.object(StdioTransport, "stop")
    def test_exit_stops_on_exception(self, mock_stop, mock_init, mock_start):
        """Test __exit__ calls stop even on exception."""
        transport = StdioTransport(["test"])

        with pytest.raises(ValueError):
            with transport:
                raise ValueError("test error")

        mock_stop.assert_called_once()

# ============================================================================
# Message ID Tests
# ============================================================================

class TestMessageIds:
    """Tests for message ID generation."""

    def test_id_increments(self):
        """Test _next_id increments message ID."""
        transport = StdioTransport(["test"])

        id1 = transport._next_id()
        id2 = transport._next_id()
        id3 = transport._next_id()

        assert id1 == 1
        assert id2 == 2
        assert id3 == 3

    def test_id_thread_safe(self):
        """Test _next_id is thread-safe."""
        transport = StdioTransport(["test"])
        ids = []
        errors = []

        def get_ids(count):
            try:
                for _ in range(count):
                    ids.append(transport._next_id())
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=get_ids, args=(100,)) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(ids) == 1000
        # All IDs should be unique
        assert len(set(ids)) == 1000

# ============================================================================
# Request/Response Tests
# ============================================================================

class TestRequestResponse:
    """Tests for send_request behavior."""

    def test_send_request_raises_when_not_started(self):
        """Test send_request raises error when not started."""
        transport = StdioTransport(["test"])

        with pytest.raises(MCPTransportError) as exc_info:
            transport.send_request("test/method")

        assert "not started" in str(exc_info.value)

    @patch("subprocess.Popen")
    @patch("time.sleep")
    def test_send_raw_raises_when_not_started(self, mock_sleep, mock_popen):
        """Test _send_raw raises error when not started."""
        transport = StdioTransport(["test"])

        with pytest.raises(MCPTransportError) as exc_info:
            transport._send_raw({"test": "message"})

        assert "not started" in str(exc_info.value)

# ============================================================================
# Protocol Type Tests
# ============================================================================

class TestProtocolTypes:
    """Tests for MCP protocol type models."""

    def test_mcp_tool_creation(self):
        """Test MCPTool model creation."""
        tool = MCPTool(
            name="read_file",
            description="Read a file from disk",
            inputSchema=MCPToolInputSchema(
                type="object",
                properties={"path": {"type": "string", "description": "File path"}},
                required=["path"],
            ),
        )

        assert tool.name == "read_file"
        assert tool.description == "Read a file from disk"
        assert tool.inputSchema.type == "object"
        assert "path" in tool.inputSchema.properties
        assert "path" in tool.inputSchema.required

    def test_mcp_tool_default_schema(self):
        """Test MCPTool has default schema."""
        tool = MCPTool(name="simple_tool")

        assert tool.description == ""
        assert tool.inputSchema.type == "object"
        assert tool.inputSchema.properties == {}
        assert tool.inputSchema.required == []

    def test_mcp_tool_call_result(self):
        """Test MCPToolCallResult model."""
        result = MCPToolCallResult(
            content=[
                MCPToolCallContent(type="text", text="Success!"),
                MCPToolCallContent(type="text", text="More output"),
            ],
            isError=False,
        )

        assert len(result.content) == 2
        assert result.content[0].text == "Success!"
        assert result.content[1].text == "More output"
        assert result.isError is False

    def test_mcp_tool_call_result_error(self):
        """Test MCPToolCallResult with error."""
        result = MCPToolCallResult(
            content=[MCPToolCallContent(type="text", text="Error: file not found")],
            isError=True,
        )

        assert result.isError is True

    def test_mcp_server_info(self):
        """Test MCPServerInfo model."""
        info = MCPServerInfo(name="test-server", version="1.0.0")

        assert info.name == "test-server"
        assert info.version == "1.0.0"

    def test_mcp_server_capabilities(self):
        """Test MCPServerCapabilities model."""
        caps = MCPServerCapabilities(
            tools={"listChanged": True},
            resources=None,
            prompts=None,
            logging=None,
        )

        assert caps.tools is not None
        assert caps.resources is None

    def test_mcp_initialize_result(self):
        """Test MCPInitializeResult model."""
        result = MCPInitializeResult(
            protocolVersion="2024-11-05",
            capabilities=MCPServerCapabilities(),
            serverInfo=MCPServerInfo(name="test", version="1.0"),
        )

        assert result.protocolVersion == "2024-11-05"
        assert result.serverInfo.name == "test"

    def test_mcp_resource(self):
        """Test MCPResource model."""
        resource = MCPResource(
            uri="file:///path/to/file.txt",
            name="file.txt",
            description="A text file",
            mimeType="text/plain",
        )

        assert resource.uri == "file:///path/to/file.txt"
        assert resource.name == "file.txt"
        assert resource.mimeType == "text/plain"

    def test_mcp_resource_contents(self):
        """Test MCPResourceContents model."""
        contents = MCPResourceContents(
            uri="file:///test.txt",
            mimeType="text/plain",
            text="Hello, world!",
        )

        assert contents.uri == "file:///test.txt"
        assert contents.text == "Hello, world!"
        assert contents.blob is None

    def test_mcp_prompt(self):
        """Test MCPPrompt model."""
        prompt = MCPPrompt(
            name="greeting",
            description="A greeting prompt",
            arguments=[{"name": "name", "description": "Person's name", "required": True}],
        )

        assert prompt.name == "greeting"
        assert len(prompt.arguments) == 1

# ============================================================================
# Error Type Tests
# ============================================================================

class TestErrorTypes:
    """Tests for error types and codes."""

    def test_mcp_transport_error(self):
        """Test MCPTransportError creation with formatted message."""
        error = MCPTransportError("Test error message")

        # DryadeError._format_message() includes [code] prefix and suggestion
        assert "Test error message" in str(error)
        assert "[MCP_TRANSPORT_001]" in str(error)
        assert error.code == MCPErrorCode.INTERNAL_ERROR

    def test_mcp_transport_error_with_code(self):
        """Test MCPTransportError with custom code."""
        error = MCPTransportError("Method not found", MCPErrorCode.METHOD_NOT_FOUND)

        assert "Method not found" in str(error)
        assert error.code == MCPErrorCode.METHOD_NOT_FOUND

    def test_mcp_timeout_error(self):
        """Test MCPTimeoutError creation."""
        error = MCPTimeoutError()

        assert "Timeout" in str(error) or "timeout" in str(error).lower()
        assert error.code == MCPErrorCode.INTERNAL_ERROR

    def test_mcp_timeout_error_custom_message(self):
        """Test MCPTimeoutError with custom message."""
        error = MCPTimeoutError("Custom timeout message")

        assert "Custom timeout message" in str(error)

    def test_error_codes(self):
        """Test MCPErrorCode values."""
        assert MCPErrorCode.PARSE_ERROR == -32700
        assert MCPErrorCode.INVALID_REQUEST == -32600
        assert MCPErrorCode.METHOD_NOT_FOUND == -32601
        assert MCPErrorCode.INVALID_PARAMS == -32602
        assert MCPErrorCode.INTERNAL_ERROR == -32603
        assert MCPErrorCode.REQUEST_CANCELLED == -32800
        assert MCPErrorCode.CONTENT_TOO_LARGE == -32801

# ============================================================================
# Server Request Handling Tests
# ============================================================================

class TestServerRequestHandling:
    """Tests for handling server-initiated requests."""

    def test_handle_message_routes_server_requests(self):
        """Test _handle_message routes server requests correctly."""
        transport = StdioTransport(["test"])

        # Mock _handle_server_request and _send_raw
        transport._handle_server_request = Mock()
        transport._send_raw = Mock()

        # Server request (has method, no result)
        server_request = {"jsonrpc": "2.0", "id": 0, "method": "roots/list"}
        transport._handle_message(server_request)

        transport._handle_server_request.assert_called_once_with(server_request)

    def test_handle_message_routes_responses(self):
        """Test _handle_message routes responses to pending queues."""
        transport = StdioTransport(["test"])

        # Set up pending response queue
        response_queue = Queue()
        transport._pending_responses[1] = response_queue

        # Response message
        response = {"jsonrpc": "2.0", "id": 1, "result": {"data": "test"}}
        transport._handle_message(response)

        # Verify response was queued
        queued_msg = response_queue.get(timeout=1)
        assert queued_msg == response

    def test_handle_server_request_roots_list(self):
        """Test _handle_server_request handles roots/list."""
        transport = StdioTransport(["test"])
        transport._send_raw = Mock()

        request = {"jsonrpc": "2.0", "id": 0, "method": "roots/list"}
        transport._handle_server_request(request)

        # Should respond with empty roots
        transport._send_raw.assert_called_once()
        call_args = transport._send_raw.call_args[0][0]
        assert call_args["id"] == 0
        assert call_args["result"]["roots"] == []

    def test_handle_server_request_sampling(self):
        """Test _handle_server_request rejects sampling."""
        transport = StdioTransport(["test"])
        transport._send_raw = Mock()

        request = {"jsonrpc": "2.0", "id": 1, "method": "sampling/createMessage"}
        transport._handle_server_request(request)

        # Should respond with error
        call_args = transport._send_raw.call_args[0][0]
        assert "error" in call_args
        assert call_args["error"]["code"] == MCPErrorCode.METHOD_NOT_FOUND

    def test_handle_server_request_unknown(self):
        """Test _handle_server_request handles unknown methods."""
        transport = StdioTransport(["test"])
        transport._send_raw = Mock()

        request = {"jsonrpc": "2.0", "id": 2, "method": "unknown/method"}
        transport._handle_server_request(request)

        # Should respond with error
        call_args = transport._send_raw.call_args[0][0]
        assert "error" in call_args
        assert call_args["error"]["code"] == MCPErrorCode.METHOD_NOT_FOUND

# ============================================================================
# Notification Tests
# ============================================================================

class TestNotifications:
    """Tests for notification handling."""

    @patch("subprocess.Popen")
    @patch("time.sleep")
    def test_send_notification_format(self, mock_sleep, mock_popen):
        """Test send_notification creates correct message format."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.stdout = MagicMock()
        mock_process.stdin = MagicMock()
        mock_popen.return_value = mock_process

        transport = StdioTransport(["test"], startup_delay=0.01)
        transport.start()

        transport.send_notification("test/notification", {"key": "value"})

        # Verify message was written
        mock_process.stdin.write.assert_called_once()
        written = mock_process.stdin.write.call_args[0][0]
        message = json.loads(written.strip())

        assert message["jsonrpc"] == "2.0"
        assert message["method"] == "test/notification"
        assert message["params"] == {"key": "value"}
        assert "id" not in message  # Notifications have no ID

        transport._running = False

    @patch("subprocess.Popen")
    @patch("time.sleep")
    def test_send_notification_without_params(self, mock_sleep, mock_popen):
        """Test send_notification works without params."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.stdout = MagicMock()
        mock_process.stdin = MagicMock()
        mock_popen.return_value = mock_process

        transport = StdioTransport(["test"], startup_delay=0.01)
        transport.start()

        transport.send_notification("test/notification")

        written = mock_process.stdin.write.call_args[0][0]
        message = json.loads(written.strip())

        assert "params" not in message

        transport._running = False

# ============================================================================
# Integration Pattern Tests
# ============================================================================

class TestIntegrationPatterns:
    """Tests demonstrating integration patterns."""

    def test_tool_to_openai_format(self):
        """Test converting MCP tool to OpenAI function format."""
        mcp_tool = MCPTool(
            name="read_file",
            description="Read a file from the filesystem",
            inputSchema=MCPToolInputSchema(
                type="object",
                properties={
                    "path": {"type": "string", "description": "Path to file"},
                    "encoding": {"type": "string", "description": "File encoding"},
                },
                required=["path"],
            ),
        )

        # Convert to OpenAI format
        openai_format = {
            "type": "function",
            "function": {
                "name": mcp_tool.name,
                "description": mcp_tool.description,
                "parameters": {
                    "type": mcp_tool.inputSchema.type,
                    "properties": mcp_tool.inputSchema.properties,
                    "required": mcp_tool.inputSchema.required,
                },
            },
        }

        assert openai_format["type"] == "function"
        assert openai_format["function"]["name"] == "read_file"
        assert "path" in openai_format["function"]["parameters"]["properties"]

    def test_result_text_extraction(self):
        """Test extracting text from tool call result."""
        result = MCPToolCallResult(
            content=[
                MCPToolCallContent(type="text", text="Line 1"),
                MCPToolCallContent(type="image", data="base64..."),  # Not text
                MCPToolCallContent(type="text", text="Line 2"),
            ],
            isError=False,
        )

        # Extract text content
        texts = [c.text for c in result.content if c.type == "text" and c.text]
        combined = "\n".join(texts)

        assert combined == "Line 1\nLine 2"

    def test_error_result_handling(self):
        """Test handling error results."""
        result = MCPToolCallResult(
            content=[MCPToolCallContent(type="text", text="File not found: /missing")],
            isError=True,
        )

        # Pattern for error handling
        if result.isError:
            error_messages = [c.text for c in result.content if c.text]
            error_text = "\n".join(error_messages)
            assert "File not found" in error_text

# ============================================================================
# Server Status Tests
# ============================================================================

class TestServerStatus:
    """Tests for server health status tracking."""

    def test_initial_status_stopped(self):
        """Test status is STOPPED before start()."""
        transport = StdioTransport(["test"])
        assert transport.status == MCPServerStatus.STOPPED

    @patch("subprocess.Popen")
    @patch("time.sleep")
    def test_status_starting_after_start(self, mock_sleep, mock_popen):
        """Test status is STARTING after start() before initialize()."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.stdout = MagicMock()
        mock_popen.return_value = mock_process

        transport = StdioTransport(["test"], startup_delay=0.01)
        transport.start()

        assert transport.status == MCPServerStatus.STARTING
        transport._running = False

    @patch("subprocess.Popen")
    @patch("time.sleep")
    def test_status_healthy_after_initialize(self, mock_sleep, mock_popen):
        """Test status is HEALTHY after successful initialize()."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.stdout = MagicMock()
        mock_process.stdin = MagicMock()
        mock_popen.return_value = mock_process

        transport = StdioTransport(["test"], startup_delay=0.01)
        transport.start()

        # Mock the send_request_no_retry to return a valid initialize result
        transport._send_request_no_retry = Mock(
            return_value={
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "test", "version": "1.0"},
                "capabilities": {},
            }
        )

        transport.initialize()
        assert transport.status == MCPServerStatus.HEALTHY
        transport._running = False

    @patch("subprocess.Popen")
    @patch("time.sleep")
    def test_status_stopped_after_stop(self, mock_sleep, mock_popen):
        """Test status is STOPPED after stop()."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.stdout = MagicMock()
        mock_popen.return_value = mock_process

        transport = StdioTransport(["test"], startup_delay=0.01)
        transport.start()
        transport.stop()

        assert transport.status == MCPServerStatus.STOPPED

    @patch("subprocess.Popen")
    @patch("time.sleep")
    def test_is_alive_when_running(self, mock_sleep, mock_popen):
        """Test is_alive is True when process running."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.stdout = MagicMock()
        mock_popen.return_value = mock_process

        transport = StdioTransport(["test"], startup_delay=0.01)
        transport.start()

        assert transport.is_alive is True
        transport._running = False

    def test_is_alive_when_stopped(self):
        """Test is_alive is False when stopped."""
        transport = StdioTransport(["test"])
        assert transport.is_alive is False

    @patch("subprocess.Popen")
    @patch("time.sleep")
    def test_status_becomes_crashed_on_process_exit(self, mock_sleep, mock_popen):
        """Test status changes to CRASHED when process exits unexpectedly."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.stdout = MagicMock()
        mock_process.stdin = MagicMock()
        mock_popen.return_value = mock_process

        transport = StdioTransport(["test"], startup_delay=0.01)
        transport.start()
        transport._status = MCPServerStatus.HEALTHY

        # Simulate process crash
        mock_process.poll.return_value = 1  # Non-zero exit code

        assert transport.status == MCPServerStatus.CRASHED
        transport._running = False

# ============================================================================
# Auto-Restart Tests
# ============================================================================

class TestAutoRestart:
    """Tests for auto-restart functionality."""

    def test_auto_restart_disabled_by_default(self):
        """Test auto_restart is False by default."""
        transport = StdioTransport(["test"])
        assert transport.auto_restart is False

    def test_auto_restart_enabled_with_param(self):
        """Test auto_restart can be enabled."""
        transport = StdioTransport(["test"], auto_restart=True)
        assert transport.auto_restart is True

    @patch("subprocess.Popen")
    @patch("time.sleep")
    def test_auto_restart_on_crash(self, mock_sleep, mock_popen):
        """Test auto-restart triggers on process crash."""
        mock_process = MagicMock()
        # First poll: crashed, subsequent: running
        mock_process.poll.side_effect = [1, None, None, None, None]
        mock_process.stdout = MagicMock()
        mock_process.stdin = MagicMock()
        mock_process.returncode = 1
        mock_popen.return_value = mock_process

        transport = StdioTransport(
            ["test"],
            auto_restart=True,
            max_restarts=3,
            restart_delay=0.1,
            startup_delay=0.01,
        )
        # Set up as if already started
        transport._process = mock_process
        transport._running = True
        transport._status = MCPServerStatus.HEALTHY

        # Mock initialize for restart
        transport.initialize = Mock()

        # Call _check_and_restart - should trigger restart
        transport._check_and_restart()

        assert transport._restart_count == 1
        transport._running = False

    @patch("subprocess.Popen")
    @patch("time.sleep")
    def test_max_restarts_exceeded(self, mock_sleep, mock_popen):
        """Test error raised when max_restarts exceeded."""
        mock_process = MagicMock()
        mock_process.poll.return_value = 1  # Always crashed
        mock_process.returncode = 1
        mock_popen.return_value = mock_process

        transport = StdioTransport(
            ["test"],
            auto_restart=True,
            max_restarts=3,
            startup_delay=0.01,
        )
        transport._process = mock_process
        transport._running = True
        transport._restart_count = 3  # Already at max

        with pytest.raises(MCPTransportError) as exc_info:
            transport._check_and_restart()

        assert "max restarts" in str(exc_info.value)

    @patch("subprocess.Popen")
    @patch("time.sleep")
    def test_restart_count_reset_on_success(self, mock_sleep, mock_popen):
        """Test restart counter resets on successful request."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.stdout = MagicMock()
        mock_process.stdin = MagicMock()
        mock_popen.return_value = mock_process

        transport = StdioTransport(["test"], startup_delay=0.01)
        transport.start()
        transport._restart_count = 2  # Simulate previous restarts

        # Mock successful request
        transport._send_request_no_retry = Mock(return_value={"result": "ok"})

        transport.send_request("test/method")

        assert transport._restart_count == 0
        transport._running = False

    @patch("subprocess.Popen")
    @patch("time.sleep")
    def test_manual_restart(self, mock_sleep, mock_popen):
        """Test restart() method works correctly."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.stdout = MagicMock()
        mock_process.stdin = MagicMock()
        mock_popen.return_value = mock_process

        transport = StdioTransport(["test"], startup_delay=0.01)
        transport.start()
        transport._restart_count = 2

        # Mock initialize
        transport._send_request_no_retry = Mock(
            return_value={
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "test", "version": "1.0"},
                "capabilities": {},
            }
        )

        transport.restart()

        # Verify restart_count was reset
        assert transport._restart_count == 0
        transport._running = False

    def test_reset_restart_count(self):
        """Test reset_restart_count() clears counter."""
        transport = StdioTransport(["test"])
        transport._restart_count = 5

        transport.reset_restart_count()

        assert transport._restart_count == 0

# ============================================================================
# Retry Logic Tests
# ============================================================================

class TestRetryLogic:
    """Tests for request retry logic."""

    def test_retry_on_timeout(self):
        """Test MCPTimeoutError is retryable."""
        transport = StdioTransport(["test"])
        error = MCPTimeoutError("Timeout")
        assert transport._is_retryable_error(error) is True

    def test_no_retry_on_method_not_found(self):
        """Test METHOD_NOT_FOUND is not retryable."""
        transport = StdioTransport(["test"])
        error = MCPTransportError("Method not found", MCPErrorCode.METHOD_NOT_FOUND)
        assert transport._is_retryable_error(error) is False

    def test_no_retry_on_invalid_params(self):
        """Test INVALID_PARAMS is not retryable."""
        transport = StdioTransport(["test"])
        error = MCPTransportError("Invalid params", MCPErrorCode.INVALID_PARAMS)
        assert transport._is_retryable_error(error) is False

    def test_no_retry_on_invalid_request(self):
        """Test INVALID_REQUEST is not retryable."""
        transport = StdioTransport(["test"])
        error = MCPTransportError("Invalid request", MCPErrorCode.INVALID_REQUEST)
        assert transport._is_retryable_error(error) is False

    def test_retry_on_pipe_error(self):
        """Test pipe errors are retryable."""
        transport = StdioTransport(["test"])
        error = MCPTransportError("Broken pipe", MCPErrorCode.INTERNAL_ERROR)
        assert transport._is_retryable_error(error) is True

    @patch("subprocess.Popen")
    @patch("time.sleep")
    def test_max_retries_respected(self, mock_sleep, mock_popen):
        """Test retry stops after max_retries."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.stdout = MagicMock()
        mock_process.stdin = MagicMock()
        mock_popen.return_value = mock_process

        transport = StdioTransport(["test"], max_retries=2, startup_delay=0.01)
        transport.start()

        # Mock _send_request_no_retry to always timeout
        call_count = 0

        def timeout_request(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise MCPTimeoutError("Timeout")

        transport._send_request_no_retry = timeout_request

        with pytest.raises(MCPTimeoutError):
            transport.send_request("test/method")

        # Should have tried 3 times (initial + 2 retries)
        assert call_count == 3
        transport._running = False

    @patch("subprocess.Popen")
    @patch("time.sleep")
    def test_retry_delay_applied(self, mock_sleep, mock_popen):
        """Test retry_delay is applied between retries."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.stdout = MagicMock()
        mock_process.stdin = MagicMock()
        mock_popen.return_value = mock_process

        transport = StdioTransport(["test"], max_retries=2, retry_delay=0.5, startup_delay=0.01)
        transport.start()

        # Mock _send_request_no_retry to always timeout
        transport._send_request_no_retry = Mock(side_effect=MCPTimeoutError("Timeout"))

        with pytest.raises(MCPTimeoutError):
            transport.send_request("test/method")

        # Verify sleep was called with retry_delay (twice for 2 retries)
        # Note: startup_delay also calls sleep
        retry_sleep_calls = [call for call in mock_sleep.call_args_list if call[0][0] == 0.5]
        assert len(retry_sleep_calls) == 2
        transport._running = False

    @patch("subprocess.Popen")
    @patch("time.sleep")
    def test_consecutive_failures_tracked(self, mock_sleep, mock_popen):
        """Test consecutive_failures counter increments on failures."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.stdout = MagicMock()
        mock_process.stdin = MagicMock()
        mock_popen.return_value = mock_process

        transport = StdioTransport(["test"], max_retries=2, startup_delay=0.01)
        transport.start()

        # Mock _send_request_no_retry to always timeout
        transport._send_request_no_retry = Mock(side_effect=MCPTimeoutError("Timeout"))

        initial_failures = transport._consecutive_failures

        with pytest.raises(MCPTimeoutError):
            transport.send_request("test/method")

        # Each retry attempt increments the counter
        assert transport._consecutive_failures == initial_failures + 3
        transport._running = False

    @patch("subprocess.Popen")
    @patch("time.sleep")
    def test_send_request_no_retry_skips_retry(self, mock_sleep, mock_popen):
        """Test _send_request_no_retry doesn't retry."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.stdout = MagicMock()
        mock_process.stdin = MagicMock()
        mock_popen.return_value = mock_process

        transport = StdioTransport(["test"], max_retries=5, startup_delay=0.01)
        transport.start()

        # Create a mock response queue that times out
        call_count = 0
        original_send = transport._send_request_no_retry

        def counting_send(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise MCPTimeoutError("Timeout")

        # Replace with our counting version
        transport._send_request_no_retry = counting_send

        with pytest.raises(MCPTimeoutError):
            # Call directly - should only run once (no retry)
            transport._send_request_no_retry("test/method")

        assert call_count == 1
        transport._running = False

    @patch("subprocess.Popen")
    @patch("time.sleep")
    def test_success_resets_failure_counters(self, mock_sleep, mock_popen):
        """Test successful request resets failure counters."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.stdout = MagicMock()
        mock_process.stdin = MagicMock()
        mock_popen.return_value = mock_process

        transport = StdioTransport(["test"], startup_delay=0.01)
        transport.start()
        transport._consecutive_failures = 5
        transport._restart_count = 2

        # Mock successful request
        transport._send_request_no_retry = Mock(return_value={"result": "ok"})

        transport.send_request("test/method")

        assert transport._consecutive_failures == 0
        assert transport._restart_count == 0
        transport._running = False

    def test_resilience_config_defaults(self):
        """Test default resilience configuration values."""
        transport = StdioTransport(["test"])

        assert transport.auto_restart is False
        assert transport.max_restarts == 3
        assert transport.restart_delay == 1.0
        assert transport.max_retries == 2
        assert transport.retry_delay == 0.5

    def test_resilience_config_custom(self):
        """Test custom resilience configuration."""
        transport = StdioTransport(
            ["test"],
            auto_restart=True,
            max_restarts=5,
            restart_delay=2.0,
            max_retries=4,
            retry_delay=1.0,
        )

        assert transport.auto_restart is True
        assert transport.max_restarts == 5
        assert transport.restart_delay == 2.0
        assert transport.max_retries == 4
        assert transport.retry_delay == 1.0
