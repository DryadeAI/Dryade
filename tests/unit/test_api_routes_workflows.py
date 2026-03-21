"""Tests for core/api/routes/workflows.py -- Workflow CRUD and lifecycle endpoints.

Tests route handler functions directly (async pattern) to avoid DB session conflicts.
Uses SQLite in-memory database (no real PostgreSQL required). Mocks ownership dependencies via patch.
"""

import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.database.models import Base, Workflow

# ---------------------------------------------------------------------------
# Per-test SQLite in-memory DB (fresh engine per test avoids UNIQUE collisions)
# ---------------------------------------------------------------------------

# Module-level shared engine used only by _make_session() calls within each test.
# Each test gets a new engine via the autouse fixture which resets _test_session_factory.

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
        import core.api.routes.workflows as _mod  # noqa: PLC0415

        monkeypatch.setattr(_mod, "get_session", _sqlite_session, raising=False)
    except Exception:
        pass
    yield
    _test_session_factory = None

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_VALID_WF_JSON: dict[str, Any] = {
    "version": "1.0.0",
    "nodes": [
        {
            "id": "task_1",
            "type": "task",
            "data": {"agent": "research", "task": "Do some research"},
            "position": {"x": 0, "y": 0},
        }
    ],
    "edges": [],
}

def _user(sub: str = "user-001", role: str = "member") -> dict:
    return {"sub": sub, "role": role}

def _make_workflow(
    db,
    user_id: str = "user-001",
    name: str = "Test Workflow",
    status: str = "draft",
    is_public: bool = False,
) -> Workflow:
    wf = Workflow(
        name=name,
        description="Test workflow",
        version="1.0.0",
        workflow_json=_VALID_WF_JSON,
        status=status,
        is_public=is_public,
        user_id=user_id,
        tags=["test"],
        execution_count=0,
    )
    db.add(wf)
    db.commit()
    db.refresh(wf)
    return wf

def _noop_background_tasks() -> BackgroundTasks:
    bt = MagicMock(spec=BackgroundTasks)
    bt.add_task = MagicMock()
    return bt

# ===========================================================================
# create_workflow handler
# ===========================================================================

class TestCreateWorkflow:
    """Tests for create_workflow handler."""

    @pytest.mark.asyncio
    async def test_create_workflow_success(self):
        """Creates a workflow in draft status."""
        from core.api.routes.workflows import CreateWorkflowRequest, create_workflow

        db = _make_session()
        req = CreateWorkflowRequest(name="My Workflow", workflow_json=_VALID_WF_JSON)
        bt = _noop_background_tasks()

        with patch("core.api.routes.workflows.WorkflowSchema") as mock_schema:
            mock_schema.model_validate.return_value = MagicMock()
            with patch("core.api.routes.workflows.log_audit"):
                result = await create_workflow(
                    request=req, background_tasks=bt, user=_user(), db=db
                )

        assert result["name"] == "My Workflow"
        assert result["status"] == "draft"
        assert result["version"] == "1.0.0"
        db.close()

    @pytest.mark.asyncio
    async def test_create_workflow_invalid_schema(self):
        """Returns 400 for invalid workflow_json."""
        from core.api.routes.workflows import CreateWorkflowRequest, create_workflow

        db = _make_session()
        req = CreateWorkflowRequest(
            name="Bad Workflow",
            workflow_json={"version": "1.0.0", "nodes": [], "edges": []},
        )
        bt = _noop_background_tasks()

        with patch("core.api.routes.workflows.WorkflowSchema") as mock_schema:
            mock_schema.model_validate.side_effect = ValueError("bad schema")
            with pytest.raises(HTTPException) as exc:
                await create_workflow(request=req, background_tasks=bt, user=_user(), db=db)

        assert exc.value.status_code == 400
        db.close()

    @pytest.mark.asyncio
    async def test_create_workflow_sets_user_from_token(self):
        """Workflow user_id is set from the JWT sub claim."""
        from core.api.routes.workflows import CreateWorkflowRequest, create_workflow

        db = _make_session()
        req = CreateWorkflowRequest(name="User Workflow", workflow_json=_VALID_WF_JSON)
        bt = _noop_background_tasks()
        user = _user(sub="user-123")

        with patch("core.api.routes.workflows.WorkflowSchema"):
            with patch("core.api.routes.workflows.log_audit"):
                result = await create_workflow(request=req, background_tasks=bt, user=user, db=db)

        assert result["user_id"] == "user-123"
        db.close()

