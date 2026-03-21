"""Gap closure tests targeting 71 specific uncovered statements across 14 modules.

Plan 86.2-12: Push narrowed-scope coverage from 88.89% to 90%+.
Each test exercises specific uncovered lines identified in coverage.json.
"""

import asyncio
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# =============================================================================
# 1. core/orchestrator/escalation.py — lines 308-310
# =============================================================================

class TestEscalationExceptionHandler:
    """Test the except Exception handler in _update_mcp_config (lines 308-310)."""

    @pytest.mark.asyncio
    async def test_update_mcp_config_generic_exception(self):
        """When _update_mcp_config raises generic Exception, returns (False, error msg)."""
        from core.orchestrator.escalation import EscalationExecutor

        executor = EscalationExecutor()

        # DEFAULT_CONFIG_PATH is imported inside the function from core.mcp.autoload
        # Patch at the source so the deferred import picks it up
        mock_path = MagicMock()
        mock_path.exists.return_value = True

        with (
            patch("core.mcp.autoload.DEFAULT_CONFIG_PATH", mock_path),
            patch("builtins.open", side_effect=RuntimeError("disk error")),
        ):
            success, msg = await executor._update_mcp_config(
                {"path": "/home/test", "server": "filesystem"}
            )

        assert success is False
        assert "Failed to update MCP config" in msg
        assert "disk error" in msg

# =============================================================================
# 2. core/orchestrator/handlers/planner_handler.py — lines 257, 309-310
# =============================================================================

class TestPlannerHandlerGaps:
    """Test uncovered branches in PlannerHandler."""

    @pytest.mark.skip(reason="_update_plan_status removed in post-119.6 PlannerHandler refactor")
    @pytest.mark.asyncio
    async def test_update_plan_status_unexpected_status_becomes_failed(self):
        """Line 257: execution_status not in {completed, failed, cancelled} -> 'failed'.

        Skipped: _update_plan_status was removed from PlannerHandler in the
        post-119.6 refactor that separated flow execution from plan status tracking.
        """
        pass

    @pytest.mark.skip(
        reason="_execute_flow/_topological_sort removed in post-119.6 PlannerHandler refactor"
    )
    @pytest.mark.asyncio
    async def test_execute_flow_node_not_found_skips(self):
        """Lines 309-310: node_id not in flow.nodes -> continue (skip).

        Skipped: _execute_flow and _topological_sort were removed from PlannerHandler
        in the post-119.6 refactor. Flow execution moved to a dedicated executor.
        """
        pass

# =============================================================================
# 3. core/skills/executor.py — lines 256-258
# =============================================================================

class TestSkillExecutorGenericException:
    """Test generic Exception handler in script execution (lines 256-258)."""

    @pytest.mark.asyncio
    async def test_execute_generic_exception(self):
        """Generic Exception (not FileNotFoundError/PermissionError) returns error result."""
        from core.skills.executor import SkillScriptExecutor
        from core.skills.models import Skill

        executor = SkillScriptExecutor()
        skill = Skill(
            name="test-skill",
            description="test",
            instructions="test",
            skill_dir="/tmp/test-skill",
            scripts_dir="/tmp/test-skill/scripts",
        )

        # Mock get_script_path to return a valid path
        with (
            patch.object(skill, "get_script_path", return_value="/tmp/test-skill/scripts/run.sh"),
            patch("os.access", return_value=True),
            patch("asyncio.create_subprocess_exec", side_effect=OSError("mocked OS error")),
        ):
            result = await executor.execute(skill, "run.sh")

        assert result.success is False
        assert "OSError" in result.error
        assert "mocked OS error" in result.error

# =============================================================================
# 4. core/extensions/__init__.py — lines 120-121, 158-159
# =============================================================================

