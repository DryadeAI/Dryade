"""Unit tests for autonomous chat_adapter module.

Tests cover:
- submit_autonomous_clarification / has_pending_autonomous_clarification
- _format_skills_xml / _format_observations_xml helpers
- LLMThinkingProvider._parse_thought_response
- LLMThinkingProvider.think (mocked LLM)
- RuntimeSkillExecutor.execute_skill (callable path, no-run-block error)
- ClarifyHumanHandler.request_input
- LEASH_PRESETS mapping
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.autonomous.chat_adapter import (
    LEASH_PRESETS,
    ClarifyHumanHandler,
    LLMThinkingProvider,
    RuntimeSkillExecutor,
    _execution_clarify_events,
    _execution_clarify_responses,
    _format_observations_xml,
    _format_skills_xml,
    has_pending_autonomous_clarification,
    submit_autonomous_clarification,
)
from core.autonomous.models import ActionType, Observation, Thought

# ---------------------------------------------------------------------------
# Clarification state helpers
# ---------------------------------------------------------------------------

class TestClarificationHelpers:
    def setup_method(self):
        """Ensure clean state before each test."""
        _execution_clarify_events.clear()
        _execution_clarify_responses.clear()

    def test_submit_returns_false_no_pending(self):
        mock_response = MagicMock()
        assert submit_autonomous_clarification("conv_1", mock_response) is False

    def test_submit_returns_true_and_sets_event(self):
        event = asyncio.Event()
        _execution_clarify_events["conv_1"] = event
        mock_response = MagicMock()
        result = submit_autonomous_clarification("conv_1", mock_response)
        assert result is True
        assert event.is_set()
        assert _execution_clarify_responses["conv_1"] is mock_response

    def test_has_pending_false(self):
        assert has_pending_autonomous_clarification("conv_nope") is False

    def test_has_pending_true(self):
        _execution_clarify_events["conv_2"] = asyncio.Event()
        assert has_pending_autonomous_clarification("conv_2") is True

    def teardown_method(self):
        _execution_clarify_events.clear()
        _execution_clarify_responses.clear()

# ---------------------------------------------------------------------------
# LEASH_PRESETS
# ---------------------------------------------------------------------------

class TestLeashPresets:
    def test_all_presets_exist(self):
        assert "conservative" in LEASH_PRESETS
        assert "standard" in LEASH_PRESETS
        assert "permissive" in LEASH_PRESETS

    def test_conservative_tighter_than_permissive(self):
        conservative = LEASH_PRESETS["conservative"]
        permissive = LEASH_PRESETS["permissive"]
        assert conservative.confidence_threshold >= permissive.confidence_threshold

# ---------------------------------------------------------------------------
# _format_skills_xml
# ---------------------------------------------------------------------------

class TestFormatSkillsXml:
    def test_empty_skills(self):
        result = _format_skills_xml([])
        assert "No skills available" in result

    def test_single_skill_formatting(self):
        skill = MagicMock()
        skill.name = "web_search"
        skill.description = "Search the web"
        skill.metadata = None
        result = _format_skills_xml([skill])
        assert '<skill name="web_search">' in result
        assert "Search the web" in result

    def test_skill_with_dict_inputs(self):
        skill = MagicMock()
        skill.name = "tool"
        skill.description = "desc"
        mock_meta = MagicMock()
        mock_meta.inputs = [{"name": "query", "type": "string", "description": "search query"}]
        skill.metadata = mock_meta
        result = _format_skills_xml([skill])
        assert '<input name="query"' in result

    def test_skill_with_object_inputs(self):
        inp = MagicMock()
        inp.name = "url"
        inp.type = "string"
        inp.description = "target url"
        skill = MagicMock()
        skill.name = "fetch"
        skill.description = "fetch url"
        mock_meta = MagicMock()
        mock_meta.inputs = [inp]
        skill.metadata = mock_meta
        result = _format_skills_xml([skill])
        assert '<input name="url"' in result

# ---------------------------------------------------------------------------
# _format_observations_xml
# ---------------------------------------------------------------------------

class TestFormatObservationsXml:
    def test_empty_observations(self):
        result = _format_observations_xml([])
        assert "No actions taken yet" in result

    def test_successful_observation(self):
        obs = Observation(
            skill_name="search",
            inputs={"q": "test"},
            result="found it",
            success=True,
            duration_ms=100,
        )
        result = _format_observations_xml([obs])
        assert 'status="success"' in result
        assert "found it" in result

    def test_failed_observation(self):
        obs = Observation(
            skill_name="deploy",
            inputs={"env": "prod"},
            result=None,
            success=False,
            error="timeout",
        )
        result = _format_observations_xml([obs])
        assert 'status="failed"' in result
        assert "timeout" in result

    def test_long_result_truncated(self):
        obs = Observation(
            skill_name="read",
            inputs={},
            result="x" * 1000,
            success=True,
        )
        result = _format_observations_xml([obs])
        assert "..." in result

# ---------------------------------------------------------------------------
# LLMThinkingProvider._parse_thought_response
# ---------------------------------------------------------------------------

class TestParseThoughtResponse:
    def setup_method(self):
        self.provider = LLMThinkingProvider()

    def test_valid_json_response(self):
        data = {
            "reasoning": "found the answer",
            "action_type": "execute_skill",
            "skill_name": "search",
            "inputs": {"q": "test"},
            "confidence": 0.9,
            "is_final": False,
        }
        thought = self.provider._parse_thought_response(json.dumps(data))
        assert thought.reasoning == "found the answer"
        assert thought.action_type == ActionType.EXECUTE_SKILL
        assert thought.skill_name == "search"
        assert thought.confidence == 0.9

    def test_markdown_code_block_stripped(self):
        data = {"reasoning": "test", "confidence": 0.5}
        wrapped = f"```json\n{json.dumps(data)}\n```"
        thought = self.provider._parse_thought_response(wrapped)
        assert thought.reasoning == "test"

    def test_ask_human_action_type(self):
        data = {"reasoning": "need help", "action_type": "ask_human", "confidence": 0.3}
        thought = self.provider._parse_thought_response(json.dumps(data))
        assert thought.action_type == ActionType.ASK_HUMAN

    def test_create_skill_action_type(self):
        data = {"reasoning": "need new skill", "action_type": "create_skill", "confidence": 0.5}
        thought = self.provider._parse_thought_response(json.dumps(data))
        assert thought.action_type == ActionType.CREATE_SKILL

    def test_invalid_json_returns_ask_human(self):
        thought = self.provider._parse_thought_response("not valid json {{{")
        assert thought.action_type == ActionType.ASK_HUMAN
        assert thought.confidence == 0.3
        assert "Could not parse" in thought.reasoning

    def test_is_final_with_answer(self):
        data = {
            "reasoning": "done",
            "is_final": True,
            "answer": "the answer is 42",
            "confidence": 0.95,
        }
        thought = self.provider._parse_thought_response(json.dumps(data))
        assert thought.is_final is True
        assert thought.answer == "the answer is 42"

    def test_defaults_for_missing_fields(self):
        data = {}
        thought = self.provider._parse_thought_response(json.dumps(data))
        assert thought.reasoning == "No reasoning provided"
        assert thought.confidence == 0.5
        assert thought.is_final is False

class TestLLMThinkingProviderThink:
    @pytest.mark.asyncio
    async def test_think_calls_llm_and_parses(self):
        provider = LLMThinkingProvider()
        mock_llm = AsyncMock()
        mock_llm.acall = AsyncMock(
            return_value=json.dumps(
                {
                    "reasoning": "analyzing",
                    "action_type": "execute_skill",
                    "skill_name": "search",
                    "inputs": {},
                    "confidence": 0.8,
                }
            )
        )
        provider._llm = mock_llm

        thought = await provider.think(
            goal="find files",
            observations=[],
            available_skills=[],
            context={},
        )
        assert thought.skill_name == "search"
        mock_llm.acall.assert_called_once()

    @pytest.mark.asyncio
    async def test_think_handles_dict_response(self):
        provider = LLMThinkingProvider()
        mock_llm = AsyncMock()
        mock_llm.acall = AsyncMock(
            return_value={
                "content": json.dumps(
                    {
                        "reasoning": "ok",
                        "confidence": 0.7,
                    }
                )
            }
        )
        provider._llm = mock_llm

        thought = await provider.think("goal", [], [], {})
        assert thought.reasoning == "ok"

    @pytest.mark.asyncio
    async def test_think_llm_failure_returns_ask_human(self):
        provider = LLMThinkingProvider()
        mock_llm = AsyncMock()
        mock_llm.acall = AsyncMock(side_effect=RuntimeError("LLM down"))
        provider._llm = mock_llm

        thought = await provider.think("goal", [], [], {})
        assert thought.action_type == ActionType.ASK_HUMAN
        assert thought.confidence == 0.1

    @pytest.mark.asyncio
    async def test_think_with_context_hints(self):
        provider = LLMThinkingProvider()
        mock_llm = AsyncMock()
        mock_llm.acall = AsyncMock(
            return_value=json.dumps(
                {
                    "reasoning": "using hints",
                    "confidence": 0.8,
                }
            )
        )
        provider._llm = mock_llm

        await provider.think("goal", [], [], {"hints": "use agent A"})
        call_args = mock_llm.acall.call_args[0][0]
        user_msg = call_args[1]["content"]
        assert "use agent A" in user_msg

    @pytest.mark.asyncio
    async def test_think_sync_fallback(self):
        """If LLM has no acall, falls back to asyncio.to_thread(llm.call)."""
        provider = LLMThinkingProvider()
        mock_llm = MagicMock(spec=[])  # No acall attribute
        mock_llm.call = MagicMock(
            return_value=json.dumps(
                {
                    "reasoning": "sync ok",
                    "confidence": 0.7,
                }
            )
        )
        provider._llm = mock_llm

        thought = await provider.think("goal", [], [], {})
        assert thought.reasoning == "sync ok"

# ---------------------------------------------------------------------------
# RuntimeSkillExecutor
# ---------------------------------------------------------------------------

class TestRuntimeSkillExecutor:
    @pytest.mark.asyncio
    async def test_execute_no_run_block_raises(self):
        executor = RuntimeSkillExecutor()
        skill = MagicMock()
        skill.name = "test_skill"
        skill.metadata = MagicMock()
        skill.metadata.extra = {}

        with pytest.raises(RuntimeError, match="no executable run: block"):
            await executor.execute_skill(skill, {}, {})

    @pytest.mark.asyncio
    async def test_execute_callable_async(self):
        executor = RuntimeSkillExecutor()
        skill = MagicMock()
        skill.name = "test_skill"

        async def my_func(**kwargs):
            return "result"

        skill.metadata = MagicMock()
        skill.metadata.extra = {"run": {"type": "callable", "callable": my_func}}

        result = await executor.execute_skill(skill, {}, {})
        assert result == "result"

    @pytest.mark.asyncio
    async def test_execute_callable_sync(self):
        executor = RuntimeSkillExecutor()
        skill = MagicMock()
        skill.name = "test_skill"

        def my_func(**kwargs):
            return "sync_result"

        skill.metadata = MagicMock()
        skill.metadata.extra = {"run": {"type": "callable", "callable": my_func}}

        result = await executor.execute_skill(skill, {}, {})
        assert result == "sync_result"

    @pytest.mark.asyncio
    async def test_execute_callable_no_function_raises(self):
        executor = RuntimeSkillExecutor()
        skill = MagicMock()
        skill.name = "test_skill"
        skill.metadata = MagicMock()
        skill.metadata.extra = {"run": {"type": "callable"}}

        with pytest.raises(RuntimeError, match="no callable function"):
            await executor.execute_skill(skill, {}, {})

    @pytest.mark.asyncio
    async def test_execute_callable_failure_raises(self):
        executor = RuntimeSkillExecutor()
        skill = MagicMock()
        skill.name = "test_skill"

        async def failing_func(**kwargs):
            raise ValueError("bad input")

        skill.metadata = MagicMock()
        skill.metadata.extra = {"run": {"type": "callable", "callable": failing_func}}

        with pytest.raises(RuntimeError, match="Callable execution failed"):
            await executor.execute_skill(skill, {}, {})

    @pytest.mark.asyncio
    async def test_execute_no_metadata_raises(self):
        executor = RuntimeSkillExecutor()
        skill = MagicMock()
        skill.name = "test_skill"
        skill.metadata = None

        with pytest.raises(RuntimeError, match="no executable run: block"):
            await executor.execute_skill(skill, {}, {})

# ---------------------------------------------------------------------------
# ClarifyHumanHandler
# ---------------------------------------------------------------------------

class TestClarifyHumanHandler:
    def test_get_pending_event_clears(self):
        handler = ClarifyHumanHandler(conversation_id="conv_1")
        event = MagicMock()
        handler._pending_event = event
        assert handler.get_pending_event() is event
        assert handler.get_pending_event() is None

    @pytest.mark.asyncio
    async def test_request_input_timeout(self):
        handler = ClarifyHumanHandler(conversation_id="conv_1")
        thought = Thought(reasoning="help", confidence=0.3)

        with patch(
            "core.clarification.request_clarification", new_callable=AsyncMock
        ) as mock_clarify:
            mock_clarify.side_effect = TimeoutError()
            result = await handler.request_input(thought, {}, "need help")
            assert not result.success
            assert "timed out" in result.reason

    @pytest.mark.asyncio
    async def test_request_input_proceed(self):
        handler = ClarifyHumanHandler(conversation_id="conv_1")
        thought = Thought(
            reasoning="deploy?",
            confidence=0.5,
            skill_name="deploy",
            inputs={"env": "prod"},
        )

        with patch(
            "core.clarification.request_clarification", new_callable=AsyncMock
        ) as mock_clarify:
            mock_clarify.return_value = "Proceed with action"
            result = await handler.request_input(thought, {}, "confirm deploy")
            assert result.success
            assert "approved" in result.output.lower()

    @pytest.mark.asyncio
    async def test_request_input_skip(self):
        handler = ClarifyHumanHandler(conversation_id="conv_1")
        thought = Thought(reasoning="skip?", confidence=0.5)

        with patch(
            "core.clarification.request_clarification", new_callable=AsyncMock
        ) as mock_clarify:
            mock_clarify.return_value = "Skip this action"
            result = await handler.request_input(thought, {}, "skip?")
            assert not result.success
            assert "skip" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_request_input_alternative(self):
        handler = ClarifyHumanHandler(conversation_id="conv_1")
        thought = Thought(reasoning="try different", confidence=0.4)

        with patch(
            "core.clarification.request_clarification", new_callable=AsyncMock
        ) as mock_clarify:
            mock_clarify.return_value = "Use backup agent instead"
            result = await handler.request_input(thought, {}, "alternatives?")
            assert result.success
            assert "Use backup agent instead" in result.output

    @pytest.mark.asyncio
    async def test_request_input_exception(self):
        handler = ClarifyHumanHandler(conversation_id="conv_1")
        thought = Thought(reasoning="error case", confidence=0.5)

        with patch(
            "core.clarification.request_clarification", new_callable=AsyncMock
        ) as mock_clarify:
            mock_clarify.side_effect = RuntimeError("network error")
            result = await handler.request_input(thought, {}, "test")
            assert not result.success
            assert "network error" in result.reason
