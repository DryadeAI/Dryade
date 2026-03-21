"""Tests for auth module coverage gaps.

Covers:
- core.auth.ownership (get_owned_resource, filter_by_owner, etc.)
- core.auth.sharing (SharingService)
- core.auth.dependencies (get_current_user, require_role, get_current_user_db)
- core.auth.audit (log_audit, log_audit_sync)
"""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

# ---------------------------------------------------------------------------
# core.auth.dependencies tests
# ---------------------------------------------------------------------------

class TestGetCurrentUser:
    """Tests for get_current_user dependency."""

    @pytest.mark.asyncio
    async def test_valid_user(self):
        """Returns user dict when request.state.user is set."""
        from core.auth.dependencies import get_current_user

        request = MagicMock()
        request.state.user = {"sub": "user-1", "role": "member", "email": "a@b.com"}
        result = await get_current_user(request)
        assert result["sub"] == "user-1"

    @pytest.mark.asyncio
    async def test_no_user_raises_401(self):
        """Raises 401 when request.state.user is None."""
        from core.auth.dependencies import get_current_user

        request = MagicMock()
        request.state.user = None
        with pytest.raises(HTTPException) as exc:
            await get_current_user(request)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_user_attribute(self):
        """Raises 401 when request.state has no user attr."""
        from core.auth.dependencies import get_current_user

        request = MagicMock()
        # delattr to remove user
        del request.state.user
        request.state.user = None
        with pytest.raises(HTTPException) as exc:
            await get_current_user(request)
        assert exc.value.status_code == 401

class TestRequireRole:
    """Tests for require_role dependency factory."""

    @pytest.mark.asyncio
    async def test_allowed_role(self):
        """User with matching role passes."""
        from core.auth.dependencies import require_role

        checker = require_role(["admin"])
        user = {"sub": "u1", "role": "admin"}
        result = await checker(user=user)
        assert result["sub"] == "u1"

    @pytest.mark.asyncio
    async def test_denied_role(self):
        """User with non-matching role raises 403."""
        from core.auth.dependencies import require_role

        checker = require_role(["admin"])
        user = {"sub": "u2", "role": "member"}
        with pytest.raises(HTTPException) as exc:
            await checker(user=user)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_multiple_allowed_roles(self):
        """User with any of the allowed roles passes."""
        from core.auth.dependencies import require_role

        checker = require_role(["admin", "member"])
        user = {"sub": "u3", "role": "member"}
        result = await checker(user=user)
        assert result["role"] == "member"

class TestRequireAdmin:
    """Tests for require_admin convenience dependency."""

    @pytest.mark.asyncio
    async def test_admin_passes(self):
        """Admin user passes require_admin."""
        from core.auth.dependencies import require_admin

        user = {"sub": "u1", "role": "admin"}
        result = await require_admin(user=user)
        assert result["role"] == "admin"

    @pytest.mark.asyncio
    async def test_member_fails(self):
        """Non-admin user fails require_admin."""
        from core.auth.dependencies import require_admin

        user = {"sub": "u2", "role": "member"}
        with pytest.raises(HTTPException) as exc:
            await require_admin(user=user)
        assert exc.value.status_code == 403

class TestGetCurrentUserDb:
    """Tests for get_current_user_db dependency."""

    @pytest.mark.asyncio
    async def test_user_found(self):
        """Returns User model when found in database."""
        from core.auth.dependencies import get_current_user_db

        mock_user_model = MagicMock()
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user_model

        user = {"sub": "u1", "role": "member"}
        result = await get_current_user_db(user=user, db=mock_db)
        assert result is mock_user_model

    @pytest.mark.asyncio
    async def test_user_not_found(self):
        """Raises 404 when user not in database."""
        from core.auth.dependencies import get_current_user_db

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        user = {"sub": "nonexistent", "role": "member"}
        with pytest.raises(HTTPException) as exc:
            await get_current_user_db(user=user, db=mock_db)
        assert exc.value.status_code == 404

# ---------------------------------------------------------------------------
# core.auth.sharing tests
# ---------------------------------------------------------------------------

