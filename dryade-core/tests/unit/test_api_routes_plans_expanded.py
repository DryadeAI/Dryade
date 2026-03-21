"""Tests for core/api/routes/plans.py -- Plan CRUD, validation, and execution routes.

Tests route handlers directly (no TestClient), mocking DB sessions and auth.
Auth is provided via the standard user dict pattern matching get_current_user output.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TEST_USER = {"sub": "test-user-001", "email": "test@example.com", "role": "user"}
_TEST_ADMIN = {"sub": "admin-001", "email": "admin@example.com", "role": "admin"}

def _make_plan(
    plan_id=1,
    user_id="test-user-001",
    name="Test Plan",
    status="draft",
    conversation_id=None,
    nodes=None,
    edges=None,
    ai_generated=False,
):
    p = MagicMock()
    p.id = plan_id
    p.user_id = user_id
    p.name = name
    p.description = "A test plan"
    p.status = status
    p.conversation_id = conversation_id or str(uuid.uuid4())
    p.nodes = nodes or [{"id": "step1", "agent": "research", "task": "Research the topic"}]
    p.edges = edges or []
    p.reasoning = "Test reasoning"
    p.confidence = 0.85
    p.ai_generated = ai_generated
    p.execution_results = []
    p.created_at = datetime(2026, 1, 13, 10, 0, 0, tzinfo=timezone.utc)
    p.updated_at = datetime(2026, 1, 13, 10, 0, 0, tzinfo=timezone.utc)
    return p

def _make_db_session():
    """Return a mock SQLAlchemy Session with chained query methods."""
    db = MagicMock()
    query_mock = MagicMock()
    query_mock.filter.return_value = query_mock
    query_mock.filter_by.return_value = query_mock
    query_mock.order_by.return_value = query_mock
    query_mock.limit.return_value = query_mock
    query_mock.offset.return_value = query_mock
    query_mock.count.return_value = 0
    query_mock.all.return_value = []
    query_mock.first.return_value = None
    query_mock.options.return_value = query_mock
    db.query.return_value = query_mock
    return db

# ===========================================================================
# list_plans
# ===========================================================================
class TestListPlans:
    """Tests for GET /plans."""

    @pytest.mark.asyncio
    async def test_list_empty(self):
        """No plans -- should return empty list."""
        db = _make_db_session()
        q = db.query.return_value.filter.return_value
        q.count.return_value = 0
        q.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []

        from core.api.routes.plans import list_plans

        result = await list_plans(user=_TEST_USER, db=db)

        assert result["total"] == 0
        assert result["plans"] == []

    @pytest.mark.asyncio
    async def test_list_with_plans(self):
        """Plans present -- should return them."""
        plan = _make_plan()
        db = _make_db_session()
        q = db.query.return_value.filter.return_value
        q.count.return_value = 1
        q.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [plan]

        from core.api.routes.plans import list_plans

        result = await list_plans(user=_TEST_USER, db=db)

        assert result["total"] == 1
        assert len(result["plans"]) == 1
        assert result["plans"][0]["name"] == "Test Plan"

    @pytest.mark.asyncio
    async def test_list_admin_sees_all(self):
        """Admin bypasses user_id filter."""
        db = _make_db_session()
        # For admin, no filter is applied (query directly)
        q = db.query.return_value
        q.count.return_value = 0
        q.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []

        from core.api.routes.plans import list_plans

        result = await list_plans(user=_TEST_ADMIN, db=db)
        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_list_with_conversation_filter(self):
        """conversation_id filter is applied."""
        conv_id = str(uuid.uuid4())
        plan = _make_plan(conversation_id=conv_id)
        db = _make_db_session()
        q = db.query.return_value.filter.return_value
        q.count.return_value = 1
        q.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [plan]

        from core.api.routes.plans import list_plans

        result = await list_plans(conversation_id=conv_id, user=_TEST_USER, db=db)

        # filter should have been called (at least for user_id and conversation_id)
        assert db.query.return_value.filter.call_count >= 1

    @pytest.mark.asyncio
    async def test_list_with_status_filter(self):
        """status filter is applied."""
        db = _make_db_session()
        q = db.query.return_value.filter.return_value
        q.count.return_value = 0
        q.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []

        from core.api.routes.plans import list_plans

        result = await list_plans(status="completed", user=_TEST_USER, db=db)
        assert result["total"] == 0

# ===========================================================================
# create_plan
# ===========================================================================
class TestCreatePlan:
    """Tests for POST /plans."""

    def test_create_valid_plan(self):
        """Valid plan creation succeeds."""
        conv_id = str(uuid.uuid4())
        conv = MagicMock()
        conv.id = conv_id
        conv.user_id = "test-user-001"

        plan = _make_plan(conversation_id=conv_id)

        db = _make_db_session()
        # First query: Conversation lookup
        conv_q = MagicMock()
        conv_q.filter_by.return_value.first.return_value = conv
        db.query.return_value = conv_q

        def fake_refresh(obj):
            obj.id = 1
            obj.created_at = datetime(2026, 1, 13, 10, 0, 0, tzinfo=timezone.utc)
            obj.updated_at = datetime(2026, 1, 13, 10, 0, 0, tzinfo=timezone.utc)
            obj.nodes = [{"id": "step1", "agent": "research", "task": "Research it"}]
            obj.edges = []
            obj.ai_generated = False

        db.refresh.side_effect = fake_refresh

        from core.api.routes.plans import CreatePlanRequest, create_plan

        req = CreatePlanRequest(
            conversation_id=conv_id,
            name="My Plan",
            nodes=[{"id": "step1", "agent": "research", "task": "Research it"}],
        )

        with patch("core.api.routes.plans._validate_plan_agents", return_value=[]):
            with patch("core.api.routes.plans._validate_step_references", return_value=[]):
                result = create_plan(request=req, user=_TEST_USER, db=db)

        db.add.assert_called_once()
        db.commit.assert_called_once()
        assert result["name"] == "My Plan"

    def test_create_missing_conversation_raises_404(self):
        """Plan creation with non-existent conversation raises 404."""
        from fastapi import HTTPException

        conv_id = str(uuid.uuid4())
        db = _make_db_session()
        db.query.return_value.filter_by.return_value.first.return_value = None

        from core.api.routes.plans import CreatePlanRequest, create_plan

        req = CreatePlanRequest(
            conversation_id=conv_id,
            name="My Plan",
            nodes=[{"id": "s1", "agent": "research", "task": "do stuff"}],
        )

        with pytest.raises(HTTPException) as exc_info:
            create_plan(request=req, user=_TEST_USER, db=db)
        assert exc_info.value.status_code == 404

    def test_create_invalid_agent_raises_400(self):
        """Plan with unknown agents raises 400."""
        import sys

        from fastapi import HTTPException

        conv_id = str(uuid.uuid4())
        conv = MagicMock()
        db = _make_db_session()
        db.query.return_value.filter_by.return_value.first.return_value = conv

        from core.api.routes.plans import CreatePlanRequest, create_plan

        req = CreatePlanRequest(
            conversation_id=conv_id,
            name="Bad Plan",
            nodes=[{"id": "s1", "agent": "nonexistent_agent", "task": "do stuff"}],
        )

        mock_adapters = MagicMock()
        mock_adapters.list_agents = MagicMock(return_value=[])

        with patch(
            "core.api.routes.plans._validate_plan_agents", return_value=["nonexistent_agent"]
        ):
            with patch.dict(sys.modules, {"core.adapters": mock_adapters}):
                with pytest.raises(HTTPException) as exc_info:
                    create_plan(request=req, user=_TEST_USER, db=db)
        assert exc_info.value.status_code == 400

# ===========================================================================
# get_plan
# ===========================================================================
class TestGetPlan:
    """Tests for GET /plans/{plan_id}."""

    @pytest.mark.asyncio
    async def test_get_own_plan(self):
        """User can get their own plan."""
        plan = _make_plan(user_id="test-user-001")
        db = _make_db_session()

        # get_plan uses joinedload, so query().options().filter_by().first()
        q = MagicMock()
        q.options.return_value = q
        q.filter_by.return_value.first.return_value = plan
        db.query.return_value = q

        from core.api.routes.plans import get_plan

        result = await get_plan(plan_id=1, user=_TEST_USER, db=db)

        assert result["id"] == 1
        assert result["name"] == "Test Plan"

    @pytest.mark.asyncio
    async def test_get_not_found_raises_404(self):
        """Non-existent plan raises 404."""
        from fastapi import HTTPException

        db = _make_db_session()
        q = MagicMock()
        q.options.return_value = q
        q.filter_by.return_value.first.return_value = None
        db.query.return_value = q

        from core.api.routes.plans import get_plan

        with pytest.raises(HTTPException) as exc_info:
            await get_plan(plan_id=999, user=_TEST_USER, db=db)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_other_users_plan_raises_403(self):
        """User cannot access another user's plan."""
        from fastapi import HTTPException

        plan = _make_plan(user_id="other-user")
        db = _make_db_session()
        q = MagicMock()
        q.options.return_value = q
        q.filter_by.return_value.first.return_value = plan
        db.query.return_value = q

        from core.api.routes.plans import get_plan

        with pytest.raises(HTTPException) as exc_info:
            await get_plan(plan_id=1, user=_TEST_USER, db=db)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_can_get_any_plan(self):
        """Admin can access any plan."""
        plan = _make_plan(user_id="other-user")
        db = _make_db_session()
        q = MagicMock()
        q.options.return_value = q
        q.filter_by.return_value.first.return_value = plan
        db.query.return_value = q

        from core.api.routes.plans import get_plan

        result = await get_plan(plan_id=1, user=_TEST_ADMIN, db=db)
        assert result["id"] == 1

