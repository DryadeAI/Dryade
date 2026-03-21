"""Tests for core/workflows/approval.py -- ApprovalService and helpers.

Covers:
- _find_downstream_node() edge matching logic (label match, positional fallback)
- ApprovalService.create_approval_request()
- ApprovalService.record_audit()
- ApprovalService.resume_from_approval() (success, no workflow, no downstream, exception)
- ApprovalService.enforce_timeout() (timeout applied, already resolved, import failures)
- ApprovalService.scan_pending_on_startup() (no pending, timed-out, still pending, exception)
"""

from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.workflows.approval import ApprovalService, _find_downstream_node

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _edge(source: str, target: str, condition: str | None = None) -> SimpleNamespace:
    """Build a simple edge object matching WorkflowSchema.edges structure."""
    data = {"condition": condition} if condition else None
    return SimpleNamespace(source=source, target=target, data=data)

def _schema(edges: list) -> SimpleNamespace:
    """Build a minimal schema object with edges."""
    return SimpleNamespace(edges=edges)

def _mock_db():
    """Return a MagicMock database session."""
    db = MagicMock()
    return db

# ===========================================================================
# _find_downstream_node tests
# ===========================================================================

class TestFindDownstreamNode:
    """Tests for the _find_downstream_node helper function."""

    def test_no_outgoing_edges(self):
        """Returns None when there are no outgoing edges from node."""
        schema = _schema([_edge("other", "target")])
        assert _find_downstream_node(schema, "node_1", "approved") is None

    def test_label_match_approved(self):
        """Finds target via edge.data.condition == 'approved'."""
        schema = _schema(
            [
                _edge("node_1", "approve_target", condition="approved"),
                _edge("node_1", "reject_target", condition="rejected"),
            ]
        )
        assert _find_downstream_node(schema, "node_1", "approved") == "approve_target"

    def test_label_match_rejected(self):
        """Finds target via edge.data.condition == 'rejected'."""
        schema = _schema(
            [
                _edge("node_1", "approve_target", condition="approved"),
                _edge("node_1", "reject_target", condition="rejected"),
            ]
        )
        assert _find_downstream_node(schema, "node_1", "rejected") == "reject_target"

    def test_positional_fallback_approved(self):
        """First outgoing edge used for 'approved' when no condition labels."""
        schema = _schema(
            [
                _edge("node_1", "first_target"),
                _edge("node_1", "second_target"),
            ]
        )
        assert _find_downstream_node(schema, "node_1", "approved") == "first_target"

    def test_positional_fallback_rejected(self):
        """Second outgoing edge used for 'rejected' when no condition labels."""
        schema = _schema(
            [
                _edge("node_1", "first_target"),
                _edge("node_1", "second_target"),
            ]
        )
        assert _find_downstream_node(schema, "node_1", "rejected") == "second_target"

    def test_positional_fallback_rejected_only_one_edge(self):
        """Returns None for 'rejected' when only one edge exists (no second edge)."""
        schema = _schema([_edge("node_1", "first_target")])
        assert _find_downstream_node(schema, "node_1", "rejected") is None

    def test_no_matching_label_and_no_positional(self):
        """Returns None when edges have data but no matching condition and no positional match."""
        schema = _schema(
            [
                _edge("node_1", "some_target", condition="custom_label"),
            ]
        )
        # 'approved' has no condition match, but positional fallback still applies (>= 1 edge)
        assert _find_downstream_node(schema, "node_1", "approved") == "some_target"

    def test_edge_data_none(self):
        """Falls through to positional when edge.data is None."""
        edge = SimpleNamespace(source="node_1", target="target_a", data=None)
        schema = _schema([edge])
        assert _find_downstream_node(schema, "node_1", "approved") == "target_a"

    def test_edge_data_not_dict(self):
        """Falls through when edge.data is not a dict (e.g., a string)."""
        edge = SimpleNamespace(source="node_1", target="target_a", data="not_a_dict")
        schema = _schema([edge])
        # No condition match from non-dict data, positional fallback for 'approved'
        assert _find_downstream_node(schema, "node_1", "approved") == "target_a"

# ===========================================================================
# ApprovalService.create_approval_request tests
# ===========================================================================

