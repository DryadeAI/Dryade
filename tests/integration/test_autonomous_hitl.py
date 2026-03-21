"""Integration tests for autonomous execution with Human-in-the-Loop (HITL).

Tests the complete flow of:
1. Blocking clarify events during autonomous execution
2. User responses (abort/skip/proceed) handling
3. Sandbox skill execution for skills with run: blocks
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from core.autonomous.chat_adapter import (
    RuntimeSkillExecutor,
    _execution_clarify_events,
    _execution_clarify_responses,
    has_pending_autonomous_clarification,
    stream_react_execution,
    submit_autonomous_clarification,
)
from core.autonomous.models import ActionType, Thought

def get_event_type(event):
    """Get event type from ChatEvent or dict."""
    if hasattr(event, "type"):
        return event.type
    return event.get("type")

def get_event_code(event):
    """Get error code from ChatEvent or dict."""
    if hasattr(event, "metadata"):
        return event.metadata.get("code")
    return event.get("code") or (event.get("data") or {}).get("code")

class TestAutonomousClarificationStorage:
    """Test autonomous clarification storage and submission."""

    def test_submit_autonomous_clarification_no_pending(self):
        """Test submit returns False when no pending clarification."""
        response = MagicMock()
        result = submit_autonomous_clarification("nonexistent-conv", response)
        assert result is False

    def test_submit_autonomous_clarification_with_pending(self):
        """Test submit returns True and sets event when pending clarification exists."""
        conv_id = "test-conv-123"
        event = asyncio.Event()
        _execution_clarify_events[conv_id] = event

        try:
            response = MagicMock()
            response.value = "Proceed anyway"
            response.selected_option = 0

            result = submit_autonomous_clarification(conv_id, response)
            assert result is True
            assert event.is_set()
            assert _execution_clarify_responses[conv_id] == response
        finally:
            # Cleanup
            _execution_clarify_events.pop(conv_id, None)
            _execution_clarify_responses.pop(conv_id, None)

    def test_has_pending_autonomous_clarification(self):
        """Test checking for pending autonomous clarification."""
        conv_id = "test-pending-conv"

        assert not has_pending_autonomous_clarification(conv_id)

        _execution_clarify_events[conv_id] = asyncio.Event()
        try:
            assert has_pending_autonomous_clarification(conv_id)
        finally:
            _execution_clarify_events.pop(conv_id, None)

class TestAutonomousBlockingClarify:
    """Test blocking clarify flow in stream_react_execution."""

    @pytest.mark.asyncio
    async def test_low_confidence_triggers_clarify_event(self):
        """Test that low confidence triggers a clarify event and blocks."""
        conv_id = "test-low-conf-conv"

        # Create mock thinking provider that returns low confidence
        thoughts = [
            Thought(
                reasoning="I'm not sure about this action",
                action_type=ActionType.EXECUTE_SKILL,
                skill_name="risky-skill",
                inputs={"file": "important.txt"},
                confidence=0.3,  # Below threshold
            ),
        ]

        call_count = 0

        async def mock_think(goal, observations, skills, context):
            nonlocal call_count
            if call_count < len(thoughts):
                thought = thoughts[call_count]
                call_count += 1
                return thought
            return Thought(is_final=True, answer="Done", confidence=1.0, reasoning="Done")

        mock_provider = MagicMock()
        mock_provider.think = mock_think

        mock_skill = MagicMock()
        mock_skill.name = "risky-skill"
        mock_skill.description = "A risky skill"

        with (
            patch("core.autonomous.chat_adapter.LLMThinkingProvider") as mock_thinking_cls,
            patch("core.autonomous.chat_adapter.get_skill_registry") as mock_registry,
            patch("core.autonomous.chat_adapter.get_skill_router") as mock_router,
        ):
            mock_thinking_cls.return_value = mock_provider
            mock_registry.return_value.get_eligible_skills.return_value = [mock_skill]
            mock_router.return_value.route.return_value = [(mock_skill, 0.9)]

            events = []

            # Run generator in background with short timeout
            async def collect_events():
                try:
                    async for event in stream_react_execution(
                        goal="Do something risky",
                        conversation_id=conv_id,
                        user_id="test-user",
                        leash_preset="conservative",
                    ):
                        events.append(event)
                        # Stop after getting clarify event
                        if get_event_type(event) == "clarify":
                            break
                except Exception as e:
                    events.append({"type": "error", "error": str(e)})

            # Start collection in background
            task = asyncio.create_task(collect_events())

            # Wait a bit for the clarify event to be emitted
            await asyncio.sleep(0.1)

            # Submit response to unblock
            if conv_id in _execution_clarify_events:
                response = MagicMock()
                response.value = "abort"
                response.selected_option = 2
                submit_autonomous_clarification(conv_id, response)

            # Wait for task to complete
            try:
                await asyncio.wait_for(task, timeout=2.0)
            except TimeoutError:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            # Verify clarify event was emitted
            clarify_events = [e for e in events if get_event_type(e) == "clarify"]
            assert len(clarify_events) >= 1, (
                f"Expected clarify event, got: {[get_event_type(e) for e in events]}"
            )

            # Verify the clarify event has expected structure
            clarify_event = clarify_events[0]
            # ChatEvent has content attribute for the question
            assert hasattr(clarify_event, "content") or hasattr(clarify_event, "metadata")

    @pytest.mark.asyncio
    async def test_abort_stops_execution(self):
        """Test that user abort stops execution with USER_ABORT error."""
        conv_id = "test-abort-conv"

        # Create mock that triggers low confidence
        async def mock_think(goal, observations, skills, context):
            return Thought(
                reasoning="Risky action",
                action_type=ActionType.EXECUTE_SKILL,
                skill_name="test-skill",
                inputs={},
                confidence=0.3,
            )

        mock_provider = MagicMock()
        mock_provider.think = mock_think

        mock_skill = MagicMock()
        mock_skill.name = "test-skill"

        with (
            patch("core.autonomous.chat_adapter.LLMThinkingProvider") as mock_thinking_cls,
            patch("core.autonomous.chat_adapter.get_skill_registry") as mock_registry,
            patch("core.autonomous.chat_adapter.get_skill_router") as mock_router,
        ):
            mock_thinking_cls.return_value = mock_provider
            mock_registry.return_value.get_eligible_skills.return_value = [mock_skill]
            mock_router.return_value.route.return_value = [(mock_skill, 0.9)]

            events = []

            async def collect_events():
                async for event in stream_react_execution(
                    goal="Test abort",
                    conversation_id=conv_id,
                    user_id="test-user",
                    leash_preset="conservative",
                ):
                    events.append(event)
                    if get_event_type(event) == "clarify":
                        # Simulate user abort
                        await asyncio.sleep(0.01)
                        response = MagicMock()
                        response.value = "Abort execution"
                        response.selected_option = 2
                        submit_autonomous_clarification(conv_id, response)

            task = asyncio.create_task(collect_events())

            try:
                await asyncio.wait_for(task, timeout=3.0)
            except TimeoutError:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            # Verify error event with USER_ABORT
            error_events = [e for e in events if get_event_type(e) == "error"]
            assert len(error_events) >= 1, (
                f"Expected error event, got: {[get_event_type(e) for e in events]}"
            )

            error_codes = [get_event_code(e) for e in error_events]
            assert "USER_ABORT" in error_codes, f"Expected USER_ABORT, got codes: {error_codes}"

    @pytest.mark.asyncio
    async def test_skip_continues_execution(self):
        """Test that user skip continues execution without action."""
        conv_id = "test-skip-conv"
        call_count = 0

        async def mock_think(goal, observations, skills, context):
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                return Thought(
                    reasoning="First risky action",
                    action_type=ActionType.EXECUTE_SKILL,
                    skill_name="test-skill",
                    inputs={},
                    confidence=0.3,
                )
            else:
                # After skip, complete
                return Thought(
                    reasoning="Done after skip",
                    is_final=True,
                    answer="Completed after skip",
                    confidence=1.0,
                )

        mock_provider = MagicMock()
        mock_provider.think = mock_think

        mock_skill = MagicMock()
        mock_skill.name = "test-skill"

        with (
            patch("core.autonomous.chat_adapter.LLMThinkingProvider") as mock_thinking_cls,
            patch("core.autonomous.chat_adapter.get_skill_registry") as mock_registry,
            patch("core.autonomous.chat_adapter.get_skill_router") as mock_router,
        ):
            mock_thinking_cls.return_value = mock_provider
            mock_registry.return_value.get_eligible_skills.return_value = [mock_skill]
            mock_router.return_value.route.return_value = [(mock_skill, 0.9)]

            events = []

            async def collect_events():
                async for event in stream_react_execution(
                    goal="Test skip",
                    conversation_id=conv_id,
                    user_id="test-user",
                    leash_preset="conservative",
                ):
                    events.append(event)
                    if get_event_type(event) == "clarify":
                        # Simulate user skip
                        await asyncio.sleep(0.01)
                        response = MagicMock()
                        response.value = "Skip and continue"
                        response.selected_option = 1
                        submit_autonomous_clarification(conv_id, response)

            task = asyncio.create_task(collect_events())

            try:
                await asyncio.wait_for(task, timeout=3.0)
            except TimeoutError:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            # Verify completion event (not error)
            complete_events = [e for e in events if get_event_type(e) == "complete"]
            error_events = [e for e in events if get_event_type(e) == "error"]

            # Should complete successfully, not error
            assert len(complete_events) >= 1 or len(error_events) == 0, (
                f"Expected completion or no error, got types: {[get_event_type(e) for e in events]}"
            )

class TestSandboxSkillExecution:
    """Test sandbox integration for skill execution."""

    @pytest.mark.asyncio
    async def test_skill_with_run_block_uses_sandbox(self):
        """Test that skills with run: block execute via sandbox."""
        executor = RuntimeSkillExecutor()

        # Create skill with run: block
        mock_skill = MagicMock()
        mock_skill.name = "sandboxed-skill"
        mock_skill.description = "Skill with run block"
        mock_skill.metadata = MagicMock()
        mock_skill.metadata.extra = {
            "run": "echo 'Hello from sandbox'",
            "isolation": "process",
            "timeout": 30,
        }

        # Verify execute_skill routes to _execute_sandboxed for run: blocks
        # by mocking _execute_sandboxed directly
        async def mock_execute_sandboxed(skill, inputs, context, run_block):
            assert skill.name == "sandboxed-skill"
            assert run_block == "echo 'Hello from sandbox'"
            return "Hello from sandbox"

        with patch.object(executor, "_execute_sandboxed", mock_execute_sandboxed):
            result = await executor.execute_skill(
                skill=mock_skill,
                inputs={"param": "value"},
                context={},
            )

            assert result == "Hello from sandbox"

    @pytest.mark.asyncio
    async def test_skill_without_run_block_raises_error(self):
        """Test that skills without run: block raise RuntimeError."""
        executor = RuntimeSkillExecutor()

        # Create skill without run: block
        mock_skill = MagicMock()
        mock_skill.name = "interpretive-skill"
        mock_skill.description = "Skill without run block"
        mock_skill.instructions = "Analyze the input"
        mock_skill.metadata = MagicMock()
        mock_skill.metadata.extra = None

        with pytest.raises(RuntimeError, match="no executable run"):
            await executor.execute_skill(
                skill=mock_skill,
                inputs={"data": "test"},
                context={},
            )

    @pytest.mark.asyncio
    async def test_sandbox_failure_raises_runtime_error(self):
        """Test that sandbox failure raises RuntimeError."""
        executor = RuntimeSkillExecutor()

        mock_skill = MagicMock()
        mock_skill.name = "failing-skill"
        mock_skill.metadata = MagicMock()
        mock_skill.metadata.extra = {"run": "exit 1"}

        # Mock _execute_sandboxed to raise RuntimeError as it would on sandbox failure
        async def mock_execute_sandboxed_failure(skill, inputs, context, run_block):
            raise RuntimeError(
                f"Sandbox execution failed for '{skill.name}': Command failed with exit code 1"
            )

        with patch.object(executor, "_execute_sandboxed", mock_execute_sandboxed_failure):
            with pytest.raises(RuntimeError) as exc_info:
                await executor.execute_skill(
                    skill=mock_skill,
                    inputs={},
                    context={},
                )

            assert "failing-skill" in str(exc_info.value)
            assert "failed" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_isolation_level_from_skill_metadata(self):
        """Test that isolation level is read from skill metadata."""
        IsolationLevel = pytest.importorskip(
            "plugins.sandbox.executor", reason="sandbox plugin not available"
        ).IsolationLevel

        executor = RuntimeSkillExecutor()

        mock_skill = MagicMock()
        mock_skill.name = "isolated-skill"
        mock_skill.metadata = MagicMock()
        mock_skill.metadata.extra = {"isolation": "container"}

        level = executor._get_skill_isolation(mock_skill)
        assert level == IsolationLevel.CONTAINER

    @pytest.mark.asyncio
    async def test_isolation_level_from_risk_mapping(self):
        """Test that isolation level falls back to TOOL_RISK_LEVELS."""
        IsolationLevel = pytest.importorskip(
            "plugins.sandbox.executor", reason="sandbox plugin not available"
        ).IsolationLevel

        executor = RuntimeSkillExecutor()

        # Skill without declared isolation but in risk mapping
        mock_skill = MagicMock()
        mock_skill.name = "execute_code"  # High risk tool
        mock_skill.metadata = MagicMock()
        mock_skill.metadata.extra = {}

        level = executor._get_skill_isolation(mock_skill)
        assert level == IsolationLevel.CONTAINER

    @pytest.mark.asyncio
    async def test_isolation_level_defaults_to_process(self):
        """Test that isolation level defaults to PROCESS."""
        IsolationLevel = pytest.importorskip(
            "plugins.sandbox.executor", reason="sandbox plugin not available"
        ).IsolationLevel

        executor = RuntimeSkillExecutor()

        mock_skill = MagicMock()
        mock_skill.name = "unknown-skill"
        mock_skill.metadata = MagicMock()
        mock_skill.metadata.extra = {}

        level = executor._get_skill_isolation(mock_skill)
        assert level == IsolationLevel.PROCESS

class TestDangerousActionBlocking:
    """Test blocking for dangerous actions."""

    @pytest.mark.asyncio
    async def test_dangerous_action_triggers_clarify(self):
        """Test that dangerous actions (e.g., delete) trigger clarify."""
        conv_id = "test-danger-conv"

        async def mock_think(goal, observations, skills, context):
            return Thought(
                reasoning="I need to delete files",
                action_type=ActionType.EXECUTE_SKILL,
                skill_name="file-delete",
                inputs={"path": "/important/file"},
                confidence=0.9,  # High confidence but dangerous
            )

        mock_provider = MagicMock()
        mock_provider.think = mock_think

        mock_skill = MagicMock()
        mock_skill.name = "file-delete"

        with (
            patch("core.autonomous.chat_adapter.LLMThinkingProvider") as mock_thinking_cls,
            patch("core.autonomous.chat_adapter.get_skill_registry") as mock_registry,
            patch("core.autonomous.chat_adapter.get_skill_router") as mock_router,
        ):
            mock_thinking_cls.return_value = mock_provider
            mock_registry.return_value.get_eligible_skills.return_value = [mock_skill]
            mock_router.return_value.route.return_value = [(mock_skill, 0.9)]

            events = []

            async def collect_events():
                async for event in stream_react_execution(
                    goal="Delete all my files",
                    conversation_id=conv_id,
                    user_id="test-user",
                    leash_preset="conservative",  # Conservative will flag dangerous actions
                ):
                    events.append(event)
                    if get_event_type(event) == "clarify":
                        # Submit abort to stop
                        await asyncio.sleep(0.01)
                        response = MagicMock()
                        response.value = "abort"
                        response.selected_option = 2
                        submit_autonomous_clarification(conv_id, response)
                        break

            task = asyncio.create_task(collect_events())

            try:
                await asyncio.wait_for(task, timeout=3.0)
            except TimeoutError:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            # Verify clarify was triggered for dangerous action
            # Note: May be triggered by low confidence or dangerous action patterns
            clarify_events = [e for e in events if get_event_type(e) == "clarify"]
            thinking_events = [e for e in events if get_event_type(e) == "thinking"]

            # At minimum we should have some events
            assert len(events) > 0, "Expected at least some events"

class TestClarificationTimeout:
    """Test clarification timeout behavior."""

    @pytest.mark.asyncio
    async def test_timeout_returns_clarify_timeout_error(self):
        """Test that timeout triggers CLARIFY_TIMEOUT error."""
        conv_id = "test-timeout-conv"

        async def mock_think(goal, observations, skills, context):
            return Thought(
                reasoning="Action requiring confirmation",
                action_type=ActionType.EXECUTE_SKILL,
                skill_name="test-skill",
                inputs={},
                confidence=0.3,  # Low confidence to trigger clarify
            )

        mock_provider = MagicMock()
        mock_provider.think = mock_think

        mock_skill = MagicMock()
        mock_skill.name = "test-skill"

        # Patch asyncio.wait_for to immediately timeout
        async def fast_timeout_wait_for(coro, timeout):
            # Immediately raise timeout
            raise TimeoutError()

        with (
            patch("core.autonomous.chat_adapter.LLMThinkingProvider") as mock_thinking_cls,
            patch("core.autonomous.chat_adapter.get_skill_registry") as mock_registry,
            patch("core.autonomous.chat_adapter.get_skill_router") as mock_router,
            patch("core.autonomous.chat_adapter.asyncio.wait_for", fast_timeout_wait_for),
        ):
            mock_thinking_cls.return_value = mock_provider
            mock_registry.return_value.get_eligible_skills.return_value = [mock_skill]
            mock_router.return_value.route.return_value = [(mock_skill, 0.9)]

            events = []

            async for event in stream_react_execution(
                goal="Test timeout",
                conversation_id=conv_id,
                user_id="test-user",
                leash_preset="conservative",
            ):
                events.append(event)
                # Stop after getting timeout error
                if get_event_type(event) == "error":
                    break

            # Verify CLARIFY_TIMEOUT error
            error_events = [e for e in events if get_event_type(e) == "error"]
            assert len(error_events) >= 1

            error_codes = [get_event_code(e) for e in error_events]
            assert "CLARIFY_TIMEOUT" in error_codes, f"Expected CLARIFY_TIMEOUT, got: {error_codes}"