# ===========================================================================
# update_plan
# ===========================================================================
class TestUpdatePlan:
    """Tests for PUT /plans/{plan_id}."""

    def test_update_draft_plan(self):
        """Draft plan can be updated."""
        plan = _make_plan(status="draft")
        plan.execution_results = []
        db = _make_db_session()
        db.query.return_value.filter_by.return_value.first.return_value = plan

        from core.api.routes.plans import UpdatePlanRequest, update_plan

        req = UpdatePlanRequest(name="Updated Plan")
        result = update_plan(plan_id=1, request=req, user=_TEST_USER, db=db)

        assert plan.name == "Updated Plan"
        db.commit.assert_called_once()

    def test_update_not_found_raises_404(self):
        """Update on non-existent plan raises 404."""
        from fastapi import HTTPException

        db = _make_db_session()
        db.query.return_value.filter_by.return_value.first.return_value = None

        from core.api.routes.plans import UpdatePlanRequest, update_plan

        with pytest.raises(HTTPException) as exc_info:
            update_plan(plan_id=999, request=UpdatePlanRequest(name="X"), user=_TEST_USER, db=db)
        assert exc_info.value.status_code == 404

    def test_update_access_denied_raises_403(self):
        """User cannot update another user's plan."""
        from fastapi import HTTPException

        plan = _make_plan(user_id="other-user")
        db = _make_db_session()
        db.query.return_value.filter_by.return_value.first.return_value = plan

        from core.api.routes.plans import UpdatePlanRequest, update_plan

        with pytest.raises(HTTPException) as exc_info:
            update_plan(plan_id=1, request=UpdatePlanRequest(name="X"), user=_TEST_USER, db=db)
        assert exc_info.value.status_code == 403

    def test_update_executing_plan_raises_400(self):
        """Executing plans cannot be modified (except status-only)."""
        from fastapi import HTTPException

        plan = _make_plan(status="executing")
        plan.execution_results = []
        db = _make_db_session()
        db.query.return_value.filter_by.return_value.first.return_value = plan

        from core.api.routes.plans import UpdatePlanRequest, update_plan

        # Attempting to change name on executing plan should fail
        with pytest.raises(HTTPException) as exc_info:
            update_plan(
                plan_id=1,
                request=UpdatePlanRequest(name="New Name"),
                user=_TEST_USER,
                db=db,
            )
        assert exc_info.value.status_code == 400

    def test_update_status_only_on_executing_plan_allowed(self):
        """Status-only updates are allowed on executing plans."""
        plan = _make_plan(status="executing")
        plan.execution_results = []
        db = _make_db_session()
        db.query.return_value.filter_by.return_value.first.return_value = plan

        from core.api.routes.plans import UpdatePlanRequest, update_plan

        # Status-only update (cancel) should succeed
        result = update_plan(
            plan_id=1,
            request=UpdatePlanRequest(status="cancelled"),
            user=_TEST_USER,
            db=db,
        )
        assert plan.status == "cancelled"

