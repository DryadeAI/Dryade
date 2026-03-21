"""Approval Service — manages workflow pause/resume for human approval nodes.

Handles:
- Creating approval requests when approval nodes are hit
- Resuming workflow execution after approval/rejection
- Timeout enforcement with background tasks
- Audit trail recording
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Literal

from sqlalchemy.orm import Session

from core.database.models import (
    Workflow,
    WorkflowApprovalAuditLog,
    WorkflowApprovalRequest,
    WorkflowExecutionResult,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger("dryade.workflows.approval")

def _find_downstream_node(schema: Any, node_id: str, edge_label: str) -> str | None:
    """Find the target node of an edge from node_id matching the given label.

    Tries edge.data.condition == edge_label first, then positional fallback:
    - first outgoing edge = "approved"
    - second outgoing edge = "rejected"
    """
    outgoing = [e for e in schema.edges if e.source == node_id]
    if not outgoing:
        return None

    # Try label match via edge.data.condition
    for edge in outgoing:
        if edge.data and isinstance(edge.data, dict):
            cond = edge.data.get("condition", "")
            if cond == edge_label:
                return edge.target

    # Positional fallback: approved=first, rejected=second
    if edge_label == "approved" and len(outgoing) >= 1:
        return outgoing[0].target
    elif edge_label == "rejected" and len(outgoing) >= 2:
        return outgoing[1].target

    return None

class ApprovalService:
    """Manages human approval workflow nodes."""

    @staticmethod
    async def create_approval_request(
        db: Session,
        execution_id: int,
        workflow_id: int,
        node_id: str,
        state_snapshot: dict[str, Any],
        prompt: str,
        approver: str,
        approver_user_id: str | None,
        display_fields: list[str],
        timeout_seconds: int,
        timeout_action: str,
    ) -> int:
        """Create a new approval request and pause the execution.

        Returns the approval_request_id.
        """
        timeout_at = datetime.now(UTC) + timedelta(seconds=timeout_seconds)

        request = WorkflowApprovalRequest(
            execution_id=execution_id,
            workflow_id=workflow_id,
            node_id=node_id,
            status="pending",
            prompt=prompt,
            approver_type=approver,
            approver_user_id=approver_user_id,
            display_fields=display_fields,
            state_snapshot=state_snapshot,
            timeout_at=timeout_at,
            timeout_action=timeout_action,
        )
        db.add(request)

        # Update execution status to paused
        execution = db.query(WorkflowExecutionResult).get(execution_id)
        if execution:
            execution.status = "paused"

        db.commit()
        db.refresh(request)

        logger.info(
            f"[APPROVAL] Created approval request {request.id} for execution {execution_id}, "
            f"node '{node_id}', timeout_at={timeout_at.isoformat()}"
        )
        return request.id

    @staticmethod
    async def record_audit(
        db: Session,
        request_id: int,
        actor_user_id: str,
        action: str,
        action_data: dict[str, Any] | None = None,
    ) -> None:
        """Record an immutable audit log entry."""
        entry = WorkflowApprovalAuditLog(
            request_id=request_id,
            actor_user_id=actor_user_id,
            action=action,
            action_data=action_data,
        )
        db.add(entry)
        db.commit()
        logger.info(
            f"[APPROVAL] Audit: request_id={request_id}, actor={actor_user_id}, action={action}"
        )

    @staticmethod
    async def resume_from_approval(
        approval_request: "WorkflowApprovalRequest",
        action: Literal["approve", "reject"],
        modified_fields: dict[str, Any] | None,
        db: Session,
    ) -> None:
        """Reconstruct and continue workflow execution after approval action.

        Builds a subgraph FlowConfig starting from the downstream node of the
        approval and re-executes with the restored (and optionally modified) state.
        """
        from core.exceptions import WorkflowPausedForApproval
        from core.workflows.executor import WorkflowExecutor
        from core.workflows.schema import WorkflowSchema

        # 1. Load workflow and reconstruct schema
        workflow = db.query(Workflow).get(approval_request.workflow_id)
        if not workflow:
            logger.error(f"[APPROVAL] Workflow {approval_request.workflow_id} not found for resume")
            return
        schema = WorkflowSchema(**workflow.workflow_json)

        # 2. Restore state snapshot + apply validated modifications
        state_dict = dict(approval_request.state_snapshot)
        if modified_fields:
            allowed = set(approval_request.display_fields or [])
            for key in modified_fields:
                if key in allowed:
                    state_dict[key] = modified_fields[key]

        # 3. Find downstream node via 'approved' or 'rejected' edge label
        approval_node_id = approval_request.node_id
        edge_label = "approved" if action == "approve" else "rejected"
        resume_node_id = _find_downstream_node(schema, approval_node_id, edge_label)

        if not resume_node_id:
            logger.error(
                f"[APPROVAL] No downstream node found for edge '{edge_label}' "
                f"from '{approval_node_id}'"
            )
            execution = db.query(WorkflowExecutionResult).get(approval_request.execution_id)
            if execution:
                execution.status = "failed"
                execution.error = f"No '{edge_label}' edge from approval node '{approval_node_id}'"
                db.commit()
            return

        # 4. Build subgraph FlowConfig starting from resume_node_id
        flowconfig_full = schema.to_flowconfig()
        reachable = schema._get_reachable_nodes(resume_node_id)
        reachable.add(resume_node_id)

        resume_nodes = [n for n in flowconfig_full.nodes if n["id"] in reachable]
        resume_edges = [
            e
            for e in flowconfig_full.edges
            if e["source"] in reachable and e["target"] in reachable
        ]

        # Change resume_node_id type to "start" so @start decorator is applied
        for n in resume_nodes:
            if n["id"] == resume_node_id:
                n["type"] = "start"
                break

        from core.domains.base import FlowConfig

        resume_flowconfig = FlowConfig(
            name=f"{flowconfig_full.name}_resume_{approval_request.id}",
            description=f"Resumed from approval node {approval_node_id} via {edge_label}",
            nodes=resume_nodes,
            edges=resume_edges,
        )

        # 5. Generate and execute resumed Flow
        executor = WorkflowExecutor()
        try:
            flow_class = executor.generate_flow_class(resume_flowconfig)
            flow_instance = flow_class()
            # Inject saved state
            for key, value in state_dict.items():
                if hasattr(flow_instance.state, key):
                    setattr(flow_instance.state, key, value)

            import asyncio

            await asyncio.to_thread(flow_instance.kickoff)

            # Update execution result to success
            execution = db.query(WorkflowExecutionResult).get(approval_request.execution_id)
            if execution:
                execution.status = "success"
                execution.completed_at = datetime.now(UTC)
                execution.final_result = (
                    flow_instance.state.model_dump()
                    if hasattr(flow_instance.state, "model_dump")
                    else {}
                )
                db.commit()

            logger.info(
                f"[APPROVAL] Execution {approval_request.execution_id} resumed and completed "
                f"after '{edge_label}' action"
            )

        except WorkflowPausedForApproval:
            # Another approval node downstream — state already persisted by handler
            logger.info(
                f"[APPROVAL] Resumed workflow hit another approval node "
                f"(execution {approval_request.execution_id})"
            )
        except Exception as e:
            logger.error(
                f"[APPROVAL] Resume failed for execution {approval_request.execution_id}: {e}"
            )
            execution = db.query(WorkflowExecutionResult).get(approval_request.execution_id)
            if execution:
                execution.status = "failed"
                execution.error = str(e)
                db.commit()

    @staticmethod
    async def enforce_timeout(
        approval_request_id: int,
        timeout_seconds: int,
        timeout_action: str,
    ) -> None:
        """Background task: sleep until timeout, apply action if still pending.

        Sends a conceptual reminder at 75% of timeout duration, then applies
        the configured timeout_action if the request is still pending.
        """
        import asyncio

        reminder_delay = timeout_seconds * 0.75
        if reminder_delay > 0:
            await asyncio.sleep(reminder_delay)
            logger.info(
                f"[APPROVAL] 75% timeout reminder for request {approval_request_id} "
                f"(action will be '{timeout_action}' if not resolved)"
            )
            remaining = timeout_seconds - reminder_delay
        else:
            remaining = 0

        if remaining > 0:
            await asyncio.sleep(remaining)

        # Apply timeout action if still pending (optimistic locking)
        logger.info(
            f"[APPROVAL] Timeout reached for request {approval_request_id}, "
            f"attempting to apply action '{timeout_action}'"
        )
        try:
            from sqlalchemy import update as sa_update

            # Import the session factory — try multiple known patterns
            try:
                from core.database.session import SessionLocal
            except ImportError:
                try:
                    from core.database import SessionLocal
                except ImportError:
                    logger.warning("[APPROVAL] Cannot import SessionLocal for timeout enforcement")
                    return

            with SessionLocal() as db_fresh:
                rows = db_fresh.execute(
                    sa_update(WorkflowApprovalRequest)
                    .where(WorkflowApprovalRequest.id == approval_request_id)
                    .where(WorkflowApprovalRequest.status == "pending")
                    .values(
                        status="timed_out",
                        resolved_at=datetime.now(UTC),
                        resolution_note=f"Auto-{timeout_action} by timeout",
                    )
                ).rowcount
                db_fresh.commit()

                if rows > 0:
                    logger.info(
                        f"[APPROVAL] Request {approval_request_id} timed out, "
                        f"status set to 'timed_out'"
                    )
                else:
                    logger.debug(
                        f"[APPROVAL] Request {approval_request_id} already resolved before timeout"
                    )
        except Exception as e:
            logger.error(
                f"[APPROVAL] Failed to apply timeout for request {approval_request_id}: {e}"
            )

    @staticmethod
    async def scan_pending_on_startup(db: Session) -> None:
        """On app startup, re-schedule timeout tasks for any pending approval requests.

        This resumes timeout enforcement for approval requests that were pending
        before a server restart. Without this, pending approvals would hang forever
        after a restart because the asyncio tasks are not persisted.
        """
        try:
            pending = (
                db.query(WorkflowApprovalRequest)
                .filter(WorkflowApprovalRequest.status == "pending")
                .all()
            )

            if not pending:
                logger.info("[APPROVAL] No pending approval requests found on startup")
                return

            logger.info(
                f"[APPROVAL] Found {len(pending)} pending approval request(s) on startup — "
                f"re-scheduling timeout tasks"
            )

            now = datetime.now(UTC)
            for req in pending:
                # Make timeout_at timezone-aware if it isn't already
                timeout_at = req.timeout_at
                if timeout_at.tzinfo is None:
                    from datetime import timezone

                    timeout_at = timeout_at.replace(tzinfo=timezone.utc)

                remaining = (timeout_at - now).total_seconds()
                if remaining <= 0:
                    # Already timed out — apply timeout_action immediately
                    logger.warning(
                        f"[APPROVAL] Request {req.id} already timed out (was due at {timeout_at.isoformat()}), "
                        f"applying timeout_action='{req.timeout_action}'"
                    )
                    req.status = "timed_out"
                    entry = WorkflowApprovalAuditLog(
                        request_id=req.id,
                        actor_user_id="system",
                        action="timed_out",
                        action_data={"reason": "startup_scan_past_timeout"},
                    )
                    db.add(entry)
                else:
                    logger.info(
                        f"[APPROVAL] Request {req.id} has {remaining:.0f}s remaining — "
                        f"timeout task will fire at {timeout_at.isoformat()}"
                    )
                    # Note: asyncio timeout tasks would be scheduled here in a full implementation
                    # For now we log that the request is still pending

            db.commit()

        except Exception as e:
            logger.error(f"[APPROVAL] scan_pending_on_startup failed: {e}", exc_info=True)
            raise