class TestSharingService:
    """Tests for SharingService."""

    def _make_service(self):
        from core.auth.sharing import SharingService

        mock_db = MagicMock()
        return SharingService(mock_db), mock_db

    def test_share_invalid_resource_type(self):
        """share() raises 400 for non-shareable resource type."""
        svc, _ = self._make_service()
        with pytest.raises(HTTPException) as exc:
            svc.share("conversation", 1, "owner", "target")
        assert exc.value.status_code == 400
        assert "Cannot share" in exc.value.detail

    def test_share_invalid_permission(self):
        """share() raises 400 for invalid permission."""
        svc, _ = self._make_service()
        with pytest.raises(HTTPException) as exc:
            svc.share("workflow", 1, "owner", "target", permission="admin")
        assert exc.value.status_code == 400
        assert "Permission" in exc.value.detail

    def test_share_target_user_not_found(self):
        """share() raises 404 when target user doesn't exist."""
        svc, db = self._make_service()
        db.query.return_value.filter.return_value.first.return_value = None
        with pytest.raises(HTTPException) as exc:
            svc.share("workflow", 1, "owner", "target")
        assert exc.value.status_code == 404

    def test_share_creates_new(self):
        """share() creates new ResourceShare when none exists."""
        svc, db = self._make_service()
        # First query: User exists
        mock_user = MagicMock()
        # We need to handle multiple .query() calls
        query_calls = []

        def side_effect(model):
            q = MagicMock()
            query_calls.append(model)
            if len(query_calls) == 1:
                # User query
                q.filter.return_value.first.return_value = mock_user
            elif len(query_calls) == 2:
                # ResourceShare query - no existing share
                q.filter.return_value.first.return_value = None
            return q

        db.query.side_effect = side_effect
        result = svc.share("workflow", 1, "owner", "target", "view")
        db.add.assert_called_once()
        db.commit.assert_called()

    def test_share_updates_existing(self):
        """share() updates permission when share already exists."""
        svc, db = self._make_service()
        mock_user = MagicMock()
        mock_existing_share = MagicMock()
        mock_existing_share.permission = "view"
        query_calls = []

        def side_effect(model):
            q = MagicMock()
            query_calls.append(model)
            if len(query_calls) == 1:
                q.filter.return_value.first.return_value = mock_user
            elif len(query_calls) == 2:
                q.filter.return_value.first.return_value = mock_existing_share
            return q

        db.query.side_effect = side_effect
        result = svc.share("workflow", 1, "owner", "target", "edit")
        assert mock_existing_share.permission == "edit"
        db.commit.assert_called()

    def test_unshare_existing(self):
        """unshare() returns True when share deleted."""
        svc, db = self._make_service()
        db.query.return_value.filter.return_value.delete.return_value = 1
        result = svc.unshare("workflow", 1, "user-1")
        assert result is True
        db.commit.assert_called()

    def test_unshare_not_found(self):
        """unshare() returns False when no share found."""
        svc, db = self._make_service()
        db.query.return_value.filter.return_value.delete.return_value = 0
        result = svc.unshare("workflow", 1, "user-1")
        assert result is False

    def test_get_permission_found(self):
        """get_permission() returns permission when share exists."""
        svc, db = self._make_service()
        mock_share = MagicMock()
        mock_share.permission = "edit"
        db.query.return_value.filter.return_value.first.return_value = mock_share
        result = svc.get_permission("workflow", 1, "user-1")
        assert result == "edit"

    def test_get_permission_not_found(self):
        """get_permission() returns None when no share."""
        svc, db = self._make_service()
        db.query.return_value.filter.return_value.first.return_value = None
        result = svc.get_permission("workflow", 1, "user-1")
        assert result is None

    def test_get_shared_users(self):
        """get_shared_users() returns list of user/permission dicts."""
        svc, db = self._make_service()
        mock_share = MagicMock()
        mock_share.user_id = "user-1"
        mock_share.permission = "view"
        mock_share.shared_by = "owner"
        db.query.return_value.filter.return_value.all.return_value = [mock_share]
        result = svc.get_shared_users("workflow", 1)
        assert len(result) == 1
        assert result[0]["user_id"] == "user-1"
        assert result[0]["permission"] == "view"
        assert result[0]["shared_by"] == "owner"

    def test_get_shared_users_empty(self):
        """get_shared_users() returns empty list when no shares."""
        svc, db = self._make_service()
        db.query.return_value.filter.return_value.all.return_value = []
        result = svc.get_shared_users("workflow", 1)
        assert result == []

# ---------------------------------------------------------------------------
# core.auth.ownership tests
# ---------------------------------------------------------------------------