# ===========================================================================
# list_workflows handler
# ===========================================================================

class TestListWorkflows:
    """Tests for list_workflows handler."""

    @pytest.mark.asyncio
    async def test_list_workflows_empty(self):
        """Returns empty list when no workflows exist."""
        from core.api.routes.workflows import list_workflows

        db = _make_session()

        async def _fake_filter(**kwargs):
            return db.query(Workflow).filter(Workflow.id == -1)  # empty result

        with patch(
            "core.api.routes.workflows.filter_by_owner_or_shared", return_value=_fake_filter
        ):
            result = await list_workflows(
                status=None, tags=None, offset=0, limit=50, user=_user(), db=db
            )

        assert result["total"] == 0
        assert result["workflows"] == []
        db.close()

    @pytest.mark.asyncio
    async def test_list_workflows_returns_all_owned(self):
        """Returns all workflows when no filter applied."""
        from core.api.routes.workflows import list_workflows

        db = _make_session()
        _make_workflow(db, name="WF 1")
        _make_workflow(db, name="WF 2")

        async def _fake_filter(**kwargs):
            return db.query(Workflow)

        with patch(
            "core.api.routes.workflows.filter_by_owner_or_shared", return_value=_fake_filter
        ):
            result = await list_workflows(
                status=None, tags=None, offset=0, limit=50, user=_user(), db=db
            )

        assert result["total"] == 2
        assert len(result["workflows"]) == 2
        db.close()

    @pytest.mark.asyncio
    async def test_list_workflows_status_filter(self):
        """Filters workflows by status."""
        from core.api.routes.workflows import list_workflows

        db = _make_session()
        _make_workflow(db, name="Draft WF", status="draft")
        _make_workflow(db, name="Published WF", status="published")

        async def _fake_filter(**kwargs):
            return db.query(Workflow)

        with patch(
            "core.api.routes.workflows.filter_by_owner_or_shared", return_value=_fake_filter
        ):
            result = await list_workflows(
                status="draft", tags=None, offset=0, limit=50, user=_user(), db=db
            )

        assert result["total"] == 1
        assert result["workflows"][0]["status"] == "draft"
        db.close()

    @pytest.mark.asyncio
    async def test_list_workflows_pagination(self):
        """Pagination returns correct results."""
        from core.api.routes.workflows import list_workflows

        db = _make_session()
        for i in range(5):
            _make_workflow(db, name=f"WF {i}")

        async def _fake_filter(**kwargs):
            return db.query(Workflow)

        with patch(
            "core.api.routes.workflows.filter_by_owner_or_shared", return_value=_fake_filter
        ):
            result = await list_workflows(
                status=None, tags=None, offset=0, limit=2, user=_user(), db=db
            )

        assert result["total"] == 5
        assert len(result["workflows"]) == 2
        assert result["has_more"] is True
        db.close()

# ===========================================================================
# get_workflow handler
# ===========================================================================

