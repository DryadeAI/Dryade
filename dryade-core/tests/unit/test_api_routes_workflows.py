"""Tests for core/api/routes/workflows.py -- Workflow CRUD and lifecycle routes.

Tests route handlers directly (no TestClient), mocking DB sessions, auth, and
ownership helpers. Auth is provided via the standard user dict pattern.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TEST_USER = {"sub": "test-user-001", "email": "test@example.com", "role": "user"}
_TEST_ADMIN = {"sub": "admin-001", "email": "admin@example.com", "role": "admin"}

_VALID_WORKFLOW_JSON = {
    "version": "1.0.0",
    "nodes": [
        {"id": "start_1", "type": "start", "data": {"label": "Start"}},
        {"id": "end_1", "type": "end", "data": {"label": "End"}},
    ],
    "edges": [
        {"id": "e1", "source": "start_1", "target": "end_1"},
    ],
}

def _make_workflow(
    workflow_id=1,
    user_id="test-user-001",
    name="Test Workflow",
    status="draft",
    is_public=False,
    tags=None,
):
    w = MagicMock()
    w.id = workflow_id
    w.user_id = user_id
    w.name = name
    w.description = "A test workflow"
    w.version = "1.0.0"
    w.workflow_json = _VALID_WORKFLOW_JSON
    w.status = status
    w.is_public = is_public
    w.tags = tags or []
    w.execution_count = 0
    w.created_at = datetime(2026, 1, 13, 10, 0, 0, tzinfo=timezone.utc)
    w.updated_at = datetime(2026, 1, 13, 10, 0, 0, tzinfo=timezone.utc)
    w.published_at = None
    return w

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

def _make_background_tasks():
    bt = MagicMock()
    bt.add_task = MagicMock()
    return bt

# ===========================================================================
# create_workflow
# ===========================================================================
class TestCreateWorkflow:
    """Tests for POST /workflows."""

    @pytest.mark.asyncio
    async def test_create_valid_workflow(self):
        """Valid workflow schema creates workflow in draft status."""
        from core.api.routes.workflows import CreateWorkflowRequest, create_workflow

        req = CreateWorkflowRequest(
            name="My Workflow",
            workflow_json=_VALID_WORKFLOW_JSON,
            tags=["data"],
        )
        db = _make_db_session()

        def fake_refresh(obj):
            obj.id = 42
            obj.created_at = datetime(2026, 1, 13, 10, 0, 0, tzinfo=timezone.utc)
            obj.updated_at = datetime(2026, 1, 13, 10, 0, 0, tzinfo=timezone.utc)
            obj.published_at = None

        db.refresh.side_effect = fake_refresh
        bt = _make_background_tasks()

        with patch("core.api.routes.workflows.log_audit") as _:
            result = await create_workflow(request=req, background_tasks=bt, user=_TEST_USER, db=db)

        db.add.assert_called_once()
        db.commit.assert_called_once()
        assert result["name"] == "My Workflow"
        assert result["status"] == "draft"

    @pytest.mark.asyncio
    async def test_create_invalid_schema_raises_400(self):
        """Workflow JSON that fails schema validation raises 400."""
        from fastapi import HTTPException

        from core.api.routes.workflows import CreateWorkflowRequest, create_workflow

        # Missing start node -- WorkflowSchema will reject this
        bad_json = {
            "version": "1.0.0",
            "nodes": [{"id": "task_1", "type": "task", "data": {"label": "Task"}}],
            "edges": [],
        }
        req = CreateWorkflowRequest(name="Bad Workflow", workflow_json=bad_json)
        db = _make_db_session()
        bt = _make_background_tasks()

        with pytest.raises(HTTPException) as exc_info:
            await create_workflow(request=req, background_tasks=bt, user=_TEST_USER, db=db)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_create_sets_user_id_from_token(self):
        """User ID is taken from the auth token, not the request body."""
        from core.api.routes.workflows import CreateWorkflowRequest, create_workflow

        req = CreateWorkflowRequest(
            name="My Workflow",
            workflow_json=_VALID_WORKFLOW_JSON,
            user_id="ignored-user-id",  # should be overridden
        )
        db = _make_db_session()

        added_objects = []
        db.add.side_effect = lambda obj: added_objects.append(obj)

        def fake_refresh(obj):
            obj.id = 1
            obj.created_at = datetime(2026, 1, 13, 10, 0, 0, tzinfo=timezone.utc)
            obj.updated_at = datetime(2026, 1, 13, 10, 0, 0, tzinfo=timezone.utc)
            obj.published_at = None

        db.refresh.side_effect = fake_refresh
        bt = _make_background_tasks()

        with patch("core.api.routes.workflows.log_audit"):
            await create_workflow(request=req, background_tasks=bt, user=_TEST_USER, db=db)

        # The object added to db should have user_id from the token
        assert len(added_objects) == 1
        assert added_objects[0].user_id == "test-user-001"

# ===========================================================================
# list_workflows
# ===========================================================================
class TestListWorkflows:
    """Tests for GET /workflows."""

    @pytest.mark.asyncio
    async def test_list_empty(self):
        """No workflows -- should return empty list."""
        db = _make_db_session()
        mock_query = MagicMock()
        mock_query.count.return_value = 0
        mock_query.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []
        mock_query.filter.return_value = mock_query

        with patch(
            "core.api.routes.workflows.filter_by_owner_or_shared",
            return_value=AsyncMock(return_value=mock_query),
        ):
            from core.api.routes.workflows import list_workflows

            result = await list_workflows(status=None, tags=None, offset=0, limit=50, user=_TEST_USER, db=db)

        assert result["total"] == 0
        assert result["workflows"] == []

    @pytest.mark.asyncio
    async def test_list_with_workflows(self):
        """Workflows present -- should return summaries."""
        w = _make_workflow()
        db = _make_db_session()

        mock_query = MagicMock()
        mock_query.count.return_value = 1
        mock_query.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [
            w
        ]
        mock_query.filter.return_value = mock_query

        with patch(
            "core.api.routes.workflows.filter_by_owner_or_shared",
            return_value=AsyncMock(return_value=mock_query),
        ):
            from core.api.routes.workflows import list_workflows

            result = await list_workflows(status=None, tags=None, offset=0, limit=50, user=_TEST_USER, db=db)

        assert result["total"] == 1
        assert len(result["workflows"]) == 1
        assert result["workflows"][0]["name"] == "Test Workflow"

    @pytest.mark.asyncio
    async def test_list_with_status_filter(self):
        """Status filter is applied to query."""
        db = _make_db_session()
        mock_query = MagicMock()
        mock_query.count.return_value = 0
        mock_query.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []
        mock_query.filter.return_value = mock_query

        with patch(
            "core.api.routes.workflows.filter_by_owner_or_shared",
            return_value=AsyncMock(return_value=mock_query),
        ):
            from core.api.routes.workflows import list_workflows

            result = await list_workflows(status="published", tags=None, offset=0, limit=50, user=_TEST_USER, db=db)

        # filter should have been called for status
        mock_query.filter.assert_called()
        assert result["total"] == 0

# ===========================================================================
# get_workflow
# ===========================================================================
class TestGetWorkflow:
    """Tests for GET /workflows/{workflow_id}."""

    @pytest.mark.asyncio
    async def test_get_existing_workflow(self):
        """Owner can retrieve their workflow."""
        w = _make_workflow(user_id="test-user-001")
        db = _make_db_session()

        with patch(
            "core.api.routes.workflows.get_owned_or_shared_resource",
            return_value=AsyncMock(return_value=w),
        ):
            from core.api.routes.workflows import get_workflow

            result = await get_workflow(workflow_id=1, user=_TEST_USER, db=db)

        assert result["id"] == 1
        assert result["name"] == "Test Workflow"

    @pytest.mark.asyncio
    async def test_get_not_found_raises_404(self):
        """Non-existent workflow raises 404."""
        from fastapi import HTTPException

        with patch(
            "core.api.routes.workflows.get_owned_or_shared_resource",
            return_value=AsyncMock(side_effect=HTTPException(status_code=404, detail="Not found")),
        ):
            from core.api.routes.workflows import get_workflow

            with pytest.raises(HTTPException) as exc_info:
                await get_workflow(workflow_id=999, user=_TEST_USER, db=_make_db_session())
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_other_users_private_workflow_raises_403(self):
        """Accessing another user's private workflow raises 403."""
        from fastapi import HTTPException

        with patch(
            "core.api.routes.workflows.get_owned_or_shared_resource",
            return_value=AsyncMock(
                side_effect=HTTPException(status_code=403, detail="Access denied")
            ),
        ):
            from core.api.routes.workflows import get_workflow

            with pytest.raises(HTTPException) as exc_info:
                await get_workflow(workflow_id=1, user=_TEST_USER, db=_make_db_session())
        assert exc_info.value.status_code == 403

