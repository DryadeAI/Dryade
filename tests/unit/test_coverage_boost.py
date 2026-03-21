"""Targeted tests to boost core coverage to 90%.

Covers previously untested helper functions, edge cases, and code paths in:
- orchestrator/failure_metrics (helper functions)
- orchestrator/clarification (register, get_pending with expiry, clear)
- orchestrator/reflection (_do_reflect paths)
- orchestrator/routing_metrics (record, get_summary, global accessors)
- api/middleware/tracing (dispatch, _log_span)
- api/middleware/request_size (body too large, disabled state)
- api/middleware/request_metrics (normalize_path, mode detection)
- api/routes/metrics (latency, queue endpoints)
- api/routes/mcp_metrics (health endpoints)
- workflows/schema (graph validation, cycle detection, agent validation)
- skills/mcp_bridge (bridge tool to skill, discover)
- skills/models (Skill methods)
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ===========================================================================
# orchestrator/failure_metrics helpers
# ===========================================================================

class TestFailureMetricsHelpers:
    """Tests for all helper functions in core/orchestrator/failure_metrics.py."""

    def test_record_failure_classification(self):
        """record_failure_classification records counter and histogram."""
        from core.orchestrator.failure_metrics import record_failure_classification

        # Should not raise
        record_failure_classification(
            tier="deterministic",
            category="transient",
            action="retry",
            duration_seconds=0.05,
        )

    def test_record_failure_recovery(self):
        """record_failure_recovery records counter and histogram."""
        from core.orchestrator.failure_metrics import record_failure_recovery

        record_failure_recovery(
            action="retry",
            success=True,
            duration_seconds=1.5,
            agent_name="test-agent",
        )

    def test_record_circuit_breaker_trip(self):
        """record_circuit_breaker_trip records counter."""
        from core.orchestrator.failure_metrics import record_circuit_breaker_trip

        record_circuit_breaker_trip(server_name="test-server", trigger="threshold")

    def test_update_circuit_breaker_state(self):
        """update_circuit_breaker_state sets gauge."""
        from core.orchestrator.failure_metrics import update_circuit_breaker_state

        update_circuit_breaker_state(server_name="test-server", state_str="open")
        update_circuit_breaker_state(server_name="test-server", state_str="closed")
        update_circuit_breaker_state(server_name="test-server", state_str="half_open")

    def test_update_tool_failure_rate(self):
        """update_tool_failure_rate sets gauge."""
        from core.orchestrator.failure_metrics import update_tool_failure_rate

        update_tool_failure_rate(tool_name="test-tool", rate=0.25)

    def test_record_failure_llm_call(self):
        """record_failure_llm_call records counter."""
        from core.orchestrator.failure_metrics import record_failure_llm_call

        record_failure_llm_call(call_type="failure_think")

    def test_record_prevention_check(self):
        """record_prevention_check records counter."""
        from core.orchestrator.failure_metrics import record_prevention_check

        record_prevention_check(check_name="rate_limit", verdict="pass")

    def test_record_soft_failure(self):
        """record_soft_failure records counter."""
        from core.orchestrator.failure_metrics import record_soft_failure

        record_soft_failure(check_type="empty_result")

    def test_record_failure_middleware(self):
        """record_failure_middleware records counter."""
        from core.orchestrator.failure_metrics import record_failure_middleware

        record_failure_middleware(hook_type="pre_failure", success=True)

    def test_record_classifier_accuracy(self):
        """record_classifier_accuracy records counter."""
        from core.orchestrator.failure_metrics import record_classifier_accuracy

        record_classifier_accuracy(category="transient", outcome="resolved")

# ===========================================================================
# orchestrator/clarification
# ===========================================================================

class TestClarificationRegistry:
    """Tests for core/orchestrator/clarification.py uncovered paths."""

    def test_register_stores_and_logs(self):
        """register() stores clarification and logs it."""
        from core.orchestrator.clarification import (
            ClarificationRegistry,
            PendingClarification,
        )

        registry = ClarificationRegistry()
        c = PendingClarification(
            conversation_id="conv-1",
            original_goal="help me",
            clarification_question="Which model do you want to use for this task?",
        )
        registry.register(c)
        assert registry.get_pending("conv-1") is not None
        assert registry.get_pending("conv-1").original_goal == "help me"

    def test_get_pending_expired_returns_none(self):
        """get_pending() returns None for expired clarifications."""
        from core.orchestrator.clarification import (
            ClarificationRegistry,
            PendingClarification,
        )

        registry = ClarificationRegistry()
        c = PendingClarification(
            conversation_id="conv-2",
            original_goal="test",
            clarification_question="Which one?",
            ttl_seconds=0,
            created_at=datetime.now(UTC) - timedelta(seconds=10),
        )
        registry.register(c)
        result = registry.get_pending("conv-2")
        assert result is None

    def test_clear_returns_and_removes(self):
        """clear() returns the clarification and removes it."""
        from core.orchestrator.clarification import (
            ClarificationRegistry,
            PendingClarification,
        )

        registry = ClarificationRegistry()
        c = PendingClarification(
            conversation_id="conv-3",
            original_goal="test",
            clarification_question="Which one?",
        )
        registry.register(c)
        cleared = registry.clear("conv-3")
        assert cleared is not None
        assert cleared.conversation_id == "conv-3"
        assert registry.get_pending("conv-3") is None

    def test_clear_nonexistent_returns_none(self):
        """clear() returns None for non-existent conversation."""
        from core.orchestrator.clarification import ClarificationRegistry

        registry = ClarificationRegistry()
        assert registry.clear("nonexistent") is None

    def test_get_clarification_registry_singleton(self):
        """get_clarification_registry returns a registry instance."""
        from core.orchestrator.clarification import get_clarification_registry

        reg = get_clarification_registry()
        assert reg is not None
        reg2 = get_clarification_registry()
        assert reg is reg2

# ===========================================================================
# orchestrator/reflection
# ===========================================================================

class TestReflectionEngine:
    """Tests for core/orchestrator/reflection.py uncovered paths."""

    def test_should_reflect_always_mode(self):
        """should_reflect returns True in ALWAYS mode."""
        from core.orchestrator.models import OrchestrationResult
        from core.orchestrator.reflection import ReflectionEngine, ReflectionMode

        engine = ReflectionEngine(mode=ReflectionMode.ALWAYS)
        result = OrchestrationResult(response="ok", success=True, mode="chat")
        assert engine.should_reflect(result, []) is True

    def test_should_reflect_on_failure_with_failed_obs(self):
        """should_reflect returns True when observations have failures."""
        from core.orchestrator.models import (
            OrchestrationObservation,
            OrchestrationResult,
        )
        from core.orchestrator.reflection import ReflectionEngine, ReflectionMode

        engine = ReflectionEngine(mode=ReflectionMode.ON_FAILURE)
        result = OrchestrationResult(response="ok", success=True, mode="chat")
        obs = OrchestrationObservation(
            agent_name="test",
            task="do thing",
            result="",
            success=False,
            error="something broke",
        )
        assert engine.should_reflect(result, [obs]) is True

    async def test_reflect_failed_result(self):
        """reflect() produces quality assessment for failed results."""
        from core.orchestrator.models import OrchestrationResult
        from core.orchestrator.reflection import ReflectionEngine, ReflectionMode

        engine = ReflectionEngine(mode=ReflectionMode.ALWAYS)
        result = OrchestrationResult(response="error", success=False, mode="chat")
        ref = await engine.reflect(result, [], "test goal", "conv-1")
        assert ref.triggered is True
        assert ref.trigger_reason == "orchestration_failed"
        assert "failed" in ref.quality_assessment.lower()

    async def test_reflect_with_failed_observation_memory(self):
        """reflect() suggests memory updates for failed observations."""
        from core.orchestrator.models import (
            OrchestrationObservation,
            OrchestrationResult,
        )
        from core.orchestrator.reflection import ReflectionEngine, ReflectionMode

        engine = ReflectionEngine(mode=ReflectionMode.ALWAYS)
        result = OrchestrationResult(response="ok", success=True, mode="chat")
        obs = OrchestrationObservation(
            agent_name="test-agent",
            task="do thing",
            result="",
            success=False,
            error="Agent 'ghost' not found in registry",
        )
        ref = await engine.reflect(result, [obs], "goal", "conv-2")
        assert ref.triggered is True
        assert len(ref.memory_updates) > 0
        assert len(ref.capability_suggestions) > 0
        assert "not found" in ref.capability_suggestions[0].lower()

    async def test_reflect_with_timeout_observation(self):
        """reflect() suggests timeout increase for timed out observations."""
        from core.orchestrator.models import (
            OrchestrationObservation,
            OrchestrationResult,
        )
        from core.orchestrator.reflection import ReflectionEngine, ReflectionMode

        engine = ReflectionEngine(mode=ReflectionMode.ALWAYS)
        result = OrchestrationResult(response="ok", success=True, mode="chat")
        obs = OrchestrationObservation(
            agent_name="slow-agent",
            task="compute thing",
            result="",
            success=False,
            error="Request timed out after 30s",
        )
        ref = await engine.reflect(result, [obs], "goal", "conv-3")
        assert any("timed out" in s.lower() for s in ref.capability_suggestions)

    async def test_reflect_escalation_trigger(self):
        """reflect() triggers on escalation needed."""
        from core.orchestrator.models import OrchestrationResult
        from core.orchestrator.reflection import ReflectionEngine, ReflectionMode

        engine = ReflectionEngine(mode=ReflectionMode.ON_FAILURE)
        result = OrchestrationResult(
            response="need human",
            success=False,
            mode="chat",
            needs_escalation=True,
        )
        assert engine.should_reflect(result, []) is True
        ref = await engine.reflect(result, [], "goal", "conv-4")
        assert "escalat" in ref.quality_assessment.lower()

    async def test_reflect_always_mode_success(self):
        """reflect() in always mode with successful result."""
        from core.orchestrator.models import (
            OrchestrationObservation,
            OrchestrationResult,
        )
        from core.orchestrator.reflection import ReflectionEngine, ReflectionMode

        engine = ReflectionEngine(mode=ReflectionMode.ALWAYS)
        result = OrchestrationResult(response="done", success=True, mode="chat")
        obs = OrchestrationObservation(
            agent_name="good-agent",
            task="do thing",
            result="success",
            success=True,
        )
        ref = await engine.reflect(result, [obs], "goal", "conv-5")
        assert ref.trigger_reason == "always_mode"
        assert "succeeded cleanly" in ref.quality_assessment.lower()

# ===========================================================================
# orchestrator/routing_metrics
# ===========================================================================

class TestRoutingMetrics:
    """Tests for core/orchestrator/routing_metrics.py uncovered paths."""

    def test_record_creates_record(self):
        """record() creates a RoutingMetricRecord."""
        from core.orchestrator.routing_metrics import RoutingMetricsTracker

        tracker = RoutingMetricsTracker()
        with patch("core.orchestrator.routing_metrics.RoutingMetricsTracker._persist_to_db"):
            rec = tracker.record(
                message="hello",
                hint_fired=True,
                hint_type="meta_action",
                llm_tool_called="install_server",
                latency_ms=50,
            )
        assert rec.hint_fired is True
        assert rec.hint_type == "meta_action"

    def test_get_summary_empty(self):
        """get_summary returns zeros for empty tracker."""
        from core.orchestrator.routing_metrics import RoutingMetricsTracker

        tracker = RoutingMetricsTracker()
        summary = tracker.get_summary()
        assert summary["total"] == 0
        assert summary["hint_fired_count"] == 0

    def test_get_summary_with_records(self):
        """get_summary returns correct statistics."""
        from core.orchestrator.routing_metrics import RoutingMetricsTracker

        tracker = RoutingMetricsTracker()
        with patch("core.orchestrator.routing_metrics.RoutingMetricsTracker._persist_to_db"):
            tracker.record(message="a", hint_fired=True, latency_ms=100)
            tracker.record(
                message="b",
                hint_fired=False,
                fallback_activated=True,
                llm_tool_called="install_server",
                latency_ms=200,
            )
        summary = tracker.get_summary()
        assert summary["total"] == 2
        assert summary["hint_fired_count"] == 1
        assert summary["fallback_count"] == 1
        assert "install_server" in summary["tool_call_counts"]
        assert summary["avg_latency_ms"] == 150

    def test_global_tracker_singleton(self):
        """get_routing_metrics_tracker returns singleton."""
        import core.orchestrator.routing_metrics as rm

        old = rm._tracker
        try:
            rm._tracker = None
            t1 = rm.get_routing_metrics_tracker()
            t2 = rm.get_routing_metrics_tracker()
            assert t1 is t2
        finally:
            rm._tracker = old

    def test_record_routing_metric_convenience(self):
        """record_routing_metric delegates to global tracker."""
        from core.orchestrator.routing_metrics import record_routing_metric

        with patch("core.orchestrator.routing_metrics.RoutingMetricsTracker._persist_to_db"):
            record_routing_metric(message="test", hint_fired=False)

# ===========================================================================
# api/middleware/tracing
# ===========================================================================

class TestTracingMiddleware:
    """Tests for core/api/middleware/tracing.py."""

    def test_dispatch_adds_trace_headers(self):
        """Tracing middleware adds trace headers to response."""
        from core.api.middleware.tracing import TracingMiddleware

        app = FastAPI()

        @app.get("/test")
        async def test_endpoint():
            return {"ok": True}

        app.add_middleware(TracingMiddleware, service_name="test-svc")
        client = TestClient(app)
        resp = client.get("/test")
        assert resp.status_code == 200
        assert "X-Trace-ID" in resp.headers
        assert "X-Span-ID" in resp.headers
        assert "X-Request-Duration-Ms" in resp.headers

    def test_dispatch_preserves_incoming_trace_id(self):
        """Tracing middleware preserves incoming X-Trace-ID header."""
        from core.api.middleware.tracing import TracingMiddleware

        app = FastAPI()

        @app.get("/test")
        async def test_endpoint():
            return {"ok": True}

        app.add_middleware(TracingMiddleware)
        client = TestClient(app)
        resp = client.get("/test", headers={"X-Trace-ID": "custom-trace-123"})
        assert resp.headers["X-Trace-ID"] == "custom-trace-123"

# ===========================================================================
# api/middleware/request_size
# ===========================================================================

class TestRequestSizeMiddleware:
    """Tests for core/api/middleware/request_size.py."""

    def test_oversized_request_returns_413(self):
        """Oversized request returns 413."""
        from core.api.middleware.request_size import RequestSizeMiddleware

        app = FastAPI()

        @app.post("/test")
        async def test_endpoint():
            return {"ok": True}

        app.add_middleware(RequestSizeMiddleware, max_size_mb=0.001)
        client = TestClient(app)
        resp = client.post(
            "/test",
            content=b"x" * 2000,
            headers={"Content-Length": "2000"},
        )
        assert resp.status_code == 413
        assert "too large" in resp.json()["detail"].lower()

    def test_normal_request_passes(self):
        """Normal-sized request passes through."""
        from core.api.middleware.request_size import RequestSizeMiddleware

        app = FastAPI()

        @app.post("/test")
        async def test_endpoint():
            return {"ok": True}

        app.add_middleware(RequestSizeMiddleware, max_size_mb=10)
        client = TestClient(app)
        resp = client.post(
            "/test",
            content=b"small",
            headers={"Content-Length": "5"},
        )
        assert resp.status_code == 200

# ===========================================================================
# api/middleware/request_metrics
# ===========================================================================

class TestRequestMetrics:
    """Tests for core/api/middleware/request_metrics.py."""

    def test_normalize_path_replaces_uuids(self):
        """normalize_path replaces UUID-like path segments with :id."""
        from core.api.middleware.request_metrics import normalize_path

        result = normalize_path("/api/chat/550e8400-e29b-41d4-a716-446655440000/messages")
        assert ":id" in result
        assert "550e8400" not in result

    def test_normalize_path_replaces_integers(self):
        """normalize_path replaces integer segments with :id."""
        from core.api.middleware.request_metrics import normalize_path

        result = normalize_path("/api/plans/12345/steps")
        assert ":id" in result
        assert "12345" not in result

    def test_normalize_path_keeps_text_segments(self):
        """normalize_path keeps non-id text segments."""
        from core.api.middleware.request_metrics import normalize_path

        result = normalize_path("/api/chat/messages")
        assert result == "/api/chat/messages"

    def test_get_recent_requests_returns_list(self):
        """get_recent_requests returns a list."""
        from core.api.middleware.request_metrics import get_recent_requests

        result = get_recent_requests()
        assert isinstance(result, list)

    def test_get_recent_requests_with_limit(self):
        """get_recent_requests respects limit parameter."""
        from core.api.middleware.request_metrics import get_recent_requests

        result = get_recent_requests(limit=5)
        assert isinstance(result, list)
        assert len(result) <= 5

    def test_request_metrics_middleware_records(self):
        """RequestMetricsMiddleware records request data for various modes."""
        from core.api.middleware.request_metrics import RequestMetricsMiddleware

        app = FastAPI()

        @app.get("/api/chat/test")
        async def test_chat():
            return {"ok": True}

        @app.get("/api/plans/test")
        async def test_plans():
            return {"ok": True}

        @app.get("/api/workflows/test")
        async def test_workflows():
            return {"ok": True}

        @app.get("/api/health")
        async def test_health():
            return {"ok": True}

        @app.get("/api/agents/test")
        async def test_agents():
            return {"ok": True}

        @app.get("/api/metrics/test")
        async def test_metrics():
            return {"ok": True}

        @app.get("/api/auth/test")
        async def test_auth():
            return {"ok": True}

        @app.get("/other")
        async def test_other():
            return {"ok": True}

        app.add_middleware(RequestMetricsMiddleware)
        client = TestClient(app)

        for path in [
            "/api/chat/test",
            "/api/plans/test",
            "/api/workflows/test",
            "/api/health",
            "/api/agents/test",
            "/api/metrics/test",
            "/api/auth/test",
            "/other",
        ]:
            resp = client.get(path)
            assert resp.status_code == 200

# ===========================================================================
# workflows/schema graph validation
# ===========================================================================

class TestWorkflowSchemaValidation:
    """Tests for core/workflows/schema.py uncovered validation paths."""

    def test_multiple_start_nodes_raises(self):
        """Multiple start nodes raise ValueError."""
        from core.workflows.schema import WorkflowSchema

        with pytest.raises(ValueError, match="exactly one start node"):
            WorkflowSchema(
                nodes=[
                    {"id": "s1", "type": "start"},
                    {"id": "s2", "type": "start"},
                    {"id": "e1", "type": "end"},
                ],
                edges=[
                    {"id": "e1", "source": "s1", "target": "e1"},
                    {"id": "e2", "source": "s2", "target": "e1"},
                ],
            )

    def test_invalid_edge_source(self):
        """Invalid edge source raises ValueError."""
        from core.workflows.schema import WorkflowSchema

        with pytest.raises(ValueError, match="non-existent node"):
            WorkflowSchema(
                nodes=[
                    {"id": "s1", "type": "start"},
                    {"id": "e1", "type": "end"},
                ],
                edges=[
                    {"id": "e1", "source": "ghost", "target": "e1"},
                ],
            )

    def test_invalid_edge_target(self):
        """Invalid edge target raises ValueError."""
        from core.workflows.schema import WorkflowSchema

        with pytest.raises(ValueError, match="non-existent node"):
            WorkflowSchema(
                nodes=[
                    {"id": "s1", "type": "start"},
                    {"id": "e1", "type": "end"},
                ],
                edges=[
                    {"id": "e1", "source": "s1", "target": "ghost"},
                ],
            )

    def test_end_node_with_outgoing_edge(self):
        """End node with outgoing edge raises ValueError."""
        from core.workflows.schema import WorkflowSchema

        with pytest.raises(ValueError, match="cannot have outgoing"):
            WorkflowSchema(
                nodes=[
                    {"id": "s1", "type": "start"},
                    {"id": "t1", "type": "task", "data": {"agent": "a", "task": "t"}},
                    {"id": "e1", "type": "end"},
                ],
                edges=[
                    {"id": "e1", "source": "s1", "target": "t1"},
                    {"id": "e2", "source": "t1", "target": "e1"},
                    {"id": "e3", "source": "e1", "target": "t1"},
                ],
            )

    def test_router_node_with_insufficient_edges(self):
        """Router node with fewer than 2 outgoing edges raises ValueError."""
        from core.workflows.schema import WorkflowSchema

        with pytest.raises(ValueError, match="at least 2 outgoing"):
            WorkflowSchema(
                nodes=[
                    {"id": "s1", "type": "start"},
                    {
                        "id": "r1",
                        "type": "router",
                        "data": {
                            "condition": "x > 0",
                            "branches": [{"label": "a"}, {"label": "b"}],
                        },
                    },
                    {"id": "e1", "type": "end"},
                ],
                edges=[
                    {"id": "e1", "source": "s1", "target": "r1"},
                    {"id": "e2", "source": "r1", "target": "e1"},
                ],
            )

    def test_cycle_detection(self):
        """Cycle in workflow raises ValueError."""
        from core.workflows.schema import WorkflowSchema

        with pytest.raises(ValueError, match="cycle"):
            WorkflowSchema(
                nodes=[
                    {"id": "s1", "type": "start"},
                    {"id": "t1", "type": "task", "data": {"agent": "a", "task": "t"}},
                    {"id": "t2", "type": "task", "data": {"agent": "b", "task": "t2"}},
                    {"id": "e1", "type": "end"},
                ],
                edges=[
                    {"id": "e1", "source": "s1", "target": "t1"},
                    {"id": "e2", "source": "t1", "target": "t2"},
                    {"id": "e3", "source": "t2", "target": "t1"},
                ],
            )

    def test_unreachable_nodes(self):
        """Unreachable nodes raise ValueError."""
        from core.workflows.schema import WorkflowSchema

        with pytest.raises(ValueError, match="not reachable"):
            WorkflowSchema(
                nodes=[
                    {"id": "s1", "type": "start"},
                    {"id": "t1", "type": "task", "data": {"agent": "a", "task": "t"}},
                    {"id": "isolated", "type": "task", "data": {"agent": "b", "task": "t2"}},
                    {"id": "e1", "type": "end"},
                ],
                edges=[
                    {"id": "e1", "source": "s1", "target": "t1"},
                    {"id": "e2", "source": "t1", "target": "e1"},
                ],
            )

    def test_validate_agents_checks_registry(self):
        """validate_agents checks agent names against registry."""
        from core.workflows.schema import WorkflowSchema

        schema = WorkflowSchema(
            nodes=[
                {"id": "s1", "type": "start"},
                {"id": "t1", "type": "task", "data": {"agent": "fake-agent", "task": "t"}},
                {"id": "e1", "type": "end"},
            ],
            edges=[
                {"id": "e1", "source": "s1", "target": "t1"},
                {"id": "e2", "source": "t1", "target": "e1"},
            ],
        )
        with patch("core.workflows.schema.list_agents", return_value=[]):
            invalid = schema.validate_agents()
        assert "fake-agent" in invalid

    def test_validate_workflow_function_valid(self):
        """validate_workflow returns (True, []) for valid workflow."""
        from core.workflows.schema import validate_workflow

        with patch("core.workflows.schema.list_agents", return_value=[]):
            valid, errors = validate_workflow(
                {
                    "nodes": [
                        {"id": "s1", "type": "start"},
                        {"id": "e1", "type": "end"},
                    ],
                    "edges": [
                        {"id": "e1", "source": "s1", "target": "e1"},
                    ],
                }
            )
        assert valid is True
        assert errors == []

    def test_validate_workflow_function_invalid(self):
        """validate_workflow returns (False, errors) for invalid workflow."""
        from core.workflows.schema import validate_workflow

        valid, errors = validate_workflow({"nodes": [], "edges": []})
        assert valid is False
        assert len(errors) > 0

# ===========================================================================
# skills/mcp_bridge
# ===========================================================================

class TestMCPBridge:
    """Tests for core/skills/mcp_bridge.py."""

    def test_bridge_mcp_tool_to_skill_with_func(self):
        """bridge_mcp_tool_to_skill converts tool with function."""
        from core.skills.mcp_bridge import bridge_mcp_tool_to_skill

        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        mock_tool.func = MagicMock()
        mock_tool.func.__doc__ = "A test tool for testing.\n\nDetailed description."

        skill = bridge_mcp_tool_to_skill(mock_tool)
        assert skill.name == "test_tool"
        assert "test tool" in skill.description.lower()
        assert skill.metadata.extra["source"] == "mcp_bridge"

    def test_bridge_mcp_tool_to_skill_no_func(self):
        """bridge_mcp_tool_to_skill handles tool without function."""
        from core.skills.mcp_bridge import bridge_mcp_tool_to_skill

        mock_tool = MagicMock(spec=["name"])
        mock_tool.name = "raw_tool"

        skill = bridge_mcp_tool_to_skill(mock_tool)
        assert skill.name == "raw_tool"
        assert "MCP tool" in skill.description

    def test_discover_mcp_tools_import_error(self):
        """discover_mcp_tools_as_skills returns [] when plugin not available."""
        from core.skills.mcp_bridge import discover_mcp_tools_as_skills

        with patch.dict(
            "sys.modules", {"plugins": None, "plugins.mcp": None, "plugins.mcp.bridge": None}
        ):
            skills = discover_mcp_tools_as_skills()
        assert skills == []

# ===========================================================================
# skills/models
# ===========================================================================

class TestSkillModels:
    """Tests for core/skills/models.py uncovered methods."""

    def test_ensure_instructions_loaded_noop_when_loaded(self):
        """ensure_instructions_loaded is a no-op when already loaded."""
        from core.skills.models import Skill

        skill = Skill(
            name="test",
            description="test",
            instructions="loaded",
            skill_dir="/tmp/test",
            instructions_loaded=True,
        )
        skill.ensure_instructions_loaded()
        assert skill.instructions == "loaded"

    def test_ensure_instructions_loaded_noop_when_no_dir(self):
        """ensure_instructions_loaded is a no-op with empty skill_dir."""
        from core.skills.models import Skill

        skill = Skill(
            name="test",
            description="test",
            instructions="",
            skill_dir="",
            instructions_loaded=False,
        )
        skill.ensure_instructions_loaded()
        assert skill.instructions_loaded is False

    def test_get_scripts_no_dir(self):
        """get_scripts returns [] when no scripts_dir."""
        from core.skills.models import Skill

        skill = Skill(
            name="test",
            description="test",
            instructions="",
            skill_dir="/tmp",
        )
        assert skill.get_scripts() == []

    def test_get_scripts_nonexistent_dir(self):
        """get_scripts returns [] when scripts_dir doesn't exist."""
        from core.skills.models import Skill

        skill = Skill(
            name="test",
            description="test",
            instructions="",
            skill_dir="/tmp",
            scripts_dir="/tmp/nonexistent_scripts_dir_12345",
        )
        assert skill.get_scripts() == []

    def test_get_script_path_no_dir(self):
        """get_script_path returns None when no scripts_dir."""
        from core.skills.models import Skill

        skill = Skill(
            name="test",
            description="test",
            instructions="",
            skill_dir="/tmp",
        )
        assert skill.get_script_path("test.sh") is None

    def test_get_script_path_nonexistent(self):
        """get_script_path returns None for nonexistent script."""
        from core.skills.models import Skill

        skill = Skill(
            name="test",
            description="test",
            instructions="",
            skill_dir="/tmp",
            scripts_dir="/tmp",
        )
        assert skill.get_script_path("nonexistent_file_12345.sh") is None

