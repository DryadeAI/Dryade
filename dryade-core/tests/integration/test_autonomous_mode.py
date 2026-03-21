"""Integration tests for autonomous chat mode.

Tests the complete ReAct execution flow:
- MCP tools discoverable as skills
- Real skill execution (no LLM hallucination)
- Thinking events with agent field
- ASK_HUMAN clarify blocking behavior
"""

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest

from core.autonomous.chat_adapter import (
    LLMThinkingProvider,
    RuntimeSkillExecutor,
    _execution_clarify_events,
    _execution_clarify_responses,
    stream_react_execution,
    submit_autonomous_clarification,
)
from core.extensions.events import emit_thinking
from core.skills.models import Skill, SkillMetadata
from core.skills.registry import get_skill_registry

class TestMCPSkillDiscovery:
    """Test that MCP tools are discoverable as skills."""

    def test_registry_includes_mcp_tools(self):
        """Verify SkillRegistry loads MCP tools."""
        registry = get_skill_registry()
        all_skills = registry.get_all_skills()

        # Check for MCP-bridged skills
        mcp_skills = [
            s for s in all_skills if s.metadata and s.metadata.extra.get("source") == "mcp_bridge"
        ]

        # Note: MCP tools may not be available in all test environments
        # If no MCP skills found, test passes but logs a warning
        if len(mcp_skills) == 0:
            pytest.skip("No MCP skills found in registry (MCP bridge may not be configured)")

        # Each MCP skill should have callable
        for skill in mcp_skills:
            run_block = skill.metadata.extra.get("run")
            assert run_block is not None, f"{skill.name} has no run block"
            assert run_block.get("type") == "callable", f"{skill.name} is not callable type"
            assert run_block.get("callable") is not None, f"{skill.name} has no callable"

    def test_capella_tools_present(self):
        """Verify capella_* tools are available when MCP is configured."""
        registry = get_skill_registry()
        all_skills = registry.get_all_skills()
        skill_names = [s.name for s in all_skills]

        # capella tools are optional - skip if not available
        capella_skills = [n for n in skill_names if n.startswith("capella_")]
        if len(capella_skills) == 0:
            pytest.skip("No capella tools found (MCP capella server may not be configured)")

        # If present, verify they have expected structure
        for skill_name in capella_skills:
            skill = registry.get_skill(skill_name)
            assert skill is not None
            assert skill.metadata is not None
            assert skill.metadata.extra.get("source") == "mcp_bridge"

class TestSkillExecution:
    """Test that skills execute with real output."""

    @pytest.fixture
    def executor(self):
        return RuntimeSkillExecutor()

    @pytest.mark.asyncio
    async def test_skill_without_run_raises_error(self, executor):
        """Skills without run: block should raise RuntimeError."""
        skill = Skill(
            name="test_no_run",
            description="Test skill without run block",
            instructions="Do nothing",
            metadata=SkillMetadata(extra={}),
            skill_dir="<test>",
        )

        with pytest.raises(RuntimeError) as exc_info:
            await executor.execute_skill(skill, {}, {})

        assert "no executable run" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_callable_skill_executes(self, executor):
        """Skills with callable run: blocks should execute the function."""
        # Create a mock callable
        mock_func = MagicMock(return_value="Mock result")

        skill = Skill(
            name="test_callable",
            description="Test callable skill",
            instructions="Execute callable",
            metadata=SkillMetadata(
                extra={
                    "run": {"type": "callable", "callable": mock_func},
                    "source": "test",
                }
            ),
            skill_dir="<test>",
        )

        result = await executor.execute_skill(skill, {"arg1": "value1"}, {})

        mock_func.assert_called_once_with(arg1="value1")
        assert result == "Mock result"

    @pytest.mark.asyncio
    async def test_async_callable_skill_executes(self, executor):
        """Skills with async callable run: blocks should execute correctly."""

        # Create an async mock callable
        async def mock_async_func(**kwargs):
            return f"Async result: {kwargs}"

        skill = Skill(
            name="test_async_callable",
            description="Test async callable skill",
            instructions="Execute async callable",
            metadata=SkillMetadata(
                extra={
                    "run": {"type": "callable", "callable": mock_async_func},
                    "source": "test",
                }
            ),
            skill_dir="<test>",
        )

        result = await executor.execute_skill(skill, {"arg1": "value1"}, {})

        assert "Async result" in result
        assert "arg1" in result

    def test_no_llm_interpretation_fallback(self, executor):
        """Verify _llm_interpret_skill is removed."""
        assert not hasattr(executor, "_llm_interpret_skill"), (
            "_llm_interpret_skill should be removed"
        )