class TestCreateApprovalRequest:
    """Tests for create_approval_request."""

    async def test_creates_request_and_pauses_execution(self):
        """Creates a WorkflowApprovalRequest, pauses execution, commits."""
        db = _mock_db()
        mock_execution = MagicMock()
        db.query.return_value.get.return_value = mock_execution

        # Mock the request object returned after refresh
        mock_request = MagicMock()
        mock_request.id = 42

        def refresh_side_effect(obj):
            obj.id = 42

        db.refresh.side_effect = refresh_side_effect

        with patch("core.workflows.approval.WorkflowApprovalRequest") as MockReq:
            instance = MagicMock()
            instance.id = 42
            MockReq.return_value = instance

            # Need db.refresh to set .id
            db.refresh.side_effect = lambda obj: None

            result = await ApprovalService.create_approval_request(
                db=db,
                execution_id=10,
                workflow_id=5,
                node_id="approval_1",
                state_snapshot={"key": "value"},
                prompt="Please approve",
                approver="owner",
                approver_user_id="user-1",
                display_fields=["key"],
                timeout_seconds=3600,
                timeout_action="reject",
            )

        db.add.assert_called_once_with(instance)
        assert mock_execution.status == "paused"
        db.commit.assert_called_once()
        assert result == 42

    async def test_execution_not_found_still_commits(self):
        """If execution not found, still commits (request is created)."""
        db = _mock_db()
        db.query.return_value.get.return_value = None  # execution not found

        with patch("core.workflows.approval.WorkflowApprovalRequest") as MockReq:
            instance = MagicMock()
            instance.id = 99
            MockReq.return_value = instance

            result = await ApprovalService.create_approval_request(
                db=db,
                execution_id=10,
                workflow_id=5,
                node_id="approval_1",
                state_snapshot={},
                prompt="Approve?",
                approver="owner",
                approver_user_id=None,
                display_fields=[],
                timeout_seconds=60,
                timeout_action="approve",
            )

        db.add.assert_called_once()
        db.commit.assert_called_once()
        assert result == 99

# ===========================================================================
# ApprovalService.record_audit tests
# ===========================================================================

class TestRecordAudit:
    """Tests for record_audit."""

    async def test_records_audit_entry(self):
        """Creates an audit log entry and commits."""
        db = _mock_db()

        with patch("core.workflows.approval.WorkflowApprovalAuditLog") as MockAudit:
            audit_instance = MagicMock()
            MockAudit.return_value = audit_instance

            await ApprovalService.record_audit(
                db=db,
                request_id=1,
                actor_user_id="user-1",
                action="approved",
                action_data={"comment": "LGTM"},
            )

        db.add.assert_called_once_with(audit_instance)
        db.commit.assert_called_once()

    async def test_records_audit_no_action_data(self):
        """Works without action_data (optional field)."""
        db = _mock_db()

        with patch("core.workflows.approval.WorkflowApprovalAuditLog") as MockAudit:
            MockAudit.return_value = MagicMock()

            await ApprovalService.record_audit(
                db=db,
                request_id=2,
                actor_user_id="system",
                action="timed_out",
            )

        db.add.assert_called_once()
        db.commit.assert_called_once()

# ===========================================================================
# ApprovalService.resume_from_approval tests
# ===========================================================================