# ===========================================================================
# update_workflow
# ===========================================================================
class TestUpdateWorkflow:
    """Tests for PUT /workflows/{workflow_id}."""

    @pytest.mark.asyncio
    async def test_update_draft_workflow(self):
        """Updating a draft workflow succeeds."""
        w = _make_workflow(status="draft")
        db = _make_db_session()
        bt = _make_background_tasks()

        with patch(
            "core.api.routes.workflows.get_owned_or_shared_resource",
            return_value=AsyncMock(return_value=w),
        ):
            from core.api.routes.workflows import UpdateWorkflowRequest, update_workflow

            req = UpdateWorkflowRequest(name="Updated Name")
            result = await update_workflow(
                workflow_id=1, request=req, background_tasks=bt, user=_TEST_USER, db=db
            )

        assert w.name == "Updated Name"
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_published_workflow_raises_403(self):
        """Published workflows cannot be modified."""
        from fastapi import HTTPException

        w = _make_workflow(status="published")
        db = _make_db_session()
        bt = _make_background_tasks()

        with patch(
            "core.api.routes.workflows.get_owned_or_shared_resource",
            return_value=AsyncMock(return_value=w),
        ):
            from core.api.routes.workflows import UpdateWorkflowRequest, update_workflow

            with pytest.raises(HTTPException) as exc_info:
                await update_workflow(
                    workflow_id=1,
                    request=UpdateWorkflowRequest(name="X"),
                    background_tasks=bt,
                    user=_TEST_USER,
                    db=db,
                )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_update_with_invalid_workflow_json_raises_400(self):
        """Providing invalid workflow_json raises 400."""
        from fastapi import HTTPException

        w = _make_workflow(status="draft")
        db = _make_db_session()
        bt = _make_background_tasks()

        bad_json = {"version": "1.0.0", "nodes": [], "edges": []}

        with patch(
            "core.api.routes.workflows.get_owned_or_shared_resource",
            return_value=AsyncMock(return_value=w),
        ):
            from core.api.routes.workflows import UpdateWorkflowRequest, update_workflow

            with pytest.raises(HTTPException) as exc_info:
                await update_workflow(
                    workflow_id=1,
                    request=UpdateWorkflowRequest(workflow_json=bad_json),
                    background_tasks=bt,
                    user=_TEST_USER,
                    db=db,
                )
        assert exc_info.value.status_code == 400