class TestThinkingEvents:
    """Test that thinking events include agent field."""

    def test_emit_thinking_default_agent(self):
        """emit_thinking should default to 'assistant' agent."""
        event = emit_thinking("Test content")
        assert event.type == "thinking"
        assert event.content == "Test content"
        assert event.metadata.get("agent") == "assistant"

    def test_emit_thinking_custom_agent(self):
        """emit_thinking should accept custom agent."""
        event = emit_thinking("Test content", agent="autonomous")
        assert event.metadata.get("agent") == "autonomous"

    def test_emit_thinking_backward_compatible(self):
        """Existing calls without agent should still work."""
        # This verifies the default parameter works
        event = emit_thinking("Content only")
        assert event.content == "Content only"
        assert "agent" in event.metadata

    def test_thinking_event_structure(self):
        """Verify thinking event has correct structure for SSE."""
        event = emit_thinking("Reasoning about next step", agent="autonomous")

        # Verify basic structure
        assert event.type == "thinking"
        assert event.content == "Reasoning about next step"
        assert event.metadata is not None
        assert isinstance(event.metadata, dict)
        assert event.metadata.get("agent") == "autonomous"

        # Verify timestamp is set
        assert event.timestamp is not None
        assert len(event.timestamp) > 0

class TestClarifyBlocking:
    """Test that clarify events block until user responds."""

    @pytest.fixture
    def cleanup(self):
        """Clean up clarify state after each test."""
        yield
        _execution_clarify_events.clear()
        _execution_clarify_responses.clear()

    def test_submit_clarification_when_pending(self, cleanup):
        """submit_autonomous_clarification should work when event pending."""
        conv_id = "test_conv"
        event = asyncio.Event()
        _execution_clarify_events[conv_id] = event

        # Mock response
        from plugins.clarify.protocol import ClarificationResponse

        response = ClarificationResponse(value="Proceed", selected_option=0)

        result = submit_autonomous_clarification(conv_id, response)
        assert result is True
        assert conv_id in _execution_clarify_responses
        assert event.is_set()

    def test_submit_clarification_when_not_pending(self, cleanup):
        """submit_autonomous_clarification should return False when no pending."""
        result = submit_autonomous_clarification("nonexistent", MagicMock())
        assert result is False

class TestAskHumanBlocking:
    """Test that ASK_HUMAN action type properly blocks execution."""

    @pytest.fixture
    def cleanup(self):
        """Clean up clarify state after each test."""
        yield
        _execution_clarify_events.clear()
        _execution_clarify_responses.clear()

    @pytest.mark.asyncio
    async def test_ask_human_creates_blocking_event(self, cleanup):
        """ASK_HUMAN should create a blocking event in _execution_clarify_events."""
        from core.autonomous.models import ActionType, Thought

        # Mock LLM to return ASK_HUMAN action
        with patch.object(LLMThinkingProvider, "think") as mock_think:
            mock_think.return_value = Thought(
                reasoning="I need clarification from the user",
                action_type=ActionType.ASK_HUMAN,
                confidence=0.5,
                is_final=False,
            )

            conv_id = "test_ask_human_conv"
            events = []

            # Run in background task with timeout
            async def collect_events():
                async for event in stream_react_execution(
                    goal="Test ASK_HUMAN",
                    conversation_id=conv_id,
                    user_id="test_user",
                ):
                    events.append(event)
                    # After clarify event, simulate user response
                    if event.type == "clarify":
                        # Simulate delayed user response
                        await asyncio.sleep(0.1)
                        from plugins.clarify.protocol import ClarificationResponse

                        response = ClarificationResponse(value="abort", selected_option=2)
                        submit_autonomous_clarification(conv_id, response)

            # Should complete (via abort) within timeout
            try:
                await asyncio.wait_for(collect_events(), timeout=5.0)
            except asyncio.TimeoutError:
                pytest.fail("ASK_HUMAN blocking did not respect user abort")

            # Verify clarify event was emitted
            clarify_events = [e for e in events if e.type == "clarify"]
            assert len(clarify_events) >= 1, "No clarify event emitted for ASK_HUMAN"

    @pytest.mark.asyncio
    async def test_ask_human_blocking_event_created(self, cleanup):
        """Verify blocking event is created when ASK_HUMAN is triggered."""
        conv_id = "test_blocking_event_conv"

        # Create the blocking event manually (simulating what stream_react_execution does)
        blocking_event = asyncio.Event()
        _execution_clarify_events[conv_id] = blocking_event

        # Verify event is pending
        assert conv_id in _execution_clarify_events
        assert not blocking_event.is_set()

        # Submit response to unblock
        from plugins.clarify.protocol import ClarificationResponse

        response = ClarificationResponse(value="Proceed", selected_option=0)
        result = submit_autonomous_clarification(conv_id, response)

        assert result is True
        assert blocking_event.is_set()