class TestResumeFromApproval:
    """Tests for resume_from_approval."""

    def _make_approval_request(
        self,
        workflow_id=1,
        execution_id=10,
        node_id="approval_1",
        state_snapshot=None,
        display_fields=None,
    ):
        req = MagicMock()
        req.workflow_id = workflow_id
        req.execution_id = execution_id
        req.node_id = node_id
        req.state_snapshot = state_snapshot or {"result": "data"}
        req.display_fields = display_fields or ["result"]
        req.id = 7
        return req

    async def test_workflow_not_found_returns_early(self):
        """Returns early if workflow not found in DB."""
        db = _mock_db()
        db.query.return_value.get.return_value = None

        approval_req = self._make_approval_request()
        await ApprovalService.resume_from_approval(approval_req, "approve", None, db)

        # No exception, just logged and returned

    async def test_no_downstream_node_marks_failed(self):
        """Sets execution to failed when no downstream edge found."""
        db = _mock_db()
        mock_workflow = MagicMock()
        mock_workflow.workflow_json = {"version": "1.0", "nodes": [], "edges": []}
        mock_execution = MagicMock()

        # First .get() returns workflow, second returns execution
        db.query.return_value.get.side_effect = [mock_workflow, mock_execution]

        with patch("core.workflows.schema.WorkflowSchema") as MockSchema:
            schema_instance = MagicMock()
            # No outgoing edges from approval node
            schema_instance.edges = []
            MockSchema.return_value = schema_instance

            approval_req = self._make_approval_request()
            await ApprovalService.resume_from_approval(approval_req, "approve", None, db)

        assert mock_execution.status == "failed"
        assert "approved" in mock_execution.error
        db.commit.assert_called()

    async def test_successful_resume(self):
        """Full resume path: build subgraph, execute, mark success."""
        db = _mock_db()
        mock_workflow = MagicMock()
        mock_workflow.workflow_json = {"version": "1.0", "nodes": [], "edges": []}
        mock_execution = MagicMock()

        db.query.return_value.get.side_effect = [mock_workflow, mock_execution]

        with (
            patch("core.workflows.schema.WorkflowSchema") as MockSchema,
            patch("core.workflows.approval._find_downstream_node") as mock_find,
            patch("core.workflows.executor.WorkflowExecutor") as MockExecutor,
            patch("core.domains.base.FlowConfig") as MockFlowConfig,
            patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread,
        ):
            schema_instance = MagicMock()
            schema_instance.to_flowconfig.return_value = MagicMock(
                name="test_wf",
                nodes=[{"id": "next_node", "type": "task"}, {"id": "end", "type": "end"}],
                edges=[{"source": "next_node", "target": "end"}],
            )
            schema_instance._get_reachable_nodes.return_value = {"end"}
            MockSchema.return_value = schema_instance

            mock_find.return_value = "next_node"

            mock_flow_instance = MagicMock()
            mock_flow_instance.state = MagicMock()
            mock_flow_instance.state.model_dump.return_value = {"done": True}
            MockExecutor.return_value.generate_flow_class.return_value.return_value = (
                mock_flow_instance
            )

            approval_req = self._make_approval_request(
                state_snapshot={"result": "data"},
                display_fields=["result"],
            )
            await ApprovalService.resume_from_approval(
                approval_req, "approve", {"result": "modified"}, db
            )

        assert mock_execution.status == "success"

    async def test_resume_exception_marks_failed(self):
        """General exception during resume marks execution as failed."""
        db = _mock_db()
        mock_workflow = MagicMock()
        mock_workflow.workflow_json = {"version": "1.0", "nodes": [], "edges": []}
        mock_execution = MagicMock()

        db.query.return_value.get.side_effect = [mock_workflow, mock_execution]

        with (
            patch("core.workflows.schema.WorkflowSchema") as MockSchema,
            patch("core.workflows.approval._find_downstream_node") as mock_find,
            patch("core.workflows.executor.WorkflowExecutor") as MockExecutor,
            patch("core.domains.base.FlowConfig"),
        ):
            schema_instance = MagicMock()
            schema_instance.to_flowconfig.return_value = MagicMock(
                name="test_wf",
                nodes=[{"id": "next", "type": "task"}],
                edges=[],
            )
            schema_instance._get_reachable_nodes.return_value = set()
            MockSchema.return_value = schema_instance
            mock_find.return_value = "next"

            MockExecutor.return_value.generate_flow_class.side_effect = RuntimeError("boom")

            approval_req = self._make_approval_request()
            # Second .get() returns execution
            db.query.return_value.get.side_effect = [mock_workflow, mock_execution]
            await ApprovalService.resume_from_approval(approval_req, "reject", None, db)

        assert mock_execution.status == "failed"
        assert "boom" in mock_execution.error

# ===========================================================================
# ApprovalService.enforce_timeout tests
# ===========================================================================