class TestGetWorkflow:
    """Tests for get_workflow handler."""

    @pytest.mark.asyncio
    async def test_get_workflow_success(self):
        """Returns full workflow details."""
        from core.api.routes.workflows import get_workflow

        db = _make_session()
        wf = _make_workflow(db, name="Test WF")

        async def _fake_getter(**kwargs):
            return db.query(Workflow).filter(Workflow.id == wf.id).first()

        with patch(
            "core.api.routes.workflows.get_owned_or_shared_resource", return_value=_fake_getter
        ):
            result = await get_workflow(workflow_id=wf.id, user=_user(), db=db)

        assert result["id"] == wf.id
        assert result["name"] == "Test WF"
        assert "workflow_json" in result
        db.close()

    @pytest.mark.asyncio
    async def test_get_workflow_not_found(self):
        """Returns 404 for non-existent workflow."""
        from core.api.routes.workflows import get_workflow

        db = _make_session()

        async def _fake_getter(**kwargs):
            raise HTTPException(status_code=404, detail="Workflow not found")

        with patch(
            "core.api.routes.workflows.get_owned_or_shared_resource", return_value=_fake_getter
        ):
            with pytest.raises(HTTPException) as exc:
                await get_workflow(workflow_id=99999, user=_user(), db=db)

        assert exc.value.status_code == 404
        db.close()

    @pytest.mark.asyncio
    async def test_get_workflow_includes_workflow_json(self):
        """Response includes full workflow_json."""
        from core.api.routes.workflows import get_workflow

        db = _make_session()
        wf = _make_workflow(db)

        async def _fake_getter(**kwargs):
            return db.query(Workflow).filter(Workflow.id == wf.id).first()

        with patch(
            "core.api.routes.workflows.get_owned_or_shared_resource", return_value=_fake_getter
        ):
            result = await get_workflow(workflow_id=wf.id, user=_user(), db=db)

        assert result["workflow_json"] == _VALID_WF_JSON
        db.close()

# ===========================================================================
# update_workflow handler
# ===========================================================================

class TestUpdateWorkflow:
    """Tests for update_workflow handler."""

    @pytest.mark.asyncio
    async def test_update_draft_workflow_name(self):
        """Updates draft workflow name."""
        from core.api.routes.workflows import UpdateWorkflowRequest, update_workflow

        db = _make_session()
        wf = _make_workflow(db, name="Original", status="draft")
        req = UpdateWorkflowRequest(name="Updated Name")
        bt = _noop_background_tasks()

        async def _fake_getter(**kwargs):
            return db.query(Workflow).filter(Workflow.id == wf.id).first()

        with patch(
            "core.api.routes.workflows.get_owned_or_shared_resource", return_value=_fake_getter
        ):
            with patch("core.api.routes.workflows.log_audit"):
                result = await update_workflow(
                    workflow_id=wf.id, request=req, background_tasks=bt, user=_user(), db=db
                )

        assert result["name"] == "Updated Name"
        db.close()

    @pytest.mark.asyncio
    async def test_update_published_workflow_rejected(self):
        """Cannot update a published workflow."""
        from core.api.routes.workflows import UpdateWorkflowRequest, update_workflow

        db = _make_session()
        wf = _make_workflow(db, status="published")
        req = UpdateWorkflowRequest(name="Attempt Update")
        bt = _noop_background_tasks()

        async def _fake_getter(**kwargs):
            return db.query(Workflow).filter(Workflow.id == wf.id).first()

        with patch(
            "core.api.routes.workflows.get_owned_or_shared_resource", return_value=_fake_getter
        ):
            with pytest.raises(HTTPException) as exc:
                await update_workflow(
                    workflow_id=wf.id, request=req, background_tasks=bt, user=_user(), db=db
                )

        assert exc.value.status_code == 403
        db.close()

# ===========================================================================
# delete_workflow handler
# ===========================================================================