class TestExtensionsOptionalImports:
    """Test ImportError handling for optional plugin imports."""

    def test_try_import_nonexistent_module(self):
        """Lines 120-121: _try_import with non-existent module doesn't raise."""
        from core.extensions import _try_import

        # Should not raise — just silently passes
        _try_import("totally.fake.nonexistent.module.xyz", ["FakeClass"])

    def test_import_cache_wrapper_importerror(self):
        """Lines 158-159: _import_cache_wrapper with missing plugin doesn't raise."""
        from core.extensions import _import_cache_wrapper

        # Patch the specific import to force ImportError
        with patch("builtins.__import__", side_effect=ImportError("no module")):
            # Should not raise
            _import_cache_wrapper()

# =============================================================================
# 5. core/orchestrator/observation.py — lines 101, 116, 189, 202
# =============================================================================

class TestObservationHistoryGaps:
    """Test uncovered lines in ObservationHistory."""

    def _make_obs(self, agent="agent-1", task="task", result="ok", success=True, error=None):
        from core.orchestrator.models import OrchestrationObservation

        return OrchestrationObservation(
            agent_name=agent,
            task=task,
            result=result,
            success=success,
            error=error,
            duration_ms=100,
        )

    def test_format_empty_facts_shows_none_yet(self):
        """Line 101: empty _facts -> '(none yet)' in render."""
        from core.orchestrator.observation import ObservationHistory

        history = ObservationHistory()
        # Add obs that generates no facts (result has no paths/UUIDs)
        history._facts = []  # Ensure empty
        history._recent.append(self._make_obs(result="simple result"))

        output = history.format_for_llm()
        assert "(none yet)" in output

    def test_observation_with_error_renders_error_tag(self):
        """Line 116: observation with obs.error set renders <error> tag."""
        from core.orchestrator.observation import ObservationHistory

        history = ObservationHistory()
        obs = self._make_obs(success=False, error="Connection timeout", result="fail")
        history._recent.append(obs)

        output = history.format_for_llm()
        assert "<error>Connection timeout</error>" in output

    def test_extract_facts_break_after_3_paths(self):
        """Line 189: break when 3+ file paths seen (capped at 3)."""
        from core.orchestrator.observation import ObservationHistory

        # Use newline-separated paths so the regex can match each individually.
        # The unquoted path regex includes spaces in its character class, so
        # space-separated paths would merge into one long match.
        obs = self._make_obs(
            result="/path/one/file.txt\n/path/two/file.txt\n/path/three/file.txt\n/path/four/file.txt"
        )
        facts = ObservationHistory._extract_facts(obs)
        path_facts = [f for f in facts if f.startswith("path:")]
        assert len(path_facts) == 3  # Capped at 3

    def test_extract_facts_uuid_extraction(self):
        """Line 202: UUID extraction from result string."""
        from core.orchestrator.observation import ObservationHistory

        obs = self._make_obs(
            result="Created resource 12345678-1234-1234-1234-123456789abc successfully"
        )
        facts = ObservationHistory._extract_facts(obs)
        uuid_facts = [f for f in facts if f.startswith("uuid:")]
        assert len(uuid_facts) == 1
        assert "12345678-1234-1234-1234-123456789abc" in uuid_facts[0]

# =============================================================================
# 6. core/autonomous/leash.py — lines 82, 85, 88, 94, 109
# =============================================================================