# ===========================================================================
# delete_workflow
# ===========================================================================
class TestDeleteWorkflow:
    """Tests for DELETE /workflows/{workflow_id}."""

    @pytest.mark.asyncio
    async def test_delete_draft_workflow(self):
        """Draft workflow can be deleted by owner."""
        w = _make_workflow(status="draft")
        db = _make_db_session()
        bt = _make_background_tasks()

        with patch(
            "core.api.routes.workflows.get_owned_resource",
            return_value=AsyncMock(return_value=w),
        ):
            from core.api.routes.workflows import delete_workflow

            await delete_workflow(workflow_id=1, background_tasks=bt, user=_TEST_USER, db=db)

        db.delete.assert_called_once_with(w)
        db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_delete_published_workflow_raises_403(self):
        """Published workflows cannot be deleted."""
        from fastapi import HTTPException

        w = _make_workflow(status="published")
        db = _make_db_session()
        bt = _make_background_tasks()

        with patch(
            "core.api.routes.workflows.get_owned_resource",
            return_value=AsyncMock(return_value=w),
        ):
            from core.api.routes.workflows import delete_workflow

            with pytest.raises(HTTPException) as exc_info:
                await delete_workflow(workflow_id=1, background_tasks=bt, user=_TEST_USER, db=db)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_not_found_raises_404(self):
        """Non-existent workflow raises 404."""
        from fastapi import HTTPException

        bt = _make_background_tasks()

        with patch(
            "core.api.routes.workflows.get_owned_resource",
            return_value=AsyncMock(side_effect=HTTPException(status_code=404, detail="Not found")),
        ):
            from core.api.routes.workflows import delete_workflow

            with pytest.raises(HTTPException) as exc_info:
                await delete_workflow(
                    workflow_id=999, background_tasks=bt, user=_TEST_USER, db=_make_db_session()
                )
        assert exc_info.value.status_code == 404

