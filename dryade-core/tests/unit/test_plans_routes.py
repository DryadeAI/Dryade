"""Tests for core/api/routes/plans.py -- Auth enforcement and concurrent guard.

Tests JWT authentication enforcement on all Plans API endpoints and the
concurrent execution guard (P1-1) that returns HTTP 409 Conflict when a
plan is already executing.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_user(user_id: str = "user-1", role: str = "user") -> dict:
    """Create a mock JWT user dict."""
    return {"sub": user_id, "role": role}

def _make_mock_plan(
    plan_id: int = 1,
    status: str = "draft",
    user_id: str = "user-1",
    conversation_id: str = "conv-1",
    name: str = "Test Plan",
    nodes: list | None = None,
    edges: list | None = None,
):
    """Create a mock ExecutionPlan object with the given attributes."""
    plan = MagicMock()
    plan.id = plan_id
    plan.status = status
    plan.user_id = user_id
    plan.conversation_id = conversation_id
    plan.name = name
    plan.description = "Test plan description"
    plan.nodes = nodes or [{"id": "step1", "agent": "test", "task": "do thing"}]
    plan.edges = edges or []
    plan.reasoning = "test reasoning"
    plan.confidence = 0.9
    plan.ai_generated = False
    plan.execution_results = []
    plan.created_at = datetime.now(UTC)
    plan.updated_at = datetime.now(UTC)
    return plan

def _make_mock_db(plan=None, conversation=None):
    """Create a mock DB session that returns the given plan on query.

    Supports chained query().filter_by().first() for both ExecutionPlan
    and Conversation model lookups.
    """
    db = MagicMock()

    def _query_side_effect(model):
        query_mock = MagicMock()
        filter_mock = MagicMock()

        # Route return value based on model name
        model_name = getattr(model, "__name__", "")
        if model_name == "Conversation":
            filter_mock.first.return_value = conversation
        else:
            filter_mock.first.return_value = plan

        query_mock.filter_by.return_value = filter_mock
        return query_mock

    db.query.side_effect = _query_side_effect
    return db

# ===========================================================================
# Concurrent execution guard tests (updated for JWT auth)
# ===========================================================================

class TestExecutePlanConcurrentGuard:
    """Tests for the concurrent execution guard (P1-1) on execute_plan."""

    @pytest.mark.asyncio
    async def test_execute_plan_rejects_concurrent_execution(self):
        """Plan with status='executing' should be rejected with HTTP 409."""
        from fastapi import HTTPException

        plan = _make_mock_plan(status="executing")
        db = _make_mock_db(plan)
        background_tasks = MagicMock()
        request = MagicMock()
        request.conversation_id = None
        request.user_id = None
        user = _make_mock_user()

        from core.api.routes.plans import execute_plan

        with pytest.raises(HTTPException) as exc_info:
            await execute_plan(
                plan_id=1,
                _request=request,
                background_tasks=background_tasks,
                user=user,
                db=db,
            )

        assert exc_info.value.status_code == 409
        assert "already executing" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_execute_plan_allows_draft_status(self):
        """Plan with status='draft' should be accepted and return execution_id."""
        plan = _make_mock_plan(status="draft")
        db = _make_mock_db(plan)
        background_tasks = MagicMock()
        request = MagicMock()
        request.conversation_id = None
        request.user_id = None
        user = _make_mock_user()

        # Mock PlanExecutionResult creation and pre-execution validation
        from core.api.routes.plans import PlanValidationResult

        mock_validation = PlanValidationResult(valid=True)
        with (
            patch("core.api.routes.plans.PlanExecutionResult") as mock_result_cls,
            patch("core.api.routes.plans.uuid") as mock_uuid,
            patch(
                "core.api.routes.plans._validate_plan_for_execution", return_value=mock_validation
            ),
        ):
            mock_uuid.uuid4.return_value = uuid.UUID("12345678-1234-1234-1234-123456789abc")
            mock_result_cls.return_value = MagicMock()

            from core.api.routes.plans import execute_plan

            result = await execute_plan(
                plan_id=1,
                _request=request,
                background_tasks=background_tasks,
                user=user,
                db=db,
            )

        assert result["status"] == "executing"
        assert result["execution_id"] == "12345678-1234-1234-1234-123456789abc"
        assert result["plan_id"] == 1
        # Verify background task was queued
        background_tasks.add_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_plan_rejects_completed_status(self):
        """Plan with status='completed' should be rejected with HTTP 400 (not 409)."""
        from fastapi import HTTPException

        plan = _make_mock_plan(status="completed")
        db = _make_mock_db(plan)
        background_tasks = MagicMock()
        request = MagicMock()
        request.conversation_id = None
        request.user_id = None
        user = _make_mock_user()

        from core.api.routes.plans import execute_plan

        with pytest.raises(HTTPException) as exc_info:
            await execute_plan(
                plan_id=1,
                _request=request,
                background_tasks=background_tasks,
                user=user,
                db=db,
            )

        assert exc_info.value.status_code == 400
        assert "completed" in exc_info.value.detail

# ===========================================================================
# Auth enforcement tests
# ===========================================================================

class TestPlanAuthEnforcement:
    """Tests for JWT auth enforcement on Plans API endpoints."""

    def test_create_plan_uses_jwt_user_id(self):
        """create_plan should use JWT sub as user_id, not request body."""
        from core.api.routes.plans import create_plan

        conversation = MagicMock()
        conversation.user_id = "conv-owner"
        plan = _make_mock_plan(user_id="jwt-user")
        db = _make_mock_db(plan=plan, conversation=conversation)
        user = _make_mock_user(user_id="jwt-user")

        request = MagicMock()
        request.conversation_id = "conv-1"
        request.user_id = "request-body-user"  # This should be overridden
        request.name = "Test Plan"
        request.description = "desc"
        request.nodes = [{"id": "step1", "agent": "test", "task": "do"}]
        request.edges = []
        request.reasoning = None
        request.confidence = None
        request.status = "draft"
        request.ai_generated = False

        with (
            patch("core.api.routes.plans.ExecutionPlan") as mock_plan_cls,
            patch("core.api.routes.plans._validate_plan_agents", return_value=[]),
            patch("core.api.routes.plans._validate_step_references", return_value=[]),
        ):
            mock_instance = _make_mock_plan(user_id="jwt-user")
            mock_plan_cls.return_value = mock_instance

            result = create_plan(request=request, user=user, db=db)

        # Verify ExecutionPlan was created with JWT user_id, not request body
        call_kwargs = mock_plan_cls.call_args
        assert call_kwargs.kwargs.get("user_id") == "jwt-user"

    def test_update_plan_rejects_non_owner(self):
        """update_plan should reject requests from non-owners with 403."""
        from fastapi import HTTPException

        from core.api.routes.plans import update_plan

        plan = _make_mock_plan(user_id="owner-1")
        db = _make_mock_db(plan)
        user = _make_mock_user(user_id="other-user", role="user")

        request = MagicMock()
        request.name = "Updated"
        request.description = None
        request.nodes = None
        request.edges = None
        request.reasoning = None
        request.confidence = None
        request.status = None

        with pytest.raises(HTTPException) as exc_info:
            update_plan(plan_id=1, request=request, user=user, db=db)

        assert exc_info.value.status_code == 403

    def test_update_plan_allows_admin(self):
        """update_plan should allow admin to update another user's plan."""
        from core.api.routes.plans import update_plan

        plan = _make_mock_plan(user_id="owner-1")
        db = _make_mock_db(plan)
        user = _make_mock_user(user_id="admin-user", role="admin")

        request = MagicMock()
        request.name = "Admin Updated"
        request.description = None
        request.nodes = None
        request.edges = None
        request.reasoning = None
        request.confidence = None
        request.status = None

        # Should not raise -- admin can update any plan
        result = update_plan(plan_id=1, request=request, user=user, db=db)
        assert result["name"] == plan.name

    def test_delete_plan_rejects_non_owner(self):
        """delete_plan should reject requests from non-owners with 403."""
        from fastapi import HTTPException

        from core.api.routes.plans import delete_plan

        plan = _make_mock_plan(user_id="owner-1")
        db = _make_mock_db(plan)
        user = _make_mock_user(user_id="other-user", role="user")

        with pytest.raises(HTTPException) as exc_info:
            delete_plan(plan_id=1, user=user, db=db)

        assert exc_info.value.status_code == 403

    def test_delete_plan_allows_admin(self):
        """delete_plan should allow admin to delete another user's plan."""
        from core.api.routes.plans import delete_plan

        plan = _make_mock_plan(user_id="owner-1")
        db = _make_mock_db(plan)
        user = _make_mock_user(user_id="admin-user", role="admin")

        # Should not raise -- admin can delete any plan
        delete_plan(plan_id=1, user=user, db=db)

        # Verify db.delete was called
        db.delete.assert_called_once_with(plan)
        db.commit.assert_called_once()

    def test_list_executions_rejects_non_owner(self):
        """list_executions should reject requests from non-owners with 403."""
        from fastapi import HTTPException

        from core.api.routes.plans import list_executions

        plan = _make_mock_plan(user_id="owner-1")
        db = _make_mock_db(plan)
        user = _make_mock_user(user_id="other-user", role="user")

        with pytest.raises(HTTPException) as exc_info:
            list_executions(plan_id=1, user=user, db=db)

        assert exc_info.value.status_code == 403

    def test_submit_feedback_rejects_non_owner(self):
        """submit_feedback should reject requests from non-owners with 403."""
        from fastapi import HTTPException

        from core.api.routes.plans import submit_feedback

        plan = _make_mock_plan(user_id="owner-1")
        db = _make_mock_db(plan)
        user = _make_mock_user(user_id="other-user", role="user")

        request = MagicMock()
        request.execution_id = "exec-1"
        request.rating = 5
        request.comment = "Great"

        with pytest.raises(HTTPException) as exc_info:
            submit_feedback(plan_id=1, request=request, user=user, db=db)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_execute_plan_rejects_non_owner(self):
        """execute_plan should reject requests from non-owners with 403."""
        from fastapi import HTTPException

        from core.api.routes.plans import execute_plan

        plan = _make_mock_plan(user_id="owner-1")
        db = _make_mock_db(plan)
        user = _make_mock_user(user_id="other-user", role="user")
        background_tasks = MagicMock()
        request = MagicMock()
        request.conversation_id = None
        request.user_id = None

        with pytest.raises(HTTPException) as exc_info:
            await execute_plan(
                plan_id=1,
                _request=request,
                background_tasks=background_tasks,
                user=user,
                db=db,
            )

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_execute_plan_allows_admin(self):
        """execute_plan should allow admin to execute another user's plan."""
        from core.api.routes.plans import PlanValidationResult, execute_plan

        plan = _make_mock_plan(user_id="owner-1", status="draft")
        db = _make_mock_db(plan)
        user = _make_mock_user(user_id="admin-user", role="admin")
        background_tasks = MagicMock()
        request = MagicMock()
        request.conversation_id = None
        request.user_id = None

        mock_validation = PlanValidationResult(valid=True)
        with (
            patch("core.api.routes.plans.PlanExecutionResult") as mock_result_cls,
            patch("core.api.routes.plans.uuid") as mock_uuid,
            patch(
                "core.api.routes.plans._validate_plan_for_execution", return_value=mock_validation
            ),
        ):
            mock_uuid.uuid4.return_value = uuid.UUID("12345678-1234-1234-1234-123456789abc")
            mock_result_cls.return_value = MagicMock()

            result = await execute_plan(
                plan_id=1,
                _request=request,
                background_tasks=background_tasks,
                user=user,
                db=db,
            )

        assert result["status"] == "executing"
        background_tasks.add_task.assert_called_once()