class TestGetOwnedResource:
    """Tests for get_owned_resource dependency factory."""

    @pytest.mark.asyncio
    async def test_admin_access(self):
        """Admin can access any resource."""
        from core.auth.ownership import get_owned_resource

        mock_model = MagicMock()
        mock_model.__name__ = "TestModel"
        mock_resource = MagicMock()
        mock_resource.user_id = "other-user"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_resource

        dep = get_owned_resource(mock_model)
        user = {"sub": "admin-1", "role": "admin"}
        result = await dep(resource_id=1, user=user, db=mock_db)
        assert result is mock_resource

    @pytest.mark.asyncio
    async def test_owner_access(self):
        """Owner can access their own resource."""
        from core.auth.ownership import get_owned_resource

        mock_model = MagicMock()
        mock_model.__name__ = "TestModel"
        mock_resource = MagicMock()
        mock_resource.user_id = "user-1"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_resource

        dep = get_owned_resource(mock_model)
        user = {"sub": "user-1", "role": "member"}
        result = await dep(resource_id=1, user=user, db=mock_db)
        assert result is mock_resource

    @pytest.mark.asyncio
    async def test_not_found(self):
        """Raises 404 when resource not found."""
        from core.auth.ownership import get_owned_resource

        mock_model = MagicMock()
        mock_model.__name__ = "TestModel"
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        dep = get_owned_resource(mock_model)
        with pytest.raises(HTTPException) as exc:
            await dep(resource_id=999, user={"sub": "u1", "role": "member"}, db=mock_db)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_access_denied(self):
        """Raises 403 when non-owner non-admin accesses resource."""
        from core.auth.ownership import get_owned_resource

        mock_model = MagicMock()
        mock_model.__name__ = "TestModel"
        mock_resource = MagicMock()
        mock_resource.user_id = "other-user"
        mock_resource.is_public = False

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_resource

        dep = get_owned_resource(mock_model)
        with pytest.raises(HTTPException) as exc:
            await dep(resource_id=1, user={"sub": "user-1", "role": "member"}, db=mock_db)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_public_access(self):
        """Public resources are accessible to non-owners."""
        from core.auth.ownership import get_owned_resource

        mock_model = MagicMock()
        mock_model.__name__ = "TestModel"
        mock_resource = MagicMock()
        mock_resource.user_id = "other-user"
        mock_resource.is_public = True

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_resource

        dep = get_owned_resource(mock_model)
        result = await dep(resource_id=1, user={"sub": "user-1", "role": "member"}, db=mock_db)
        assert result is mock_resource

class TestFilterByOwner:
    """Tests for filter_by_owner dependency factory."""

    @pytest.mark.asyncio
    async def test_admin_sees_all(self):
        """Admin gets unfiltered query."""
        from core.auth.ownership import filter_by_owner

        mock_model = MagicMock()
        mock_query = MagicMock()
        mock_db = MagicMock()
        mock_db.query.return_value = mock_query

        dep = filter_by_owner(mock_model)
        result = await dep(user={"sub": "admin-1", "role": "admin"}, db=mock_db)
        assert result is mock_query

    @pytest.mark.asyncio
    async def test_member_filtered(self):
        """Non-admin gets filtered query."""
        from core.auth.ownership import filter_by_owner

        mock_model = MagicMock()
        mock_model.user_id = "user-1"
        # Remove is_public attribute
        del mock_model.is_public
        mock_query = MagicMock()
        mock_db = MagicMock()
        mock_db.query.return_value = mock_query

        dep = filter_by_owner(mock_model)
        result = await dep(user={"sub": "user-1", "role": "member"}, db=mock_db)
        # filter was called on the query
        mock_query.filter.assert_called_once()

# ---------------------------------------------------------------------------
# core.auth.audit tests
# ---------------------------------------------------------------------------

class TestLogAudit:
    """Tests for log_audit and log_audit_sync functions."""

    @pytest.mark.asyncio
    async def test_log_audit_success(self):
        """log_audit creates AuditLog entry via its own session."""
        from unittest.mock import patch

        from core.auth.audit import log_audit

        mock_session = MagicMock()
        mock_session.execute.return_value.scalar.return_value = 999

        with patch("core.database.session.get_session") as mock_get_session:
            mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

            await log_audit(
                db=MagicMock(),
                user_id="user-1",
                action="login",
                resource_type="session",
                resource_id="123",
                ip_address="127.0.0.1",
                metadata={"browser": "chrome"},
            )
        mock_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_audit_no_optional_fields(self):
        """log_audit works with minimal fields."""
        from unittest.mock import patch

        from core.auth.audit import log_audit

        mock_session = MagicMock()
        mock_session.execute.return_value.scalar.return_value = 999

        with patch("core.database.session.get_session") as mock_get_session:
            mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

            await log_audit(db=MagicMock(), user_id="user-1", action="create")
        mock_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_audit_exception_swallowed(self):
        """log_audit does not raise on database error."""
        from core.auth.audit import log_audit

        mock_db = MagicMock()
        mock_db.add.side_effect = RuntimeError("db error")
        # Should not raise
        await log_audit(db=mock_db, user_id="user-1", action="delete")

    def test_log_audit_sync_success(self):
        """log_audit_sync creates AuditLog entry via its own session."""
        from unittest.mock import patch

        from core.auth.audit import log_audit_sync

        mock_session = MagicMock()
        mock_session.execute.return_value.scalar.return_value = 999

        with patch("core.database.session.get_session") as mock_get_session:
            mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

            log_audit_sync(
                db=MagicMock(),
                user_id="user-1",
                action="update",
                resource_type="workflow",
                resource_id="42",
            )
        mock_session.add.assert_called_once()

    def test_log_audit_sync_exception_swallowed(self):
        """log_audit_sync does not raise on database error."""
        from core.auth.audit import log_audit_sync

        mock_db = MagicMock()
        mock_db.commit.side_effect = RuntimeError("db error")
        # Should not raise
        log_audit_sync(db=mock_db, user_id="user-1", action="share")
