"""VLLMBaseLLM - Direct vLLM integration bypassing LiteLLM.

ONLY USE IF:
1. You're running vLLM locally
2. LiteLLM's chat templates cause issues

For Ollama or cloud LLMs, use CrewAI's native LLM class instead.

Features:
- Direct HTTP calls to vLLM OpenAI-compatible endpoint
- Proper chat template handling (add_generation_prompt, continue_final_message)
- Tool/function calling support
- Async support
- Reasoning model support (enable_thinking for Qwen3, DeepSeek, Granite, Mistral)

Note: This class inherits from CrewAI's BaseLLM (NOT LLM) to ensure compatibility
with CrewAI's create_llm() function. BaseLLM is an abstract class without __new__
hijacking, so inheritance works correctly.

Migrated from plugins/starter/vllm/llm.py into core (Phase 191 gap fix).
"""

import asyncio
import json
import logging
import os
from typing import TYPE_CHECKING, Any

import httpx
from crewai.llms.base_llm import BaseLLM

if TYPE_CHECKING:
    from crewai.agent.core import Agent
    from crewai.task import Task

logger = logging.getLogger(__name__)

class VLLMConnectionError(Exception):
    """Raised when VLLMBaseLLM cannot connect to the vLLM server."""

    def __init__(self, message: str, error_type: str = "connection"):
        super().__init__(message)
        self.error_type = error_type  # timeout, connection, http, network