# ===========================================================================
# Agent validation tests
# ===========================================================================

class TestValidatePlanAgents:
    """Tests for _validate_plan_agents() agent name validation."""

    @patch("core.api.routes.plans._resolve_agent_name")
    def test_valid_agents_returns_empty(self, mock_resolve):
        """All agents resolvable returns empty list."""
        mock_resolve.return_value = ("resolved", MagicMock())
        nodes = [{"id": "s1", "agent": "research"}, {"id": "s2", "agent": "writer"}]
        from core.api.routes.plans import _validate_plan_agents

        assert _validate_plan_agents(nodes) == []

    @patch("core.api.routes.plans._resolve_agent_name")
    def test_invalid_agent_returned(self, mock_resolve):
        """Unresolvable agent name appears in result."""
        mock_resolve.side_effect = (
            lambda name: (name, MagicMock()) if name == "research" else (name, None)
        )
        nodes = [{"id": "s1", "agent": "research"}, {"id": "s2", "agent": "nonexistent"}]
        from core.api.routes.plans import _validate_plan_agents

        result = _validate_plan_agents(nodes)
        assert "nonexistent" in result

    @patch("core.api.routes.plans._resolve_agent_name")
    def test_nodes_without_agent_skipped(self, mock_resolve):
        """Nodes without agent field are silently skipped."""
        mock_resolve.return_value = ("x", MagicMock())
        nodes = [{"id": "s1"}, {"id": "s2", "agent": ""}]
        from core.api.routes.plans import _validate_plan_agents

        assert _validate_plan_agents(nodes) == []

    @patch("core.api.routes.plans._resolve_agent_name")
    def test_fuzzy_match_accepted(self, mock_resolve):
        """Fuzzy-matchable names (e.g. capella.capella -> mcp-capella) are accepted."""
        mock_resolve.return_value = ("mcp-capella", MagicMock())
        nodes = [{"id": "s1", "agent": "capella.capella"}]
        from core.api.routes.plans import _validate_plan_agents

        assert _validate_plan_agents(nodes) == []