# ===========================================================================
# delete_plan
# ===========================================================================
class TestDeletePlan:
    """Tests for DELETE /plans/{plan_id}."""

    def test_delete_draft_plan(self):
        """Draft plan can be deleted."""
        plan = _make_plan(status="draft")
        db = _make_db_session()
        db.query.return_value.filter_by.return_value.first.return_value = plan

        from core.api.routes.plans import delete_plan

        delete_plan(plan_id=1, user=_TEST_USER, db=db)

        db.delete.assert_called_once_with(plan)
        db.commit.assert_called()

    def test_delete_not_found_raises_404(self):
        """Deleting non-existent plan raises 404."""
        from fastapi import HTTPException

        db = _make_db_session()
        db.query.return_value.filter_by.return_value.first.return_value = None

        from core.api.routes.plans import delete_plan

        with pytest.raises(HTTPException) as exc_info:
            delete_plan(plan_id=999, user=_TEST_USER, db=db)
        assert exc_info.value.status_code == 404

    def test_delete_access_denied_raises_403(self):
        """User cannot delete another user's plan."""
        from fastapi import HTTPException

        plan = _make_plan(user_id="other-user")
        db = _make_db_session()
        db.query.return_value.filter_by.return_value.first.return_value = plan

        from core.api.routes.plans import delete_plan

        with pytest.raises(HTTPException) as exc_info:
            delete_plan(plan_id=1, user=_TEST_USER, db=db)
        assert exc_info.value.status_code == 403

    def test_delete_executing_plan_raises_400(self):
        """Executing plans cannot be deleted."""
        from fastapi import HTTPException

        plan = _make_plan(status="executing")
        db = _make_db_session()
        db.query.return_value.filter_by.return_value.first.return_value = plan

        from core.api.routes.plans import delete_plan

        with pytest.raises(HTTPException) as exc_info:
            delete_plan(plan_id=1, user=_TEST_USER, db=db)
        assert exc_info.value.status_code == 400

    def test_admin_can_delete_any_plan(self):
        """Admin can delete any plan."""
        plan = _make_plan(user_id="other-user", status="draft")
        db = _make_db_session()
        db.query.return_value.filter_by.return_value.first.return_value = plan

        from core.api.routes.plans import delete_plan

        delete_plan(plan_id=1, user=_TEST_ADMIN, db=db)
        db.delete.assert_called_once_with(plan)