# ===========================================================================
# publish_workflow
# ===========================================================================
class TestPublishWorkflow:
    """Tests for POST /workflows/{workflow_id}/publish."""

    @pytest.mark.asyncio
    async def test_publish_draft_workflow(self):
        """Draft workflow can be published."""
        w = _make_workflow(status="draft")
        db = _make_db_session()
        bt = _make_background_tasks()

        with patch(
            "core.api.routes.workflows.get_owned_resource",
            return_value=AsyncMock(return_value=w),
        ):
            from core.api.routes.workflows import publish_workflow

            result = await publish_workflow(
                workflow_id=1, background_tasks=bt, user=_TEST_USER, db=db
            )

        assert w.status == "published"
        db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_publish_already_published_raises_403(self):
        """Cannot publish an already-published workflow."""
        from fastapi import HTTPException

        w = _make_workflow(status="published")
        db = _make_db_session()
        bt = _make_background_tasks()

        with patch(
            "core.api.routes.workflows.get_owned_resource",
            return_value=AsyncMock(return_value=w),
        ):
            from core.api.routes.workflows import publish_workflow

            with pytest.raises(HTTPException) as exc_info:
                await publish_workflow(workflow_id=1, background_tasks=bt, user=_TEST_USER, db=db)
        assert exc_info.value.status_code == 403

# ===========================================================================
# validate_workflow
# ===========================================================================
class TestValidateWorkflow:
    """Tests for POST /workflows/{workflow_id}/validate."""

    @pytest.mark.asyncio
    async def test_validate_valid_workflow(self):
        """Valid workflow returns valid=True."""
        w = _make_workflow()
        db = _make_db_session()

        with patch(
            "core.api.routes.workflows.get_owned_or_shared_resource",
            return_value=AsyncMock(return_value=w),
        ):
            from core.api.routes.workflows import validate_workflow

            result = await validate_workflow(workflow_id=1, user=_TEST_USER, db=db)

        assert result.valid is True
        assert result.errors == []

    @pytest.mark.asyncio
    async def test_validate_not_found_raises_404(self):
        """Non-existent workflow raises 404."""
        from fastapi import HTTPException

        with patch(
            "core.api.routes.workflows.get_owned_or_shared_resource",
            return_value=AsyncMock(side_effect=HTTPException(status_code=404, detail="Not found")),
        ):
            from core.api.routes.workflows import validate_workflow

            with pytest.raises(HTTPException) as exc_info:
                await validate_workflow(workflow_id=999, user=_TEST_USER, db=_make_db_session())
        assert exc_info.value.status_code == 404