class TestEnforceTimeout:
    """Tests for enforce_timeout background task."""

    async def test_timeout_applied(self):
        """When request is still pending at timeout, status set to timed_out."""
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_session.execute.return_value = mock_result
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        with (
            patch("asyncio.sleep", new_callable=AsyncMock),
            patch(
                "core.workflows.approval.SessionLocal",
                return_value=mock_session,
                create=True,
            ),
            patch("core.database.session.SessionLocal", mock_session, create=True),
        ):
            # Patch the import inside the method
            import importlib
            import sys

            # Provide SessionLocal in the expected import path
            mock_module = MagicMock()
            mock_module.SessionLocal = MagicMock(return_value=mock_session)
            with patch.dict(sys.modules, {"core.database.session": mock_module}):
                await ApprovalService.enforce_timeout(
                    approval_request_id=1,
                    timeout_seconds=10,
                    timeout_action="reject",
                )

        mock_session.commit.assert_called()

    async def test_timeout_already_resolved(self):
        """When request already resolved, rowcount is 0 -- no error."""
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session.execute.return_value = mock_result
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        import sys

        mock_module = MagicMock()
        mock_module.SessionLocal = MagicMock(return_value=mock_session)
        with (
            patch("asyncio.sleep", new_callable=AsyncMock),
            patch.dict(sys.modules, {"core.database.session": mock_module}),
        ):
            await ApprovalService.enforce_timeout(
                approval_request_id=2,
                timeout_seconds=5,
                timeout_action="approve",
            )

        mock_session.commit.assert_called()

    async def test_timeout_zero_seconds(self):
        """With timeout_seconds=0, no sleep called before timeout."""
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_session.execute.return_value = mock_result
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        import sys

        mock_module = MagicMock()
        mock_module.SessionLocal = MagicMock(return_value=mock_session)
        with (
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            patch.dict(sys.modules, {"core.database.session": mock_module}),
        ):
            await ApprovalService.enforce_timeout(
                approval_request_id=3,
                timeout_seconds=0,
                timeout_action="reject",
            )

        # With 0 seconds, reminder_delay=0, so no sleeps called
        mock_sleep.assert_not_called()

    async def test_timeout_import_failure(self):
        """Gracefully handles SessionLocal import failure."""
        import sys

        # Remove both possible import paths
        with (
            patch("asyncio.sleep", new_callable=AsyncMock),
            patch.dict(
                sys.modules,
                {
                    "core.database.session": None,
                    "core.database": None,
                },
            ),
        ):
            # Should not raise, just log warning and return
            await ApprovalService.enforce_timeout(
                approval_request_id=4,
                timeout_seconds=1,
                timeout_action="reject",
            )

# ===========================================================================
# ApprovalService.scan_pending_on_startup tests
# ===========================================================================

class TestScanPendingOnStartup:
    """Tests for scan_pending_on_startup."""

    async def test_no_pending_requests(self):
        """Returns early when no pending requests found."""
        db = _mock_db()
        db.query.return_value.filter.return_value.all.return_value = []

        await ApprovalService.scan_pending_on_startup(db)
        db.commit.assert_not_called()

    async def test_already_timed_out_requests(self):
        """Marks past-timeout requests as timed_out with audit entry."""
        db = _mock_db()
        past_time = datetime.now(UTC) - timedelta(hours=1)
        req = MagicMock()
        req.id = 10
        req.timeout_at = past_time
        req.timeout_action = "reject"
        req.status = "pending"

        db.query.return_value.filter.return_value.all.return_value = [req]

        await ApprovalService.scan_pending_on_startup(db)

        assert req.status == "timed_out"
        db.add.assert_called_once()  # audit entry
        db.commit.assert_called_once()

    async def test_naive_timeout_at_handled(self):
        """Handles naive (no tzinfo) timeout_at by adding UTC."""
        db = _mock_db()
        # Naive datetime in the past
        past_time = datetime(2020, 1, 1, 0, 0, 0)
        req = MagicMock()
        req.id = 11
        req.timeout_at = past_time
        req.timeout_action = "approve"
        req.status = "pending"

        db.query.return_value.filter.return_value.all.return_value = [req]

        await ApprovalService.scan_pending_on_startup(db)

        assert req.status == "timed_out"

    async def test_still_pending_requests(self):
        """Requests with future timeout are not timed out."""
        db = _mock_db()
        future_time = datetime.now(UTC) + timedelta(hours=1)
        req = MagicMock()
        req.id = 12
        req.timeout_at = future_time
        req.timeout_action = "reject"
        req.status = "pending"

        db.query.return_value.filter.return_value.all.return_value = [req]

        await ApprovalService.scan_pending_on_startup(db)

        # Status should not be changed
        assert req.status == "pending"
        db.commit.assert_called_once()

    async def test_exception_propagated(self):
        """Exceptions during scan are re-raised after logging."""
        db = _mock_db()
        db.query.side_effect = RuntimeError("DB connection failed")

        with pytest.raises(RuntimeError, match="DB connection failed"):
            await ApprovalService.scan_pending_on_startup(db)