class TestDeleteWorkflow:
    """Tests for delete_workflow handler."""

    @pytest.mark.asyncio
    async def test_delete_draft_workflow(self):
        """Deletes draft workflow successfully."""
        from core.api.routes.workflows import delete_workflow

        db = _make_session()
        wf = _make_workflow(db, status="draft")
        bt = _noop_background_tasks()

        async def _fake_getter(**kwargs):
            return db.query(Workflow).filter(Workflow.id == wf.id).first()

        with patch("core.api.routes.workflows.get_owned_resource", return_value=_fake_getter):
            with patch("core.api.routes.workflows.log_audit"):
                result = await delete_workflow(
                    workflow_id=wf.id, background_tasks=bt, user=_user(), db=db
                )

        assert result is None  # 204 No Content
        assert db.query(Workflow).filter(Workflow.id == wf.id).first() is None
        db.close()

    @pytest.mark.asyncio
    async def test_delete_published_workflow_rejected(self):
        """Cannot delete a published workflow."""
        from core.api.routes.workflows import delete_workflow

        db = _make_session()
        wf = _make_workflow(db, status="published")
        bt = _noop_background_tasks()

        async def _fake_getter(**kwargs):
            return db.query(Workflow).filter(Workflow.id == wf.id).first()

        with patch("core.api.routes.workflows.get_owned_resource", return_value=_fake_getter):
            with pytest.raises(HTTPException) as exc:
                await delete_workflow(workflow_id=wf.id, background_tasks=bt, user=_user(), db=db)

        assert exc.value.status_code == 403
        db.close()

# ===========================================================================
# publish_workflow handler
# ===========================================================================

class TestPublishWorkflow:
    """Tests for publish_workflow handler."""

    @pytest.mark.asyncio
    async def test_publish_draft_workflow(self):
        """Publishing transitions workflow to published."""
        from core.api.routes.workflows import publish_workflow

        db = _make_session()
        wf = _make_workflow(db, status="draft")
        bt = _noop_background_tasks()

        async def _fake_getter(**kwargs):
            return db.query(Workflow).filter(Workflow.id == wf.id).first()

        with patch("core.api.routes.workflows.get_owned_resource", return_value=_fake_getter):
            with patch("core.api.routes.workflows.WorkflowSchema"):
                with patch("core.api.routes.workflows.log_audit"):
                    result = await publish_workflow(
                        workflow_id=wf.id, background_tasks=bt, user=_user(), db=db
                    )

        assert result["status"] == "published"
        assert result["published_at"] is not None
        db.close()

    @pytest.mark.asyncio
    async def test_publish_already_published_rejected(self):
        """Cannot publish already-published workflow."""
        from core.api.routes.workflows import publish_workflow

        db = _make_session()
        wf = _make_workflow(db, status="published")
        bt = _noop_background_tasks()

        async def _fake_getter(**kwargs):
            return db.query(Workflow).filter(Workflow.id == wf.id).first()

        with patch("core.api.routes.workflows.get_owned_resource", return_value=_fake_getter):
            with pytest.raises(HTTPException) as exc:
                await publish_workflow(workflow_id=wf.id, background_tasks=bt, user=_user(), db=db)

        assert exc.value.status_code == 403
        db.close()

    @pytest.mark.asyncio
    async def test_publish_invalid_schema_rejected(self):
        """Invalid workflow_json prevents publishing."""
        from core.api.routes.workflows import publish_workflow

        db = _make_session()
        wf = _make_workflow(db, status="draft")
        bt = _noop_background_tasks()

        async def _fake_getter(**kwargs):
            return db.query(Workflow).filter(Workflow.id == wf.id).first()

        with patch("core.api.routes.workflows.get_owned_resource", return_value=_fake_getter):
            with patch("core.api.routes.workflows.WorkflowSchema") as mock_schema:
                mock_schema.model_validate.side_effect = ValueError("bad")
                with pytest.raises(HTTPException) as exc:
                    await publish_workflow(
                        workflow_id=wf.id, background_tasks=bt, user=_user(), db=db
                    )

        assert exc.value.status_code == 400
        db.close()

# ===========================================================================
# archive_workflow handler
# ===========================================================================

