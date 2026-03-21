"""Unit tests for unified event stream."""

class TestChatEvent:
    """Tests for ChatEvent model."""

    def test_token_event(self):
        """Test token event creation."""
        from core.extensions.events import emit_token

        event = emit_token("Hello")
        assert event.type == "token"
        assert event.content == "Hello"
        assert event.timestamp

    def test_thinking_event(self):
        """Test thinking event creation."""
        from core.extensions.events import emit_thinking

        event = emit_thinking("Analyzing...")
        assert event.type == "thinking"
        assert event.content == "Analyzing..."

    def test_tool_events(self):
        """Test tool start/result events."""
        from core.extensions.events import emit_tool_result, emit_tool_start

        start = emit_tool_start("capella_list", {"layer": "LA"})
        assert start.type == "tool_start"
        assert start.metadata["tool"] == "capella_list"
        assert start.metadata["args"]["layer"] == "LA"

        result = emit_tool_result("capella_list", ["item1", "item2"], 150.5)
        assert result.type == "tool_result"
        assert result.metadata["duration_ms"] == 150.5
        assert result.metadata["success"] is True

    def test_agent_events(self):
        """Test agent start/complete events."""
        from core.extensions.events import emit_agent_complete, emit_agent_start

        start = emit_agent_start("CatalogAgent", "List functions")
        assert start.type == "agent_start"
        assert start.metadata["agent"] == "CatalogAgent"
        assert start.metadata["task"] == "List functions"

        complete = emit_agent_complete("CatalogAgent", "Found 10 functions", 500.0)
        assert complete.type == "agent_complete"
        assert complete.metadata["duration_ms"] == 500.0

    def test_flow_events(self):
        """Test flow events."""
        from core.extensions.events import (
            emit_flow_complete,
            emit_flow_start,
            emit_node_complete,
            emit_node_start,
        )

        flow_start = emit_flow_start("analysis", {"input": "test"})
        assert flow_start.type == "flow_start"
        assert flow_start.metadata["flow"] == "analysis"

        node_start = emit_node_start("node_1", "agent", "analysis")
        assert node_start.type == "node_start"

        node_complete = emit_node_complete("node_1", "result", 100.0, ["node_2"])
        assert node_complete.type == "node_complete"
        assert node_complete.metadata["next_nodes"] == ["node_2"]

        flow_complete = emit_flow_complete("analysis", "done", 1000.0)
        assert flow_complete.type == "flow_complete"

    def test_clarify_events(self):
        """Test clarification events."""
        from core.extensions.events import emit_clarify, emit_clarify_response

        clarify = emit_clarify("Which layer?", ["LA", "PA", "SA"])
        assert clarify.type == "clarify"
        assert clarify.content == "Which layer?"
        assert clarify.metadata["options"] == ["LA", "PA", "SA"]

        response = emit_clarify_response("LA", 0)
        assert response.type == "clarify_response"
        assert response.content == "LA"

    def test_completion_events(self):
        """Test completion events."""
        from core.extensions.events import emit_complete, emit_error

        complete = emit_complete("Final response", {"key": "value"})
        assert complete.type == "complete"
        assert complete.content == "Final response"
        assert complete.metadata["exports"]["key"] == "value"

        error = emit_error("Something went wrong", "ERR_001")
        assert error.type == "error"
        assert error.content == "Something went wrong"
        assert error.metadata["code"] == "ERR_001"

    def test_sse_conversion(self):
        """Test SSE format conversion."""
        from core.extensions.events import emit_token

        event = emit_token("Test")
        sse = event.to_sse()

        assert sse.startswith("data: ")
        assert sse.endswith("\n\n")
        # JSON may or may not have spaces after colons depending on serializer
        assert '"type":' in sse and '"token"' in sse

    def test_openai_sse_format(self):
        """Test OpenAI-compatible SSE format."""
        from core.extensions.events import emit_token, to_openai_sse

        event = emit_token("Hello")
        sse = to_openai_sse(event)

        assert "chat.completion.chunk" in sse
        assert '"content": "Hello"' in sse

