"""Trigger Handler - Unified multi-source workflow triggering.

Enables workflow scenarios to be triggered from chat commands, UI buttons,
REST API calls, or scheduled jobs with consistent SSE progress streaming.
Target: ~300 LOC
"""

import json
import logging
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from core.database.models import ScenarioExecutionResult
from core.database.session import get_session
from core.exceptions import WorkflowPausedForApproval
from core.workflows.checkpointed_executor import CheckpointedWorkflowExecutor
from core.workflows.scenarios import InputSchema, ScenarioRegistry
from core.workflows.schema import WorkflowSchema

logger = logging.getLogger("dryade.workflows.triggers")

# =============================================================================
# Enums and Types
# =============================================================================

class TriggerSource(str, Enum):
    """Source of workflow trigger for observability tracking."""

    CHAT = "chat"  # Triggered via chat command (e.g., /analyze-report)
    API = "api"  # Triggered via REST API endpoint
    UI = "ui"  # Triggered via UI button configuration
    SCHEDULE = "schedule"  # Future: cron-based triggers

# =============================================================================
# TriggerHandler
# =============================================================================

class TriggerHandler:
    """Unified handler for triggering workflow scenarios from any source.

    Provides consistent execution and SSE progress streaming regardless of
    how the workflow was invoked (chat, API, UI, or scheduled).

    Usage:
        registry = ScenarioRegistry()
        executor = CheckpointedWorkflowExecutor()
        handler = TriggerHandler(registry, executor)

        async for event in handler.trigger("financial_reporting", inputs, TriggerSource.API):
            yield event  # SSE events for streaming
    """

    def __init__(
        self,
        registry: ScenarioRegistry,
        executor: CheckpointedWorkflowExecutor,
    ):
        """Initialize trigger handler.

        Args:
            registry: ScenarioRegistry for loading scenario configs.
            executor: CheckpointedWorkflowExecutor for workflow execution.
        """
        self._registry = registry
        self._executor = executor

    def _create_execution_record(
        self,
        execution_id: str,
        scenario_name: str,
        trigger_source: str,
        user_id: str | None,
        inputs: dict[str, Any],
        started_at: datetime,
    ) -> None:
        """Create a new execution record in the database.

        Args:
            execution_id: Unique execution identifier.
            scenario_name: Name of the scenario being executed.
            trigger_source: Source of the trigger (chat, api, ui, schedule).
            user_id: Optional user ID who triggered.
            inputs: Input values for the workflow.
            started_at: Execution start timestamp.
        """
        try:
            # Extract template provenance from inputs (GAP-T2)
            template_id = inputs.pop("_template_id", None) or inputs.pop("template_id", None)
            template_version_id = inputs.pop("_template_version_id", None) or inputs.pop(
                "template_version_id", None
            )
            metadata = {}
            if template_id:
                metadata["template_id"] = template_id
            if template_version_id:
                metadata["template_version_id"] = template_version_id

            with get_session() as db:
                record = ScenarioExecutionResult(
                    execution_id=execution_id,
                    scenario_name=scenario_name,
                    user_id=user_id,
                    trigger_source=trigger_source,
                    status="running",
                    started_at=started_at,
                    inputs=inputs,
                    metadata_=metadata if metadata else {},
                )
                db.add(record)

                # Populate CostRecord template_id if available (GAP-T9)
                if template_id:
                    from core.database.models import CostRecord

                    # Update any cost records created during this execution
                    # that don't yet have template_id set
                    db.query(CostRecord).filter(
                        CostRecord.task_id == execution_id,
                        CostRecord.template_id.is_(None),
                    ).update(
                        {
                            CostRecord.template_id: template_id,
                            CostRecord.template_version_id: template_version_id,
                        },
                        synchronize_session=False,
                    )
                # Commit handled by context manager
            logger.debug(f"[TRIGGER_HANDLER] Created execution record: {execution_id}")
        except Exception as e:
            logger.error(f"[TRIGGER_HANDLER] Failed to create execution record: {e}")
            # Don't fail the execution if DB write fails - rollback handled by context manager

    def _update_execution_complete(
        self,
        execution_id: str,
        final_result: dict[str, Any] | None = None,
        node_results: list[dict[str, Any]] | None = None,
        error: str | None = None,
    ) -> None:
        """Update execution record on completion or failure.

        Args:
            execution_id: Execution to update.
            final_result: Final workflow output (if successful).
            node_results: Per-node execution results.
            error: Error message (if failed).
        """
        try:
            with get_session() as db:
                record = (
                    db.query(ScenarioExecutionResult)
                    .filter(ScenarioExecutionResult.execution_id == execution_id)
                    .first()
                )

                if not record:
                    logger.warning(f"[TRIGGER_HANDLER] Execution record not found: {execution_id}")
                    return

                completed_at = datetime.now(UTC)
                record.completed_at = completed_at
                record.status = "failed" if error else "completed"

                if record.started_at:
                    duration = (completed_at - record.started_at).total_seconds() * 1000
                    record.duration_ms = int(duration)

                if final_result:
                    record.final_result = final_result
                if node_results:
                    record.node_results = node_results
                if error:
                    record.error = error

                # Populate CostRecord template_id at completion (GAP-T9)
                template_id = (record.metadata_ or {}).get("template_id")
                if template_id:
                    from core.database.models import CostRecord

                    db.query(CostRecord).filter(
                        CostRecord.task_id == execution_id,
                        CostRecord.template_id.is_(None),
                    ).update(
                        {
                            CostRecord.template_id: template_id,
                            CostRecord.template_version_id: (record.metadata_ or {}).get(
                                "template_version_id"
                            ),
                        },
                        synchronize_session=False,
                    )
                # Commit handled by context manager

            logger.debug(
                f"[TRIGGER_HANDLER] Updated execution record: {execution_id} "
                f"status={'failed' if error else 'completed'}"
            )
        except Exception as e:
            logger.error(f"[TRIGGER_HANDLER] Failed to update execution record: {e}")
            # Rollback handled by context manager

    def _update_execution_paused(self, execution_id: str) -> None:
        """Update execution record to paused status for approval nodes.

        Does NOT set completed_at — the execution is still in progress,
        waiting for human approval before it can continue.

        Args:
            execution_id: Execution to mark as paused.
        """
        try:
            with get_session() as db:
                record = (
                    db.query(ScenarioExecutionResult)
                    .filter(ScenarioExecutionResult.execution_id == execution_id)
                    .first()
                )
                if record:
                    record.status = "paused"
                    # Do NOT set completed_at -- still in progress, waiting for approval
            logger.debug(
                f"[TRIGGER_HANDLER] Updated execution record: {execution_id} status=paused"
            )
        except Exception as e:
            logger.error(f"[TRIGGER_HANDLER] Failed to update execution to paused: {e}")

    async def trigger(
        self,
        scenario_name: str,
        inputs: dict[str, Any],
        trigger_source: TriggerSource,
        user_id: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Trigger workflow scenario and stream progress events.

        Args:
            scenario_name: Name of the scenario to execute.
            inputs: Input values for the workflow.
            trigger_source: Source of the trigger (chat, api, ui, schedule).
            user_id: Optional user ID for tracking.

        Yields:
            SSE-formatted events: 'data: {json}\\n\\n'

        Raises:
            FileNotFoundError: If scenario not found.
            ValueError: If inputs fail validation.
        """
        execution_id = str(uuid.uuid4())
        started_at = datetime.now(UTC)

        logger.info(
            f"[TRIGGER_HANDLER] Starting scenario={scenario_name} "
            f"execution_id={execution_id} source={trigger_source.value}"
        )

        try:
            # 1. Load scenario
            config, workflow = self._registry.get_scenario(scenario_name)

            # 2. Validate inputs against schema
            validated = self._validate_inputs(config.inputs, inputs)

            # 3. Persist execution record to database
            self._create_execution_record(
                execution_id=execution_id,
                scenario_name=scenario_name,
                trigger_source=trigger_source.value,
                user_id=user_id,
                inputs=validated,
                started_at=started_at,
            )

            # 4. Create execution context
            context = {
                "execution_id": execution_id,
                "scenario_name": scenario_name,
                "trigger_source": trigger_source.value,
                "user_id": user_id,
                "started_at": started_at.isoformat(),
                "inputs": validated,
            }

            # 5. Execute workflow with progress streaming
            async for event in self._execute_with_progress(workflow, validated, context):
                yield event

        except FileNotFoundError:
            logger.error(f"[TRIGGER_HANDLER] Scenario not found: {scenario_name}")
            self._update_execution_complete(
                execution_id, error=f"Scenario not found: {scenario_name}"
            )
            yield self._format_event(
                {
                    "type": "error",
                    "execution_id": execution_id,
                    "error": f"Scenario not found: {scenario_name}",
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
        except ValueError as e:
            logger.error(f"[TRIGGER_HANDLER] Validation error: {e}")
            self._update_execution_complete(execution_id, error=str(e))
            yield self._format_event(
                {
                    "type": "error",
                    "execution_id": execution_id,
                    "error": str(e),
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
        except Exception as e:
            logger.exception(f"[TRIGGER_HANDLER] Execution error: {e}")
            self._update_execution_complete(execution_id, error=str(e))
            yield self._format_event(
                {
                    "type": "error",
                    "execution_id": execution_id,
                    "error": str(e),
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )

    def _validate_inputs(self, schema: list[InputSchema], inputs: dict[str, Any]) -> dict[str, Any]:
        """Validate inputs against scenario schema.

        Args:
            schema: List of InputSchema from scenario config.
            inputs: Input values to validate.

        Returns:
            Validated and processed inputs with defaults applied.

        Raises:
            ValueError: If required fields missing or type mismatch.
        """
        validated = {}

        for field in schema:
            value = inputs.get(field.name)

            # Check required fields
            if value is None:
                if field.required and field.default is None:
                    raise ValueError(f"Required input missing: {field.name}")
                value = field.default

            # Type coercion/validation
            if value is not None:
                validated[field.name] = self._coerce_type(value, field.type, field.name)

        # Pass through any extra inputs not in schema
        for key, value in inputs.items():
            if key not in validated:
                validated[key] = value

        return validated

    def _coerce_type(self, value: Any, type_name: str, field_name: str) -> Any:
        """Coerce value to expected type.

        Args:
            value: Value to coerce.
            type_name: Target type name (string, number, boolean, json, file).
            field_name: Field name for error messages.

        Returns:
            Coerced value.

        Raises:
            ValueError: If coercion fails.
        """
        if type_name == "string":
            return str(value)
        elif type_name == "number":
            try:
                return float(value) if "." in str(value) else int(value)
            except (ValueError, TypeError) as e:
                raise ValueError(f"Invalid number for {field_name}: {value}") from e
        elif type_name == "boolean":
            if isinstance(value, bool):
                return value
            return str(value).lower() in ("true", "1", "yes")
        elif type_name == "json":
            if isinstance(value, (dict, list)):
                return value
            try:
                return json.loads(value)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON for {field_name}: {value}") from e
        elif type_name == "file":
            # File inputs are paths or file-like objects, pass through
            return value
        else:
            return value

    async def _execute_with_progress(
        self, workflow: WorkflowSchema, inputs: dict[str, Any], context: dict[str, Any]
    ) -> AsyncGenerator[str, None]:
        """Execute workflow with SSE progress events.

        SSE format: Each event is JSON followed by double newline.
        Example emission:
            event = {"type": "node_start", "execution_id": "abc", ...}
            yield f'data: {json.dumps(event)}\\n\\n'

        Args:
            workflow: WorkflowSchema to execute.
            inputs: Validated inputs for the workflow.
            context: Execution context with metadata.

        Yields:
            SSE-formatted progress events.
        """
        execution_id = context["execution_id"]

        # Emit workflow_start
        yield self._format_event(
            {
                "type": "workflow_start",
                "execution_id": execution_id,
                "scenario_name": context.get("scenario_name"),
                "trigger_source": context.get("trigger_source"),
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

        try:
            # Generate flow class from workflow
            from core.workflows.translator import WorkflowTranslator

            translator = WorkflowTranslator()
            flowconfig = translator.to_flowconfig(workflow)
            flow_class = self._executor.generate_flow_class(flowconfig)
            flow_instance = flow_class()

            # Set initial state inputs (state model allows extra fields for dynamic inputs)
            for key, value in inputs.items():
                setattr(flow_instance.state, key, value)

            # Emit workflow_nodes event with node list (for UI progress tracking)
            yield self._format_event(
                {
                    "type": "workflow_nodes",
                    "execution_id": execution_id,
                    "nodes": [
                        {"id": n.get("id", ""), "type": n.get("type", "")} for n in flowconfig.nodes
                    ],
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )

            # GAP-S1/S4: Execute flow with heartbeat events during execution
            # Run kickoff in executor thread while emitting heartbeats every 10s
            import asyncio

            loop = asyncio.get_event_loop()
            future = loop.run_in_executor(None, flow_instance.kickoff)

            # Poll for completion while yielding heartbeat events
            heartbeat_interval = 10  # seconds
            while True:
                try:
                    result = await asyncio.wait_for(
                        asyncio.shield(future), timeout=heartbeat_interval
                    )
                    break  # Execution completed
                except asyncio.TimeoutError:
                    # Execution still running — emit heartbeat
                    yield self._format_event(
                        {
                            "type": "heartbeat",
                            "execution_id": execution_id,
                            "timestamp": datetime.now(UTC).isoformat(),
                        }
                    )

            # Emit node_complete for each node with output
            # Note: Full per-node callbacks during execution require injecting
            # event hooks into generate_flow_class() — deferred to future phase.
            # Currently emitted after kickoff completes.
            state_dict = (
                flow_instance.state.model_dump()
                if hasattr(flow_instance.state, "model_dump")
                else {}
            )

            # Collect executed nodes (those with non-None output)
            executed_nodes = []
            for key, value in state_dict.items():
                if "_output" in key and value is not None:
                    node_id = key.replace("_output", "")
                    executed_nodes.append(node_id)

                    # Format output - preserve structure for dict/list, limit string length
                    if isinstance(value, (dict, list)):
                        # Keep structured data intact for proper JSON serialization
                        formatted_output = value
                    elif isinstance(value, str):
                        # Limit string output to 2000 chars (increased from 500)
                        formatted_output = value[:2000] if len(value) > 2000 else value
                    else:
                        formatted_output = str(value)

                    yield self._format_event(
                        {
                            "type": "node_complete",
                            "execution_id": execution_id,
                            "node_id": node_id,
                            "data": formatted_output,
                            "timestamp": datetime.now(UTC).isoformat(),
                        }
                    )

            # Build comprehensive final result
            final_result = {
                "output": result if isinstance(result, dict) else str(result),
                "executed_nodes": executed_nodes,
                "state": {
                    k: v
                    for k, v in state_dict.items()
                    if k not in ("id", "started_at", "completed_at", "error") and v is not None
                },
            }

            # Include error if present
            if state_dict.get("error"):
                final_result["error"] = state_dict["error"]

            # Build node_results for database persistence
            node_results = []
            for node_id in executed_nodes:
                node_output = state_dict.get(f"{node_id}_output")
                node_results.append(
                    {
                        "node_id": node_id,
                        "status": "completed",
                        "output": node_output
                        if isinstance(node_output, (dict, list, str, int, float, bool, type(None)))
                        else str(node_output),
                    }
                )

            # Update execution record with results
            self._update_execution_complete(
                execution_id=execution_id,
                final_result=final_result,
                node_results=node_results,
                error=state_dict.get("error"),
            )

            # Emit workflow_complete
            yield self._format_event(
                {
                    "type": "workflow_complete",
                    "execution_id": execution_id,
                    "result": final_result,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )

            logger.info(
                f"[TRIGGER_HANDLER] Workflow completed execution_id={execution_id} "
                f"executed_nodes={executed_nodes}"
            )

        except Exception as e:
            # Check for approval sentinel (may be direct raise or wrapped via asyncio thread pool)
            if isinstance(e, WorkflowPausedForApproval) or isinstance(
                getattr(e, "__cause__", None), WorkflowPausedForApproval
            ):
                # Extract approval metadata from flow state
                state_dict = (
                    flow_instance.state.model_dump()
                    if hasattr(flow_instance.state, "model_dump")
                    else {}
                )
                approval_meta = None
                for _k, _v in state_dict.items():
                    if isinstance(_v, dict) and _v.get("status") == "awaiting_approval":
                        approval_meta = _v
                        break

                # Update DB record to paused status
                self._update_execution_paused(execution_id=execution_id)

                # Emit approval_pending SSE event
                yield self._format_event(
                    {
                        "type": "approval_pending",
                        "execution_id": execution_id,
                        "node_id": approval_meta["node_id"] if approval_meta else "unknown",
                        "prompt": (
                            approval_meta["prompt"]
                            if approval_meta
                            else "Workflow paused for approval"
                        ),
                        "approver": (
                            approval_meta.get("approver", "owner") if approval_meta else "owner"
                        ),
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                )
                logger.info(
                    f"[TRIGGER_HANDLER] Workflow paused for approval execution_id={execution_id}"
                )
            else:
                # Actual error -- existing error handling (unchanged)
                logger.exception(f"[TRIGGER_HANDLER] Execution failed: {e}")
                # Update execution record with error
                self._update_execution_complete(execution_id=execution_id, error=str(e))
                yield self._format_event(
                    {
                        "type": "error",
                        "execution_id": execution_id,
                        "error": str(e),
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                )

    def _format_event(self, event: dict[str, Any]) -> str:
        """Format event as SSE data line.

        Args:
            event: Event dict to format.

        Returns:
            SSE-formatted string: 'data: {json}\\n\\n'
        """
        return f"data: {json.dumps(event)}\n\n"

# =============================================================================
# Helper Functions
# =============================================================================

def get_trigger_handler(
    scenarios_dir: str = "workflows/scenarios",
) -> TriggerHandler:
    """Get a configured TriggerHandler instance.

    Args:
        scenarios_dir: Path to scenarios directory.

    Returns:
        Configured TriggerHandler.
    """
    from core.workflows.scenarios import get_registry

    registry = get_registry(scenarios_dir)
    executor = CheckpointedWorkflowExecutor()
    return TriggerHandler(registry, executor)