class VLLMBaseLLM(BaseLLM):
    """vLLM LLM class that inherits from CrewAI's BaseLLM.

    Inherits from BaseLLM to pass CrewAI's isinstance() checks in create_llm().
    This ensures the LLM instance is used as-is rather than being replaced.

    Bypasses LiteLLM to handle vLLM-specific quirks:
    - Chat template flags (add_generation_prompt, continue_final_message)
    - Token handling
    - Stop sequences
    - Reasoning model support (enable_thinking)

    Usage:
        llm = VLLMBaseLLM(
            model="mistralai/Mistral-7B-Instruct-v0.2",
            base_url="http://localhost:8000/v1",
        )

        response = llm.call([
            {"role": "user", "content": "Hello!"}
        ])
    """

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        timeout: float = 300.0,
        stop: list[str] | None = None,
        add_generation_prompt: bool = True,
        continue_final_message: bool = False,
        **kwargs: Any,
    ):
        """Initialize VLLMBaseLLM.

        Args:
            model: Model name (default from VLLM_MODEL env)
            base_url: vLLM API base URL (default from VLLM_BASE_URL env)
            api_key: API key (default from VLLM_API_KEY env)
            temperature: Sampling temperature (0.0-2.0)
            max_tokens: Maximum output tokens
            timeout: Request timeout in seconds
            stop: Optional stop sequences
            add_generation_prompt: Add generation prompt to chat template
            continue_final_message: Continue from last message
            **kwargs: Additional parameters passed to BaseLLM
        """
        resolved_model = model or os.getenv("VLLM_MODEL", "local-llm")
        raw_url = base_url or os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1")
        # Normalize base_url: ensure it ends with /v1 for OpenAI-compatible API
        resolved_base_url = self._normalize_base_url(raw_url)
        resolved_api_key = api_key or os.getenv("VLLM_API_KEY", "not-needed")

        # Call BaseLLM.__init__ for CrewAI compatibility
        super().__init__(
            model=resolved_model,
            temperature=temperature,
            api_key=resolved_api_key,
            base_url=resolved_base_url,
            provider="vllm",
            stop=stop,
            **kwargs,
        )

        # vLLM-specific attributes
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.add_generation_prompt = add_generation_prompt
        self.continue_final_message = continue_final_message
        self._max_model_len: int | None = None  # Cached from /v1/models

        # Lazy import httpx
        self._client = None
        self._async_client = None

        logger.info("[VLLM] Initialized VLLMBaseLLM (inherits from CrewAI BaseLLM)")
        logger.info(f"[VLLM] model={self.model}, base_url={self.base_url}")

    def _get_max_model_len(self) -> int | None:
        """Query /v1/models once and cache max_model_len."""
        if self._max_model_len is not None:
            return self._max_model_len
        try:
            import httpx as _httpx

            resp = _httpx.get(
                f"{self.base_url}/models",
                timeout=5.0,
            )
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                if data:
                    self._max_model_len = data[0].get("max_model_len")
                    if self._max_model_len:
                        logger.info(f"[VLLM] max_model_len={self._max_model_len}")
                        return self._max_model_len
        except Exception:
            pass
        return None

    def _clamp_max_tokens(self, messages: list[dict], requested_max: int) -> int:
        """Clamp max_tokens to fit within model context window."""
        max_len = self._get_max_model_len()
        if not max_len:
            return requested_max
        # Rough estimate: ~4 chars per token
        input_chars = sum(len(str(m.get("content", ""))) for m in messages)
        est_input_tokens = input_chars // 4
        available = max_len - est_input_tokens
        if available < requested_max and available > 0:
            clamped = max(available - 64, 128)  # leave 64 token margin, min 128
            logger.info(
                f"[VLLM] Clamping max_tokens: {requested_max} -> {clamped} "
                f"(est input={est_input_tokens}, max_model_len={max_len})"
            )
            return clamped
        return requested_max

    @staticmethod
    def _normalize_base_url(url: str) -> str:
        """Normalize base URL to ensure it ends with /v1 for OpenAI-compatible API.

        Handles various user inputs:
        - http://host:8000 -> http://host:8000/v1
        - http://host:8000/ -> http://host:8000/v1
        - http://host:8000/v1 -> http://host:8000/v1
        - http://host:8000/v1/ -> http://host:8000/v1

        Args:
            url: Raw base URL from user or environment

        Returns:
            Normalized URL ending with /v1 (no trailing slash)
        """
        url = url.rstrip("/")
        if not url.endswith("/v1"):
            url = f"{url}/v1"
        return url

    def _get_client(self):
        """Get or create sync HTTP client."""
        if self._client is None:
            import httpx

            self._client = httpx.Client(timeout=self.timeout)
        return self._client

    def _get_async_client(self):
        """Get or create async HTTP client."""
        if self._async_client is None:
            import httpx

            self._async_client = httpx.AsyncClient(timeout=self.timeout)
        return self._async_client

    def _sanitize_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Sanitize messages for vLLM compatibility.

        - Consolidates consecutive system messages
        - Moves system messages that appear after assistant to be merged with next user message
        - Ensures valid message ordering: system? -> (user -> assistant)*
        """
        if not messages:
            return messages

        sanitized = []
        pending_system = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                # If we have an assistant message before this system message,
                # store it to merge with the next user message
                if sanitized and sanitized[-1].get("role") == "assistant":
                    pending_system.append(content)
                elif sanitized and sanitized[-1].get("role") == "system":
                    # Merge consecutive system messages
                    sanitized[-1]["content"] += "\n\n" + content
                else:
                    sanitized.append({"role": "system", "content": content})
            elif role == "user":
                # Prepend any pending system content to this user message
                if pending_system:
                    content = "\n\n".join(pending_system) + "\n\n" + content
                    pending_system = []
                sanitized.append({"role": "user", "content": content})
            else:
                # assistant or other roles
                sanitized.append({"role": role, "content": content})

        # If there's leftover pending system content, append as user message
        if pending_system:
            sanitized.append({"role": "user", "content": "\n\n".join(pending_system)})

        return sanitized

    def _build_payload(
        self, messages: list[dict[str, Any]], tools: list[dict] | None = None, **kwargs
    ) -> dict[str, Any]:
        """Build the API request payload."""
        # Sanitize messages for vLLM compatibility
        sanitized_messages = self._sanitize_messages(messages)

        # Check if thinking mode is enabled (for reasoning models like Ministral-3-Reasoning)
        # Reasoning is enabled via chat_template_kwargs only - the model handles [THINK] tokens
        # Server must be started with: --reasoning-parser mistral
        enable_thinking = kwargs.get("enable_thinking", False)

        # Determine add_generation_prompt based on last message role
        # If last message is from assistant, use continue_final_message instead
        last_role = sanitized_messages[-1].get("role") if sanitized_messages else "user"
        if last_role == "assistant":
            add_gen_prompt = False
            continue_final = True
        else:
            add_gen_prompt = self.add_generation_prompt
            continue_final = self.continue_final_message

        # Build extra_body with vLLM-specific parameters
        extra_body = {
            "add_generation_prompt": add_gen_prompt,
            "continue_final_message": continue_final,
        }

        # Add chat_template_kwargs for enable_thinking (vLLM request-level override)
        if enable_thinking:
            extra_body["chat_template_kwargs"] = {"enable_thinking": True}

        requested_max = kwargs.get("max_tokens", self.max_tokens)
        clamped_max = self._clamp_max_tokens(sanitized_messages, requested_max)

        payload = {
            "model": self.model,
            "messages": sanitized_messages,
            "temperature": kwargs.get("temperature", self.temperature),
            "max_tokens": clamped_max,
            "extra_body": extra_body,
        }

        # Merge extra sampling params from inference config (Phase 211)
        # These are params like top_p, top_k, repetition_penalty that vLLM
        # accepts as top-level request fields in the OpenAI-compatible API.
        extra_sampling = getattr(self, "_extra_sampling", None)
        if extra_sampling:
            for k, v in extra_sampling.items():
                if k not in payload:  # Don't override explicit kwargs
                    payload[k] = v

        if self.stop:
            payload["stop"] = self.stop

        if tools:
            payload["tools"] = tools
            # Only set tool_choice if explicitly requested.
            # Default "auto" requires vLLM's --enable-auto-tool-choice flag,
            # which not all deployments have. Without tool_choice, vLLM still
            # passes tools to the model but doesn't enforce structured output.
            if "tool_choice" in kwargs:
                payload["tool_choice"] = kwargs["tool_choice"]

        return payload

    def _parse_response(self, data: dict) -> str | dict:
        """Parse the API response, including reasoning for thinking models.

        Handles multiple field names for cross-model compatibility:
        - Mistral uses: reasoning_content
        - DeepSeek R1, Qwen3, Granite, etc. use: reasoning
        """
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})

        # Check for tool calls
        if message.get("tool_calls"):
            return message

        # Check for reasoning content (support both field names for cross-model compat)
        # - Mistral: reasoning_content
        # - DeepSeek, Qwen, Granite, etc.: reasoning
        reasoning = message.get("reasoning") or message.get("reasoning_content")
        # Use `or ""` because .get() returns None if key exists with null value
        content = message.get("content") or ""

        if reasoning:
            # Return structured response with both reasoning and content
            # Normalize to "reasoning_content" for consistent downstream handling
            return {
                "reasoning_content": reasoning,
                "content": content,
            }

        # Return content only
        return content

    def _execute_tool_calls(
        self,
        messages: list[dict[str, Any]],
        response_message: dict,
        available_functions: dict[str, Any],
        tools: list[dict[str, Any]] | None = None,
        max_rounds: int = 5,
        **kwargs,
    ) -> str:
        """Execute tool calls from LLM response and loop back with results.

        When the LLM returns tool_calls, this method executes them using
        available_functions and feeds the results back to the LLM for a
        final text response. Supports multiple rounds of tool calling.

        Args:
            messages: The conversation messages so far.
            response_message: The LLM response dict containing tool_calls.
            available_functions: Dict of function_name -> callable.
            tools: Tool definitions to include in follow-up calls.
            max_rounds: Maximum tool-call rounds to prevent infinite loops.
            **kwargs: Additional parameters for LLM calls.

        Returns:
            Final text response after tool execution.
        """
        conversation = list(messages)
        current_message = response_message

        for round_num in range(max_rounds):
            tool_calls = current_message.get("tool_calls", [])
            if not tool_calls:
                # No more tool calls -- return content
                return current_message.get("content") or ""

            # Append the assistant message with tool_calls to conversation
            conversation.append(
                {
                    "role": "assistant",
                    "content": current_message.get("content"),
                    "tool_calls": tool_calls,
                }
            )

            # Execute each tool call and append results
            for tc in tool_calls:
                tc_id = tc.get("id", "")
                func_info = tc.get("function", {})
                func_name = func_info.get("name", "")
                func_args_str = func_info.get("arguments", "{}")

                try:
                    func_args = json.loads(func_args_str) if func_args_str else {}
                except json.JSONDecodeError:
                    func_args = {}

                func = available_functions.get(func_name)
                if func is None:
                    result = json.dumps({"error": f"Function '{func_name}' not found"})
                    logger.warning(f"[VLLM] Tool '{func_name}' not in available_functions")
                else:
                    try:
                        logger.info(f"[VLLM] Executing tool '{func_name}' (round {round_num + 1})")
                        raw_result = func(**func_args) if func_args else func()
                        result = str(raw_result) if not isinstance(raw_result, str) else raw_result
                    except Exception as e:
                        logger.exception(f"[VLLM] Tool '{func_name}' execution failed: {e}")
                        result = json.dumps({"error": f"{type(e).__name__}: {str(e)}"})

                conversation.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": result,
                    }
                )

            # Call LLM again with tool results
            client = self._get_client()
            payload = self._build_payload(conversation, tools, **kwargs)
            url = f"{self.base_url}/chat/completions"

            logger.info(f"[VLLM] POST {url} | tool follow-up round {round_num + 1}")
            try:
                response = client.post(
                    url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                )
                response.raise_for_status()
                data = response.json()
            except httpx.TimeoutException as e:
                logger.warning(f"[VLLM] Tool follow-up timed out after {self.timeout}s: {e}")
                raise VLLMConnectionError(
                    f"vLLM tool follow-up timed out after {self.timeout}s. "
                    "Check that vLLM is responsive or increase the timeout.",
                    error_type="timeout",
                ) from e
            except httpx.ConnectError as e:
                logger.warning(f"[VLLM] Tool follow-up connection failed to {self.base_url}: {e}")
                raise VLLMConnectionError(
                    f"Cannot connect to vLLM at {self.base_url}. "
                    "Please check that vLLM is running.",
                    error_type="connection",
                ) from e
            except httpx.HTTPStatusError as e:
                body = e.response.text[:200] if e.response else ""
                logger.warning(f"[VLLM] Tool follow-up HTTP {e.response.status_code}: {body}")
                raise VLLMConnectionError(
                    f"vLLM returned HTTP {e.response.status_code}: {body}",
                    error_type="http",
                ) from e
            except httpx.NetworkError as e:
                logger.warning(f"[VLLM] Tool follow-up network error with {self.base_url}: {e}")
                raise VLLMConnectionError(
                    f"Network error communicating with vLLM at {self.base_url}: {e}",
                    error_type="network",
                ) from e

            parsed = self._parse_response(data)
            if isinstance(parsed, dict) and parsed.get("tool_calls"):
                # Another round of tool calls
                current_message = parsed
            elif isinstance(parsed, dict):
                # Reasoning model response without tool calls
                return parsed.get("content") or parsed.get("reasoning_content") or ""
            else:
                return parsed

        # Exhausted max rounds -- return whatever we have
        logger.warning(f"[VLLM] Exhausted {max_rounds} tool-call rounds")
        return current_message.get("content") or ""

    def call(
        self,
        messages: str | list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        callbacks: Any | None = None,
        available_functions: dict[str, Any] | None = None,
        from_task: "Task | None" = None,
        from_agent: "Agent | None" = None,
        response_model: Any | None = None,
        **kwargs,
    ) -> str | dict:
        """Synchronous call to vLLM (implements BaseLLM.call).

        When tool_calls are returned and available_functions is provided,
        executes the tools and loops back to the LLM with results until
        a final text response is produced. This enables CrewAI agents
        to use vLLM with native function calling.

        Args:
            messages: String prompt or list of message dicts with role and content
            tools: Optional list of tool definitions
            callbacks: Optional callbacks (unused, for compatibility)
            available_functions: Optional dict of callable functions. When
                provided, tool_calls from the LLM are executed automatically
                and results fed back for a final text response.
            from_task: Optional task context (unused)
            from_agent: Optional agent context (unused)
            response_model: Optional response model (unused)
            **kwargs: Additional parameters (temperature, max_tokens, enable_thinking, etc.)

        Returns:
            Response content string, or message dict if tool calls present
            and no available_functions provided
        """
        # Unused parameters for vLLM
        _ = from_task, from_agent, response_model
        # Handle string input (for classifier compatibility)
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]

        logger.debug(f"[VLLM] call() invoked with {len(messages)} messages")
        if tools:
            logger.info(f"[VLLM] Including {len(tools)} tools in payload")
            logger.debug(f"[VLLM] Tool names: {[t.get('function', {}).get('name') for t in tools]}")

        client = self._get_client()
        payload = self._build_payload(messages, tools, **kwargs)
        url = f"{self.base_url}/chat/completions"

        logger.info(f"[VLLM] POST {url} | model={self.model}")
        logger.debug(f"[VLLM] Payload: {payload}")

        try:
            response = client.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException as e:
            logger.warning(f"[VLLM] Request timed out after {self.timeout}s: {e}")
            raise VLLMConnectionError(
                f"vLLM request timed out after {self.timeout}s. "
                "Check that vLLM is responsive or increase the timeout.",
                error_type="timeout",
            ) from e
        except httpx.ConnectError as e:
            logger.warning(f"[VLLM] Connection failed to {self.base_url}: {e}")
            raise VLLMConnectionError(
                f"Cannot connect to vLLM at {self.base_url}. Please check that vLLM is running.",
                error_type="connection",
            ) from e
        except httpx.HTTPStatusError as e:
            body = e.response.text[:200] if e.response else ""
            status_code = e.response.status_code if e.response else 0

            # Targeted retry for transient template parsing errors (XR-E03)
            if (
                status_code == 500
                and "unexpected tokens" in body.lower()
                and not kwargs.get("_retried_template_error")
            ):
                logger.warning(
                    f"[VLLM] Template parsing error (HTTP 500), retrying once. Body: {body}"
                )
                import time

                time.sleep(0.5)  # Brief delay before retry
                kwargs["_retried_template_error"] = True
                return self.call(messages, tools, callbacks, available_functions, **kwargs)

            # vLLM rejects tools when server lacks --enable-auto-tool-choice.
            # Fall back to text-only call so orchestration continues via
            # the text-based JSON path instead of crashing.
            if (
                status_code == 400
                and tools
                and not kwargs.get("_retried_without_tools")
            ):
                logger.warning(
                    f"[VLLM] Server rejected tools (HTTP 400). "
                    "Falling back to text-only call."
                )
                kwargs["_retried_without_tools"] = True
                return self.call(messages, None, callbacks, None, **kwargs)

            logger.warning(f"[VLLM] HTTP {status_code}: {body}")
            raise VLLMConnectionError(
                f"vLLM returned HTTP {status_code}: {body}",
                error_type="http",
            ) from e
        except httpx.NetworkError as e:
            logger.warning(f"[VLLM] Network error communicating with {self.base_url}: {e}")
            raise VLLMConnectionError(
                f"Network error communicating with vLLM at {self.base_url}: {e}",
                error_type="network",
            ) from e

        result = self._parse_response(data)

        # --- 3-path response routing for tool_calls ---
        #
        # Path 1: tool_calls + available_functions -> execute tools (CrewAI path)
        #   CrewAI agents pass available_functions so the LLM can autonomously
        #   call Python functions and loop back for a final text answer.
        #
        # Path 2: tool_calls + tools in request -> return raw dict (orchestrator path)
        #   The orchestrator passes tools (not available_functions) and expects
        #   the raw tool_call dict back so _convert_tool_calls_to_json can
        #   transform it into an orchestration step.
        #
        # Path 3 was removed (Phase 101): The legacy "Action:/Action Input:" text
        #   conversion only triggered when tool_calls existed but NEITHER tools
        #   NOR available_functions was provided. This is dead code because:
        #   - The orchestrator always passes tools (via _call_llm)
        #   - CrewAI always passes available_functions
        #   - Tool_calls without tools in the request means the model hallucinated
        #     tool calls unprompted, which is not a real scenario
        #   The crewai_adapter._parse_action_response() handles Action: text from
        #   CrewAI kickoff results independently and does not depend on this path.

        # Path 1: tool_calls + available_functions -> execute tools (CrewAI)
        if isinstance(result, dict) and result.get("tool_calls") and available_functions:
            logger.info(
                f"[VLLM] Executing {len(result['tool_calls'])} tool_call(s) "
                "via available_functions (CrewAI path)"
            )
            return self._execute_tool_calls(
                messages=messages,
                response_message=result,
                available_functions=available_functions,
                tools=tools,
                **kwargs,
            )

        # Path 2: tool_calls + tools in request -> return raw dict (orchestrator)
        if isinstance(result, dict) and result.get("tool_calls") and tools:
            logger.info(
                f"[VLLM] Returning {len(result['tool_calls'])} tool_call(s) as dict "
                "(native tool calling path -- tools were in request)"
            )
            return result

        # Log which non-tool-call path was taken for debugging
        if isinstance(result, dict) and not result.get("tool_calls"):
            logger.info("[VLLM] Returning text response (no tool_calls in LLM output)")
        elif isinstance(result, str):
            logger.info("[VLLM] Returning text response (string result)")

        return result

    async def acall(
        self,
        messages: str | list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        callbacks: Any | None = None,
        available_functions: dict[str, Any] | None = None,
        from_task: "Task | None" = None,
        from_agent: "Agent | None" = None,
        response_model: Any | None = None,
        **kwargs,
    ) -> str | dict:
        """Asynchronous call to vLLM (implements BaseLLM.acall).

        Has the same 3-path response routing as call():
        - Path 1: tool_calls + available_functions -> execute tools (CrewAI)
        - Path 2: tool_calls + tools in request -> return raw dict (orchestrator)
        - Non-tool-call responses returned as-is

        Args:
            messages: String prompt or list of message dicts with role and content
            tools: Optional list of tool definitions
            callbacks: Optional callbacks (unused, for compatibility)
            available_functions: Optional dict of callable functions. When
                provided, tool_calls from the LLM are executed automatically
                and results fed back for a final text response.
            from_task: Optional task context (unused)
            from_agent: Optional agent context (unused)
            response_model: Optional response model (unused)
            **kwargs: Additional parameters (enable_thinking, temperature, etc.)

        Returns:
            Response content string, or message dict if tool calls present
        """
        # Unused parameters for vLLM
        _ = from_task, from_agent, response_model
        # Handle string input
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]

        client = self._get_async_client()
        payload = self._build_payload(messages, tools, **kwargs)
        url = f"{self.base_url}/chat/completions"

        logger.info(f"[VLLM] POST (async) {url} | model={self.model}")
        logger.debug(f"[VLLM] Payload: {payload}")

        try:
            response = await client.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException as e:
            logger.warning(f"[VLLM] (async) Request timed out after {self.timeout}s: {e}")
            raise VLLMConnectionError(
                f"vLLM request timed out after {self.timeout}s. "
                "Check that vLLM is responsive or increase the timeout.",
                error_type="timeout",
            ) from e
        except httpx.ConnectError as e:
            logger.warning(f"[VLLM] (async) Connection failed to {self.base_url}: {e}")
            raise VLLMConnectionError(
                f"Cannot connect to vLLM at {self.base_url}. Please check that vLLM is running.",
                error_type="connection",
            ) from e
        except httpx.HTTPStatusError as e:
            body = e.response.text[:200] if e.response else ""
            status_code = e.response.status_code if e.response else 0

            # Targeted retry for transient template parsing errors (XR-E03)
            if (
                status_code == 500
                and "unexpected tokens" in body.lower()
                and not kwargs.get("_retried_template_error")
            ):
                logger.warning(
                    f"[VLLM] (async) Template parsing error (HTTP 500), retrying once. Body: {body}"
                )
                await asyncio.sleep(0.5)  # Brief delay before retry
                kwargs["_retried_template_error"] = True
                return await self.acall(messages, tools, callbacks, available_functions, **kwargs)

            # vLLM rejects tools when server lacks --enable-auto-tool-choice.
            if (
                status_code == 400
                and tools
                and not kwargs.get("_retried_without_tools")
            ):
                logger.warning(
                    f"[VLLM] (async) Server rejected tools (HTTP 400). "
                    "Falling back to text-only call."
                )
                kwargs["_retried_without_tools"] = True
                return await self.acall(messages, None, callbacks, None, **kwargs)

            logger.warning(f"[VLLM] (async) HTTP {status_code}: {body}")
            raise VLLMConnectionError(
                f"vLLM returned HTTP {status_code}: {body}",
                error_type="http",
            ) from e
        except httpx.NetworkError as e:
            logger.warning(f"[VLLM] (async) Network error communicating with {self.base_url}: {e}")
            raise VLLMConnectionError(
                f"Network error communicating with vLLM at {self.base_url}: {e}",
                error_type="network",
            ) from e

        result = self._parse_response(data)

        # Path 1: tool_calls + available_functions -> execute tools (CrewAI)
        # _execute_tool_calls is sync (uses httpx.Client), so wrap in thread
        if isinstance(result, dict) and result.get("tool_calls") and available_functions:
            logger.info(
                f"[VLLM] (async) Executing {len(result['tool_calls'])} tool_call(s) "
                "via available_functions (CrewAI path)"
            )
            return await asyncio.to_thread(
                self._execute_tool_calls,
                messages=messages,
                response_message=result,
                available_functions=available_functions,
                tools=tools,
                **kwargs,
            )

        # Path 2: tool_calls + tools in request -> return raw dict (orchestrator)
        if isinstance(result, dict) and result.get("tool_calls") and tools:
            logger.info(
                f"[VLLM] (async) Returning {len(result['tool_calls'])} tool_call(s) as dict "
                "(native tool calling path -- tools were in request)"
            )
            return result

        # Log which non-tool-call path was taken for debugging
        if isinstance(result, dict) and not result.get("tool_calls"):
            logger.info("[VLLM] (async) Returning text response (no tool_calls in LLM output)")
        elif isinstance(result, str):
            logger.info("[VLLM] (async) Returning text response (string result)")

        return result

    async def astream(
        self, messages: str | list[dict[str, str]], callbacks: Any | None = None, **kwargs
    ):
        """Async streaming call to vLLM.

        Yields:
            Dict with either:
            - {"type": "reasoning", "content": str} for thinking content
            - {"type": "content", "content": str} for regular response content
            - str (backward compat) if no reasoning_content present
        """
        # Handle string input
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]

        client = self._get_async_client()
        payload = self._build_payload(messages, **kwargs)
        payload["stream"] = True
        url = f"{self.base_url}/chat/completions"

        enable_thinking = kwargs.get("enable_thinking", False)

        logger.info(f"[VLLM] POST (stream) {url} | model={self.model}")
        logger.debug(f"[VLLM] Payload: {payload}")

        try:
            async with client.stream(
                "POST",
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            ) as response:
                if response.status_code >= 400:
                    await response.aread()
                    raise httpx.HTTPStatusError(
                        f"HTTP {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            delta = data.get("choices", [{}])[0].get("delta", {})

                            # Handle reasoning for thinking models (cross-model compatible)
                            # - Mistral: reasoning_content
                            # - DeepSeek, Qwen, Granite, etc.: reasoning
                            reasoning = delta.get("reasoning") or delta.get("reasoning_content")
                            content = delta.get("content", "")

                            if enable_thinking and reasoning:
                                yield {"type": "reasoning", "content": reasoning}

                            if content:
                                if enable_thinking:
                                    yield {"type": "content", "content": content}
                                else:
                                    yield content  # Backward compatible string yield
                        except json.JSONDecodeError:
                            continue
        except httpx.TimeoutException as e:
            logger.warning(f"[VLLM] (stream) Request timed out after {self.timeout}s: {e}")
            raise VLLMConnectionError(
                f"vLLM streaming request timed out after {self.timeout}s. "
                "Check that vLLM is responsive or increase the timeout.",
                error_type="timeout",
            ) from e
        except httpx.ConnectError as e:
            logger.warning(f"[VLLM] (stream) Connection failed to {self.base_url}: {e}")
            raise VLLMConnectionError(
                f"Cannot connect to vLLM at {self.base_url}. Please check that vLLM is running.",
                error_type="connection",
            ) from e
        except httpx.HTTPStatusError as e:
            body = e.response.text[:200] if hasattr(e.response, "text") else ""
            logger.warning(f"[VLLM] (stream) HTTP {e.response.status_code}: {body}")
            raise VLLMConnectionError(
                f"vLLM returned HTTP {e.response.status_code}: {body}",
                error_type="http",
            ) from e
        except httpx.StreamError as e:
            logger.warning(f"[VLLM] (stream) Stream error from {self.base_url}: {e}")
            raise VLLMConnectionError(
                f"vLLM stream interrupted: {e}",
                error_type="network",
            ) from e
        except httpx.NetworkError as e:
            logger.warning(f"[VLLM] (stream) Network error communicating with {self.base_url}: {e}")
            raise VLLMConnectionError(
                f"Network error communicating with vLLM at {self.base_url}: {e}",
                error_type="network",
            ) from e

    def close(self):
        """Explicitly close HTTP clients to release connections and file descriptors.

        Call this when the VLLMBaseLLM instance is no longer needed (e.g., after
        an orchestration session completes). Prevents connection pool exhaustion
        that causes backend unhealthiness after sequential agent invocations.
        """
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
        if self._async_client is not None:
            try:
                # Schedule async close if we're in an event loop
                import asyncio

                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(self._async_client.aclose())
                except RuntimeError:
                    # No running loop -- force sync close (httpx supports this)
                    try:
                        asyncio.run(self._async_client.aclose())
                    except RuntimeError:
                        pass  # Already closed or no loop available
            except Exception:
                pass
            self._async_client = None

    async def aclose(self):
        """Async close for use in async contexts."""
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
        if self._async_client is not None:
            try:
                await self._async_client.aclose()
            except Exception:
                pass
            self._async_client = None

    def __del__(self):
        """Cleanup HTTP clients on garbage collection (best-effort fallback).

        Prefer calling close() or aclose() explicitly.
        """
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
        # Async client cannot be reliably closed in __del__ (no event loop).
        # If close()/aclose() was not called, log a warning.
        if self._async_client is not None:
            logger.warning(
                "[VLLM] VLLMBaseLLM garbage collected without close() -- "
                "async httpx client may leak. Call close() or aclose() explicitly."
            )

    # CrewAI compatibility properties and methods
    @property
    def model_name(self) -> str:
        """Return model name for CrewAI compatibility."""
        return self.model

    def supports_function_calling(self) -> bool:
        """Check if model supports function calling."""
        return True

    def supports_streaming(self) -> bool:
        """Check if model supports streaming."""
        return True

    def __call__(self, prompt: str, **kwargs) -> str | dict:
        """Make VLLMBaseLLM callable for compatibility with IntentClassifier.

        Converts single prompt string to messages format and calls `.call()`.

        Args:
            prompt: The prompt string to send to the LLM
            **kwargs: Additional parameters passed to `.call()`

        Returns:
            Response content string, or message dict if tool calls present
        """
        return self.call(prompt, **kwargs)

# -----------------------------------------------------------------------------
# Factory function
# -----------------------------------------------------------------------------

def get_vllm_llm(model: str | None = None, base_url: str | None = None, **kwargs) -> VLLMBaseLLM:
    """Create a VLLMBaseLLM instance with environment defaults.

    Args:
        model: Model name (optional, uses VLLM_MODEL env)
        base_url: API base URL (optional, uses VLLM_BASE_URL env)
        **kwargs: Additional VLLMBaseLLM parameters

    Returns:
        Configured VLLMBaseLLM instance
    """
    return VLLMBaseLLM(model=model, base_url=base_url, **kwargs)

# -----------------------------------------------------------------------------
# Convenience wrapper for CrewAI Agent usage
# -----------------------------------------------------------------------------

def create_vllm_for_crewai(**kwargs) -> VLLMBaseLLM:
    """Create a VLLMBaseLLM configured for CrewAI usage.

    Returns an LLM instance that can be passed to CrewAI Agent:

        llm = create_vllm_for_crewai()
        agent = Agent(
            role="...",
            llm=llm,
            ...
        )
    """
    return get_vllm_llm(**kwargs)