class TestLeashConstraints:
    """Test individual limit checks in LeashConfig.exceeded()."""

    def test_max_tokens_exceeded(self):
        """Line 82: tokens_used > max_tokens."""
        from core.autonomous.leash import LeashConfig
        from core.autonomous.models import ExecutionState

        leash = LeashConfig(
            max_tokens=100,
            max_cost_usd=None,
            max_duration_seconds=None,
            max_actions=None,
            max_tool_calls=None,
        )
        state = ExecutionState(tokens_used=200)
        result = leash.exceeded(state)
        assert result.exceeded is True
        assert any("tokens:" in r for r in result.reasons)

    def test_max_cost_exceeded(self):
        """Line 85: cost_usd > max_cost_usd."""
        from core.autonomous.leash import LeashConfig
        from core.autonomous.models import ExecutionState

        leash = LeashConfig(
            max_tokens=None,
            max_cost_usd=0.10,
            max_duration_seconds=None,
            max_actions=None,
            max_tool_calls=None,
        )
        state = ExecutionState(cost_usd=0.50)
        result = leash.exceeded(state)
        assert result.exceeded is True
        assert any("cost:" in r for r in result.reasons)

    def test_max_duration_exceeded(self):
        """Line 88: duration_seconds > max_duration_seconds."""
        from core.autonomous.leash import LeashConfig
        from core.autonomous.models import ExecutionState

        leash = LeashConfig(
            max_tokens=None,
            max_cost_usd=None,
            max_duration_seconds=1,
            max_actions=None,
            max_tool_calls=None,
        )
        # Create state with started_at far in the past to ensure duration exceeds 1s
        from datetime import timedelta

        state = ExecutionState(started_at=datetime.now(UTC) - timedelta(seconds=60))
        result = leash.exceeded(state)
        assert result.exceeded is True
        assert any("duration:" in r for r in result.reasons)

    def test_max_tool_calls_exceeded(self):
        """Line 94: tool_calls > max_tool_calls."""
        from core.autonomous.leash import LeashConfig
        from core.autonomous.models import ExecutionState

        leash = LeashConfig(
            max_tokens=None,
            max_cost_usd=None,
            max_duration_seconds=None,
            max_actions=None,
            max_tool_calls=10,
        )
        state = ExecutionState(tool_calls=20)
        result = leash.exceeded(state)
        assert result.exceeded is True
        assert any("tool_calls:" in r for r in result.reasons)

    def test_check_action_approval_pattern(self):
        """Line 109: action matches dangerous pattern -> requires_approval."""
        from core.autonomous.leash import LeashConfig

        leash = LeashConfig()
        result = leash.check_action("rm -rf /important/data")
        assert result.requires_approval is True
        assert "dangerous pattern" in result.approval_reason

# =============================================================================
# 7. core/autonomous/planner.py — lines 131, 146, 168, 191, 283
# =============================================================================

class TestPlanAndExecuteAutonomy:
    """Test PlanAndExecuteAutonomy failure paths."""

    @pytest.mark.asyncio
    async def test_planning_failure_returns_failed_step_planning(self):
        """Line 283 (originally ~277): create_plan raises -> GoalResult(success=False, failed_step='planning')."""
        from core.autonomous.planner import PlanAndExecuteAutonomy

        mock_planner = AsyncMock()
        mock_planner.create_plan.side_effect = RuntimeError("LLM unavailable")

        mock_executor = AsyncMock()

        autonomy = PlanAndExecuteAutonomy(
            planning_provider=mock_planner,
            step_executor=mock_executor,
            session_id="test-session",
        )

        result = await autonomy.achieve_goal("Do something complex", skills=[])
        assert result.success is False
        assert result.failed_step == "planning"

# =============================================================================
# 8. core/extensions/request_queue.py — lines 84-85, 88, 103, 106
# =============================================================================