# ===========================================================================
# list_executions
# ===========================================================================
class TestListExecutions:
    """Tests for GET /plans/{plan_id}/executions."""

    def test_list_executions_not_found_raises_404(self):
        """Non-existent plan raises 404."""
        from fastapi import HTTPException

        db = _make_db_session()
        db.query.return_value.filter_by.return_value.first.return_value = None

        from core.api.routes.plans import list_executions

        with pytest.raises(HTTPException) as exc_info:
            list_executions(plan_id=999, user=_TEST_USER, db=db)
        assert exc_info.value.status_code == 404

    def test_list_executions_access_denied_raises_403(self):
        """User cannot list executions for another user's plan."""
        from fastapi import HTTPException

        plan = _make_plan(user_id="other-user")
        db = _make_db_session()
        db.query.return_value.filter_by.return_value.first.return_value = plan

        from core.api.routes.plans import list_executions

        with pytest.raises(HTTPException) as exc_info:
            list_executions(plan_id=1, user=_TEST_USER, db=db)
        assert exc_info.value.status_code == 403

    def test_list_executions_empty(self):
        """Plan with no executions returns empty list."""
        plan = _make_plan(user_id="test-user-001")
        db = _make_db_session()

        # First query: get plan
        plan_q = MagicMock()
        plan_q.filter_by.return_value.first.return_value = plan
        # Second query: get executions
        exec_q = MagicMock()
        exec_q.filter_by.return_value.order_by.return_value.all.return_value = []
        db.query.side_effect = [plan_q, exec_q]

        from core.api.routes.plans import list_executions

        result = list_executions(plan_id=1, user=_TEST_USER, db=db)
        assert result == []