class TestEventDispatchingAndHandling:
    """Tests for event subscription and dispatch patterns."""

    def test_event_to_ws_format(self):
        """Test WebSocket format conversion."""
        from core.extensions.events import emit_token

        event = emit_token("Test")
        ws_msg = event.to_ws()

        assert ws_msg["type"] == "event"
        assert "data" in ws_msg
        assert ws_msg["data"]["type"] == "token"
        assert ws_msg["data"]["content"] == "Test"

    def test_multiple_event_types_in_sequence(self):
        """Test creating multiple different event types."""
        from core.extensions.events import (
            emit_agent_start,
            emit_complete,
            emit_thinking,
            emit_token,
            emit_tool_start,
        )

        events = [
            emit_thinking("Analyzing..."),
            emit_tool_start("search", {"query": "test"}),
            emit_agent_start("TestAgent", "Do task"),
            emit_token("Result"),
            emit_complete("Done"),
        ]

        assert len(events) == 5
        assert events[0].type == "thinking"
        assert events[1].type == "tool_start"
        assert events[2].type == "agent_start"
        assert events[3].type == "token"
        assert events[4].type == "complete"

    def test_event_metadata_persistence(self):
        """Test that metadata is properly stored in events."""
        from core.extensions.events import emit_tool_start

        event = emit_tool_start("my_tool", {"arg1": "val1", "arg2": 123})

        assert event.metadata["tool"] == "my_tool"
        assert event.metadata["args"]["arg1"] == "val1"
        assert event.metadata["args"]["arg2"] == 123

    def test_async_event_handler_pattern(self):
        """Test pattern for async event handlers."""
        import asyncio

        from core.extensions.events import emit_token

        async def async_handler(event):
            await asyncio.sleep(0.001)
            return event.content

        event = emit_token("Test")
        result = asyncio.run(async_handler(event))

        assert result == "Test"

    def test_event_filtering_by_type(self):
        """Test filtering events by type."""
        from core.extensions.events import emit_error, emit_thinking, emit_token

        events = [
            emit_token("chunk1"),
            emit_thinking("thought"),
            emit_token("chunk2"),
            emit_error("oops"),
        ]

        tokens = [e for e in events if e.type == "token"]
        errors = [e for e in events if e.type == "error"]

        assert len(tokens) == 2
        assert len(errors) == 1

    def test_tool_result_with_error(self):
        """Test tool_result event with error."""
        from core.extensions.events import emit_tool_result

        result = emit_tool_result("failing_tool", None, 100.0, success=False)

        assert result.type == "tool_result"
        assert result.metadata["success"] is False
        assert result.metadata["duration_ms"] == 100.0

    def test_state_export_event(self):
        """Test state export event creation."""
        from core.extensions.events import emit_state_export

        exports = {"mbse.session_id": "sess_123", "mbse.model_path": "/path"}
        event = emit_state_export(exports)

        assert event.type == "state_export"
        assert event.metadata["exports"]["mbse.session_id"] == "sess_123"
        assert event.metadata["exports"]["mbse.model_path"] == "/path"

    def test_state_conflict_event(self):
        """Test state conflict event creation."""
        from core.extensions.events import emit_state_conflict

        candidates = [
            {"value": "sess_1", "source": "tool_a"},
            {"value": "sess_2", "source": "tool_b"},
        ]
        event = emit_state_conflict("mbse.session_id", candidates, "my_tool")

        assert event.type == "state_conflict"
        assert "session id" in event.content.lower()
        assert event.metadata["state_key"] == "mbse.session_id"
        assert len(event.metadata["candidates"]) == 2
        assert event.metadata["required_by"] == "my_tool"

    def test_openai_sse_thinking_format(self):
        """Test OpenAI SSE format for thinking events."""
        from core.extensions.events import emit_thinking, to_openai_sse

        event = emit_thinking("Let me think...")
        sse = to_openai_sse(event)

        assert "reasoning_content" in sse
        assert "Let me think..." in sse

    def test_openai_sse_complete_format(self):
        """Test OpenAI SSE format for complete events."""
        from core.extensions.events import emit_complete, to_openai_sse

        event = emit_complete("Final answer")
        sse = to_openai_sse(event)

        assert "finish_reason" in sse
        assert "stop" in sse

    def test_openai_sse_error_format(self):
        """Test OpenAI SSE format for error events."""
        from core.extensions.events import emit_error, to_openai_sse

        event = emit_error("Something failed")
        sse = to_openai_sse(event)

        assert "finish_reason" in sse
        assert "error" in sse

    def test_emit_done_termination(self):
        """Test emit_done SSE termination message."""
        from core.extensions.events import emit_done

        done_msg = emit_done()
        assert done_msg == "data: [DONE]\n\n"

    def test_event_timestamp_auto_generation(self):
        """Test that events automatically generate timestamps."""
        from core.extensions.events import emit_token

        event = emit_token("Test")
        assert event.timestamp is not None
        assert len(event.timestamp) > 0

    def test_clarify_with_context(self):
        """Test clarify event with additional context."""
        from core.extensions.events import emit_clarify

        context = {"tool": "my_tool", "state_key": "mbse.layer"}
        event = emit_clarify("Which layer?", ["LA", "PA"], context)

        assert event.metadata["context"]["tool"] == "my_tool"
        assert event.metadata["context"]["state_key"] == "mbse.layer"

    def test_complete_with_usage_stats(self):
        """Test complete event with usage statistics."""
        from core.extensions.events import emit_complete

        usage = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
        event = emit_complete("Response", usage=usage)

        assert event.metadata["usage"]["prompt_tokens"] == 100
        assert event.metadata["usage"]["completion_tokens"] == 50

    def test_error_with_details(self):
        """Test error event with detailed information."""
        from core.extensions.events import emit_error

        details = {"stack_trace": "...", "line": 42}
        event = emit_error("Error occurred", code="ERR_INTERNAL", details=details)

        assert event.metadata["code"] == "ERR_INTERNAL"
        assert event.metadata["details"]["line"] == 42
