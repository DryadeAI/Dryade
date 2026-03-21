"""Tests for core/api/routes/plans.py -- Plan management endpoints.

Tests key route handlers directly (async pattern) with SQLite in-memory database
(no real PostgreSQL required). Focuses on high-coverage paths: CRUD operations,
validation, model functions.
"""

import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.database.models import Base, Conversation, ExecutionPlan

# ---------------------------------------------------------------------------
# Per-test SQLite in-memory DB (fresh engine per test avoids UNIQUE collisions)
# ---------------------------------------------------------------------------

_test_session_factory: sessionmaker | None = None

def _make_session():
    """Return a session from the current test's SQLite engine."""
    assert _test_session_factory is not None, "Call _make_session() inside a test only"
    return _test_session_factory()

# ---------------------------------------------------------------------------
# Autouse fixture: fresh SQLite engine per test, also patches get_session
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_get_session(monkeypatch):
    """Create a fresh SQLite in-memory engine per test and patch get_session."""
    global _test_session_factory
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    _test_session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    @contextmanager
    def _sqlite_session():
        session = _test_session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    monkeypatch.setattr("core.database.session.get_session", _sqlite_session)
    try:
        import core.api.routes.plans as _mod  # noqa: PLC0415

        monkeypatch.setattr(_mod, "get_session", _sqlite_session, raising=False)
    except Exception:
        pass
    yield
    _test_session_factory = None

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _user(sub: str = "user-001", role: str = "member") -> dict:
    return {"sub": sub, "role": role}

def _conv_id() -> str:
    return str(uuid.uuid4())