class TestReActExecution:
    """Integration test for full ReAct execution flow."""

    @pytest.mark.asyncio
    async def test_stream_yields_thinking_with_agent(self):
        """stream_react_execution should yield thinking events with agent field."""
        from core.autonomous.models import ActionType, Thought

        # Mock LLM to return immediate final answer
        with patch.object(LLMThinkingProvider, "think") as mock_think:
            mock_think.return_value = Thought(
                reasoning="Goal is trivial, completing immediately",
                action_type=ActionType.EXECUTE_SKILL,
                confidence=1.0,
                is_final=True,
                answer="Done",
            )

            events = []
            async for event in stream_react_execution(
                goal="Simple test",
                conversation_id="test_conv",
                user_id="test_user",
            ):
                events.append(event)

            # Check for thinking events
            thinking_events = [e for e in events if e.type == "thinking"]
            assert len(thinking_events) >= 1, "Should have at least one thinking event"

            # All thinking events should have agent in metadata
            for event in thinking_events:
                assert event.metadata is not None, f"Thinking event has no metadata: {event}"
                assert event.metadata.get("agent") is not None, (
                    f"Thinking event missing agent in metadata: {event}"
                )
                # Verify it's 'autonomous' specifically for stream_react_execution
                assert event.metadata.get("agent") == "autonomous", (
                    f"Expected agent='autonomous', got: {event.metadata.get('agent')}"
                )

    @pytest.mark.asyncio
    async def test_thinking_events_have_agent_in_serialized_output(self):
        """Verify thinking events serialize with agent at top level for SSE."""

        event = emit_thinking("Test reasoning", agent="autonomous")
        data = event.model_dump()

        # Simulate SSE flattening (what chat routes do)
        if data.get("metadata"):
            metadata = data.pop("metadata")
            data.update(metadata)

        # Verify agent at top level after flattening
        assert "agent" in data, f"agent not at top level: {data}"
        assert data["agent"] == "autonomous", f"wrong agent value: {data}"

        # Verify complete structure matches frontend expectations
        json_str = json.dumps(data)
        assert '"type": "thinking"' in json_str or '"type":"thinking"' in json_str
        assert '"agent": "autonomous"' in json_str or '"agent":"autonomous"' in json_str

    @pytest.mark.asyncio
    async def test_to_openai_sse_includes_agent(self):
        """Verify to_openai_sse includes agent in dryade field."""
        from core.extensions.events import to_openai_sse

        event = emit_thinking("Test reasoning", agent="autonomous")
        sse_output = to_openai_sse(event)

        # Parse the SSE output
        assert sse_output.startswith("data: ")
        json_data = json.loads(sse_output[6:].strip())

        # Check dryade field has agent
        assert "dryade" in json_data, f"dryade field missing: {json_data}"
        dryade = json_data["dryade"]
        assert dryade.get("type") == "thinking"
        assert dryade.get("agent") == "autonomous", f"agent missing or wrong: {dryade}"
        assert dryade.get("content") == "Test reasoning"

class TestThinkingStreamIntegration:
    """Test thinking events work with ThinkingStream frontend component."""

    def test_thinking_event_json_structure(self):
        """Verify JSON structure matches ThinkingStream expectations."""
        event = emit_thinking("Analyzing the goal...", agent="autonomous")

        # The frontend ThinkingStream expects:
        # { type: "thinking", agent: string, content: string }
        data = event.model_dump()

        # After flattening metadata (done by SSE handling)
        flattened = {"type": data["type"], "content": data["content"], **data.get("metadata", {})}

        assert flattened["type"] == "thinking"
        assert flattened["agent"] == "autonomous"
        assert flattened["content"] == "Analyzing the goal..."

    def test_multiple_agents_distinguishable(self):
        """Different agent values should be distinguishable."""
        event1 = emit_thinking("Assistant thinking", agent="assistant")
        event2 = emit_thinking("Autonomous thinking", agent="autonomous")

        assert event1.metadata["agent"] != event2.metadata["agent"]
        assert event1.metadata["agent"] == "assistant"
        assert event2.metadata["agent"] == "autonomous"