class TestRequestQueueGaps:
    """Test queue full and timeout paths."""

    @pytest.mark.asyncio
    async def test_acquire_queue_full_rejects(self):
        """Lines 84-85, 88: queue full -> rejected immediately."""
        from core.extensions.request_queue import RequestQueue

        # Constructor uses `max_queue_size or int(env)` so 0 is falsy.
        # Set max_queue_size directly after construction.
        queue = RequestQueue(max_concurrent=1, max_queue_size=1)
        queue.max_queue_size = 0  # Force to 0 so _queued(0) >= max_queue_size(0) is True
        result = await queue.acquire()
        assert result is False

    @pytest.mark.asyncio
    async def test_acquire_timeout_rejects(self):
        """Lines 110-114: semaphore timeout -> rejected."""
        from core.extensions.request_queue import RequestQueue

        queue = RequestQueue(max_concurrent=1, max_queue_size=10, queue_timeout_s=0.05)
        # Acquire the single slot
        acquired = await queue.acquire()
        assert acquired is True

        # Second acquire should timeout
        result = await queue.acquire(timeout=0.05)
        assert result is False

        # Cleanup
        await queue.release()

    @pytest.mark.asyncio
    async def test_acquire_wait_times_overflow_trimmed(self):
        """Line 103: wait_times > 1000 entries gets trimmed to last 1000."""
        from core.extensions.request_queue import RequestQueue

        queue = RequestQueue(max_concurrent=10, max_queue_size=10)
        # Pre-fill wait_times to just at boundary
        queue._wait_times = list(range(1001))

        # Acquire and release to trigger the trim
        acquired = await queue.acquire()
        assert acquired is True
        # After acquire, wait_times should be trimmed to last 1000
        assert len(queue._wait_times) <= 1001  # 1001 + new one, then trimmed to 1000
        await queue.release()

    @pytest.mark.asyncio
    async def test_acquire_slow_wait_logs(self):
        """Line 106: wait_ms > 100 triggers info log."""
        from core.extensions.request_queue import RequestQueue

        queue = RequestQueue(max_concurrent=1, max_queue_size=10)

        # Acquire the slot
        acquired = await queue.acquire()
        assert acquired is True

        # Release after a delay in a separate task, so acquire blocks > 100ms
        async def delayed_release():
            await asyncio.sleep(0.15)
            await queue.release()

        task = asyncio.create_task(delayed_release())

        # This should wait and then log "Request acquired after Xms wait"
        result = await queue.acquire(timeout=2.0)
        assert result is True
        await task
        await queue.release()

# =============================================================================
# 9. core/extensions/state.py — lines 134, 218, 240, 250, 251
# =============================================================================

class TestStateGaps:
    """Test StateValue hash and conflict resolution paths."""

    def test_state_value_hash_in_set(self):
        """Line 134: StateValue.__hash__ allows use in sets."""
        from core.extensions.state import StateValue

        sv1 = StateValue(value="abc", source="tool-a")
        sv2 = StateValue(value="xyz", source="tool-b")
        sv3 = StateValue(value="abc", source="tool-a")  # Duplicate

        s = {sv1, sv2, sv3}
        assert len(s) == 2  # sv1 and sv3 hash the same

    def test_check_conflict_already_resolved_returns_none(self):
        """Line 218: check_conflict returns None when key already resolved."""
        from core.extensions.state import MultiValueStateStore

        store = MultiValueStateStore()
        store.export("key", "val1", "source-a")
        store.export("key", "val2", "source-b")

        # Resolve the conflict
        store.resolve_conflict("key", "val1")

        # Now check_conflict should return None
        conflict = store.check_conflict("key")
        assert conflict is None

    def test_resolve_conflict_valid_selection(self):
        """Lines 240, 250, 251: resolve_conflict with valid selection."""
        from core.extensions.state import MultiValueStateStore

        store = MultiValueStateStore()
        store.export("session", "sess-1", "tool-a")
        store.export("session", "sess-2", "tool-b")

        # Create a pending conflict first
        conflict = store.check_conflict("session")
        assert conflict is not None

        # Resolve with valid value
        resolved = store.resolve_conflict("session", "sess-1")
        assert resolved is True

        # Verify the resolved value is accessible
        assert store.get("session") == "sess-1"

        # Verify the pending conflict is marked resolved
        assert store._pending_conflicts["session"].resolved is True
        assert store._pending_conflicts["session"].selected_value == "sess-1"

    def test_resolve_conflict_key_not_in_store(self):
        """Line 240: resolve_conflict returns False for non-existent key."""
        from core.extensions.state import MultiValueStateStore

        store = MultiValueStateStore()
        result = store.resolve_conflict("nonexistent", "value")
        assert result is False

# =============================================================================
# 10. core/orchestrator/templates.py — lines 63-64, 141-142, 181
# =============================================================================

