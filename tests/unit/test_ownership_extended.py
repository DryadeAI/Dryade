"""Extended tests for core/auth/ownership.py -- Resource ownership dependencies.

Complements test_auth_coverage.py by covering the remaining functions:
- get_owned_or_shared_resource (all branches)
- filter_by_owner_or_shared (all branches)
- filter_by_owner with is_public model

The existing test_auth_coverage.py covers get_owned_resource and filter_by_owner
(basic paths). This file targets the sharing-aware variants and edge cases
to bring ownership.py above 60% coverage.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_model(name="TestModel", has_is_public=True):
    """Build a mock SQLAlchemy model class."""
    model = MagicMock()
    model.__name__ = name

    # Column comparators: __eq__ must return a MagicMock (not bool) so that
    # SQLAlchemy-style | chaining works in filter expressions during tests.
    col_id = MagicMock()
    col_id.__eq__ = lambda self, other: MagicMock()
    col_id.__or__ = lambda self, other: MagicMock()
    model.id = col_id

    col_uid = MagicMock()
    col_uid.__eq__ = lambda self, other: MagicMock()
    col_uid.__or__ = lambda self, other: MagicMock()
    model.user_id = col_uid

    if has_is_public:
        col_pub = MagicMock()
        col_pub.__eq__ = lambda self, other: MagicMock()
        col_pub.__or__ = lambda self, other: MagicMock()
        model.is_public = col_pub
    else:
        # Remove is_public so hasattr returns False
        del model.is_public
    return model

def _mock_resource(user_id="owner-1", is_public=False, has_is_public=True):
    """Build a mock resource instance."""
    resource = MagicMock()
    resource.user_id = user_id
    if has_is_public:
        resource.is_public = is_public
    else:
        del resource.is_public
    return resource

def _user(sub="user-1", role="member"):
    return {"sub": sub, "role": role}

def _mock_db(resource=None):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = resource
    return db

# ===========================================================================
# get_owned_or_shared_resource tests
# ===========================================================================

class TestGetOwnedOrSharedResource:
    """Tests for get_owned_or_shared_resource dependency factory."""

    async def test_admin_access(self):
        """Admin can access any resource regardless of ownership or sharing."""
        from core.auth.ownership import get_owned_or_shared_resource

        model = _mock_model()
        resource = _mock_resource(user_id="other-user")
        db = _mock_db(resource)

        dep = get_owned_or_shared_resource(model, "workflow")
        result = await dep(resource_id=1, user=_user(role="admin"), db=db)
        assert result is resource

    async def test_owner_access(self):
        """Owner can access their own resource."""
        from core.auth.ownership import get_owned_or_shared_resource

        model = _mock_model()
        resource = _mock_resource(user_id="user-1")
        db = _mock_db(resource)

        dep = get_owned_or_shared_resource(model, "workflow")
        result = await dep(resource_id=1, user=_user(sub="user-1"), db=db)
        assert result is resource

    async def test_not_found_raises_404(self):
        """Raises 404 when resource not found."""
        from core.auth.ownership import get_owned_or_shared_resource

        model = _mock_model()
        db = _mock_db(resource=None)

        dep = get_owned_or_shared_resource(model, "workflow")
        with pytest.raises(HTTPException) as exc:
            await dep(resource_id=999, user=_user(), db=db)
        assert exc.value.status_code == 404

    async def test_public_access_view_only(self):
        """Public resource accessible when require_edit=False."""
        from core.auth.ownership import get_owned_or_shared_resource

        model = _mock_model()
        resource = _mock_resource(user_id="other-user", is_public=True)
        db = _mock_db(resource)

        dep = get_owned_or_shared_resource(model, "workflow", require_edit=False)
        result = await dep(resource_id=1, user=_user(), db=db)
        assert result is resource

    async def test_public_not_accessible_when_edit_required(self):
        """Public resource NOT accessible when require_edit=True, falls to sharing check."""
        from core.auth.ownership import get_owned_or_shared_resource

        model = _mock_model()
        resource = _mock_resource(user_id="other-user", is_public=True)
        db = _mock_db(resource)

        with patch("core.auth.ownership.SharingService") as MockSharing:
            mock_svc = MagicMock()
            mock_svc.get_permission.return_value = None  # No share
            MockSharing.return_value = mock_svc

            dep = get_owned_or_shared_resource(model, "workflow", require_edit=True)
            with pytest.raises(HTTPException) as exc:
                await dep(resource_id=1, user=_user(), db=db)
            assert exc.value.status_code == 403

    async def test_shared_view_permission(self):
        """Shared resource with view permission accessible when require_edit=False."""
        from core.auth.ownership import get_owned_or_shared_resource

        model = _mock_model()
        resource = _mock_resource(user_id="other-user", is_public=False)
        db = _mock_db(resource)

        with patch("core.auth.ownership.SharingService") as MockSharing:
            mock_svc = MagicMock()
            mock_svc.get_permission.return_value = "view"
            MockSharing.return_value = mock_svc

            dep = get_owned_or_shared_resource(model, "workflow")
            result = await dep(resource_id=1, user=_user(), db=db)
            assert result is resource

    async def test_shared_edit_permission_when_edit_required(self):
        """Shared resource with edit permission accessible when require_edit=True."""
        from core.auth.ownership import get_owned_or_shared_resource

        model = _mock_model()
        resource = _mock_resource(user_id="other-user", is_public=False)
        db = _mock_db(resource)

        with patch("core.auth.ownership.SharingService") as MockSharing:
            mock_svc = MagicMock()
            mock_svc.get_permission.return_value = "edit"
            MockSharing.return_value = mock_svc

            dep = get_owned_or_shared_resource(model, "workflow", require_edit=True)
            result = await dep(resource_id=1, user=_user(), db=db)
            assert result is resource

    async def test_shared_view_permission_denied_when_edit_required(self):
        """Shared resource with view-only raises 403 when require_edit=True."""
        from core.auth.ownership import get_owned_or_shared_resource

        model = _mock_model()
        resource = _mock_resource(user_id="other-user", is_public=False)
        db = _mock_db(resource)

        with patch("core.auth.ownership.SharingService") as MockSharing:
            mock_svc = MagicMock()
            mock_svc.get_permission.return_value = "view"
            MockSharing.return_value = mock_svc

            dep = get_owned_or_shared_resource(model, "workflow", require_edit=True)
            with pytest.raises(HTTPException) as exc:
                await dep(resource_id=1, user=_user(), db=db)
            assert exc.value.status_code == 403
            assert "Edit permission" in exc.value.detail

    async def test_no_access_raises_403(self):
        """Non-owner, non-public, non-shared resource raises 403."""
        from core.auth.ownership import get_owned_or_shared_resource

        model = _mock_model()
        resource = _mock_resource(user_id="other-user", is_public=False)
        db = _mock_db(resource)

        with patch("core.auth.ownership.SharingService") as MockSharing:
            mock_svc = MagicMock()
            mock_svc.get_permission.return_value = None
            MockSharing.return_value = mock_svc

            dep = get_owned_or_shared_resource(model, "workflow")
            with pytest.raises(HTTPException) as exc:
                await dep(resource_id=1, user=_user(), db=db)
            assert exc.value.status_code == 403

    async def test_resource_without_user_id(self):
        """Resource without user_id falls through to public/sharing check."""
        from core.auth.ownership import get_owned_or_shared_resource

        model = _mock_model()
        resource = MagicMock()
        # Remove user_id so hasattr returns False
        del resource.user_id
        resource.is_public = True
        db = _mock_db(resource)

        dep = get_owned_or_shared_resource(model, "workflow")
        result = await dep(resource_id=1, user=_user(), db=db)
        assert result is resource

    async def test_custom_id_param(self):
        """Custom id_param works correctly."""
        from core.auth.ownership import get_owned_or_shared_resource

        model = _mock_model()
        resource = _mock_resource(user_id="user-1")
        db = _mock_db(resource)

        dep = get_owned_or_shared_resource(model, "workflow", id_param="workflow_id")
        result = await dep(resource_id=1, user=_user(sub="user-1"), db=db)
        assert result is resource

# ===========================================================================
# filter_by_owner_or_shared tests
# ===========================================================================

class TestFilterByOwnerOrShared:
    """Tests for filter_by_owner_or_shared dependency factory."""

    async def test_admin_sees_all(self):
        """Admin gets unfiltered query."""
        from core.auth.ownership import filter_by_owner_or_shared

        model = _mock_model()
        mock_query = MagicMock()
        db = MagicMock()
        db.query.return_value = mock_query

        dep = filter_by_owner_or_shared(model, "workflow")
        result = await dep(user=_user(role="admin"), db=db)
        assert result is mock_query

    async def test_member_with_is_public(self):
        """Non-admin with is_public model gets owned OR shared OR public filter."""
        from core.auth.ownership import filter_by_owner_or_shared

        model = _mock_model(has_is_public=True)
        mock_query = MagicMock()
        db = MagicMock()
        db.query.return_value = mock_query

        dep = filter_by_owner_or_shared(model, "workflow")
        result = await dep(user=_user(sub="user-1"), db=db)
        # Filter should have been called on the query (at least once for main filter)
        assert mock_query.filter.called

    async def test_member_without_is_public(self):
        """Non-admin without is_public model gets owned OR shared filter."""
        from core.auth.ownership import filter_by_owner_or_shared

        model = _mock_model(has_is_public=False)
        mock_query = MagicMock()
        db = MagicMock()
        db.query.return_value = mock_query

        dep = filter_by_owner_or_shared(model, "workflow")
        result = await dep(user=_user(sub="user-1"), db=db)
        assert mock_query.filter.called

    async def test_shared_ids_subquery_constructed(self):
        """Verifies shared_ids subquery is constructed from ResourceShare."""
        from core.auth.ownership import filter_by_owner_or_shared

        model = _mock_model(has_is_public=False)
        db = MagicMock()
        mock_query = MagicMock()
        db.query.return_value = mock_query

        dep = filter_by_owner_or_shared(model, "workflow")
        await dep(user=_user(sub="user-1"), db=db)

        # db.query should be called at least twice:
        # once for ResourceShare subquery, once for the main model query
        assert db.query.call_count >= 2

# ===========================================================================
# filter_by_owner extended tests (coverage for is_public branch)
# ===========================================================================

class TestFilterByOwnerExtended:
    """Extended tests for filter_by_owner to cover is_public branch."""

    async def test_member_with_is_public_model(self):
        """Non-admin with is_public model gets owned OR public filter."""
        from core.auth.ownership import filter_by_owner

        model = _mock_model(has_is_public=True)
        mock_query = MagicMock()
        db = MagicMock()
        db.query.return_value = mock_query

        dep = filter_by_owner(model)
        result = await dep(user=_user(sub="user-1"), db=db)
        mock_query.filter.assert_called_once()

    async def test_member_without_is_public_model(self):
        """Non-admin without is_public model gets owned-only filter."""
        from core.auth.ownership import filter_by_owner

        model = _mock_model(has_is_public=False)
        mock_query = MagicMock()
        db = MagicMock()
        db.query.return_value = mock_query

        dep = filter_by_owner(model)
        result = await dep(user=_user(sub="user-1"), db=db)
        mock_query.filter.assert_called_once()

# ===========================================================================
# get_owned_resource extended tests (edge cases)
# ===========================================================================

class TestGetOwnedResourceExtended:
    """Additional edge case tests for get_owned_resource."""

    async def test_resource_without_user_id_attr(self):
        """Resource without user_id attribute falls through to public check."""
        from core.auth.ownership import get_owned_resource

        model = _mock_model()
        resource = MagicMock()
        del resource.user_id  # No user_id attribute
        resource.is_public = True
        db = _mock_db(resource)

        dep = get_owned_resource(model)
        result = await dep(resource_id=1, user=_user(), db=db)
        assert result is resource

    async def test_resource_without_user_id_and_not_public(self):
        """Resource without user_id and not public raises 403."""
        from core.auth.ownership import get_owned_resource

        model = _mock_model()
        resource = MagicMock()
        del resource.user_id
        resource.is_public = False
        db = _mock_db(resource)

        dep = get_owned_resource(model)
        with pytest.raises(HTTPException) as exc:
            await dep(resource_id=1, user=_user(), db=db)
        assert exc.value.status_code == 403

    async def test_resource_without_is_public_attr(self):
        """Resource without is_public attribute and non-owner raises 403."""
        from core.auth.ownership import get_owned_resource

        model = _mock_model()
        resource = MagicMock()
        resource.user_id = "other-user"
        del resource.is_public  # No is_public attribute
        db = _mock_db(resource)

        dep = get_owned_resource(model)
        with pytest.raises(HTTPException) as exc:
            await dep(resource_id=1, user=_user(), db=db)
        assert exc.value.status_code == 403