# ===========================================================================
# validate_before_execute
# ===========================================================================
class TestValidateBeforeExecute:
    """Tests for POST /plans/{plan_id}/validate."""

    @pytest.mark.asyncio
    async def test_validate_not_found_raises_404(self):
        """Non-existent plan raises 404."""
        from fastapi import HTTPException

        db = _make_db_session()
        db.query.return_value.filter_by.return_value.first.return_value = None

        from core.api.routes.plans import validate_before_execute

        with pytest.raises(HTTPException) as exc_info:
            await validate_before_execute(plan_id=999, user=_TEST_USER, db=db)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_validate_access_denied_raises_403(self):
        """User cannot validate another user's plan."""
        from fastapi import HTTPException

        plan = _make_plan(user_id="other-user")
        db = _make_db_session()
        db.query.return_value.filter_by.return_value.first.return_value = plan

        from core.api.routes.plans import validate_before_execute

        with pytest.raises(HTTPException) as exc_info:
            await validate_before_execute(plan_id=1, user=_TEST_USER, db=db)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_validate_valid_plan(self):
        """Valid plan returns validation result."""
        plan = _make_plan(user_id="test-user-001", status="draft")
        db = _make_db_session()
        db.query.return_value.filter_by.return_value.first.return_value = plan

        from core.api.routes.plans import PlanValidationResult, validate_before_execute

        mock_result = PlanValidationResult(valid=True, errors=[], warnings=[])
        with patch("core.api.routes.plans._validate_plan_for_execution", return_value=mock_result):
            result = await validate_before_execute(plan_id=1, user=_TEST_USER, db=db)

        assert result.valid is True
        assert result.errors == []

# ===========================================================================
# submit_feedback
# ===========================================================================
class TestSubmitFeedback:
    """Tests for POST /plans/{plan_id}/feedback."""

    def test_submit_feedback_plan_not_found(self):
        """Feedback on non-existent plan raises 404."""
        from fastapi import HTTPException

        db = _make_db_session()
        db.query.return_value.filter_by.return_value.first.return_value = None

        from core.api.routes.plans import FeedbackRequest, submit_feedback

        req = FeedbackRequest(execution_id="exec-123", rating=5)

        with pytest.raises(HTTPException) as exc_info:
            submit_feedback(plan_id=999, request=req, user=_TEST_USER, db=db)
        assert exc_info.value.status_code == 404

    def test_submit_feedback_access_denied(self):
        """User cannot submit feedback for another user's plan."""
        from fastapi import HTTPException

        plan = _make_plan(user_id="other-user")
        db = _make_db_session()
        db.query.return_value.filter_by.return_value.first.return_value = plan

        from core.api.routes.plans import FeedbackRequest, submit_feedback

        req = FeedbackRequest(execution_id="exec-123", rating=4)

        with pytest.raises(HTTPException) as exc_info:
            submit_feedback(plan_id=1, request=req, user=_TEST_USER, db=db)
        assert exc_info.value.status_code == 403

    def test_submit_feedback_execution_not_found(self):
        """Feedback on non-existent execution raises 404."""
        from fastapi import HTTPException

        plan = _make_plan(user_id="test-user-001")
        db = _make_db_session()

        # First query: plan lookup
        plan_q = MagicMock()
        plan_q.filter_by.return_value.first.return_value = plan
        # Second query: execution lookup
        exec_q = MagicMock()
        exec_q.filter_by.return_value.first.return_value = None
        db.query.side_effect = [plan_q, exec_q]

        from core.api.routes.plans import FeedbackRequest, submit_feedback

        req = FeedbackRequest(execution_id="exec-nonexistent", rating=3)

        with pytest.raises(HTTPException) as exc_info:
            submit_feedback(plan_id=1, request=req, user=_TEST_USER, db=db)
        assert exc_info.value.status_code == 404

    def test_submit_feedback_success(self):
        """Valid feedback submission succeeds."""
        plan = _make_plan(user_id="test-user-001")
        exec_result = MagicMock()
        exec_result.user_feedback_rating = None
        exec_result.user_feedback_comment = None

        db = _make_db_session()
        plan_q = MagicMock()
        plan_q.filter_by.return_value.first.return_value = plan
        exec_q = MagicMock()
        exec_q.filter_by.return_value.first.return_value = exec_result
        db.query.side_effect = [plan_q, exec_q]

        from core.api.routes.plans import FeedbackRequest, submit_feedback

        req = FeedbackRequest(execution_id="exec-123", rating=5, comment="Great!")
        result = submit_feedback(plan_id=1, request=req, user=_TEST_USER, db=db)

        assert result["rating"] == 5
        assert exec_result.user_feedback_rating == 5
        assert exec_result.user_feedback_comment == "Great!"
        db.commit.assert_called_once()