class TestArchiveWorkflow:
    """Tests for archive_workflow handler."""

    @pytest.mark.asyncio
    async def test_archive_published_workflow(self):
        """Archives published workflow successfully."""
        from core.api.routes.workflows import archive_workflow

        db = _make_session()
        wf = _make_workflow(db, status="published")
        bt = _noop_background_tasks()

        async def _fake_getter(**kwargs):
            return db.query(Workflow).filter(Workflow.id == wf.id).first()

        with patch("core.api.routes.workflows.get_owned_resource", return_value=_fake_getter):
            with patch("core.api.routes.workflows.log_audit"):
                result = await archive_workflow(
                    workflow_id=wf.id, background_tasks=bt, user=_user(), db=db
                )

        assert result["status"] == "archived"
        db.close()

    @pytest.mark.asyncio
    async def test_archive_draft_rejected(self):
        """Cannot archive a draft workflow directly."""
        from core.api.routes.workflows import archive_workflow

        db = _make_session()
        wf = _make_workflow(db, status="draft")
        bt = _noop_background_tasks()

        async def _fake_getter(**kwargs):
            return db.query(Workflow).filter(Workflow.id == wf.id).first()

        with patch("core.api.routes.workflows.get_owned_resource", return_value=_fake_getter):
            with pytest.raises(HTTPException) as exc:
                await archive_workflow(workflow_id=wf.id, background_tasks=bt, user=_user(), db=db)

        assert exc.value.status_code == 400
        db.close()

# ===========================================================================
# clone_workflow handler
# ===========================================================================

class TestCloneWorkflow:
    """Tests for clone_workflow handler."""

    @pytest.mark.asyncio
    async def test_clone_workflow_success(self):
        """Cloning creates a new draft workflow."""
        from core.api.routes.workflows import CloneWorkflowRequest, clone_workflow

        db = _make_session()
        wf = _make_workflow(db, name="Original", status="published")
        req = CloneWorkflowRequest()

        async def _fake_getter(**kwargs):
            return db.query(Workflow).filter(Workflow.id == wf.id).first()

        with patch(
            "core.api.routes.workflows.get_owned_or_shared_resource", return_value=_fake_getter
        ):
            with patch("core.api.routes.workflows.log_audit"):
                result = await clone_workflow(workflow_id=wf.id, request=req, user=_user(), db=db)

        assert result["status"] == "draft"
        assert result["id"] != wf.id
        db.close()

    @pytest.mark.asyncio
    async def test_clone_workflow_custom_name(self):
        """Cloning with custom name uses provided name."""
        from core.api.routes.workflows import CloneWorkflowRequest, clone_workflow

        db = _make_session()
        wf = _make_workflow(db, name="Original", status="published")
        req = CloneWorkflowRequest(name="Cloned WF")

        async def _fake_getter(**kwargs):
            return db.query(Workflow).filter(Workflow.id == wf.id).first()

        with patch(
            "core.api.routes.workflows.get_owned_or_shared_resource", return_value=_fake_getter
        ):
            with patch("core.api.routes.workflows.log_audit"):
                result = await clone_workflow(workflow_id=wf.id, request=req, user=_user(), db=db)

        assert result["name"] == "Cloned WF"
        db.close()

    @pytest.mark.asyncio
    async def test_clone_workflow_default_name(self):
        """Cloning without name generates default copy name."""
        from core.api.routes.workflows import CloneWorkflowRequest, clone_workflow

        db = _make_session()
        wf = _make_workflow(db, name="My Workflow", status="published")
        req = CloneWorkflowRequest()

        async def _fake_getter(**kwargs):
            return db.query(Workflow).filter(Workflow.id == wf.id).first()

        with patch(
            "core.api.routes.workflows.get_owned_or_shared_resource", return_value=_fake_getter
        ):
            with patch("core.api.routes.workflows.log_audit"):
                result = await clone_workflow(workflow_id=wf.id, request=req, user=_user(), db=db)

        assert "copy" in result["name"].lower() or "My Workflow" in result["name"]
        db.close()

# ===========================================================================
# validate_workflow handler
# ===========================================================================