# ===========================================================================
# Step reference validation tests
# ===========================================================================

class TestValidateStepReferences:
    """Tests for _validate_step_references() step ref validation."""

    def test_valid_references_returns_empty(self):
        from core.api.routes.plans import _validate_step_references

        nodes = [
            {"id": "s1", "agent": "a", "arguments": {}},
            {"id": "s2", "agent": "b", "arguments": {"input": "{{s1}}"}},
        ]
        assert _validate_step_references(nodes) == []

    def test_invalid_reference_returns_error(self):
        from core.api.routes.plans import _validate_step_references

        nodes = [
            {"id": "s1", "agent": "a", "arguments": {"input": "{{nonexistent}}"}},
        ]
        errors = _validate_step_references(nodes)
        assert len(errors) == 1
        assert "nonexistent" in errors[0]

    def test_dotted_reference_validated(self):
        """{{step.field}} patterns are also validated for step existence."""
        from core.api.routes.plans import _validate_step_references

        nodes = [
            {"id": "s1", "agent": "a", "arguments": {}},
            {"id": "s2", "agent": "b", "arguments": {"data": "{{s1.output}}"}},
        ]
        assert _validate_step_references(nodes) == []

    def test_no_arguments_skipped(self):
        from core.api.routes.plans import _validate_step_references

        nodes = [{"id": "s1", "agent": "a"}]
        assert _validate_step_references(nodes) == []

    def test_non_string_arguments_skipped(self):
        from core.api.routes.plans import _validate_step_references

        nodes = [{"id": "s1", "agent": "a", "arguments": {"count": 5}}]
        assert _validate_step_references(nodes) == []

