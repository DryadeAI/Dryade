"""
Unit tests for vllm plugin.

Tests cover:
1. Plugin protocol implementation
2. VLLMBaseLLM initialization and URL normalization
3. Message sanitization
4. Payload building
5. Response parsing (content, tool calls, reasoning)
6. CrewAI compatibility properties
7. Factory functions
8. Error handling (VLLMConnectionError for httpx errors)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

@pytest.mark.unit
class TestVLLMPlugin:
    """Tests for VLLMPlugin protocol implementation."""

    def test_plugin_protocol_attributes(self):
        """Test plugin has required protocol attributes."""
        from plugins.vllm.plugin import VLLMPlugin

        plugin = VLLMPlugin()
        assert plugin.name == "vllm"
        assert plugin.version == "1.0.0"
        assert hasattr(plugin, "register")
        assert hasattr(plugin, "startup")
        assert hasattr(plugin, "shutdown")

    def test_plugin_register_noop(self):
        """Test register is a no-op for vllm."""
        from plugins.vllm.plugin import VLLMPlugin

        plugin = VLLMPlugin()
        registry = MagicMock()
        plugin.register(registry)
        # Should not call any registry methods
        registry.register.assert_not_called()

@pytest.mark.unit
class TestVLLMBaseLLMInit:
    """Tests for VLLMBaseLLM initialization."""

    def test_default_initialization(self):
        """Test default init uses environment defaults."""
        from core.providers.vllm_llm import VLLMBaseLLM

        llm = VLLMBaseLLM()
        assert llm.model == "local-llm"
        assert llm.base_url.endswith("/v1")
        assert llm.temperature == 0.7
        assert llm.max_tokens == 4096

    def test_custom_initialization(self):
        """Test custom parameters are stored correctly."""
        from core.providers.vllm_llm import VLLMBaseLLM

        llm = VLLMBaseLLM(
            model="mistral-7b",
            base_url="http://gpu-server:8000",
            temperature=0.5,
            max_tokens=2048,
            timeout=60.0,
        )
        assert llm.model == "mistral-7b"
        assert llm.base_url == "http://gpu-server:8000/v1"
        assert llm.temperature == 0.5
        assert llm.max_tokens == 2048
        assert llm.timeout == 60.0

@pytest.mark.unit
class TestVLLMURLNormalization:
    """Tests for base URL normalization."""

    def test_adds_v1_suffix(self):
        """Test URL without /v1 gets it added."""
        from core.providers.vllm_llm import VLLMBaseLLM

        assert VLLMBaseLLM._normalize_base_url("http://host:8000") == "http://host:8000/v1"

    def test_strips_trailing_slash_and_adds_v1(self):
        """Test trailing slash is stripped before adding /v1."""
        from core.providers.vllm_llm import VLLMBaseLLM

        assert VLLMBaseLLM._normalize_base_url("http://host:8000/") == "http://host:8000/v1"

    def test_preserves_existing_v1(self):
        """Test URL already ending in /v1 is unchanged."""
        from core.providers.vllm_llm import VLLMBaseLLM

        assert VLLMBaseLLM._normalize_base_url("http://host:8000/v1") == "http://host:8000/v1"

    def test_strips_trailing_slash_from_v1(self):
        """Test /v1/ trailing slash is stripped."""
        from core.providers.vllm_llm import VLLMBaseLLM

        assert VLLMBaseLLM._normalize_base_url("http://host:8000/v1/") == "http://host:8000/v1"

@pytest.mark.unit
class TestVLLMMessageSanitization:
    """Tests for message sanitization logic."""

    def test_empty_messages(self):
        """Test empty messages pass through."""
        from core.providers.vllm_llm import VLLMBaseLLM

        llm = VLLMBaseLLM()
        assert llm._sanitize_messages([]) == []

    def test_normal_conversation(self):
        """Test normal user/assistant messages pass through."""
        from core.providers.vllm_llm import VLLMBaseLLM

        llm = VLLMBaseLLM()
        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ]
        result = llm._sanitize_messages(messages)
        assert len(result) == 3
        assert result[0]["role"] == "system"
        assert result[1]["role"] == "user"
        assert result[2]["role"] == "assistant"

    def test_consecutive_system_messages_merged(self):
        """Test consecutive system messages are consolidated."""
        from core.providers.vllm_llm import VLLMBaseLLM

        llm = VLLMBaseLLM()
        messages = [
            {"role": "system", "content": "System 1"},
            {"role": "system", "content": "System 2"},
            {"role": "user", "content": "Hello"},
        ]
        result = llm._sanitize_messages(messages)
        assert len(result) == 2
        assert "System 1" in result[0]["content"]
        assert "System 2" in result[0]["content"]

    def test_system_after_assistant_merged_into_next_user(self):
        """Test system message after assistant is merged into next user message."""
        from core.providers.vllm_llm import VLLMBaseLLM

        llm = VLLMBaseLLM()
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
            {"role": "system", "content": "Extra instructions"},
            {"role": "user", "content": "Follow up"},
        ]
        result = llm._sanitize_messages(messages)
        assert len(result) == 3
        # The system content should be prepended to the user message
        assert "Extra instructions" in result[2]["content"]
        assert "Follow up" in result[2]["content"]

@pytest.mark.unit
class TestVLLMPayloadBuilding:
    """Tests for API request payload building."""

    def test_basic_payload(self):
        """Test basic payload structure."""
        from core.providers.vllm_llm import VLLMBaseLLM

        llm = VLLMBaseLLM(model="test-model")
        messages = [{"role": "user", "content": "Hello"}]
        payload = llm._build_payload(messages)
        assert payload["model"] == "test-model"
        assert len(payload["messages"]) == 1
        assert "temperature" in payload
        assert "max_tokens" in payload
        assert "extra_body" in payload

    def test_payload_with_tools(self):
        """Test payload includes tools when provided."""
        from core.providers.vllm_llm import VLLMBaseLLM

        llm = VLLMBaseLLM()
        tools = [{"function": {"name": "test_tool"}}]
        payload = llm._build_payload([{"role": "user", "content": "Hello"}], tools=tools)
        assert "tools" in payload
        assert payload["tool_choice"] == "auto"

    def test_payload_continue_final_message(self):
        """Test payload sets continue_final_message when last message is assistant."""
        from core.providers.vllm_llm import VLLMBaseLLM

        llm = VLLMBaseLLM()
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "I will"},
        ]
        payload = llm._build_payload(messages)
        assert payload["extra_body"]["continue_final_message"] is True
        assert payload["extra_body"]["add_generation_prompt"] is False

    def test_payload_enable_thinking(self):
        """Test payload includes chat_template_kwargs for thinking mode."""
        from core.providers.vllm_llm import VLLMBaseLLM

        llm = VLLMBaseLLM()
        messages = [{"role": "user", "content": "Think carefully"}]
        payload = llm._build_payload(messages, enable_thinking=True)
        assert "chat_template_kwargs" in payload["extra_body"]
        assert payload["extra_body"]["chat_template_kwargs"]["enable_thinking"] is True

@pytest.mark.unit
class TestVLLMResponseParsing:
    """Tests for response parsing."""

    def test_parse_content_response(self):
        """Test parsing a normal content response."""
        from core.providers.vllm_llm import VLLMBaseLLM

        llm = VLLMBaseLLM()
        data = {"choices": [{"message": {"content": "Hello world"}}]}
        result = llm._parse_response(data)
        assert result == "Hello world"

    def test_parse_tool_calls_response(self):
        """Test parsing a tool call response."""
        from core.providers.vllm_llm import VLLMBaseLLM

        llm = VLLMBaseLLM()
        tool_calls = [{"id": "1", "function": {"name": "test"}}]
        data = {"choices": [{"message": {"content": "", "tool_calls": tool_calls}}]}
        result = llm._parse_response(data)
        assert isinstance(result, dict)
        assert "tool_calls" in result

    def test_parse_reasoning_response(self):
        """Test parsing a reasoning model response."""
        from core.providers.vllm_llm import VLLMBaseLLM

        llm = VLLMBaseLLM()
        data = {
            "choices": [
                {
                    "message": {
                        "content": "The answer is 42",
                        "reasoning_content": "Let me think...",
                    }
                }
            ]
        }
        result = llm._parse_response(data)
        assert isinstance(result, dict)
        assert result["reasoning_content"] == "Let me think..."
        assert result["content"] == "The answer is 42"

    def test_parse_empty_response(self):
        """Test parsing an empty response gracefully."""
        from core.providers.vllm_llm import VLLMBaseLLM

        llm = VLLMBaseLLM()
        data = {"choices": [{"message": {}}]}
        result = llm._parse_response(data)
        assert result == ""

@pytest.mark.unit
class TestVLLMCrewAICompat:
    """Tests for CrewAI compatibility."""

    def test_model_name_property(self):
        """Test model_name returns model."""
        from core.providers.vllm_llm import VLLMBaseLLM

        llm = VLLMBaseLLM(model="test-model")
        assert llm.model_name == "test-model"

    def test_supports_function_calling(self):
        """Test supports_function_calling returns True."""
        from core.providers.vllm_llm import VLLMBaseLLM

        llm = VLLMBaseLLM()
        assert llm.supports_function_calling() is True

    def test_supports_streaming(self):
        """Test supports_streaming returns True."""
        from core.providers.vllm_llm import VLLMBaseLLM

        llm = VLLMBaseLLM()
        assert llm.supports_streaming() is True

@pytest.mark.unit
class TestVLLMFactoryFunctions:
    """Tests for factory functions."""

    def test_get_vllm_llm(self):
        """Test get_vllm_llm creates VLLMBaseLLM instance."""
        from core.providers.vllm_llm import VLLMBaseLLM, get_vllm_llm

        llm = get_vllm_llm(model="test-model")
        assert isinstance(llm, VLLMBaseLLM)
        assert llm.model == "test-model"

    def test_create_vllm_for_crewai(self):
        """Test create_vllm_for_crewai creates instance."""
        from core.providers.vllm_llm import VLLMBaseLLM, create_vllm_for_crewai

        llm = create_vllm_for_crewai()
        assert isinstance(llm, VLLMBaseLLM)

@pytest.mark.unit
class TestVLLMToolCallsFallback:
    """Tests for tool_calls behavior when available_functions not provided."""

    def test_tool_calls_returned_as_dict_without_available_functions_or_tools(self):
        """When tool_calls returned but no available_functions and no tools,
        result is the raw message dict (Path 3 / Action: text was removed in Phase 101).
        This scenario is abnormal (model hallucinated tool_calls unprompted),
        but should not crash."""
        from core.providers.vllm_llm import VLLMBaseLLM

        llm = VLLMBaseLLM()

        # Simulate vLLM response with tool_calls
        api_response = {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "function": {
                                    "name": "capella_list",
                                    "arguments": '{"session_id": "abc", "element_type": "LogicalFunction"}',
                                },
                            }
                        ],
                    }
                }
            ]
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = api_response
        mock_response.raise_for_status = MagicMock()

        with patch.object(llm, "_get_client") as mock_client_factory:
            mock_client = MagicMock()
            mock_client.post.return_value = mock_response
            mock_client_factory.return_value = mock_client

            # Call WITHOUT available_functions and WITHOUT tools
            result = llm.call(
                messages=[{"role": "user", "content": "List functions"}],
            )

        # With Path 3 removed, the raw message dict falls through both Path 1 and Path 2
        # and is returned as-is (a dict with tool_calls)
        assert isinstance(result, dict)
        assert "tool_calls" in result

    def test_tool_calls_executed_with_available_functions(self):
        """When tool_calls returned and available_functions provided, execute them."""
        from core.providers.vllm_llm import VLLMBaseLLM

        llm = VLLMBaseLLM()

        # First API response: tool_calls
        tool_calls_response = {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "function": {
                                    "name": "my_tool",
                                    "arguments": '{"x": 1}',
                                },
                            }
                        ],
                    }
                }
            ]
        }

        # Second API response: final text after tool execution
        final_response = {
            "choices": [
                {
                    "message": {
                        "content": "Tool result: 42",
                    }
                }
            ]
        }

        mock_response_1 = MagicMock()
        mock_response_1.status_code = 200
        mock_response_1.json.return_value = tool_calls_response
        mock_response_1.raise_for_status = MagicMock()

        mock_response_2 = MagicMock()
        mock_response_2.status_code = 200
        mock_response_2.json.return_value = final_response
        mock_response_2.raise_for_status = MagicMock()

        mock_tool = MagicMock(return_value="42")

        with patch.object(llm, "_get_client") as mock_client_factory:
            mock_client = MagicMock()
            mock_client.post.side_effect = [mock_response_1, mock_response_2]
            mock_client_factory.return_value = mock_client

            # Call WITH available_functions
            result = llm.call(
                messages=[{"role": "user", "content": "Call my tool"}],
                available_functions={"my_tool": mock_tool},
            )

        # Tool should have been called
        mock_tool.assert_called_once_with(x=1)
        # Result should be the final text
        assert result == "Tool result: 42"

# ---------------------------------------------------------------------------
# Shared mock API responses for response routing tests
# ---------------------------------------------------------------------------

TOOL_CALL_API_RESPONSE = {
    "choices": [
        {
            "message": {
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "list_directory",
                            "arguments": '{"path": "/home"}',
                        },
                    }
                ],
            }
        }
    ],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
}

TEXT_API_RESPONSE = {
    "choices": [
        {
            "message": {
                "content": "Here are the files in /home...",
                "tool_calls": None,
            }
        }
    ],
    "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
}

SAMPLE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List directory contents",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
            },
        },
    }
]

def _make_mock_http_response(api_response):
    """Create a mock httpx response from an API response dict."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = api_response
    resp.raise_for_status = MagicMock()
    return resp