# ===========================================================================
# clone_workflow
# ===========================================================================
class TestCloneWorkflow:
    """Tests for POST /workflows/{workflow_id}/clone."""

    @pytest.mark.asyncio
    async def test_clone_workflow(self):
        """Cloning a workflow creates a new draft with incremented version."""
        original = _make_workflow(workflow_id=1, name="Original", status="published")
        original.tags = []
        db = _make_db_session()

        # clone_workflow queries Workflow directly via db.query(Workflow).filter(...).first()
        q = MagicMock()
        q.filter.return_value.first.return_value = original
        db.query.return_value = q

        def fake_refresh(obj):
            obj.id = 2
            obj.created_at = datetime(2026, 1, 13, 10, 0, 0, tzinfo=timezone.utc)
            obj.updated_at = datetime(2026, 1, 13, 10, 0, 0, tzinfo=timezone.utc)
            obj.published_at = None

        db.refresh.side_effect = fake_refresh

        from core.api.routes.workflows import CloneWorkflowRequest, clone_workflow

        req = CloneWorkflowRequest(name="Clone of Original")
        result = await clone_workflow(workflow_id=1, request=req, user=_TEST_USER, db=db)

        db.add.assert_called_once()
        db.commit.assert_called()
        assert result["status"] == "draft"

    @pytest.mark.asyncio
    async def test_clone_not_found_raises_404(self):
        """Cloning non-existent workflow raises 404."""
        from fastapi import HTTPException

        db = _make_db_session()
        q = MagicMock()
        q.filter.return_value.first.return_value = None
        db.query.return_value = q

        from core.api.routes.workflows import CloneWorkflowRequest, clone_workflow

        with pytest.raises(HTTPException) as exc_info:
            await clone_workflow(
                workflow_id=999,
                request=CloneWorkflowRequest(),
                user=_TEST_USER,
                db=db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_clone_private_workflow_of_other_user_raises_403(self):
        """Cannot clone a private workflow owned by another user."""
        from fastapi import HTTPException

        w = _make_workflow(workflow_id=1, user_id="other-user", is_public=False)
        w.tags = []
        db = _make_db_session()
        q = MagicMock()
        q.filter.return_value.first.return_value = w
        db.query.return_value = q

        from core.api.routes.workflows import CloneWorkflowRequest, clone_workflow

        with pytest.raises(HTTPException) as exc_info:
            await clone_workflow(
                workflow_id=1,
                request=CloneWorkflowRequest(),
                user=_TEST_USER,
                db=db,
            )
        assert exc_info.value.status_code == 403

# ===========================================================================
# archive_workflow
# ===========================================================================
class TestArchiveWorkflow:
    """Tests for POST /workflows/{workflow_id}/archive."""

    @pytest.mark.asyncio
    async def test_archive_published_workflow(self):
        """Published workflow can be archived."""
        w = _make_workflow(status="published")
        db = _make_db_session()
        bt = _make_background_tasks()

        with patch(
            "core.api.routes.workflows.get_owned_resource",
            return_value=AsyncMock(return_value=w),
        ):
            from core.api.routes.workflows import archive_workflow

            result = await archive_workflow(
                workflow_id=1, background_tasks=bt, user=_TEST_USER, db=db
            )

        assert w.status == "archived"
        db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_archive_draft_raises_400(self):
        """Draft workflows cannot be archived -- raises 400."""
        from fastapi import HTTPException

        w = _make_workflow(status="draft")
        db = _make_db_session()
        bt = _make_background_tasks()

        with patch(
            "core.api.routes.workflows.get_owned_resource",
            return_value=AsyncMock(return_value=w),
        ):
            from core.api.routes.workflows import archive_workflow

            with pytest.raises(HTTPException) as exc_info:
                await archive_workflow(workflow_id=1, background_tasks=bt, user=_TEST_USER, db=db)
        assert exc_info.value.status_code == 400

# ===========================================================================
# increment_version (helper function)
# ===========================================================================
class TestIncrementVersion:
    """Tests for the increment_version helper."""

    def test_increment_minor(self):
        """1.0.0 -> 1.1.0."""
        from core.api.routes.workflows import increment_version

        assert increment_version("1.0.0") == "1.1.0"

    def test_increment_minor_from_nonzero(self):
        """1.3.5 -> 1.4.5."""
        from core.api.routes.workflows import increment_version

        assert increment_version("1.3.5") == "1.4.5"

    def test_bad_version_falls_back(self):
        """Non-semver falls back to 1.1.0."""
        from core.api.routes.workflows import increment_version

        result = increment_version("not-a-version")
        assert result == "1.1.0"
