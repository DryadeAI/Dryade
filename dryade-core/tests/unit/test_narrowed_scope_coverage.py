"""Targeted coverage tests for narrowed-scope modules.

Closes coverage gaps in modules tracked by pyproject.toml [tool.coverage.run]:
- core/extensions/state.py (resolve_state_with_conflicts, export_state_to_store)
- core/extensions/decorator.py (with_extensions execution, _store_* helpers)
- core/orchestrator/router.py (escalation handling, unknown mode, route_request)
- core/orchestrator/escalation.py (_verify_mcp_restart, _restart_mcp_server)
- core/skills/watcher.py (SkillWatcher lifecycle, _watch_loop)
- core/orchestrator/handlers/orchestrate_handler.py (visibility filter, event helpers)
- core/skills/models.py (Skill.get_scripts, get_script_path)
- core/skills/mcp_bridge.py (bridge_mcp_tool_to_skill, discover_mcp_tools_as_skills)
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# =============================================================================
# state.py -- resolve_state_with_conflicts and export_state_to_store
# =============================================================================

class TestResolveStateWithConflicts:
    """Tests for resolve_state_with_conflicts (lines 321-350)."""

    def test_no_requirements_returns_args_unchanged(self):
        from core.extensions.state import MultiValueStateStore, resolve_state_with_conflicts

        store = MultiValueStateStore()

        def plain_fn():
            pass

        args = {"key": "value"}
        resolved, conflicts = resolve_state_with_conflicts(plain_fn, args, store)
        assert resolved == args
        assert conflicts == []

    def test_single_value_resolved(self):
        from core.extensions.state import (
            MultiValueStateStore,
            requires_state,
            resolve_state_with_conflicts,
        )

        @requires_state("ns.session_id")
        def my_tool(session_id=None):
            pass

        store = MultiValueStateStore()
        store.export("ns.session_id", "sess_123", "tool_a")

        resolved, conflicts = resolve_state_with_conflicts(my_tool, {}, store)
        assert resolved["session_id"] == "sess_123"
        assert conflicts == []

    def test_conflict_detected(self):
        from core.extensions.state import (
            MultiValueStateStore,
            requires_state,
            resolve_state_with_conflicts,
        )

        @requires_state("ns.session_id")
        def my_tool(session_id=None):
            pass

        store = MultiValueStateStore()
        store.export("ns.session_id", "sess_a", "tool_a")
        store.export("ns.session_id", "sess_b", "tool_b")

        resolved, conflicts = resolve_state_with_conflicts(my_tool, {}, store)
        assert len(conflicts) == 1
        assert conflicts[0].state_key == "ns.session_id"
        assert "session_id" not in resolved

    def test_provided_arg_not_overridden(self):
        from core.extensions.state import (
            MultiValueStateStore,
            requires_state,
            resolve_state_with_conflicts,
        )

        @requires_state("ns.val")
        def my_tool(val=None):
            pass

        store = MultiValueStateStore()
        store.export("ns.val", "from_store", "tool_a")

        resolved, conflicts = resolve_state_with_conflicts(my_tool, {"val": "from_user"}, store)
        assert resolved["val"] == "from_user"
        assert conflicts == []

    def test_uses_global_store_when_none(self):
        from core.extensions.state import (
            get_state_store,
            requires_state,
            reset_state_store,
            resolve_state_with_conflicts,
        )

        reset_state_store()
        store = get_state_store()
        store.export("ns.key", "global_val", "src")

        @requires_state("ns.key")
        def my_tool(key=None):
            pass

        resolved, conflicts = resolve_state_with_conflicts(my_tool, {})
        assert resolved["key"] == "global_val"
        reset_state_store()

    def test_missing_value_not_filled(self):
        from core.extensions.state import (
            MultiValueStateStore,
            requires_state,
            resolve_state_with_conflicts,
        )

        @requires_state("ns.missing")
        def my_tool(missing=None):
            pass

        store = MultiValueStateStore()

        resolved, conflicts = resolve_state_with_conflicts(my_tool, {}, store)
        assert "missing" not in resolved
        assert conflicts == []

class TestExportStateToStore:
    """Tests for export_state_to_store (lines 366-375)."""

    def test_exports_from_result(self):
        from core.extensions.state import MultiValueStateStore, export_state_to_store

        store = MultiValueStateStore()
        result = {"data": "value", "_exports": {"ns.key": "exported_val"}}

        exports = export_state_to_store(result, "my_tool", store)
        assert exports == {"ns.key": "exported_val"}
        assert store.get("ns.key") == "exported_val"

    def test_skips_none_exports(self):
        from core.extensions.state import MultiValueStateStore, export_state_to_store

        store = MultiValueStateStore()
        result = {"_exports": {"ns.key": None, "ns.other": "val"}}

        exports = export_state_to_store(result, "my_tool", store)
        assert "ns.key" not in exports
        assert exports["ns.other"] == "val"

    def test_no_exports_in_result(self):
        from core.extensions.state import MultiValueStateStore, export_state_to_store

        store = MultiValueStateStore()
        result = {"data": "value"}

        exports = export_state_to_store(result, "my_tool", store)
        assert exports == {}

    def test_non_dict_result(self):
        from core.extensions.state import MultiValueStateStore, export_state_to_store

        store = MultiValueStateStore()
        exports = export_state_to_store("string_result", "my_tool", store)
        assert exports == {}

    def test_uses_global_store_when_none(self):
        from core.extensions.state import (
            export_state_to_store,
            get_state_store,
            reset_state_store,
        )

        reset_state_store()
        result = {"_exports": {"ns.key": "val"}}
        exports = export_state_to_store(result, "tool")
        assert exports["ns.key"] == "val"
        assert get_state_store().get("ns.key") == "val"
        reset_state_store()

# =============================================================================
# decorator.py -- with_extensions decorator and _store_* helpers
# =============================================================================

class TestWithExtensionsDecorator:
    """Tests for with_extensions decorator (lines 60, 102-103)."""

    @pytest.mark.asyncio
    async def test_basic_execution(self):
        """Test decorator wraps and executes function."""
        from core.extensions.decorator import with_extensions

        @with_extensions(operation="test_op")
        async def my_func(arg1, arg2=None):
            return {"result": arg1, "metadata": {}}

        with (
            patch("core.extensions.decorator._store_extension_execution", new_callable=AsyncMock),
            patch("core.extensions.decorator._store_timeline_entry", new_callable=AsyncMock),
        ):
            result = await my_func("hello", arg2="world")
        assert result["result"] == "hello"

    @pytest.mark.asyncio
    async def test_exception_propagation(self):
        """Test decorator propagates exceptions."""
        from core.extensions.decorator import with_extensions

        @with_extensions(operation="test_op")
        async def failing_func():
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            await failing_func()

class TestStoreExtensionExecution:
    """Tests for _store_extension_execution (lines 130-151)."""

    @pytest.mark.asyncio
    async def test_store_execution_handles_import_error(self):
        """Test graceful handling when DB modules not available."""
        from core.extensions.decorator import _store_extension_execution

        # The function uses lazy imports inside try/except, so an import
        # error within the try block is caught and logged as warning
        with patch.dict("sys.modules", {"core.database.models": None}):
            # Should not raise - just logs warning
            await _store_extension_execution(
                request_id="req-1",
                conversation_id=None,
                extensions_applied=["ext1"],
                duration_ms=10.0,
                cache_hit=False,
                healed=False,
                threats_found=[],
            )

    @pytest.mark.asyncio
    async def test_store_execution_with_empty_extensions(self):
        """Test with empty extensions list (no DB writes)."""
        from core.extensions.decorator import _store_extension_execution

        # With empty list, the inner loop doesn't execute
        # Still exercises the function body and the try/except
        await _store_extension_execution(
            request_id="req-1",
            conversation_id="conv-1",
            extensions_applied=[],
            duration_ms=50.0,
            cache_hit=False,
            healed=False,
            threats_found=[],
        )

class TestStoreTimelineEntry:
    """Tests for _store_timeline_entry (lines 165-187)."""

    @pytest.mark.asyncio
    async def test_store_timeline_handles_import_error(self):
        """Test graceful handling when DB modules not available."""
        from core.extensions.decorator import _store_timeline_entry

        with patch.dict("sys.modules", {"core.database.models": None}):
            await _store_timeline_entry(
                request_id="req-1",
                conversation_id=None,
                operation="op",
                extensions_applied=[],
                duration_ms=0,
                cache_hit=False,
                healed=False,
                threats_found=[],
            )

# =============================================================================
# router.py -- escalation handling in ExecutionRouter
# =============================================================================

class TestExecutionRouterEscalation:
    """Tests for router escalation handling (lines 105, 135-205)."""

    @pytest.mark.asyncio
    async def test_unknown_mode_emits_error(self):
        """Test that an unknown mode emits error event."""
        from core.orchestrator.router import ExecutionContext, ExecutionRouter

        router = ExecutionRouter()
        context = ExecutionContext(conversation_id="conv-1")
        # Force an unknown mode by patching the handler dict lookup to miss
        context.mode = "nonexistent_mode"

        events = []
        async for event in router.route("test", context):
            events.append(event)

        # Should get an error event -- check content field
        assert any(e.type in ("error",) and "Unknown mode" in (e.content or "") for e in events)

    @pytest.mark.asyncio
    async def test_escalation_rejection_flow(self):
        """Test escalation rejection path (lines 145-156)."""
        from core.orchestrator.escalation import (
            EscalationAction,
            EscalationActionType,
            EscalationRegistry,
            PendingEscalation,
        )
        from core.orchestrator.router import ExecutionContext, ExecutionRouter

        router = ExecutionRouter()
        context = ExecutionContext(conversation_id="test-esc-reject")

        escalation = PendingEscalation(
            conversation_id="test-esc-reject",
            original_goal="read file",
            action=EscalationAction(
                action_type=EscalationActionType.UPDATE_MCP_CONFIG,
                parameters={"path": "/tmp"},
            ),
            question="Allow?",
        )

        mock_registry = EscalationRegistry()
        mock_registry.register(escalation)

        with patch(
            "core.orchestrator.escalation.get_escalation_registry",
            return_value=mock_registry,
        ):
            events = []
            async for event in router.route("no", context):
                events.append(event)

        event_types = [e.type for e in events]
        assert "thinking" in event_types
        assert "complete" in event_types

    @pytest.mark.asyncio
    async def test_escalation_cleared_for_non_response(self):
        """Test escalation cleared when message is not approval/rejection."""
        from core.orchestrator.escalation import (
            EscalationAction,
            EscalationActionType,
            EscalationRegistry,
            PendingEscalation,
        )
        from core.orchestrator.router import ExecutionContext, ExecutionRouter

        router = ExecutionRouter()
        context = ExecutionContext(conversation_id="test-esc-clear")

        escalation = PendingEscalation(
            conversation_id="test-esc-clear",
            original_goal="do something",
            action=EscalationAction(
                action_type=EscalationActionType.UPDATE_MCP_CONFIG,
            ),
            question="Proceed?",
        )

        mock_registry = EscalationRegistry()
        mock_registry.register(escalation)

        async def empty_gen(*a, **kw):
            return
            yield  # noqa: make it an async generator

        with (
            patch(
                "core.orchestrator.escalation.get_escalation_registry",
                return_value=mock_registry,
            ),
            patch.object(router._orchestrate_handler, "handle", side_effect=empty_gen),
        ):
            events = []
            async for event in router.route("what do you mean?", context):
                events.append(event)

        # Escalation should be cleared
        assert mock_registry.get_pending("test-esc-clear") is None

    @pytest.mark.asyncio
    async def test_escalation_approval_success(self):
        """Test escalation approval with successful execution."""
        from core.orchestrator.escalation import (
            EscalationAction,
            EscalationActionType,
            EscalationRegistry,
            PendingEscalation,
        )
        from core.orchestrator.router import ExecutionContext, ExecutionRouter

        router = ExecutionRouter()
        context = ExecutionContext(conversation_id="test-esc-approve")

        escalation = PendingEscalation(
            conversation_id="test-esc-approve",
            original_goal="read /tmp/file",
            action=EscalationAction(
                action_type=EscalationActionType.UPDATE_MCP_CONFIG,
                parameters={"path": "/tmp"},
                description="Add /tmp to allowed",
            ),
            question="Allow?",
        )

        mock_registry = EscalationRegistry()
        mock_registry.register(escalation)

        async def mock_handle(*a, **kw):
            from core.extensions.events import emit_complete

            yield emit_complete("Done!", {})

        with (
            patch(
                "core.orchestrator.escalation.get_escalation_registry",
                return_value=mock_registry,
            ),
            patch("core.orchestrator.escalation.EscalationExecutor") as MockExecutor,
            patch.object(router._orchestrate_handler, "handle", side_effect=mock_handle),
        ):
            MockExecutor.return_value.execute = AsyncMock(return_value=(True, "Config updated"))

            events = []
            async for event in router.route("yes", context):
                events.append(event)

        event_types = [e.type for e in events]
        assert "thinking" in event_types
        assert "complete" in event_types

    @pytest.mark.asyncio
    async def test_escalation_approval_failure(self):
        """Test escalation approval when execution fails."""
        from core.orchestrator.escalation import (
            EscalationAction,
            EscalationActionType,
            EscalationRegistry,
            PendingEscalation,
        )
        from core.orchestrator.router import ExecutionContext, ExecutionRouter

        router = ExecutionRouter()
        context = ExecutionContext(conversation_id="test-esc-fail")

        escalation = PendingEscalation(
            conversation_id="test-esc-fail",
            original_goal="read /tmp/file",
            action=EscalationAction(
                action_type=EscalationActionType.UPDATE_MCP_CONFIG,
                parameters={"path": "/tmp"},
                description="Add /tmp",
            ),
            question="Allow?",
        )

        mock_registry = EscalationRegistry()
        mock_registry.register(escalation)

        with (
            patch(
                "core.orchestrator.escalation.get_escalation_registry",
                return_value=mock_registry,
            ),
            patch("core.orchestrator.escalation.EscalationExecutor") as MockExecutor,
        ):
            MockExecutor.return_value.execute = AsyncMock(
                return_value=(False, "Config update failed")
            )

            events = []
            async for event in router.route("yes", context):
                events.append(event)

        event_types = [e.type for e in events]
        # Post-fix: escalation failure emits "thinking" (with error message) then
        # "complete" (with failure_msg) instead of "error" to avoid killing the
        # event stream (frontend's error handler returns early before emit_complete).
        assert "thinking" in event_types
        assert "complete" in event_types

class TestRouteRequest:
    """Tests for route_request convenience function."""

    def test_route_request_mode_mapping(self):
        """Test route_request maps mode strings correctly."""
        from core.orchestrator.router import _MODE_MAP, ExecutionMode

        assert _MODE_MAP["planner"] == ExecutionMode.PLANNER
        assert _MODE_MAP["flow"] == ExecutionMode.PLANNER
        assert _MODE_MAP["chat"] == ExecutionMode.ORCHESTRATE
        assert _MODE_MAP["orchestrate"] == ExecutionMode.ORCHESTRATE
        assert _MODE_MAP["crew"] == ExecutionMode.ORCHESTRATE
        assert _MODE_MAP["autonomous"] == ExecutionMode.ORCHESTRATE

# =============================================================================
# escalation.py -- _verify_mcp_restart and _restart_mcp_server
# =============================================================================

class TestVerifyMCPRestart:
    """Tests for EscalationExecutor._verify_mcp_restart (lines 330-365)."""

    @pytest.mark.asyncio
    async def test_verify_success(self):
        from core.orchestrator.escalation import EscalationExecutor

        executor = EscalationExecutor()
        mock_registry = MagicMock()
        mock_registry.is_running.return_value = True
        mock_registry.list_tools.return_value = ["tool1", "tool2"]

        with patch(
            "core.mcp.registry.get_registry",
            return_value=mock_registry,
        ):
            success, msg = await executor._verify_mcp_restart("filesystem")

        assert success is True
        assert "restarted successfully" in msg

    @pytest.mark.asyncio
    async def test_verify_not_running(self):
        from core.orchestrator.escalation import EscalationExecutor

        executor = EscalationExecutor()
        mock_registry = MagicMock()
        mock_registry.is_running.return_value = False

        with patch(
            "core.mcp.registry.get_registry",
            return_value=mock_registry,
        ):
            success, msg = await executor._verify_mcp_restart(
                "filesystem", max_retries=1, retry_delay=0.01
            )

        assert success is False
        assert "could not be verified" in msg

    @pytest.mark.asyncio
    async def test_verify_exception_handling(self):
        from core.orchestrator.escalation import EscalationExecutor

        executor = EscalationExecutor()
        mock_registry = MagicMock()
        mock_registry.is_running.side_effect = Exception("connection error")

        with patch(
            "core.mcp.registry.get_registry",
            return_value=mock_registry,
        ):
            success, msg = await executor._verify_mcp_restart(
                "filesystem", max_retries=1, retry_delay=0.01
            )

        assert success is False

    @pytest.mark.asyncio
    async def test_verify_tools_none(self):
        """Test when server is running but list_tools returns None."""
        from core.orchestrator.escalation import EscalationExecutor

        executor = EscalationExecutor()
        mock_registry = MagicMock()
        mock_registry.is_running.return_value = True
        mock_registry.list_tools.return_value = None

        with patch(
            "core.mcp.registry.get_registry",
            return_value=mock_registry,
        ):
            success, msg = await executor._verify_mcp_restart(
                "filesystem", max_retries=1, retry_delay=0.01
            )

        assert success is False

class TestRestartMCPServer:
    """Tests for EscalationExecutor._restart_mcp_server (lines 379-421)."""

    @pytest.mark.asyncio
    async def test_restart_success(self):
        from core.orchestrator.escalation import EscalationExecutor

        executor = EscalationExecutor()
        mock_registry = MagicMock()
        mock_registry.is_running.return_value = True
        mock_registry.is_registered.return_value = True

        mock_config = {
            "servers": {
                "filesystem": {"command": ["npx", "-y", "@modelcontextprotocol/server-filesystem"]}
            }
        }

        with (
            patch("core.mcp.registry.get_registry", return_value=mock_registry),
            patch("core.mcp.autoload.load_mcp_config", return_value=mock_config),
            patch("core.mcp.autoload._config_to_mcp_server_config", return_value=MagicMock()),
            patch.object(
                executor, "_verify_mcp_restart", new_callable=AsyncMock, return_value=(True, "OK")
            ),
        ):
            success, msg = await executor._restart_mcp_server("filesystem")

        assert success is True
        mock_registry.stop.assert_called_once_with("filesystem")
        mock_registry.unregister.assert_called_once_with("filesystem")
        mock_registry.register.assert_called_once()
        mock_registry.start.assert_called_once_with("filesystem")

    @pytest.mark.asyncio
    async def test_restart_server_not_in_config(self):
        from core.orchestrator.escalation import EscalationExecutor

        executor = EscalationExecutor()
        mock_registry = MagicMock()
        mock_registry.is_running.return_value = False

        with (
            patch("core.mcp.registry.get_registry", return_value=mock_registry),
            patch("core.mcp.autoload.load_mcp_config", return_value={"servers": {}}),
        ):
            success, msg = await executor._restart_mcp_server("missing_server")

        assert success is False
        assert "not found" in msg

    @pytest.mark.asyncio
    async def test_restart_exception(self):
        from core.orchestrator.escalation import EscalationExecutor

        executor = EscalationExecutor()

        with patch(
            "core.mcp.registry.get_registry",
            side_effect=Exception("import error"),
        ):
            success, msg = await executor._restart_mcp_server("filesystem")

        assert success is False
        assert "Failed to restart" in msg

    @pytest.mark.asyncio
    async def test_restart_verify_failure(self):
        """Test restart when verification fails."""
        from core.orchestrator.escalation import EscalationExecutor

        executor = EscalationExecutor()
        mock_registry = MagicMock()
        mock_registry.is_running.return_value = False
        mock_registry.is_registered.return_value = False

        mock_config = {"servers": {"filesystem": {"command": ["npx"]}}}

        with (
            patch("core.mcp.registry.get_registry", return_value=mock_registry),
            patch("core.mcp.autoload.load_mcp_config", return_value=mock_config),
            patch("core.mcp.autoload._config_to_mcp_server_config", return_value=MagicMock()),
            patch.object(
                executor,
                "_verify_mcp_restart",
                new_callable=AsyncMock,
                return_value=(False, "verification failed"),
            ),
        ):
            success, msg = await executor._restart_mcp_server("filesystem")

        assert success is False
        assert "verification failed" in msg

# =============================================================================
# watcher.py -- SkillWatcher lifecycle
# =============================================================================

class TestSkillWatcher:
    """Tests for SkillWatcher (lines 17-18, 81-84, 96-97, 113-153)."""

    def test_watcher_init(self):
        from core.skills.watcher import SkillWatcher

        watcher = SkillWatcher()
        assert watcher.is_running is False
        assert watcher._task is None

    def test_watcher_with_custom_paths(self):
        from core.skills.watcher import SkillWatcher

        paths = [Path("/tmp/skills")]
        watcher = SkillWatcher(watch_paths=paths)
        assert watcher._watch_paths == paths

    @pytest.mark.asyncio
    async def test_start_without_watchfiles(self):
        """Test start is no-op without watchfiles."""
        from core.skills.watcher import SkillWatcher

        watcher = SkillWatcher()
        with patch("core.skills.watcher.WATCHFILES_AVAILABLE", False):
            await watcher.start()
        assert watcher.is_running is False

    @pytest.mark.asyncio
    async def test_start_already_running(self):
        """Test start is no-op when already running."""
        from core.skills.watcher import SkillWatcher

        watcher = SkillWatcher()
        watcher._running = True
        await watcher.start()
        assert watcher._task is None

    @pytest.mark.asyncio
    async def test_stop_not_running(self):
        """Test stop is no-op when not running."""
        from core.skills.watcher import SkillWatcher

        watcher = SkillWatcher()
        await watcher.stop()

    @pytest.mark.asyncio
    async def test_stop_running_cancels_task(self):
        """Test stop cancels task and resets state."""
        from core.skills.watcher import SkillWatcher

        watcher = SkillWatcher()
        watcher._running = True

        # Create a real asyncio task that sleeps forever
        async def sleep_forever():
            await asyncio.sleep(3600)

        watcher._task = asyncio.create_task(sleep_forever())

        await watcher.stop()
        assert watcher.is_running is False
        assert watcher._task is None

    def test_get_watch_paths_from_registry(self):
        """Test _get_watch_paths uses registry when no explicit paths."""
        from core.skills.watcher import SkillWatcher

        watcher = SkillWatcher()
        mock_registry = MagicMock()
        mock_registry.get_search_paths.return_value = [Path("/tmp/skills")]

        with patch(
            "core.skills.registry.get_skill_registry",
            return_value=mock_registry,
        ):
            paths = watcher._get_watch_paths()

        assert paths == [Path("/tmp/skills")]

    def test_get_watch_paths_explicit(self):
        """Test _get_watch_paths returns explicit paths."""
        from core.skills.watcher import SkillWatcher

        explicit = [Path("/custom/skills")]
        watcher = SkillWatcher(watch_paths=explicit)
        paths = watcher._get_watch_paths()
        assert paths == explicit

    def test_is_hot_reload_available(self):
        """Test is_hot_reload_available returns correct value."""
        from core.skills.watcher import is_hot_reload_available

        assert isinstance(is_hot_reload_available(), bool)

    def test_get_skill_watcher_singleton(self):
        """Test get_skill_watcher returns singleton."""
        import core.skills.watcher as mod

        mod._watcher = None
        from core.skills.watcher import get_skill_watcher

        w1 = get_skill_watcher()
        w2 = get_skill_watcher()
        assert w1 is w2
        mod._watcher = None

    @pytest.mark.asyncio
    async def test_start_skill_watcher(self):
        """Test convenience start function."""
        from core.skills.watcher import start_skill_watcher

        with patch("core.skills.watcher.get_skill_watcher") as mock_get:
            mock_watcher = AsyncMock()
            mock_get.return_value = mock_watcher
            await start_skill_watcher()
            mock_watcher.start.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stop_skill_watcher(self):
        """Test convenience stop function."""
        from core.skills.watcher import stop_skill_watcher

        with patch("core.skills.watcher.get_skill_watcher") as mock_get:
            mock_watcher = AsyncMock()
            mock_get.return_value = mock_watcher
            await stop_skill_watcher()
            mock_watcher.stop.assert_awaited_once()

# =============================================================================
# orchestrate_handler.py -- visibility filter and event helpers
# =============================================================================

class TestVisibilityFilter:
    """Tests for _should_emit visibility filter."""

    def test_minimal_blocks_most_events(self):
        from core.orchestrator.handlers._utils import _should_emit

        assert _should_emit("complete", "minimal") is True
        assert _should_emit("error", "minimal") is True
        assert _should_emit("thinking", "minimal") is False
        assert _should_emit("token", "minimal") is False
        assert _should_emit("agent_start", "minimal") is False
        assert _should_emit("progress", "minimal") is False
        assert _should_emit("cost_update", "minimal") is False

    def test_named_steps_blocks_noisy(self):
        from core.orchestrator.handlers._utils import _should_emit

        assert _should_emit("complete", "named-steps") is True
        assert _should_emit("error", "named-steps") is True
        assert _should_emit("thinking", "named-steps") is True
        assert _should_emit("agent_start", "named-steps") is True
        assert _should_emit("token", "named-steps") is True  # Phase 111: tokens are answer content
        assert _should_emit("tool_start", "named-steps") is False
        assert _should_emit("cost_update", "named-steps") is False

    def test_full_transparency_allows_all(self):
        from core.orchestrator.handlers._utils import _should_emit

        assert _should_emit("complete", "full-transparency") is True
        assert _should_emit("thinking", "full-transparency") is True
        assert _should_emit("token", "full-transparency") is True
        assert _should_emit("cost_update", "full-transparency") is True
        assert _should_emit("agent_start", "full-transparency") is True

    def test_unknown_level_defaults_to_named_steps(self):
        from core.orchestrator.handlers._utils import _should_emit

        assert _should_emit("complete", "nonexistent") is True
        assert (
            _should_emit("token", "nonexistent") is True
        )  # Phase 111: tokens pass at named-steps default

    def test_new_event_types_visible_by_default(self):
        """Test denylist semantics: unknown event types are visible."""
        from core.orchestrator.handlers._utils import _should_emit

        assert _should_emit("brand_new_event_type", "minimal") is True
        assert _should_emit("brand_new_event_type", "named-steps") is True
        assert _should_emit("brand_new_event_type", "full-transparency") is True

class TestVisibilityDenyConfig:
    """Tests for VISIBILITY_DENY configuration."""

    def test_deny_sets_are_well_formed(self):
        from core.orchestrator.handlers._utils import VISIBILITY_DENY

        assert "minimal" in VISIBILITY_DENY
        assert "named-steps" in VISIBILITY_DENY
        assert "full-transparency" in VISIBILITY_DENY
        assert len(VISIBILITY_DENY["full-transparency"]) == 0
        assert len(VISIBILITY_DENY["minimal"]) > len(VISIBILITY_DENY["named-steps"])

# =============================================================================
# skills/models.py -- Skill.get_scripts, get_script_path
# =============================================================================

class TestSkillModel:
    """Tests for Skill model methods (lines 57-64, 77-82)."""

    def test_get_scripts_no_scripts_dir(self):
        """Test get_scripts returns empty when no scripts_dir."""
        from core.skills.models import Skill

        skill = Skill(name="test", description="desc", instructions="inst", skill_dir="/tmp")
        assert skill.get_scripts() == []

    def test_get_scripts_nonexistent_dir(self):
        """Test get_scripts returns empty for nonexistent dir."""
        from core.skills.models import Skill

        skill = Skill(
            name="test",
            description="desc",
            instructions="inst",
            skill_dir="/tmp",
            scripts_dir="/nonexistent/path/scripts",
        )
        assert skill.get_scripts() == []

    def test_get_scripts_with_files(self, tmp_path):
        """Test get_scripts returns script filenames."""
        from core.skills.models import Skill

        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "run.sh").write_text("#!/bin/bash")
        (scripts_dir / "process.py").write_text("# python")
        (scripts_dir / ".hidden").write_text("hidden")

        skill = Skill(
            name="test",
            description="desc",
            instructions="inst",
            skill_dir=str(tmp_path),
            scripts_dir=str(scripts_dir),
        )
        scripts = skill.get_scripts()
        assert "run.sh" in scripts
        assert "process.py" in scripts
        assert ".hidden" not in scripts

    def test_get_script_path_no_scripts_dir(self):
        """Test get_script_path returns None when no scripts_dir."""
        from core.skills.models import Skill

        skill = Skill(name="test", description="desc", instructions="inst", skill_dir="/tmp")
        assert skill.get_script_path("run.sh") is None

    def test_get_script_path_found(self, tmp_path):
        """Test get_script_path returns path when script exists."""
        from core.skills.models import Skill

        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "run.sh").write_text("#!/bin/bash")

        skill = Skill(
            name="test",
            description="desc",
            instructions="inst",
            skill_dir=str(tmp_path),
            scripts_dir=str(scripts_dir),
        )
        path = skill.get_script_path("run.sh")
        assert path is not None
        assert "run.sh" in path

    def test_get_script_path_not_found(self, tmp_path):
        """Test get_script_path returns None when script missing."""
        from core.skills.models import Skill

        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()

        skill = Skill(
            name="test",
            description="desc",
            instructions="inst",
            skill_dir=str(tmp_path),
            scripts_dir=str(scripts_dir),
        )
        assert skill.get_script_path("nonexistent.sh") is None

# =============================================================================
# skills/mcp_bridge.py -- bridge_mcp_tool_to_skill, discover_mcp_tools_as_skills
# =============================================================================

class TestMCPBridge:
    """Tests for mcp_bridge functions (lines 47, 107-116)."""

    def test_bridge_tool_with_docstring(self):
        """Test bridging a tool with function docstring."""
        from core.skills.mcp_bridge import bridge_mcp_tool_to_skill

        mock_func = MagicMock()
        mock_func.__doc__ = "Read a file from the filesystem.\n\nReturns file content."

        mock_tool = MagicMock()
        mock_tool.name = "read_file"
        mock_tool.func = mock_func

        skill = bridge_mcp_tool_to_skill(mock_tool)
        assert skill.name == "read_file"
        assert "Read a file" in skill.description

    def test_bridge_tool_without_docstring(self):
        """Test bridging a tool without function docstring (line 47)."""
        from core.skills.mcp_bridge import bridge_mcp_tool_to_skill

        mock_func = MagicMock()
        mock_func.__doc__ = None

        mock_tool = MagicMock()
        mock_tool.name = "mystery_tool"
        mock_tool.func = mock_func

        skill = bridge_mcp_tool_to_skill(mock_tool)
        assert skill.name == "mystery_tool"
        assert "MCP tool:" in skill.description

    def test_discover_mcp_tools_import_error(self):
        """Test discover_mcp_tools_as_skills when plugin not available."""
        from core.skills.mcp_bridge import discover_mcp_tools_as_skills

        with patch.dict("sys.modules", {"plugins.mcp.bridge": None}):
            skills = discover_mcp_tools_as_skills()
        assert skills == []

    def test_discover_mcp_tools_bridge_failure(self):
        """Test discover handles individual tool bridge failure (lines 107-109)."""
        from core.skills.mcp_bridge import discover_mcp_tools_as_skills

        bad_tool = MagicMock()
        bad_tool.name = "bad_tool"

        mock_module = MagicMock()
        mock_module.CAPELLA_TOOLS = [bad_tool]

        with (
            patch.dict("sys.modules", {"plugins.mcp.bridge": mock_module}),
            patch(
                "core.skills.mcp_bridge.bridge_mcp_tool_to_skill",
                side_effect=Exception("bridge error"),
            ),
        ):
            skills = discover_mcp_tools_as_skills()
        assert skills == []

    def test_discover_mcp_tools_general_exception(self):
        """Test discover handles general exception (lines 115-116)."""
        from core.skills.mcp_bridge import discover_mcp_tools_as_skills

        mock_module = MagicMock()
        # Make CAPELLA_TOOLS iteration raise
        mock_module.CAPELLA_TOOLS = MagicMock(side_effect=RuntimeError("boom"))

        with patch.dict("sys.modules", {"plugins.mcp.bridge": mock_module}):
            skills = discover_mcp_tools_as_skills()
        assert skills == []

# =============================================================================
# skills/models.py -- SkillGateResult
# =============================================================================

class TestSkillGateResult:
    """Tests for SkillGateResult model."""

    def test_eligible_result(self):
        from core.skills.models import SkillGateResult

        result = SkillGateResult(eligible=True)
        assert result.eligible is True
        assert result.reason is None
        assert result.missing_bins == []

    def test_ineligible_result(self):
        from core.skills.models import SkillGateResult

        result = SkillGateResult(
            eligible=False,
            reason="Missing required binary",
            missing_bins=["git", "docker"],
            missing_env=["API_KEY"],
        )
        assert result.eligible is False
        assert len(result.missing_bins) == 2
        assert result.missing_env == ["API_KEY"]