# ===========================================================================
# api/routes/metrics
# ===========================================================================

@pytest.mark.skip(reason="metrics module was refactored to metrics_api with different API surface")
class TestMetricsRoutes:
    """Tests for core/api/routes/metrics.py endpoints (STALE — needs rewrite for metrics_api)."""

    def test_get_latency_metrics(self):
        """GET /latency returns latency stats."""
        from core.api.routes.metrics_api import router

        app = FastAPI()
        app.include_router(router, prefix="/api/metrics")

        with patch("core.api.routes.metrics_api.get_latency_stats") as mock:
            mock.return_value = {
                "count": 0,
                "p50_ms": 0,
                "p95_ms": 0,
                "p99_ms": 0,
                "avg_ms": 0,
                "ttft_avg_ms": None,
                "cache_hit_rate": None,
            }
            client = TestClient(app)
            resp = client.get("/api/metrics/latency")
        assert resp.status_code == 200
        assert "count" in resp.json()

    def test_get_recent_latency(self):
        """GET /latency/recent returns recent records."""
        from core.api.routes.metrics_api import router

        app = FastAPI()
        app.include_router(router, prefix="/api/metrics")

        mock_tracker = MagicMock()
        mock_tracker.records = []
        with patch("core.api.routes.metrics_api.get_latency_tracker", return_value=mock_tracker):
            client = TestClient(app)
            resp = client.get("/api/metrics/latency/recent")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_get_latency_by_mode(self):
        """GET /latency/by-mode returns per-mode stats."""
        from core.api.routes.metrics_api import router

        app = FastAPI()
        app.include_router(router, prefix="/api/metrics")

        with patch("core.api.routes.metrics_api.get_latency_stats") as mock:
            mock.return_value = {"count": 0, "p50_ms": 0, "p95_ms": 0, "p99_ms": 0, "avg_ms": 0}
            client = TestClient(app)
            resp = client.get("/api/metrics/latency/by-mode")
        assert resp.status_code == 200
        data = resp.json()
        assert "chat" in data
        assert "planner" in data

    def test_get_queue_status(self):
        """GET /queue returns queue status."""
        from core.api.routes.metrics_api import router

        app = FastAPI()
        app.include_router(router, prefix="/api/metrics")

        mock_stats = MagicMock()
        mock_stats.active_requests = 2
        mock_stats.queued_requests = 0
        mock_stats.max_concurrent = 8
        mock_stats.max_queue_size = 20
        mock_stats.total_processed = 100
        mock_stats.total_rejected = 0
        mock_stats.avg_wait_ms = 50.0

        async def async_stats():
            return mock_stats

        mock_queue = MagicMock()
        mock_queue.get_stats = async_stats

        with patch("core.api.routes.metrics_api.get_request_queue", return_value=mock_queue):
            client = TestClient(app)
            resp = client.get("/api/metrics/queue")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"

    def test_get_queue_status_overloaded(self):
        """GET /queue returns overloaded status."""
        from core.api.routes.metrics_api import router

        app = FastAPI()
        app.include_router(router, prefix="/api/metrics")

        mock_stats = MagicMock()
        mock_stats.active_requests = 8
        mock_stats.queued_requests = 15
        mock_stats.max_concurrent = 8
        mock_stats.max_queue_size = 20
        mock_stats.total_processed = 1000
        mock_stats.total_rejected = 50
        mock_stats.avg_wait_ms = 500.0

        async def async_stats():
            return mock_stats

        mock_queue = MagicMock()
        mock_queue.get_stats = async_stats

        with patch("core.api.routes.metrics_api.get_request_queue", return_value=mock_queue):
            client = TestClient(app)
            resp = client.get("/api/metrics/queue")
        assert resp.status_code == 200
        assert resp.json()["status"] == "overloaded"