# ===========================================================================
# Cycle detection tests
# ===========================================================================

class TestFindCycleNodes:
    """Tests for WorkflowSchema._find_cycle_nodes() enhanced cycle detection."""

    def _make_schema(self, nodes, edges):
        """Create a WorkflowSchema-like object for testing _find_cycle_nodes."""
        from core.workflows.schema import WorkflowSchema

        schema = MagicMock(spec=WorkflowSchema)
        schema.nodes = [MagicMock(id=n) for n in nodes]
        schema.edges = [MagicMock(source=s, target=t) for s, t in edges]
        schema._find_cycle_nodes = WorkflowSchema._find_cycle_nodes.__get__(schema)
        return schema

    def test_no_cycle_returns_empty(self):
        schema = self._make_schema(["a", "b", "c"], [("a", "b"), ("b", "c")])
        assert schema._find_cycle_nodes() == []

    def test_simple_cycle_identified(self):
        schema = self._make_schema(["a", "b", "c"], [("a", "b"), ("b", "c"), ("c", "a")])
        cycle = schema._find_cycle_nodes()
        assert len(cycle) == 3
        assert set(cycle) == {"a", "b", "c"}

    def test_self_loop_identified(self):
        schema = self._make_schema(["a", "b"], [("a", "b"), ("b", "b")])
        cycle = schema._find_cycle_nodes()
        assert "b" in cycle

    def test_disconnected_with_cycle(self):
        """Cycle in one component, other component acyclic."""
        schema = self._make_schema(["a", "b", "c", "d"], [("a", "b"), ("c", "d"), ("d", "c")])
        cycle = schema._find_cycle_nodes()
        assert len(cycle) >= 2
        assert "c" in cycle and "d" in cycle