@pytest.mark.unit
class TestVLLMToolCallResponseRouting:
    """Tests for the 3-path response routing in VLLMBaseLLM.call() and acall().

    Phase 101-02: Exercises actual HTTP response routing (not mocked at call() level).
    Each test constructs a mock vLLM API response and verifies the correct path is taken.
    """

    def test_tool_calls_returned_as_dict_when_tools_in_request(self):
        """Path 2: call() with tools, no available_functions -> return raw dict."""
        from core.providers.vllm_llm import VLLMBaseLLM

        llm = VLLMBaseLLM()
        mock_resp = _make_mock_http_response(TOOL_CALL_API_RESPONSE)

        with patch.object(llm, "_get_client") as mock_factory:
            mock_client = MagicMock()
            mock_client.post.return_value = mock_resp
            mock_factory.return_value = mock_client

            result = llm.call(
                messages=[{"role": "user", "content": "List files"}],
                tools=SAMPLE_TOOLS,
            )

        assert isinstance(result, dict)
        assert "tool_calls" in result
        assert result["tool_calls"][0]["function"]["name"] == "list_directory"

    def test_tool_calls_executed_when_available_functions_present(self):
        """Path 1: call() with available_functions -> _execute_tool_calls called."""
        from core.providers.vllm_llm import VLLMBaseLLM

        llm = VLLMBaseLLM()
        mock_resp = _make_mock_http_response(TOOL_CALL_API_RESPONSE)

        with patch.object(llm, "_get_client") as mock_factory:
            mock_client = MagicMock()
            mock_client.post.return_value = mock_resp
            mock_factory.return_value = mock_client

            with patch.object(
                llm, "_execute_tool_calls", return_value="executed result"
            ) as mock_exec:
                result = llm.call(
                    messages=[{"role": "user", "content": "List files"}],
                    available_functions={"list_directory": lambda path: "files"},
                )

        mock_exec.assert_called_once()
        assert result == "executed result"

    def test_tool_calls_converted_to_text_when_no_tools_no_available_functions(self):
        """No Path 1 or Path 2: call() with no tools, no available_functions,
        vLLM returns tool_calls -> falls through, returns raw dict (no text conversion)."""
        from core.providers.vllm_llm import VLLMBaseLLM

        llm = VLLMBaseLLM()
        mock_resp = _make_mock_http_response(TOOL_CALL_API_RESPONSE)

        with patch.object(llm, "_get_client") as mock_factory:
            mock_client = MagicMock()
            mock_client.post.return_value = mock_resp
            mock_factory.return_value = mock_client

            result = llm.call(
                messages=[{"role": "user", "content": "List files"}],
            )

        # With Path 3 removed, raw dict falls through
        assert isinstance(result, dict)
        assert "tool_calls" in result

    def test_available_functions_takes_priority_over_dict_return(self):
        """Path 1 before Path 2: call() with tools AND available_functions ->
        available_functions path (execute) wins."""
        from core.providers.vllm_llm import VLLMBaseLLM

        llm = VLLMBaseLLM()
        mock_resp = _make_mock_http_response(TOOL_CALL_API_RESPONSE)

        with patch.object(llm, "_get_client") as mock_factory:
            mock_client = MagicMock()
            mock_client.post.return_value = mock_resp
            mock_factory.return_value = mock_client

            with patch.object(llm, "_execute_tool_calls", return_value="executed") as mock_exec:
                result = llm.call(
                    messages=[{"role": "user", "content": "List files"}],
                    tools=SAMPLE_TOOLS,
                    available_functions={"list_directory": lambda path: "files"},
                )

        # Path 1 (available_functions) should win over Path 2 (tools -> dict)
        mock_exec.assert_called_once()
        assert result == "executed"

    @pytest.mark.asyncio
    async def test_acall_returns_dict_when_tools_in_request(self):
        """Path 2 async: acall() with tools, no available_functions -> return raw dict."""
        from core.providers.vllm_llm import VLLMBaseLLM

        llm = VLLMBaseLLM()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = TOOL_CALL_API_RESPONSE
        mock_resp.raise_for_status = MagicMock()

        mock_async_client = MagicMock()
        mock_async_client.post = AsyncMock(return_value=mock_resp)

        with patch.object(llm, "_get_async_client", return_value=mock_async_client):
            result = await llm.acall(
                messages=[{"role": "user", "content": "List files"}],
                tools=SAMPLE_TOOLS,
            )

        assert isinstance(result, dict)
        assert "tool_calls" in result
        assert result["tool_calls"][0]["function"]["name"] == "list_directory"

    @pytest.mark.asyncio
    async def test_acall_text_fallback_when_no_tools(self):
        """acall() with no tools, vLLM returns text -> returns string."""
        from core.providers.vllm_llm import VLLMBaseLLM

        llm = VLLMBaseLLM()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = TEXT_API_RESPONSE
        mock_resp.raise_for_status = MagicMock()

        mock_async_client = MagicMock()
        mock_async_client.post = AsyncMock(return_value=mock_resp)

        with patch.object(llm, "_get_async_client", return_value=mock_async_client):
            result = await llm.acall(
                messages=[{"role": "user", "content": "List files"}],
            )

        assert isinstance(result, str)
        assert "Here are the files" in result

    def test_normal_text_response_unaffected(self):
        """call() with tools, vLLM returns normal text (no tool_calls) -> string."""
        from core.providers.vllm_llm import VLLMBaseLLM

        llm = VLLMBaseLLM()
        mock_resp = _make_mock_http_response(TEXT_API_RESPONSE)

        with patch.object(llm, "_get_client") as mock_factory:
            mock_client = MagicMock()
            mock_client.post.return_value = mock_resp
            mock_factory.return_value = mock_client

            result = llm.call(
                messages=[{"role": "user", "content": "Hello"}],
                tools=SAMPLE_TOOLS,
            )

        assert isinstance(result, str)
        assert "Here are the files" in result