# ===========================================================================
# list_plan_templates
# ===========================================================================
class TestListPlanTemplates:
    """Tests for GET /plan-templates."""

    def test_list_templates_empty(self):
        """Empty template list returns correctly."""
        import sys

        from core.api.routes.plans import list_plan_templates

        # list_templates is imported inside the function body from core.orchestrator.templates
        mock_module = MagicMock()
        mock_module.list_templates = MagicMock(return_value=[])
        with patch.dict(sys.modules, {"core.orchestrator.templates": mock_module}):
            result = list_plan_templates()

        assert result["total"] == 0
        assert result["templates"] == []

    def test_list_templates_error_raises_500(self):
        """Template listing error raises 500."""
        import sys

        from fastapi import HTTPException

        from core.api.routes.plans import list_plan_templates

        mock_module = MagicMock()
        mock_module.list_templates = MagicMock(side_effect=RuntimeError("fail"))
        with patch.dict(sys.modules, {"core.orchestrator.templates": mock_module}):
            with pytest.raises(HTTPException) as exc_info:
                list_plan_templates()
        assert exc_info.value.status_code == 500

# ===========================================================================
# cleanup_plans
# ===========================================================================
class TestCleanupPlans:
    """Tests for POST /plans/cleanup."""

    def test_cleanup_requires_admin(self):
        """Non-admin user gets 403."""
        from fastapi import HTTPException

        from core.api.routes.plans import cleanup_plans

        with pytest.raises(HTTPException) as exc_info:
            cleanup_plans(user=_TEST_USER, db=_make_db_session())
        assert exc_info.value.status_code == 403

    def test_cleanup_admin_succeeds(self):
        """Admin can trigger cleanup."""
        db = _make_db_session()

        from core.api.routes.plans import cleanup_plans

        with patch("core.api.routes.plans.cleanup_old_draft_plans", return_value=3):
            result = cleanup_plans(user=_TEST_ADMIN, db=db)

        assert result["deleted"] == 3

# ===========================================================================
# _topological_sort helper
# ===========================================================================
class TestTopologicalSort:
    """Tests for the _topological_sort helper function."""

    def test_linear_chain(self):
        """Linear A->B->C should sort correctly."""
        from core.api.routes.plans import _topological_sort

        nodes = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        edges = [
            {"source": "a", "target": "b"},
            {"source": "b", "target": "c"},
        ]
        sorted_ids, dropped = _topological_sort(nodes, edges)

        assert sorted_ids == ["a", "b", "c"]
        assert dropped == []

    def test_parallel_nodes(self):
        """Parallel nodes A->C and B->C should both precede C."""
        from core.api.routes.plans import _topological_sort

        nodes = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        edges = [
            {"source": "a", "target": "c"},
            {"source": "b", "target": "c"},
        ]
        sorted_ids, dropped = _topological_sort(nodes, edges)

        assert "c" in sorted_ids
        assert sorted_ids.index("a") < sorted_ids.index("c")
        assert sorted_ids.index("b") < sorted_ids.index("c")
        assert dropped == []

    def test_cycle_detection(self):
        """Cycles result in dropped nodes."""
        from core.api.routes.plans import _topological_sort

        nodes = [{"id": "a"}, {"id": "b"}]
        edges = [
            {"source": "a", "target": "b"},
            {"source": "b", "target": "a"},
        ]
        sorted_ids, dropped = _topological_sort(nodes, edges)

        # All nodes should be dropped (cycle)
        assert len(dropped) > 0

    def test_empty_graph(self):
        """Empty nodes and edges returns empty lists."""
        from core.api.routes.plans import _topological_sort

        sorted_ids, dropped = _topological_sort([], [])
        assert sorted_ids == []
        assert dropped == []

    def test_legacy_from_to_edges(self):
        """Edges with 'from'/'to' fields (legacy format) are handled."""
        from core.api.routes.plans import _topological_sort

        nodes = [{"id": "a"}, {"id": "b"}]
        edges = [{"from": "a", "to": "b"}]
        sorted_ids, dropped = _topological_sort(nodes, edges)

        assert sorted_ids == ["a", "b"]
        assert dropped == []
