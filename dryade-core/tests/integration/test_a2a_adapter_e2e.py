"""A2A adapter e2e tests with mock JSON-RPC server.

Spins up a real HTTP server implementing the A2A protocol to validate
the adapter's JSON-RPC 2.0 message/send, card fetch, and error handling.
No external dependencies needed -- uses stdlib http.server + threading.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from uuid import uuid4

import pytest

from core.adapters.a2a_adapter import A2AAgentAdapter
from core.adapters.protocol import AgentFramework

class _A2AHandler(BaseHTTPRequestHandler):
    """HTTP handler implementing minimal A2A protocol."""

    # Class-level flag to force JSON-RPC errors
    force_error: bool = False

    def log_message(self, format, *args):  # noqa: A002
        """Suppress request logging in tests."""
        pass

    def do_GET(self):
        if self.path == "/.well-known/agent.json":
            card = {
                "name": "mock_a2a_agent",
                "description": "Test A2A agent",
                "version": "1.0",
                "capabilities": [],
            }
            self._send_json(200, card)
        else:
            self._send_json(404, {"error": "Not found"})

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        try:
            request = json.loads(body)
        except json.JSONDecodeError:
            self._send_json(400, {"error": "Invalid JSON"})
            return

        method = request.get("method", "")
        req_id = request.get("id", "1")
        params = request.get("params", {})

        if self.__class__.force_error and method == "message/send":
            self._send_json(
                200,
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32000,
                        "message": "Forced test error",
                    },
                },
            )
            return

        if method == "message/send":
            # Extract input text
            message = params.get("message", {})
            parts = message.get("parts", [])
            input_text = parts[0].get("text", "") if parts else ""

            # Include metadata in response if provided
            metadata = params.get("metadata", {})

            task_id = f"task-{uuid4()}"
            response = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "id": task_id,
                    "status": {
                        "state": "completed",
                        "message": {
                            "role": "agent",
                            "parts": [{"text": f"Echo: {input_text}"}],
                        },
                    },
                    "metadata": metadata,
                },
            }
            self._send_json(200, response)
        else:
            self._send_json(
                200,
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method}",
                    },
                },
            )

    def _send_json(self, status: int, data: dict):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

class MockA2AServer:
    """Context manager that runs a mock A2A JSON-RPC server on a random port."""

    def __init__(self, *, force_error: bool = False):
        self._force_error = force_error
        self.port: int | None = None
        self.server: HTTPServer | None = None
        self.thread: threading.Thread | None = None

    def __enter__(self):
        # Create handler class with the force_error flag
        handler_class = type(
            "_ConfiguredHandler",
            (_A2AHandler,),
            {"force_error": self._force_error},
        )
        self.server = HTTPServer(("127.0.0.1", 0), handler_class)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *args):
        if self.server:
            self.server.shutdown()
        if self.thread:
            self.thread.join(timeout=5)

    @property
    def endpoint(self) -> str:
        return f"http://127.0.0.1:{self.port}"

@pytest.mark.integration
class TestA2AAdapterE2E:
    """End-to-end tests for A2A adapter with mock JSON-RPC server."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_a2a_adapter_message_send(self):
        """A2A adapter sends message/send and receives completed response."""
        with MockA2AServer() as server:
            adapter = A2AAgentAdapter(server.endpoint, timeout=10.0)
            try:
                result = await adapter.execute("Hello A2A")

                assert result.status == "ok", f"Expected ok, got {result.status}: {result.error}"
                assert "Echo: Hello A2A" in result.result
                assert result.metadata["framework"] == "a2a"
                assert result.metadata["endpoint"] == server.endpoint
            finally:
                await adapter.close()

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_a2a_adapter_fetch_card(self):
        """A2A adapter fetches agent card from .well-known/agent.json."""
        with MockA2AServer() as server:
            adapter = A2AAgentAdapter(server.endpoint, timeout=10.0)
            try:
                card = await adapter._fetch_card()

                assert card.name == "mock_a2a_agent"
                assert card.framework == AgentFramework.A2A
            finally:
                await adapter.close()

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_a2a_adapter_connection_refused(self):
        """A2A adapter returns error on connection refused."""
        adapter = A2AAgentAdapter("http://127.0.0.1:1", timeout=5.0)
        try:
            result = await adapter.execute("test")
            assert result.status == "error"
        finally:
            await adapter.close()

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_a2a_adapter_jsonrpc_error_response(self):
        """A2A adapter handles JSON-RPC error responses from server."""
        with MockA2AServer(force_error=True) as server:
            adapter = A2AAgentAdapter(server.endpoint, timeout=10.0)
            try:
                result = await adapter.execute("test")

                assert result.status == "error"
                assert "Forced test error" in result.error
            finally:
                await adapter.close()

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_a2a_adapter_with_metadata(self):
        """A2A adapter passes context as metadata in JSON-RPC request."""
        with MockA2AServer() as server:
            adapter = A2AAgentAdapter(server.endpoint, timeout=10.0)
            try:
                result = await adapter.execute("Hello", context={"session_id": "test-123"})

                assert result.status == "ok"
                assert "Echo: Hello" in result.result
                assert result.metadata["framework"] == "a2a"
            finally:
                await adapter.close()