# ---------------------------------------------------------------------------
# Error handling tests (Phase 103-02)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestVLLMErrorHandling:
    """Tests for VLLMConnectionError on httpx transport errors.

    Phase 103: VLLMBaseLLM wraps httpx exceptions into VLLMConnectionError
    with error_type field for duck-typed detection in ThinkingProvider.
    """

    def test_call_raises_vllm_connection_error_on_connect_error(self):
        """call() raises VLLMConnectionError(error_type='connection') on httpx.ConnectError."""
        from core.providers.vllm_llm import VLLMBaseLLM, VLLMConnectionError

        llm = VLLMBaseLLM()

        with patch.object(llm, "_get_client") as mock_factory:
            mock_client = MagicMock()
            mock_client.post.side_effect = httpx.ConnectError("Connection refused")
            mock_factory.return_value = mock_client

            with pytest.raises(VLLMConnectionError) as exc_info:
                llm.call(messages=[{"role": "user", "content": "Hello"}])

        assert exc_info.value.error_type == "connection"
        assert "Cannot connect" in str(exc_info.value)

    def test_call_raises_vllm_connection_error_on_timeout(self):
        """call() raises VLLMConnectionError(error_type='timeout') on httpx.TimeoutException."""
        from core.providers.vllm_llm import VLLMBaseLLM, VLLMConnectionError

        llm = VLLMBaseLLM()

        with patch.object(llm, "_get_client") as mock_factory:
            mock_client = MagicMock()
            mock_client.post.side_effect = httpx.TimeoutException("timed out")
            mock_factory.return_value = mock_client

            with pytest.raises(VLLMConnectionError) as exc_info:
                llm.call(messages=[{"role": "user", "content": "Hello"}])

        assert exc_info.value.error_type == "timeout"
        assert "timed out" in str(exc_info.value)

    def test_call_raises_vllm_connection_error_on_http_status_error(self):
        """call() raises VLLMConnectionError(error_type='http') on httpx.HTTPStatusError."""
        from core.providers.vllm_llm import VLLMBaseLLM, VLLMConnectionError

        llm = VLLMBaseLLM()

        mock_request = httpx.Request("POST", "http://localhost:8000/v1/chat/completions")
        mock_response = httpx.Response(500, request=mock_request, text="Internal Server Error")

        with patch.object(llm, "_get_client") as mock_factory:
            mock_client = MagicMock()
            # post() returns the response, then raise_for_status raises
            mock_resp = MagicMock()
            mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                "500", request=mock_request, response=mock_response
            )
            mock_client.post.return_value = mock_resp
            mock_factory.return_value = mock_client

            with pytest.raises(VLLMConnectionError) as exc_info:
                llm.call(messages=[{"role": "user", "content": "Hello"}])

        assert exc_info.value.error_type == "http"
        assert "500" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_acall_raises_vllm_connection_error_on_connect_error(self):
        """acall() raises VLLMConnectionError(error_type='connection') on httpx.ConnectError."""
        from core.providers.vllm_llm import VLLMBaseLLM, VLLMConnectionError

        llm = VLLMBaseLLM()

        mock_async_client = MagicMock()
        mock_async_client.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

        with patch.object(llm, "_get_async_client", return_value=mock_async_client):
            with pytest.raises(VLLMConnectionError) as exc_info:
                await llm.acall(messages=[{"role": "user", "content": "Hello"}])

        assert exc_info.value.error_type == "connection"

    @pytest.mark.asyncio
    async def test_acall_raises_vllm_connection_error_on_timeout(self):
        """acall() raises VLLMConnectionError(error_type='timeout') on httpx.TimeoutException."""
        from core.providers.vllm_llm import VLLMBaseLLM, VLLMConnectionError

        llm = VLLMBaseLLM()

        mock_async_client = MagicMock()
        mock_async_client.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))

        with patch.object(llm, "_get_async_client", return_value=mock_async_client):
            with pytest.raises(VLLMConnectionError) as exc_info:
                await llm.acall(messages=[{"role": "user", "content": "Hello"}])

        assert exc_info.value.error_type == "timeout"

    @pytest.mark.asyncio
    async def test_astream_raises_vllm_connection_error_on_connect_error(self):
        """astream() raises VLLMConnectionError(error_type='connection') on httpx.ConnectError."""
        from core.providers.vllm_llm import VLLMBaseLLM, VLLMConnectionError

        llm = VLLMBaseLLM()

        mock_async_client = MagicMock()
        # stream() context manager raises on __aenter__
        mock_cm = AsyncMock()
        mock_cm.__aenter__.side_effect = httpx.ConnectError("Connection refused")
        mock_async_client.stream.return_value = mock_cm

        with patch.object(llm, "_get_async_client", return_value=mock_async_client):
            with pytest.raises(VLLMConnectionError) as exc_info:
                async for _ in llm.astream(messages=[{"role": "user", "content": "Hello"}]):
                    pass

        assert exc_info.value.error_type == "connection"

    @pytest.mark.asyncio
    async def test_astream_raises_vllm_connection_error_on_timeout(self):
        """astream() raises VLLMConnectionError(error_type='timeout') on httpx.TimeoutException."""
        from core.providers.vllm_llm import VLLMBaseLLM, VLLMConnectionError

        llm = VLLMBaseLLM()

        mock_async_client = MagicMock()
        # stream() context manager raises on __aenter__
        mock_cm = AsyncMock()
        mock_cm.__aenter__.side_effect = httpx.TimeoutException("timed out")
        mock_async_client.stream.return_value = mock_cm

        with patch.object(llm, "_get_async_client", return_value=mock_async_client):
            with pytest.raises(VLLMConnectionError) as exc_info:
                async for _ in llm.astream(messages=[{"role": "user", "content": "Hello"}]):
                    pass

        assert exc_info.value.error_type == "timeout"

    def test_execute_tool_calls_raises_on_connect_error(self):
        """_execute_tool_calls raises VLLMConnectionError on httpx.ConnectError."""
        from core.providers.vllm_llm import VLLMBaseLLM, VLLMConnectionError

        llm = VLLMBaseLLM()

        # response_message with a tool_call
        response_message = {
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "function": {"name": "my_tool", "arguments": '{"x": 1}'},
                }
            ],
        }

        mock_tool = MagicMock(return_value="42")

        with patch.object(llm, "_get_client") as mock_factory:
            mock_client = MagicMock()
            # Follow-up POST (after tool execution) raises ConnectError
            mock_client.post.side_effect = httpx.ConnectError("Connection refused")
            mock_factory.return_value = mock_client

            with pytest.raises(VLLMConnectionError) as exc_info:
                llm._execute_tool_calls(
                    messages=[{"role": "user", "content": "Call tool"}],
                    response_message=response_message,
                    available_functions={"my_tool": mock_tool},
                )

        assert exc_info.value.error_type == "connection"
        mock_tool.assert_called_once_with(x=1)
