"""A2A Protocol Adapter.

Enables communication with any A2A-compliant remote agent using JSON-RPC 2.0.

Protocol methods:
  - message/send: Synchronous task execution
  - message/stream: SSE streaming execution
  - tasks/get: Poll long-running task status
  - tasks/cancel: Cancel a running task

See: https://github.com/a2aproject/A2A
     https://developers.googleblog.com/en/a2a-a-new-era-of-agent-interoperability/
"""

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator
from typing import Any
from uuid import uuid4

import httpx

from core.adapters.protocol import (
    AgentCapabilities,
    AgentCapability,
    AgentCard,
    AgentFramework,
    AgentResult,
    UniversalAgent,
)

logger = logging.getLogger(__name__)

# Map A2A task states to Dryade AgentResult statuses
_A2A_STATE_TO_STATUS = {
    "completed": "ok",
    "failed": "error",
    "canceled": "error",
    "rejected": "error",
    "working": "partial",
    "input_required": "partial",
}

class A2AAgentAdapter(UniversalAgent):
    """Connect to A2A-compliant remote agents.

    A2A Protocol (Agent2Agent) is a Linux Foundation standard
    for agent interoperability, contributed by Google.

    Uses JSON-RPC 2.0 for all protocol communication:
    - message/send for synchronous execution
    - message/stream for SSE streaming
    - tasks/get for polling long-running tasks
    - tasks/cancel for cancellation

    Supports 150+ organizations including Salesforce, SAP,
    ServiceNow, and more.
    """

    def __init__(
        self,
        endpoint: str,
        timeout: float = 300.0,
        auth_token: str | None = None,
        api_key: str | None = None,
        card_cache_ttl_seconds: int = 300,
        local_handler: Any | None = None,
    ):
        """Initialize A2A adapter.

        Args:
            endpoint: Base URL of A2A-compliant agent
            timeout: Request timeout in seconds
            auth_token: Optional Bearer token for authentication
            api_key: Optional API key for authentication
            card_cache_ttl_seconds: TTL for agent card cache (default 300s)
            local_handler: Optional async callable for in-process execution (bypasses HTTP)
        """
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout
        self._auth_token = auth_token
        self._api_key = api_key
        self._card_cache_ttl = card_cache_ttl_seconds
        self._card_cached_at: float = 0.0
        self._client = httpx.AsyncClient(timeout=timeout)
        self._card: AgentCard | None = None
        self._security_schemes: dict[str, Any] = {}
        self._local_handler = local_handler

    def _build_headers(self) -> dict[str, str]:
        """Build HTTP headers with authentication based on agent card security schemes.

        Auth selection priority:
        1. Bearer token (if auth_token is set and card declares http/bearer scheme)
        2. API key (if api_key is set and card declares apiKey scheme)
        3. Fallback: use whatever credentials are provided regardless of card schemes
        """
        headers: dict[str, str] = {"Content-Type": "application/json"}

        # If security schemes are parsed from card, respect them
        if self._security_schemes:
            for _scheme_name, scheme in self._security_schemes.items():
                scheme_type = scheme.get("type", "")

                # Bearer token auth
                if scheme_type == "http" and scheme.get("scheme") == "bearer" and self._auth_token:
                    headers["Authorization"] = f"Bearer {self._auth_token}"
                    return headers

                # API key auth (header-based)
                if scheme_type == "apiKey" and self._api_key:
                    header_name = scheme.get("name", "X-API-Key")
                    location = scheme.get("in", "header")
                    if location == "header":
                        headers[header_name] = self._api_key
                    return headers

        # Fallback: apply whatever credentials are available
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"
        if self._api_key:
            headers["X-API-Key"] = self._api_key

        return headers

    async def _fetch_card(self) -> AgentCard:
        """Fetch agent card from remote endpoint (cached with TTL).

        Parses securitySchemes from the agent card to configure authentication
        headers dynamically based on the remote agent's requirements.
        """
        # Return cached card if still valid
        if self._card is not None and (time.time() - self._card_cached_at) < self._card_cache_ttl:
            return self._card

        try:
            response = await self._client.get(
                f"{self.endpoint}/.well-known/agent.json",
                headers=self._build_headers(),
            )
            response.raise_for_status()
            data = response.json()

            # Parse security schemes from agent card
            self._security_schemes = data.get("securitySchemes", {})

            # Parse A2A agent card format
            capabilities = [
                AgentCapability(
                    name=cap.get("name", ""),
                    description=cap.get("description", ""),
                    input_schema=cap.get("inputSchema", {}),
                    output_schema=cap.get("outputSchema", {}),
                )
                for cap in data.get("capabilities", [])
            ]

            card = AgentCard(
                name=data.get("name", "unknown"),
                description=data.get("description", ""),
                version=data.get("version", "1.0"),
                framework=AgentFramework.A2A,
                endpoint=self.endpoint,
                capabilities=capabilities,
                metadata=data.get("metadata", {}),
            )
            self._card = card
            self._card_cached_at = time.time()
            return card
        except Exception as e:
            # Return minimal card if fetch fails
            return AgentCard(
                name="remote_agent",
                description=f"Remote A2A agent at {self.endpoint}",
                version="unknown",
                framework=AgentFramework.A2A,
                endpoint=self.endpoint,
                capabilities=[],
                metadata={"error": str(e)},
            )

    def get_card(self) -> AgentCard:
        """Return agent's capability card (cached)."""
        if self._card is None:
            # Sync wrapper for async fetch
            try:
                loop = asyncio.get_event_loop()
                self._card = loop.run_until_complete(self._fetch_card())
            except RuntimeError:
                # No event loop, create one
                self._card = asyncio.run(self._fetch_card())
        return self._card

    # ------------------------------------------------------------------
    # JSON-RPC helpers
    # ------------------------------------------------------------------

    def _build_jsonrpc_request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Build a JSON-RPC 2.0 request envelope.

        Args:
            method: JSON-RPC method name (e.g. "message/send", "tasks/get")
            params: Method parameters

        Returns:
            Complete JSON-RPC 2.0 request dict
        """
        return {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": str(uuid4()),
        }

    async def _send_jsonrpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send a JSON-RPC 2.0 request and return the result.

        Args:
            method: JSON-RPC method name
            params: Method parameters

        Returns:
            The "result" field from the JSON-RPC response

        Raises:
            httpx exceptions on transport errors
            ValueError on JSON-RPC error responses
        """
        payload = self._build_jsonrpc_request(method, params)
        response = await self._client.post(
            f"{self.endpoint}/",
            json=payload,
            headers=self._build_headers(),
        )
        response.raise_for_status()
        data = response.json()

        # Check for JSON-RPC error
        if "error" in data:
            error = data["error"]
            code = error.get("code", -1)
            message = error.get("message", "Unknown JSON-RPC error")
            raise ValueError(f"JSON-RPC error {code}: {message}")

        return data.get("result", {})

    # ------------------------------------------------------------------
    # Core execution methods
    # ------------------------------------------------------------------

    async def execute(self, task: str, context: dict[str, Any] | None = None) -> AgentResult:
        """Execute task on remote A2A agent via JSON-RPC 2.0 message/send.

        Sends a message/send JSON-RPC request per the A2A protocol spec.
        The response contains an A2A Task object with status and artifacts.

        Args:
            task: Natural language task description
            context: Optional execution context (passed as metadata)

        Returns:
            AgentResult with mapped status and extracted result text
        """
        try:
            # Local dispatch: bypass HTTP for local:// endpoints
            if self._local_handler is not None:
                try:
                    result = await self._local_handler(task, context)
                    if isinstance(result, AgentResult):
                        return result
                    # If handler returns a dict or string, wrap it
                    return AgentResult(
                        result=str(result) if result else None,
                        status="ok",
                        metadata={"framework": "a2a", "endpoint": self.endpoint, "local": True},
                    )
                except Exception as e:
                    logger.exception(f"A2A local handler failed for {self.endpoint}: {e}")
                    return AgentResult(
                        result=None,
                        status="error",
                        error=f"Local handler failed: {type(e).__name__}: {e}",
                        metadata={
                            "error_type": "local_handler",
                            "framework": "a2a",
                            "endpoint": self.endpoint,
                        },
                    )

            # Build message/send params per A2A spec
            params: dict[str, Any] = {
                "message": {
                    "role": "user",
                    "parts": [{"text": task}],
                }
            }
            if context:
                params["metadata"] = context

            result = await self._send_jsonrpc("message/send", params)

            # Parse A2A Task from result
            task_id = result.get("id")
            status = result.get("status", {})
            state = status.get("state", "completed")

            # Extract text from status message parts
            result_text = None
            status_message = status.get("message", {})
            if status_message:
                parts = status_message.get("parts", [])
                if parts:
                    result_text = parts[0].get("text", "")

            # Also check artifacts for output
            artifacts = result.get("artifacts", [])
            if not result_text and artifacts:
                # Extract text from first artifact's parts
                for artifact in artifacts:
                    for part in artifact.get("parts", []):
                        if "text" in part:
                            result_text = part["text"]
                            break
                    if result_text:
                        break

            # Map A2A state to AgentResult status
            mapped_status = _A2A_STATE_TO_STATUS.get(state, "error")

            return AgentResult(
                result=result_text,
                status=mapped_status,
                error=f"Task {state}" if mapped_status == "error" else None,
                metadata={
                    "framework": "a2a",
                    "endpoint": self.endpoint,
                    "task_id": task_id,
                    "a2a_state": state,
                },
            )

        except httpx.TimeoutException as e:
            logger.warning(f"A2A JSON-RPC timeout for {self.endpoint}: {e}")
            return AgentResult(
                result=None,
                status="error",
                error=f"Agent timed out after {self.timeout}s. Try simplifying the request.",
                metadata={"error_type": "timeout", "framework": "a2a", "endpoint": self.endpoint},
            )
        except httpx.NetworkError as e:
            logger.warning(f"A2A JSON-RPC network error for {self.endpoint}: {e}")
            return AgentResult(
                result=None,
                status="error",
                error=f"Network error: {e}. Check network connectivity and try again.",
                metadata={
                    "error_type": "network",
                    "framework": "a2a",
                    "endpoint": self.endpoint,
                },
            )
        except httpx.HTTPStatusError as e:
            logger.warning(f"A2A JSON-RPC HTTP error for {self.endpoint}: {e.response.status_code}")
            return AgentResult(
                result=None,
                status="error",
                error=f"HTTP {e.response.status_code}: {e.response.text[:200]}",
                metadata={
                    "error_type": "http",
                    "framework": "a2a",
                    "endpoint": self.endpoint,
                    "status_code": e.response.status_code,
                },
            )
        except ValueError as e:
            # JSON-RPC protocol error
            logger.warning(f"A2A JSON-RPC error for {self.endpoint}: {e}")
            return AgentResult(
                result=None,
                status="error",
                error=str(e),
                metadata={"error_type": "jsonrpc", "framework": "a2a", "endpoint": self.endpoint},
            )
        except Exception as e:
            logger.exception(f"A2A adapter execution failed for {self.endpoint}: {e}")
            return AgentResult(
                result=None,
                status="error",
                error=f"Agent execution failed: {type(e).__name__}",
                metadata={"error_type": "execution", "framework": "a2a", "endpoint": self.endpoint},
            )

    # ------------------------------------------------------------------
    # Long-running task support
    # ------------------------------------------------------------------

    async def get_task_status(self, task_id: str) -> dict[str, Any]:
        """Get status of a task via JSON-RPC 2.0 tasks/get.

        Args:
            task_id: The A2A task ID to query

        Returns:
            A2A Task dict containing id, status, and artifacts
        """
        return await self._send_jsonrpc("tasks/get", {"id": task_id})

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task via JSON-RPC 2.0 tasks/cancel.

        Args:
            task_id: The A2A task ID to cancel

        Returns:
            True if cancellation succeeded, False otherwise
        """
        try:
            result = await self._send_jsonrpc("tasks/cancel", {"id": task_id})
            state = result.get("status", {}).get("state", "")
            return state == "canceled"
        except Exception as e:
            logger.warning(f"A2A task cancel failed for {task_id}: {e}")
            return False

    async def execute_with_polling(
        self,
        task: str,
        context: dict[str, Any] | None = None,
        poll_interval: float = 2.0,
        max_polls: int = 150,
    ) -> AgentResult:
        """Execute task with automatic polling for long-running tasks.

        Calls execute() first. If the task is still in progress (status="partial"),
        polls tasks/get at the configured interval until completion or timeout.

        Args:
            task: Natural language task description
            context: Optional execution context
            poll_interval: Seconds between poll requests (default 2.0)
            max_polls: Maximum number of poll iterations (default 150)

        Returns:
            AgentResult with final task status
        """
        initial = await self.execute(task, context)

        # If task completed immediately, return result
        if initial.status != "partial":
            return initial

        # Long-running task: poll for completion
        task_id = initial.metadata.get("task_id")
        if not task_id:
            return AgentResult(
                result=initial.result,
                status="error",
                error="Long-running task returned no task_id for polling",
                metadata=initial.metadata,
            )

        logger.info(
            f"A2A task {task_id} is long-running, polling every {poll_interval}s (max {max_polls})"
        )

        for poll_num in range(max_polls):
            await asyncio.sleep(poll_interval)

            try:
                task_data = await self.get_task_status(task_id)
            except Exception as e:
                logger.warning(
                    f"A2A poll {poll_num + 1}/{max_polls} failed for task {task_id}: {e}"
                )
                continue  # Retry on transient errors

            status = task_data.get("status", {})
            state = status.get("state", "unknown")

            if state in ("completed", "failed", "canceled", "rejected"):
                # Terminal state -- extract result
                result_text = None
                status_message = status.get("message", {})
                if status_message:
                    parts = status_message.get("parts", [])
                    if parts:
                        result_text = parts[0].get("text", "")

                # Check artifacts
                artifacts = task_data.get("artifacts", [])
                if not result_text and artifacts:
                    for artifact in artifacts:
                        for part in artifact.get("parts", []):
                            if "text" in part:
                                result_text = part["text"]
                                break
                        if result_text:
                            break

                mapped_status = _A2A_STATE_TO_STATUS.get(state, "error")
                return AgentResult(
                    result=result_text,
                    status=mapped_status,
                    error=f"Task {state}" if mapped_status == "error" else None,
                    metadata={
                        "framework": "a2a",
                        "endpoint": self.endpoint,
                        "task_id": task_id,
                        "a2a_state": state,
                        "polls": poll_num + 1,
                    },
                )

            # Still working or input_required -- continue polling
            logger.debug(f"A2A task {task_id} state={state}, poll {poll_num + 1}/{max_polls}")

        # Timeout -- max polls exceeded
        return AgentResult(
            result=None,
            status="error",
            error=f"Task timed out after polling {max_polls} times ({max_polls * poll_interval}s)",
            metadata={
                "framework": "a2a",
                "endpoint": self.endpoint,
                "task_id": task_id,
                "a2a_state": "timeout",
                "polls": max_polls,
            },
        )

    # ------------------------------------------------------------------
    # SSE streaming
    # ------------------------------------------------------------------

    async def execute_streaming(
        self, task: str, context: dict[str, Any] | None = None
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Execute task on remote A2A agent with SSE streaming.

        Uses httpx stream() for real-time task updates via Server-Sent Events.

        Args:
            task: Natural language task description
            context: Optional execution context

        Yields:
            Dryade-compatible event dicts with type/state/message/data keys
        """
        headers = self._build_headers()
        headers["Accept"] = "text/event-stream"

        # Build JSON-RPC 2.0 payload following A2A spec
        payload = self._build_jsonrpc_request(
            "message/stream",
            {
                "message": {
                    "role": "user",
                    "parts": [{"text": task}],
                }
            },
        )

        if context:
            payload["params"]["context"] = context

        try:
            async with self._client.stream(
                "POST", f"{self.endpoint}/", json=payload, headers=headers
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            event_data = json.loads(line[6:])
                            mapped = self._process_sse_event(event_data)
                            if mapped:
                                yield mapped
                        except json.JSONDecodeError:
                            logger.warning(f"[A2A] Invalid SSE JSON: {line[:100]}")
        except httpx.StreamError as e:
            logger.warning(f"[A2A] Stream error for {self.endpoint}: {e}")
            yield {"type": "error", "message": f"Stream error: {e}"}
        except httpx.TimeoutException as e:
            logger.warning(f"[A2A] Stream timeout for {self.endpoint}: {e}")
            yield {"type": "error", "message": f"Stream timed out after {self.timeout}s"}
        except httpx.HTTPStatusError as e:
            logger.warning(f"[A2A] Stream HTTP error for {self.endpoint}: {e.response.status_code}")
            yield {
                "type": "error",
                "message": f"HTTP {e.response.status_code}: {e.response.text[:200]}",
            }
        except Exception as e:
            logger.exception(f"[A2A] Streaming failed for {self.endpoint}: {e}")
            yield {"type": "error", "message": f"Streaming failed: {type(e).__name__}"}

    def _process_sse_event(self, event_data: dict[str, Any]) -> dict[str, Any] | None:
        """Map A2A SSE event to Dryade-compatible dict.

        Handles all A2A task states: working, completed, failed,
        canceled, rejected, input_required.

        Args:
            event_data: Raw JSON-RPC event from A2A SSE stream

        Returns:
            Mapped event dict with type/state/message/data keys, or None if unknown
        """
        result = event_data.get("result")
        if result is None:
            return None

        if "status" in result:
            status = result["status"]
            state = status.get("state")

            # Extract text from A2A message parts
            message_parts = status.get("message", {}).get("parts", [{}])
            text = message_parts[0].get("text", "") if message_parts else ""

            # Map additional A2A states to specific Dryade events
            if state == "input_required":
                return {"type": "input_required", "message": text}
            if state == "canceled":
                return {"type": "canceled"}
            if state == "rejected":
                return {"type": "error", "message": text or "Task rejected"}

            return {
                "type": "status",
                "state": state,
                "message": text,
            }

        if "artifact" in result:
            return {
                "type": "artifact",
                "data": result["artifact"],
            }

        if "error" in result:
            return {
                "type": "error",
                "message": str(result.get("error", "Unknown A2A error")),
            }

        return None

    # ------------------------------------------------------------------
    # Agent interface methods
    # ------------------------------------------------------------------

    async def supports_streaming(self) -> bool:
        """Check if the remote agent supports SSE streaming."""
        await self._fetch_card()
        # A2A agents that support streaming declare it in capabilities
        # Default to True (most A2A implementations support streaming)
        return True

    def get_tools(self) -> list[dict[str, Any]]:
        """Return available tools in OpenAI function format."""
        card = self.get_card()
        return [
            {
                "type": "function",
                "function": {
                    "name": cap.name,
                    "description": cap.description,
                    "parameters": cap.input_schema,
                },
            }
            for cap in card.capabilities
        ]

    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()

    def __del__(self):
        """Cleanup on deletion - close synchronously if possible."""
        try:
            # Check if the client has an active transport to close
            if hasattr(self._client, "_transport") and self._client._transport is not None:
                loop = None
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    # No running loop, safe to create one
                    asyncio.run(self.close())
                    return

                # Loop is running, schedule cleanup as task
                if loop and not loop.is_closed():
                    loop.create_task(self.close())
        except Exception:
            # Best effort cleanup - don't raise from __del__
            pass

    def capabilities(self) -> AgentCapabilities:
        """Return A2A-specific capabilities."""
        card = self.get_card()
        supports_push_val = card.metadata.get("supports_push", False)
        return AgentCapabilities(
            supports_streaming=True,
            supports_async_tasks=True,
            supports_push=supports_push_val,
            max_retries=3,
            timeout_seconds=30,
            framework_specific={"a2a_protocol": True},
        )

    def get_memory(self) -> dict | None:
        """A2A agents are remote, no local memory access."""
        return None

    def supports_push(self) -> bool:
        """Check if agent supports push notifications."""
        card = self.get_card()
        return card.metadata.get("supports_push", False)