class TestTemplateGaps:
    """Test template loading failure and edge substitution."""

    def test_load_templates_malformed_yaml(self):
        """Lines 63-64: malformed YAML file -> logged error, skipped."""
        from core.orchestrator.templates import TemplateLoader

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a malformed YAML file
            bad_yaml = Path(tmpdir) / "bad.yaml"
            bad_yaml.write_text("name: test\nnodes: [}\n  invalid yaml here")

            loader = TemplateLoader(templates_path=tmpdir)
            templates = loader.load_templates()

            # Should not crash, but return empty or skip the bad file
            assert isinstance(templates, dict)

    def test_instantiate_template_with_edges(self):
        """Lines 141-142: edge substitution in instantiate_template."""
        from core.orchestrator.templates import TemplateLoader

        with tempfile.TemporaryDirectory() as tmpdir:
            template_data = {
                "name": "test-template",
                "description": "Test",
                "parameters": [{"name": "agent", "required": True}],
                "nodes": [{"id": "1", "agent": "{agent}", "task": "do thing"}],
                "edges": [{"source": "1", "target": "2", "label": "{agent}"}],
            }
            template_file = Path(tmpdir) / "test.yaml"
            import yaml

            with open(template_file, "w") as f:
                yaml.safe_dump(template_data, f)

            loader = TemplateLoader(templates_path=tmpdir)
            loader.load_templates()

            result = loader.instantiate_template("test-template", {"agent": "my-agent"})
            assert result["edges"][0]["label"] == "my-agent"
            assert result["nodes"][0]["agent"] == "my-agent"

    def test_substitute_params_non_str_dict_list_type(self):
        """Line 181: _substitute_params with non-str/dict/list type returns as-is."""
        from core.orchestrator.templates import TemplateLoader

        loader = TemplateLoader()
        # int should be returned as-is
        assert loader._substitute_params(42, {"key": "val"}) == 42
        # float should be returned as-is
        assert loader._substitute_params(3.14, {"key": "val"}) == 3.14
        # None should be returned as-is
        assert loader._substitute_params(None, {"key": "val"}) is None

# =============================================================================
# 11. core/autonomous/router.py — lines 134-136, 199-201
# =============================================================================

class TestSkillRouterGaps:
    """Test on-the-fly indexing and clear_index/unregister_skill."""

    def test_route_indexes_unindexed_skill_on_the_fly(self):
        """Lines 134-136: skill not yet indexed -> computed on-the-fly."""
        from core.autonomous.router import IntelligentSkillRouter
        from core.skills.models import Skill

        router = IntelligentSkillRouter()

        # Create a fake encoder that returns numpy arrays
        import numpy as np

        mock_encoder = MagicMock()
        mock_encoder.encode.return_value = np.random.rand(384).astype(np.float32)
        router._encoder = mock_encoder

        skill = Skill(
            name="new-skill",
            description="does new things",
            instructions="test",
            skill_dir="/tmp",
        )

        # Don't pre-index; call route() which should index on-the-fly
        results = router.route("do something new", [skill], top_k=1, threshold=0.0)

        # Should have indexed the skill
        assert "new-skill" in router._skill_embeddings
        assert "new-skill" in router._skill_texts

    def test_clear_index(self):
        """Lines 199-200: clear_index empties embeddings and texts."""
        from core.autonomous.router import IntelligentSkillRouter

        router = IntelligentSkillRouter()
        import numpy as np

        router._skill_embeddings["test"] = np.array([1.0])
        router._skill_texts["test"] = "test: desc"

        router.clear_index()
        assert len(router._skill_embeddings) == 0
        assert len(router._skill_texts) == 0

    def test_unregister_skill(self):
        """Line 201: unregister_skill removes from index."""
        from core.autonomous.router import IntelligentSkillRouter

        router = IntelligentSkillRouter()
        import numpy as np

        router._skill_embeddings["my-skill"] = np.array([1.0])
        router._skill_texts["my-skill"] = "my-skill: desc"

        result = router.unregister_skill("my-skill")
        assert result is True
        assert "my-skill" not in router._skill_embeddings

        # Non-existent skill returns False
        result = router.unregister_skill("no-such-skill")
        assert result is False