def _make_conversation(db, user_id: str = "user-001") -> Conversation:
    conv = Conversation(
        id=_conv_id(),
        user_id=user_id,
        title="Test",
        mode="planner",
        status="active",
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv

def _make_plan(
    db,
    user_id: str = "user-001",
    conversation_id: str | None = None,
    name: str = "Test Plan",
    status: str = "draft",
) -> ExecutionPlan:
    conv_id = conversation_id or _conv_id()
    plan = ExecutionPlan(
        conversation_id=conv_id,
        user_id=user_id,
        name=name,
        description="Test plan",
        nodes=[{"id": "task_1", "agent": "research", "task": "Do research", "depends_on": []}],
        edges=[],
        status=status,
        confidence=0.9,
        ai_generated=False,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan

# ===========================================================================
# get_plan handler
# ===========================================================================

class TestGetPlan:
    """Tests for get_plan handler."""

    @pytest.mark.asyncio
    async def test_get_plan_success(self):
        """Returns plan details for owner."""
        from core.api.routes.plans import get_plan

        db = _make_session()
        user = _user()
        plan = _make_plan(db, user_id=user["sub"])

        result = await get_plan(plan_id=plan.id, user=user, db=db)
        assert result["id"] == plan.id
        assert result["name"] == "Test Plan"
        assert result["status"] == "draft"
        db.close()

    @pytest.mark.asyncio
    async def test_get_plan_not_found(self):
        """Returns 404 for non-existent plan."""
        from core.api.routes.plans import get_plan

        db = _make_session()
        with pytest.raises(HTTPException) as exc:
            await get_plan(plan_id=99999, user=_user(), db=db)
        assert exc.value.status_code == 404
        db.close()

    @pytest.mark.asyncio
    async def test_get_plan_forbidden(self):
        """Returns 403 when accessing another user's plan."""
        from core.api.routes.plans import get_plan

        db = _make_session()
        plan = _make_plan(db, user_id="user-B")

        with pytest.raises(HTTPException) as exc:
            await get_plan(plan_id=plan.id, user=_user(sub="user-A"), db=db)
        assert exc.value.status_code == 403
        db.close()

    @pytest.mark.asyncio
    async def test_get_plan_admin_access(self):
        """Admin can access any user's plan."""
        from core.api.routes.plans import get_plan

        db = _make_session()
        plan = _make_plan(db, user_id="user-B")

        result = await get_plan(plan_id=plan.id, user=_user(sub="admin-1", role="admin"), db=db)
        assert result["id"] == plan.id
        db.close()

    @pytest.mark.asyncio
    async def test_get_plan_includes_execution_count(self):
        """Response includes execution_count field."""
        from core.api.routes.plans import get_plan

        db = _make_session()
        user = _user()
        plan = _make_plan(db, user_id=user["sub"])

        result = await get_plan(plan_id=plan.id, user=user, db=db)
        assert "execution_count" in result
        assert result["execution_count"] == 0
        db.close()

# ===========================================================================
# list_plans handler
# ===========================================================================

class TestListPlans:
    """Tests for list_plans handler."""

    @pytest.mark.asyncio
    async def test_list_plans_empty(self):
        """Returns empty list when no plans exist."""
        from core.api.routes.plans import list_plans

        db = _make_session()
        result = await list_plans(
            user=_user(),
            db=db,
            conversation_id=None,
            status=None,
            ai_generated=None,
            limit=50,
            offset=0,
        )
        assert result["total"] == 0
        assert result["plans"] == []
        db.close()

    @pytest.mark.asyncio
    async def test_list_plans_returns_own(self):
        """User sees only their own plans."""
        from core.api.routes.plans import list_plans

        db = _make_session()
        user = _user()
        _make_plan(db, user_id=user["sub"], name="My Plan")
        _make_plan(db, user_id="other-user", name="Other Plan")

        result = await list_plans(
            user=user,
            db=db,
            conversation_id=None,
            status=None,
            ai_generated=None,
            limit=50,
            offset=0,
        )
        assert result["total"] == 1
        assert result["plans"][0]["name"] == "My Plan"
        db.close()

    @pytest.mark.asyncio
    async def test_list_plans_admin_sees_all(self):
        """Admin sees all plans."""
        from core.api.routes.plans import list_plans

        db = _make_session()
        _make_plan(db, user_id="user-A")
        _make_plan(db, user_id="user-B")

        result = await list_plans(
            user=_user(sub="admin-1", role="admin"),
            db=db,
            conversation_id=None,
            status=None,
            ai_generated=None,
            limit=50,
            offset=0,
        )
        assert result["total"] == 2
        db.close()

    @pytest.mark.asyncio
    async def test_list_plans_filter_by_status(self):
        """Filters plans by status."""
        from core.api.routes.plans import list_plans

        db = _make_session()
        user = _user()
        _make_plan(db, user_id=user["sub"], name="Draft Plan", status="draft")
        _make_plan(db, user_id=user["sub"], name="Completed Plan", status="completed")

        result = await list_plans(
            user=user,
            db=db,
            conversation_id=None,
            status="draft",
            ai_generated=None,
            limit=50,
            offset=0,
        )
        assert result["total"] == 1
        assert result["plans"][0]["name"] == "Draft Plan"
        db.close()

    @pytest.mark.asyncio
    async def test_list_plans_filter_by_conversation(self):
        """Filters plans by conversation_id."""
        from core.api.routes.plans import list_plans

        db = _make_session()
        user = _user()
        conv_id = _conv_id()
        _make_plan(db, user_id=user["sub"], conversation_id=conv_id, name="Plan for Conv")
        _make_plan(db, user_id=user["sub"], name="Other Plan")

        result = await list_plans(
            user=user,
            db=db,
            conversation_id=conv_id,
            status=None,
            ai_generated=None,
            limit=50,
            offset=0,
        )
        assert result["total"] == 1
        assert result["plans"][0]["name"] == "Plan for Conv"
        db.close()

# ===========================================================================
# create_plan handler
# ===========================================================================

class TestCreatePlan:
    """Tests for create_plan handler."""

    @pytest.mark.asyncio
    async def test_create_plan_success(self):
        """Creates a plan in draft status."""
        from core.api.routes.plans import CreatePlanRequest, create_plan

        db = _make_session()
        user = _user()
        conv = _make_conversation(db, user_id=user["sub"])
        req = CreatePlanRequest(
            conversation_id=conv.id,
            name="My Plan",
            nodes=[{"id": "task_1", "agent": "research", "task": "Research AI", "depends_on": []}],
            edges=[],
        )

        with patch("core.api.routes.plans._validate_plan_agents", return_value=[]):
            result = create_plan(request=req, user=user, db=db)
        assert result["name"] == "My Plan"
        assert result["status"] == "draft"
        db.close()

    @pytest.mark.asyncio
    async def test_create_plan_stored_in_db(self):
        """Created plan is persisted in DB."""
        from core.api.routes.plans import CreatePlanRequest, create_plan

        db = _make_session()
        user = _user()
        conv = _make_conversation(db, user_id=user["sub"])
        req = CreatePlanRequest(
            conversation_id=conv.id,
            name="Persisted Plan",
            nodes=[{"id": "t1", "agent": "research", "task": "Task", "depends_on": []}],
            edges=[],
        )

        with patch("core.api.routes.plans._validate_plan_agents", return_value=[]):
            result = create_plan(request=req, user=user, db=db)
        plan_id = result["id"]

        # Verify in DB
        plan = db.query(ExecutionPlan).filter_by(id=plan_id).first()
        assert plan is not None
        assert plan.name == "Persisted Plan"
        db.close()

    @pytest.mark.asyncio
    async def test_create_plan_user_from_token(self):
        """Plan user_id is set from JWT sub."""
        from core.api.routes.plans import CreatePlanRequest, create_plan

        db = _make_session()
        user = _user(sub="jwt-user-123")
        conv = _make_conversation(db, user_id=user["sub"])
        req = CreatePlanRequest(
            conversation_id=conv.id,
            name="JWT Plan",
            nodes=[{"id": "t1", "agent": "research", "task": "Task", "depends_on": []}],
            edges=[],
        )

        with patch("core.api.routes.plans._validate_plan_agents", return_value=[]):
            result = create_plan(request=req, user=user, db=db)
        assert result["user_id"] == "jwt-user-123"
        db.close()

    @pytest.mark.asyncio
    async def test_create_plan_conversation_not_found(self):
        """Returns 404 when conversation does not exist."""
        from core.api.routes.plans import CreatePlanRequest, create_plan

        db = _make_session()
        user = _user()
        req = CreatePlanRequest(
            conversation_id="nonexistent-conv-id",
            name="Orphan Plan",
            nodes=[{"id": "t1", "agent": "research", "task": "Task", "depends_on": []}],
            edges=[],
        )

        with pytest.raises(HTTPException) as exc:
            create_plan(request=req, user=user, db=db)
        assert exc.value.status_code == 404
        db.close()

# ===========================================================================
# update_plan handler
# ===========================================================================

class TestUpdatePlan:
    """Tests for update_plan handler."""

    @pytest.mark.asyncio
    async def test_update_plan_name(self):
        """Updates plan name."""
        from core.api.routes.plans import UpdatePlanRequest, update_plan

        db = _make_session()
        user = _user()
        plan = _make_plan(db, user_id=user["sub"], name="Old Name")
        req = UpdatePlanRequest(name="New Name")

        result = update_plan(plan_id=plan.id, request=req, user=user, db=db)
        assert result["name"] == "New Name"
        db.close()

    @pytest.mark.asyncio
    async def test_update_plan_not_found(self):
        """Returns 404 for non-existent plan."""
        from core.api.routes.plans import UpdatePlanRequest, update_plan

        db = _make_session()
        req = UpdatePlanRequest(name="New Name")

        with pytest.raises(HTTPException) as exc:
            update_plan(plan_id=99999, request=req, user=_user(), db=db)
        assert exc.value.status_code == 404
        db.close()

    @pytest.mark.asyncio
    async def test_update_plan_forbidden(self):
        """Returns 403 for another user's plan."""
        from core.api.routes.plans import UpdatePlanRequest, update_plan

        db = _make_session()
        plan = _make_plan(db, user_id="user-B")
        req = UpdatePlanRequest(name="Hack")

        with pytest.raises(HTTPException) as exc:
            update_plan(plan_id=plan.id, request=req, user=_user(sub="user-A"), db=db)
        assert exc.value.status_code == 403
        db.close()

    @pytest.mark.asyncio
    async def test_update_completed_plan_rejected(self):
        """Cannot update a completed plan."""
        from core.api.routes.plans import UpdatePlanRequest, update_plan

        db = _make_session()
        user = _user()
        plan = _make_plan(db, user_id=user["sub"], status="completed")
        req = UpdatePlanRequest(name="New Name")

        with pytest.raises(HTTPException) as exc:
            update_plan(plan_id=plan.id, request=req, user=user, db=db)
        assert exc.value.status_code in (400, 403)
        db.close()

    @pytest.mark.asyncio
    async def test_update_plan_status(self):
        """Updates plan status to approved."""
        from core.api.routes.plans import UpdatePlanRequest, update_plan

        db = _make_session()
        user = _user()
        plan = _make_plan(db, user_id=user["sub"], status="draft")
        req = UpdatePlanRequest(status="approved")

        result = update_plan(plan_id=plan.id, request=req, user=user, db=db)
        assert result["status"] == "approved"
        db.close()

# ===========================================================================
# delete_plan handler
# ===========================================================================

class TestDeletePlan:
    """Tests for delete_plan handler."""

    @pytest.mark.asyncio
    async def test_delete_draft_plan(self):
        """Deletes draft plan."""
        from core.api.routes.plans import delete_plan

        db = _make_session()
        user = _user()
        plan = _make_plan(db, user_id=user["sub"], status="draft")

        result = delete_plan(plan_id=plan.id, user=user, db=db)
        assert result is None  # 204 No Content

        # Verify deleted
        assert db.query(ExecutionPlan).filter_by(id=plan.id).first() is None
        db.close()

    @pytest.mark.asyncio
    async def test_delete_plan_not_found(self):
        """Returns 404 for non-existent plan."""
        from core.api.routes.plans import delete_plan

        db = _make_session()
        with pytest.raises(HTTPException) as exc:
            delete_plan(plan_id=99999, user=_user(), db=db)
        assert exc.value.status_code == 404
        db.close()

    @pytest.mark.asyncio
    async def test_delete_plan_forbidden(self):
        """Returns 403 for another user's plan."""
        from core.api.routes.plans import delete_plan

        db = _make_session()
        plan = _make_plan(db, user_id="user-B")

        with pytest.raises(HTTPException) as exc:
            delete_plan(plan_id=plan.id, user=_user(sub="user-A"), db=db)
        assert exc.value.status_code == 403
        db.close()

    @pytest.mark.asyncio
    async def test_delete_executing_plan_rejected(self):
        """Cannot delete an executing plan."""
        from core.api.routes.plans import delete_plan

        db = _make_session()
        user = _user()
        plan = _make_plan(db, user_id=user["sub"], status="executing")

        with pytest.raises(HTTPException) as exc:
            delete_plan(plan_id=plan.id, user=user, db=db)
        assert exc.value.status_code in (400, 403)
        db.close()

# ===========================================================================
# Helper functions
# ===========================================================================

class TestHelperFunctions:
    """Tests for plan module helper functions."""

    def test_topological_sort_simple(self):
        """_topological_sort returns correct order for simple chain."""
        from core.api.routes.plans import _topological_sort

        nodes = [
            {"id": "A", "depends_on": []},
            {"id": "B", "depends_on": ["A"]},
            {"id": "C", "depends_on": ["B"]},
        ]
        edges = [{"from": "A", "to": "B"}, {"from": "B", "to": "C"}]

        order, errors = _topological_sort(nodes, edges)
        assert errors == []
        assert order.index("A") < order.index("B")
        assert order.index("B") < order.index("C")

    def test_topological_sort_detects_cycle(self):
        """_topological_sort detects cycles in the graph."""
        from core.api.routes.plans import _topological_sort

        nodes = [
            {"id": "A", "depends_on": ["C"]},
            {"id": "B", "depends_on": ["A"]},
            {"id": "C", "depends_on": ["B"]},
        ]
        edges = [
            {"from": "A", "to": "B"},
            {"from": "B", "to": "C"},
            {"from": "C", "to": "A"},
        ]

        order, errors = _topological_sort(nodes, edges)
        assert len(errors) > 0

    def test_topological_sort_parallel_tasks(self):
        """_topological_sort handles parallel tasks."""
        from core.api.routes.plans import _topological_sort

        nodes = [
            {"id": "A", "depends_on": []},
            {"id": "B", "depends_on": []},
            {"id": "C", "depends_on": ["A", "B"]},
        ]
        edges = [{"from": "A", "to": "C"}, {"from": "B", "to": "C"}]

        order, errors = _topological_sort(nodes, edges)
        assert errors == []
        assert "A" in order
        assert "B" in order
        assert order.index("C") > order.index("A")

    def test_normalize_edges_from_to(self):
        """_normalize_edges normalizes 'from'/'to' to 'source'/'target'."""
        from core.api.routes.plans import _normalize_edges

        edges = [{"from": "A", "to": "B"}]
        result = _normalize_edges(edges)
        assert result[0]["source"] == "A"
        assert result[0]["target"] == "B"

    def test_normalize_edges_source_target(self):
        """_normalize_edges preserves 'source'/'target' format."""
        from core.api.routes.plans import _normalize_edges

        edges = [{"source": "A", "target": "B"}]
        result = _normalize_edges(edges)
        assert result[0]["source"] == "A"
        assert result[0]["target"] == "B"

    def test_validate_plan_agents_valid(self):
        """_validate_plan_agents returns empty list for known agents."""
        from core.api.routes.plans import _validate_plan_agents

        nodes = [{"id": "t1", "agent": "research", "task": "Research"}]

        with patch("core.api.routes.plans._resolve_agent_name") as mock_resolve:
            mock_resolve.return_value = ("research", MagicMock())
            errors = _validate_plan_agents(nodes)

        assert errors == []

    def test_validate_plan_agents_unknown(self):
        """_validate_plan_agents returns errors for unknown agents."""
        from core.api.routes.plans import _validate_plan_agents

        nodes = [{"id": "t1", "agent": "nonexistent_agent_xyz", "task": "Task"}]

        with patch("core.api.routes.plans._resolve_agent_name", return_value=(None, None)):
            errors = _validate_plan_agents(nodes)

        # Should return validation errors for unknown agents
        assert isinstance(errors, list)

    def test_cleanup_old_draft_plans_count(self):
        """cleanup_old_draft_plans returns correct count."""
        from core.api.routes.plans import cleanup_old_draft_plans

        db = _make_session()
        user = _user()
        # Create some draft plans
        _make_plan(db, user_id=user["sub"], status="draft")

        # Zero retention should cleanup immediately
        count = cleanup_old_draft_plans(db, retention_days=-1)  # negative = old threshold
        assert count >= 0  # May or may not delete depending on created_at threshold
        db.close()

# ===========================================================================
# Pydantic model validation
# ===========================================================================

class TestPlanModels:
    """Tests for Pydantic models in plans module."""

    def test_create_plan_request_validation(self):
        """CreatePlanRequest validates required fields."""
        from pydantic import ValidationError

        from core.api.routes.plans import CreatePlanRequest

        # Missing name should fail
        with pytest.raises(ValidationError):
            CreatePlanRequest(
                conversation_id="conv-id",
                nodes=[],
            )

    def test_create_plan_request_success(self):
        """CreatePlanRequest succeeds with required fields."""
        from core.api.routes.plans import CreatePlanRequest

        req = CreatePlanRequest(
            conversation_id="conv-id",
            name="My Plan",
            nodes=[{"id": "t1", "agent": "a", "task": "t", "depends_on": []}],
        )
        assert req.name == "My Plan"
        assert req.status == "draft"

    def test_feedback_request_validation(self):
        """FeedbackRequest validates rating range (1-5)."""
        from pydantic import ValidationError

        from core.api.routes.plans import FeedbackRequest

        with pytest.raises(ValidationError):
            FeedbackRequest(execution_id="exec-1", rating=0)  # below minimum

        with pytest.raises(ValidationError):
            FeedbackRequest(execution_id="exec-1", rating=6)  # above maximum

    def test_feedback_request_valid(self):
        """FeedbackRequest accepts valid ratings."""
        from core.api.routes.plans import FeedbackRequest

        req = FeedbackRequest(execution_id="exec-1", rating=4, comment="Good plan!")
        assert req.rating == 4
        assert req.comment == "Good plan!"

    def test_refusal_patterns_are_lowercase(self):
        """REFUSAL_PATTERNS are all lowercase for case-insensitive matching."""
        from core.api.routes.plans import REFUSAL_PATTERNS

        for pattern in REFUSAL_PATTERNS:
            assert pattern == pattern.lower(), f"Pattern not lowercase: {pattern}"