class TestValidateWorkflow:
    """Tests for validate_workflow handler."""

    @pytest.mark.asyncio
    async def test_validate_valid_workflow(self):
        """Valid workflow returns valid=True."""
        from core.api.routes.workflows import validate_workflow

        db = _make_session()
        wf = _make_workflow(db)

        async def _fake_getter(**kwargs):
            return db.query(Workflow).filter(Workflow.id == wf.id).first()

        # Mock the schema so it returns no invalid agents and no cycles
        mock_schema_instance = MagicMock()
        mock_schema_instance.validate_agents.return_value = []  # no invalid agents
        mock_schema_instance._find_cycle_nodes.return_value = []  # no cycles

        with patch(
            "core.api.routes.workflows.get_owned_or_shared_resource", return_value=_fake_getter
        ):
            with patch("core.api.routes.workflows.WorkflowSchema") as mock_schema_cls:
                mock_schema_cls.model_validate.return_value = mock_schema_instance
                result = await validate_workflow(workflow_id=wf.id, user=_user(), db=db)

        # validate_workflow returns a WorkflowValidationResult Pydantic model
        assert result.valid is True
        assert result.errors == []
        db.close()

    @pytest.mark.asyncio
    async def test_validate_invalid_workflow(self):
        """Invalid workflow returns valid=False with errors."""
        from core.api.routes.workflows import validate_workflow

        db = _make_session()
        wf = _make_workflow(db)

        async def _fake_getter(**kwargs):
            return db.query(Workflow).filter(Workflow.id == wf.id).first()

        with patch(
            "core.api.routes.workflows.get_owned_or_shared_resource", return_value=_fake_getter
        ):
            with patch("core.api.routes.workflows.WorkflowSchema") as mock_schema:
                mock_schema.model_validate.side_effect = ValueError("missing node connection")
                result = await validate_workflow(workflow_id=wf.id, user=_user(), db=db)

        # validate_workflow returns a WorkflowValidationResult Pydantic model
        assert result.valid is False
        assert len(result.errors) > 0
        db.close()

# ===========================================================================
# Helper functions
# ===========================================================================

class TestHelperFunctions:
    """Tests for module-level helper functions."""

    def test_increment_version(self):
        """increment_version increments minor version."""
        from core.api.routes.workflows import increment_version

        assert increment_version("1.0.0") == "1.1.0"
        assert increment_version("2.3.1") == "2.4.1"

    def test_increment_version_single_dot(self):
        """increment_version handles single dot."""
        from core.api.routes.workflows import increment_version

        assert increment_version("1.0") == "1.1"

    def test_increment_version_malformed(self):
        """increment_version handles malformed versions gracefully."""
        from core.api.routes.workflows import increment_version

        result = increment_version("invalid")
        assert result == "1.1.0"

    def test_workflow_to_summary_excludes_json(self):
        """workflow_to_summary excludes workflow_json."""
        from core.api.routes.workflows import workflow_to_summary

        wf = MagicMock()
        wf.id = 1
        wf.name = "Test"
        wf.description = "Desc"
        wf.version = "1.0.0"
        wf.status = "draft"
        wf.is_public = False
        wf.user_id = "user-1"
        wf.tags = ["tag1"]
        wf.execution_count = 5
        wf.created_at = datetime.now(UTC)
        wf.updated_at = datetime.now(UTC)

        result = workflow_to_summary(wf)
        assert "workflow_json" not in result
        assert result["name"] == "Test"
        assert result["execution_count"] == 5

    def test_workflow_to_response_includes_json(self):
        """workflow_to_response includes workflow_json."""
        from core.api.routes.workflows import workflow_to_response

        wf = MagicMock()
        wf.id = 1
        wf.name = "Test"
        wf.description = None
        wf.version = "1.0.0"
        wf.workflow_json = _VALID_WF_JSON
        wf.status = "draft"
        wf.is_public = False
        wf.user_id = "user-1"
        wf.tags = []
        wf.execution_count = 0
        wf.created_at = datetime.now(UTC)
        wf.updated_at = datetime.now(UTC)
        wf.published_at = None

        result = workflow_to_response(wf)
        assert "workflow_json" in result
        assert result["workflow_json"] == _VALID_WF_JSON