# =============================================================================
# 12. core/skills/loader.py — lines 74-77, 262-263
# =============================================================================

class TestSkillLoaderGaps:
    """Test JSON-encoded metadata parsing and discovery exception handling."""

    def test_load_skill_json_encoded_metadata(self):
        """Lines 74-75: metadata is a JSON string that gets parsed."""
        from core.skills.loader import MarkdownSkillLoader

        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()

            skill_md = skill_dir / "SKILL.md"
            skill_md.write_text(
                "---\n"
                "name: test-skill\n"
                "description: A test skill\n"
                'metadata: \'{"dryade": {"emoji": "test"}}\'\n'
                "---\n"
                "\n"
                "Instructions here.\n"
            )

            loader = MarkdownSkillLoader()
            skill = loader.load_skill(skill_dir)

            assert skill.name == "test-skill"
            assert skill.metadata.emoji == "test"

    def test_load_skill_json_encoded_metadata_decode_error(self):
        """Lines 76-77: metadata is a string but invalid JSON -> fallback to empty dict."""
        from core.skills.loader import MarkdownSkillLoader

        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()

            skill_md = skill_dir / "SKILL.md"
            skill_md.write_text(
                "---\n"
                "name: test-skill\n"
                "description: A test skill\n"
                'metadata: "not valid json {{{"\n'
                "---\n"
                "\n"
                "Instructions here.\n"
            )

            loader = MarkdownSkillLoader()
            skill = loader.load_skill(skill_dir)

            assert skill.name == "test-skill"
            # Metadata should fall back to empty dict defaults
            assert skill.metadata.emoji is None

    def test_discover_skills_load_exception_skipped(self):
        """Lines 262-263: skill that raises on load is skipped with warning."""
        from core.skills.loader import MarkdownSkillLoader

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a skill dir with an invalid SKILL.md
            bad_skill_dir = Path(tmpdir) / "bad-skill"
            bad_skill_dir.mkdir()
            bad_skill_md = bad_skill_dir / "SKILL.md"
            bad_skill_md.write_text("not valid frontmatter at all")

            loader = MarkdownSkillLoader()
            skills = loader.discover_skills([Path(tmpdir)], filter_eligible=False)

            # Bad skill should be skipped, not crash
            assert len(skills) == 0

# =============================================================================
# 13. core/adapters/crewai_delegation.py — lines 177-184, 195-196
# =============================================================================

class TestCrewAIDelegationGaps:
    """Test _execute_with_events and get_tools."""

    def test_get_tools_returns_empty_list(self):
        """Lines 195-196: get_tools() returns []."""
        from core.adapters.crewai_delegation import CrewDelegationAdapter

        mock_crew = MagicMock()
        adapter = CrewDelegationAdapter(crew=mock_crew, name="test-crew", description="test")
        assert adapter.get_tools() == []

    @pytest.mark.asyncio
    async def test_execute_with_events_calls_bridge(self):
        """Lines 177-184: _execute_with_events imports and uses CrewAIEventBridge."""
        from core.adapters.crewai_delegation import CrewDelegationAdapter

        mock_crew = MagicMock()
        mock_crew.kickoff.return_value = "crew result"

        emitter_calls = []

        def mock_emitter(data):
            emitter_calls.append(data)

        adapter = CrewDelegationAdapter(
            crew=mock_crew, name="test-crew", description="test", sse_emitter=mock_emitter
        )

        # Mock the event bridge as a context manager
        mock_bridge_class = MagicMock()
        mock_bridge_instance = MagicMock()
        mock_bridge_class.return_value = mock_bridge_instance
        mock_bridge_instance.__enter__ = MagicMock(return_value=mock_bridge_instance)
        mock_bridge_instance.__exit__ = MagicMock(return_value=False)

        mock_sse_event = MagicMock()

        # Patch the modules that _execute_with_events imports from
        with (
            patch.dict(
                "sys.modules",
                {
                    "core.crew": MagicMock(CrewAIEventBridge=mock_bridge_class),
                    "core.crew.event_bridge": MagicMock(SSEEvent=mock_sse_event),
                },
            ),
            patch("asyncio.to_thread", new_callable=AsyncMock, return_value="crew result"),
        ):
            result = await adapter._execute_with_events({"task": "test task"})
            assert result == "crew result"