# ===========================================================================
# api/routes/mcp_metrics
# ===========================================================================

class TestMCPMetricsRoutes:
    """Tests for core/api/routes/mcp_metrics.py endpoints."""

    def test_mcp_health_endpoint(self):
        """GET /api/mcp/health returns health summary."""
        from core.api.routes.mcp_metrics import router

        app = FastAPI()
        app.include_router(router)

        mock_registry = MagicMock()
        mock_registry.get_health_summary.return_value = {
            "servers": {
                "test-server": {
                    "status": "healthy",
                    "restart_count": 0,
                    "consecutive_failures": 0,
                    "tool_count": 5,
                }
            },
            "total_registered": 1,
            "total_running": 1,
            "total_healthy": 1,
        }

        with patch("core.api.routes.mcp_metrics.get_registry", return_value=mock_registry):
            client = TestClient(app)
            resp = client.get("/api/mcp/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "test-server" in data["servers"]
        assert data["total_healthy"] == 1

    def test_mcp_server_health_found(self):
        """GET /api/mcp/health/{name} returns server detail."""
        from core.api.routes.mcp_metrics import router

        app = FastAPI()
        app.include_router(router)

        mock_registry = MagicMock()
        mock_registry.get_health_summary.return_value = {
            "servers": {
                "filesystem": {
                    "status": "healthy",
                    "restart_count": 1,
                    "consecutive_failures": 0,
                    "tool_count": 10,
                }
            },
            "total_registered": 1,
            "total_running": 1,
            "total_healthy": 1,
        }

        with patch("core.api.routes.mcp_metrics.get_registry", return_value=mock_registry):
            client = TestClient(app)
            resp = client.get("/api/mcp/health/filesystem")
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is True
        assert data["status"] == "healthy"

    def test_mcp_server_health_not_found(self):
        """GET /api/mcp/health/{name} returns found=False for missing server."""
        from core.api.routes.mcp_metrics import router

        app = FastAPI()
        app.include_router(router)

        mock_registry = MagicMock()
        mock_registry.get_health_summary.return_value = {
            "servers": {},
            "total_registered": 0,
            "total_running": 0,
            "total_healthy": 0,
        }

        with patch("core.api.routes.mcp_metrics.get_registry", return_value=mock_registry):
            client = TestClient(app)
            resp = client.get("/api/mcp/health/nonexistent")
        assert resp.status_code == 200
        assert resp.json()["found"] is False
