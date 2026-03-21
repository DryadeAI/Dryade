"""Tests for delegation adapter coverage gaps.

Covers:
- core.adapters.crewai_delegation (CrewDelegationAdapter)
- core.adapters.langgraph_delegation (LangGraphDelegationAdapter)
- core.adapters.skill_adapter (SkillAgentAdapter)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.adapters.protocol import AgentCapabilities, AgentFramework

# ---------------------------------------------------------------------------
# CrewDelegationAdapter tests
# ---------------------------------------------------------------------------

class TestCrewDelegationAdapter:
    """Tests for CrewDelegationAdapter."""

    def _make_adapter(self, **kwargs):
        from core.adapters.crewai_delegation import CrewDelegationAdapter

        crew = MagicMock()
        crew.agents = [MagicMock(), MagicMock()]
        crew.tasks = [MagicMock()]
        crew.process = MagicMock()
        crew.process.value = "sequential"
        crew.memory = False
        return CrewDelegationAdapter(
            crew=crew,
            name="test-crew",
            description="Test crew",
            **kwargs,
        )

    def test_get_card(self):
        """get_card returns correct AgentCard."""
        adapter = self._make_adapter()
        card = adapter.get_card()
        assert card.name == "test-crew"
        assert card.description == "Test crew"
        assert card.framework == AgentFramework.CREWAI
        assert card.metadata["delegation"] is True
        assert card.metadata["agents_count"] == 2
        assert card.metadata["tasks_count"] == 1
        assert card.metadata["process"] == "sequential"

    def test_get_tools_empty(self):
        """get_tools returns empty list."""
        adapter = self._make_adapter()
        assert adapter.get_tools() == []

    def test_supports_streaming(self):
        """supports_streaming returns True."""
        adapter = self._make_adapter()
        assert adapter.supports_streaming() is True

    def test_capabilities(self):
        """capabilities returns delegation-specific caps."""
        adapter = self._make_adapter()
        caps = adapter.capabilities()
        assert isinstance(caps, AgentCapabilities)
        assert caps.supports_streaming is True
        assert caps.supports_delegation is True
        assert caps.framework_specific["delegation"] is True

    def test_process_value_fallback(self):
        """_process_value handles missing process gracefully."""
        from core.adapters.crewai_delegation import CrewDelegationAdapter

        crew = MagicMock()
        crew.process = None
        crew.agents = []
        crew.tasks = []
        adapter = CrewDelegationAdapter(crew=crew, name="n", description="d")
        assert adapter._process_value == "sequential"

    def test_agents_count_none(self):
        """_agents_count handles None agents."""
        from core.adapters.crewai_delegation import CrewDelegationAdapter

        crew = MagicMock()
        crew.agents = None
        crew.tasks = []
        crew.process = None
        adapter = CrewDelegationAdapter(crew=crew, name="n", description="d")
        assert adapter._agents_count == 0

    def test_tasks_count_none(self):
        """_tasks_count handles None tasks."""
        from core.adapters.crewai_delegation import CrewDelegationAdapter

        crew = MagicMock()
        crew.agents = []
        crew.tasks = None
        crew.process = None
        adapter = CrewDelegationAdapter(crew=crew, name="n", description="d")
        assert adapter._tasks_count == 0

    @pytest.mark.asyncio
    async def test_execute_success(self):
        """execute returns AgentResult on success."""
        adapter = self._make_adapter()
        with patch("core.providers.llm_adapter.get_configured_llm", return_value=MagicMock()):
            adapter._crew.kickoff = MagicMock(return_value="crew output")
            with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
                mock_thread.return_value = "crew output"
                result = await adapter.execute("do something")
        assert result.status == "ok"
        assert result.result == "crew output"
        assert result.metadata["framework"] == "crewai"
        assert result.metadata["delegation"] is True

    @pytest.mark.asyncio
    async def test_execute_failure(self):
        """execute returns error AgentResult on exception."""
        adapter = self._make_adapter()
        with patch("core.providers.llm_adapter.get_configured_llm", return_value=MagicMock()):
            with patch(
                "asyncio.to_thread", new_callable=AsyncMock, side_effect=RuntimeError("boom")
            ):
                result = await adapter.execute("do something")
        assert result.status == "error"
        assert result.result is None
        assert "Crew execution failed" in result.error

    @pytest.mark.asyncio
    async def test_execute_with_context(self):
        """execute merges context into inputs."""
        adapter = self._make_adapter()
        with patch("core.providers.llm_adapter.get_configured_llm", return_value=MagicMock()):
            with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
                mock_thread.return_value = "output"
                result = await adapter.execute("task", context={"key": "val"})
        assert result.status == "ok"

    @pytest.mark.asyncio
    async def test_execute_with_sse_emitter(self):
        """execute uses event bridge when sse_emitter is set."""
        emitter = MagicMock()
        adapter = self._make_adapter(sse_emitter=emitter)
        with (
            patch("core.providers.llm_adapter.get_configured_llm", return_value=MagicMock()),
            patch.object(adapter, "_execute_with_events", new_callable=AsyncMock) as mock_events,
        ):
            mock_events.return_value = "streamed result"
            result = await adapter.execute("task")
        assert result.status == "ok"
        assert result.result == "streamed result"
        mock_events.assert_awaited_once()

    def test_capabilities_with_memory(self):
        """capabilities detects crew memory flag."""
        from core.adapters.crewai_delegation import CrewDelegationAdapter

        crew = MagicMock()
        crew.memory = True
        crew.agents = []
        crew.tasks = []
        crew.process = None
        adapter = CrewDelegationAdapter(crew=crew, name="n", description="d")
        caps = adapter.capabilities()
        assert caps.supports_memory is True

# ---------------------------------------------------------------------------
# LangGraphDelegationAdapter tests
# ---------------------------------------------------------------------------

class TestLangGraphDelegationAdapter:
    """Tests for LangGraphDelegationAdapter."""

    def _make_adapter(self, **kwargs):
        from core.adapters.langgraph_delegation import LangGraphDelegationAdapter

        graph = MagicMock()
        # Remove builder so it doesn't try to recompile
        del graph.builder
        return LangGraphDelegationAdapter(
            graph=graph,
            name="test-graph",
            description="Test graph",
            checkpointer=None,
            **kwargs,
        )

    def test_get_card(self):
        """get_card returns correct AgentCard."""
        adapter = self._make_adapter()
        card = adapter.get_card()
        assert card.name == "test-graph"
        assert card.framework == AgentFramework.LANGCHAIN
        assert card.metadata["is_langgraph"] is True
        assert card.metadata["delegation"] is True

    def test_get_tools_empty(self):
        """get_tools returns empty list."""
        adapter = self._make_adapter()
        assert adapter.get_tools() == []

    def test_supports_streaming(self):
        """supports_streaming returns True."""
        adapter = self._make_adapter()
        assert adapter.supports_streaming() is True

    def test_capabilities(self):
        """capabilities returns LangGraph-specific caps."""
        adapter = self._make_adapter()
        caps = adapter.capabilities()
        assert caps.supports_streaming is True
        assert caps.supports_delegation is True
        assert caps.framework_specific["is_langgraph"] is True

    @pytest.mark.asyncio
    async def test_execute_langgraph_not_available(self):
        """execute returns error when langgraph not installed."""
        adapter = self._make_adapter()
        with patch("core.adapters.langgraph_delegation._LANGGRAPH_AVAILABLE", False):
            result = await adapter.execute("task")
        assert result.status == "error"
        assert "not installed" in result.error

    @pytest.mark.asyncio
    async def test_execute_success(self):
        """execute returns AgentResult on success."""
        adapter = self._make_adapter()
        adapter._graph.ainvoke = AsyncMock(return_value={"output": "done"})
        with patch("core.adapters.langgraph_delegation._LANGGRAPH_AVAILABLE", True):
            result = await adapter.execute("task")
        assert result.status == "ok"
        assert result.result == {"output": "done"}
        assert result.metadata["framework"] == "langgraph"
        assert result.metadata["delegation"] is True
        assert "thread_id" in result.metadata

    @pytest.mark.asyncio
    async def test_execute_failure(self):
        """execute returns error AgentResult on exception."""
        adapter = self._make_adapter()
        adapter._graph.ainvoke = AsyncMock(side_effect=RuntimeError("graph error"))
        with patch("core.adapters.langgraph_delegation._LANGGRAPH_AVAILABLE", True):
            result = await adapter.execute("task")
        assert result.status == "error"
        assert "Graph execution failed" in result.error

    @pytest.mark.asyncio
    async def test_execute_with_context_and_thread_id(self):
        """execute uses thread_id from context."""
        adapter = self._make_adapter()
        adapter._graph.ainvoke = AsyncMock(return_value={"output": "ok"})
        with patch("core.adapters.langgraph_delegation._LANGGRAPH_AVAILABLE", True):
            result = await adapter.execute("task", context={"thread_id": "custom-thread"})
        assert result.metadata["thread_id"] == "custom-thread"

    @pytest.mark.asyncio
    async def test_execute_with_sse_emitter(self):
        """execute uses streaming when sse_emitter is set."""
        emitter = MagicMock()
        adapter = self._make_adapter(sse_emitter=emitter)
        with (
            patch("core.adapters.langgraph_delegation._LANGGRAPH_AVAILABLE", True),
            patch.object(adapter, "_execute_streaming", new_callable=AsyncMock) as mock_stream,
        ):
            mock_stream.return_value = ({"final": "state"}, ["node1", "node2"])
            result = await adapter.execute("task")
        assert result.status == "ok"
        assert result.metadata["nodes_executed"] == ["node1", "node2"]

    @pytest.mark.asyncio
    async def test_execute_streaming_internal(self):
        """_execute_streaming emits SSE events for each node."""
        emitter = MagicMock()
        adapter = self._make_adapter(sse_emitter=emitter)

        async def fake_astream(*args, **kwargs):
            yield {"node1": {"data": "a"}}
            yield {"node2": {"data": "b"}}

        adapter._graph.astream = fake_astream
        state, nodes = await adapter._execute_streaming(
            {"input": "test"}, {"configurable": {"thread_id": "t1"}}
        )
        assert nodes == ["node1", "node2"]
        assert emitter.call_count == 2

    def test_checkpointer_recompile_with_builder(self):
        """Adapter recompiles graph with checkpointer if builder available."""
        from core.adapters.langgraph_delegation import LangGraphDelegationAdapter

        graph = MagicMock()
        compiled = MagicMock()
        graph.builder.compile.return_value = compiled
        checkpointer = MagicMock()

        adapter = LangGraphDelegationAdapter(
            graph=graph, name="n", description="d", checkpointer=checkpointer
        )
        assert adapter._graph is compiled

    def test_checkpointer_recompile_failure(self):
        """Adapter falls back to original graph when recompile fails."""
        from core.adapters.langgraph_delegation import LangGraphDelegationAdapter

        graph = MagicMock()
        graph.builder.compile.side_effect = RuntimeError("compile error")
        checkpointer = MagicMock()

        adapter = LangGraphDelegationAdapter(
            graph=graph, name="n", description="d", checkpointer=checkpointer
        )
        assert adapter._graph is graph

    def test_has_checkpointer_in_card(self):
        """AgentCard reflects checkpointer presence."""
        from core.adapters.langgraph_delegation import LangGraphDelegationAdapter

        graph = MagicMock()
        del graph.builder
        checkpointer = MagicMock()

        adapter = LangGraphDelegationAdapter(
            graph=graph, name="n", description="d", checkpointer=checkpointer
        )
        card = adapter.get_card()
        assert card.metadata["has_checkpointer"] is True

# ---------------------------------------------------------------------------
# SkillAgentAdapter tests
# ---------------------------------------------------------------------------

class TestSkillAgentAdapter:
    """Tests for SkillAgentAdapter."""

    def _make_skill(self, has_scripts=False, scripts_dir=None, scripts_list=None):
        from core.skills.models import Skill, SkillMetadata

        skill = Skill(
            name="test-skill",
            description="A test skill",
            instructions="Do the thing",
            metadata=SkillMetadata(emoji="T"),
            skill_dir="/tmp/test-skill",
            plugin_id="test-plugin",
            scripts_dir=scripts_dir,
            has_scripts=has_scripts,
            chat_eligible=True,
        )
        if scripts_list:
            skill.get_scripts = MagicMock(return_value=scripts_list)
        return skill

    def _make_adapter(self, **kwargs):
        from core.adapters.skill_adapter import SkillAgentAdapter

        skill = self._make_skill(**kwargs)
        with patch("core.adapters.skill_adapter.get_skill_executor") as mock_exec:
            mock_exec.return_value = MagicMock()
            adapter = SkillAgentAdapter(skill)
        return adapter

    def test_adapter_name(self):
        """adapter_name is prefixed with skill-."""
        adapter = self._make_adapter()
        assert adapter.adapter_name == "skill-test-skill"

    def test_get_card_instruction_only(self):
        """get_card for instruction-only skill."""
        adapter = self._make_adapter()
        card = adapter.get_card()
        assert card.name == "skill-test-skill"
        assert card.framework == AgentFramework.CUSTOM
        assert card.metadata["is_skill"] is True
        assert card.metadata["skill_type"] == "instruction"
        assert len(card.capabilities) == 1
        assert card.capabilities[0].name == "instruction-guidance"

    def test_get_card_script_bearing(self):
        """get_card for script-bearing skill."""
        adapter = self._make_adapter(
            has_scripts=True,
            scripts_dir="/tmp/scripts",
            scripts_list=["run.sh", "check.py"],
        )
        card = adapter.get_card()
        assert card.metadata["skill_type"] == "script"
        assert len(card.capabilities) == 2

    def test_get_tools_instruction_only(self):
        """get_tools for instruction-only skill."""
        adapter = self._make_adapter()
        tools = adapter.get_tools()
        assert len(tools) == 1
        assert "apply_instructions" in tools[0]["function"]["name"]

    def test_get_tools_script_bearing(self):
        """get_tools for script-bearing skill."""
        adapter = self._make_adapter(
            has_scripts=True,
            scripts_dir="/tmp/scripts",
            scripts_list=["run.sh"],
        )
        tools = adapter.get_tools()
        assert len(tools) == 1
        assert "run_sh" in tools[0]["function"]["name"]

    def test_supports_streaming(self):
        """Skills don't support streaming."""
        adapter = self._make_adapter()
        assert adapter.supports_streaming() is False

    def test_capabilities_instruction(self):
        """capabilities for instruction-only skill."""
        adapter = self._make_adapter()
        caps = adapter.capabilities()
        assert caps.supports_streaming is False
        assert caps.timeout_seconds == 5
        assert caps.framework_specific["is_skill"] is True

    def test_capabilities_script(self):
        """capabilities for script-bearing skill."""
        adapter = self._make_adapter(has_scripts=True, scripts_dir="/tmp/s", scripts_list=["a.sh"])
        caps = adapter.capabilities()
        assert caps.timeout_seconds == 60

    @pytest.mark.asyncio
    async def test_execute_instruction(self):
        """execute returns instruction context for instruction-only skill."""
        adapter = self._make_adapter()
        with patch("core.skills.adapter.MarkdownSkillAdapter") as MockAdapter:
            mock_instance = MagicMock()
            mock_instance.build_skill_guidance.return_value = "guidance text"
            MockAdapter.return_value = mock_instance
            result = await adapter.execute("apply instructions")
        assert result.status == "ok"
        assert "test-skill" in result.result
        assert result.metadata["skill_type"] == "instruction"
        assert result.metadata["is_context_enrichment"] is True

    @pytest.mark.asyncio
    async def test_execute_script_success(self):
        """execute runs script for script-bearing skill."""
        from core.skills.executor import ScriptExecutionResult

        adapter = self._make_adapter(
            has_scripts=True, scripts_dir="/tmp/s", scripts_list=["run.sh"]
        )
        mock_result = ScriptExecutionResult(
            success=True, stdout="output", return_code=0, duration_ms=100
        )
        adapter._executor.execute = AsyncMock(return_value=mock_result)
        result = await adapter.execute("run something")
        assert result.status == "ok"
        assert result.result == "output"

    @pytest.mark.asyncio
    async def test_execute_script_failure(self):
        """execute returns error for failed script."""
        from core.skills.executor import ScriptExecutionResult

        adapter = self._make_adapter(
            has_scripts=True, scripts_dir="/tmp/s", scripts_list=["run.sh"]
        )
        mock_result = ScriptExecutionResult(
            success=False, stderr="error msg", return_code=1, error="script failed"
        )
        adapter._executor.execute = AsyncMock(return_value=mock_result)
        result = await adapter.execute("run something")
        assert result.status == "error"
        assert result.error == "script failed"

    @pytest.mark.asyncio
    async def test_execute_exception(self):
        """execute handles unexpected exception."""
        adapter = self._make_adapter()
        with patch("core.skills.adapter.MarkdownSkillAdapter") as MockAdapter:
            MockAdapter.side_effect = RuntimeError("unexpected")
            result = await adapter.execute("apply")
        assert result.status == "error"
        assert "RuntimeError" in result.error

    @pytest.mark.asyncio
    async def test_execute_script_no_scripts_found(self):
        """execute returns error when scripts_dir exists but no scripts found."""
        adapter = self._make_adapter(has_scripts=True, scripts_dir="/tmp/s", scripts_list=[])
        result = await adapter.execute("run")
        assert result.status == "error"
        assert "no scripts found" in result.error

    @pytest.mark.asyncio
    async def test_execute_script_selection_from_context(self):
        """execute uses script name from context."""
        from core.skills.executor import ScriptExecutionResult

        adapter = self._make_adapter(
            has_scripts=True, scripts_dir="/tmp/s", scripts_list=["a.sh", "b.sh"]
        )
        mock_result = ScriptExecutionResult(
            success=True, stdout="from b", return_code=0, duration_ms=50
        )
        adapter._executor.execute = AsyncMock(return_value=mock_result)
        result = await adapter.execute("run", context={"script": "b.sh"})
        assert result.status == "ok"
        # Verify the script name passed to executor
        call_kwargs = adapter._executor.execute.call_args
        assert call_kwargs.kwargs.get("script") == "b.sh" or call_kwargs[1].get("script") == "b.sh"

    @pytest.mark.asyncio
    async def test_execute_script_selection_from_task(self):
        """execute finds script name mentioned in task text."""
        from core.skills.executor import ScriptExecutionResult

        adapter = self._make_adapter(
            has_scripts=True, scripts_dir="/tmp/s", scripts_list=["check.py", "run.sh"]
        )
        mock_result = ScriptExecutionResult(
            success=True, stdout="checked", return_code=0, duration_ms=50
        )
        adapter._executor.execute = AsyncMock(return_value=mock_result)
        result = await adapter.execute("please run check.py on the data")
        assert result.status == "ok"

    @pytest.mark.asyncio
    async def test_execute_script_with_args_and_env(self):
        """execute passes args, env, stdin_data to executor."""
        from core.skills.executor import ScriptExecutionResult

        adapter = self._make_adapter(
            has_scripts=True, scripts_dir="/tmp/s", scripts_list=["run.sh"]
        )
        mock_result = ScriptExecutionResult(success=True, stdout="ok", return_code=0)
        adapter._executor.execute = AsyncMock(return_value=mock_result)
        result = await adapter.execute(
            "task",
            context={
                "args": ["--verbose", "--output", "file.txt"],
                "env": {"MY_VAR": "value"},
                "stdin_data": "input data",
            },
        )
        assert result.status == "ok"