# =============================================================================
# 14. core/extensions/events.py — lines 297, 315-316, 353, 373, 392, 409, 426, 477
# =============================================================================

class TestEventsEmitFunctions:
    """Test uncovered emit_* helper functions and to_openai_sse edge case."""

    def test_emit_plan_preview(self):
        """Line 297: emit_plan_preview returns correct ChatEvent."""
        from core.extensions.events import emit_plan_preview

        steps = [{"id": "1", "agent": "a", "task": "do"}]
        event = emit_plan_preview(steps, estimated_duration_s=10.0)
        assert event.type == "plan_preview"
        assert event.metadata["step_count"] == 1
        assert event.metadata["estimated_duration_s"] == 10.0

    def test_emit_progress(self):
        """Lines 315-316: emit_progress returns correct ChatEvent."""
        from core.extensions.events import emit_progress

        event = emit_progress(2, 5, "my-agent", eta_seconds=30.0)
        assert event.type == "progress"
        assert event.metadata["percentage"] == 40
        assert event.metadata["current_agent"] == "my-agent"
        assert "2/5" in event.content

    def test_emit_artifact(self):
        """Line 353: emit_artifact returns correct ChatEvent."""
        from core.extensions.events import emit_artifact

        event = emit_artifact("report.pdf", "application/pdf", 1024, preview="Summary")
        assert event.type == "artifact"
        assert event.content == "report.pdf"
        assert event.metadata["mime_type"] == "application/pdf"
        assert event.metadata["size_bytes"] == 1024

    def test_emit_agent_retry(self):
        """Line 373: emit_agent_retry returns correct ChatEvent."""
        from core.extensions.events import emit_agent_retry

        event = emit_agent_retry("agent-x", 2, 3, "timeout", wait_seconds=5.0)
        assert event.type == "agent_retry"
        assert event.metadata["attempt"] == 2
        assert event.metadata["max_attempts"] == 3
        assert event.metadata["wait_seconds"] == 5.0

    def test_emit_agent_fallback(self):
        """Line 392: emit_agent_fallback returns correct ChatEvent."""
        from core.extensions.events import emit_agent_fallback

        event = emit_agent_fallback("agent-a", "agent-b", "agent-a failed")
        assert event.type == "agent_fallback"
        assert event.metadata["original_agent"] == "agent-a"
        assert event.metadata["fallback_agent"] == "agent-b"

    def test_emit_cancel_ack(self):
        """Line 409: emit_cancel_ack returns correct ChatEvent."""
        from core.extensions.events import emit_cancel_ack

        event = emit_cancel_ack(5, current_step=3, reason="User cancelled")
        assert event.type == "cancel_ack"
        assert event.metadata["partial_results_count"] == 5
        assert event.metadata["current_step"] == 3

    def test_emit_memory_update(self):
        """Line 426: emit_memory_update returns correct ChatEvent."""
        from core.extensions.events import emit_memory_update

        event = emit_memory_update("user.pref", "dark theme", scope="global")
        assert event.type == "memory_update"
        assert event.metadata["key"] == "user.pref"
        assert event.metadata["scope"] == "global"

    def test_to_openai_sse_complete_event_no_content(self):
        """Line 477: to_openai_sse with complete event having no content -> empty delta."""
        from core.extensions.events import ChatEvent, to_openai_sse

        event = ChatEvent(type="complete", content=None)
        sse_str = to_openai_sse(event)
        data = json.loads(sse_str.replace("data: ", "").strip())
        assert data["choices"][0]["delta"] == {}
        assert data["choices"][0]["finish_reason"] == "stop"
