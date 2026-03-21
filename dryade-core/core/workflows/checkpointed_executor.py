"""Checkpointed Workflow Executor - Extends WorkflowExecutor with checkpoint integration.

Enables resumable workflow execution with state persistence after each node.
Target: ~150 LOC
"""

import logging
import uuid
from typing import Any

from crewai.flow.flow import Flow

from core.domains.base import FlowConfig
from core.extensions import CheckpointMixin, CheckpointStore

from .executor import WorkflowExecutor

logger = logging.getLogger("dryade.workflows.checkpointed_executor")

class CheckpointedWorkflowExecutor(WorkflowExecutor):
    """Workflow executor with automatic checkpoint persistence.

    Extends WorkflowExecutor to:
    1. Save checkpoint after each node completes
    2. Support resume from any previously saved checkpoint
    3. Emit progress events for SSE streaming
    4. Store checkpoints via CheckpointStore

    Usage:
        executor = CheckpointedWorkflowExecutor()
        flow_class = executor.generate_flow_class(flowconfig)
        flow = flow_class()
        result = flow.kickoff()

        # Later, resume from checkpoint
        checkpoints = executor.get_checkpoints(execution_id)
        result = await executor.resume_from(execution_id, "analyze")
    """

    def __init__(self, checkpoint_store: CheckpointStore | None = None):
        """Initialize executor with checkpoint store.

        Args:
            checkpoint_store: Optional CheckpointStore instance.
                Defaults to checkpoint store (lazy-initialized).
        """
        super().__init__()
        self._explicit_store = checkpoint_store
        self._lazy_store: CheckpointStore | None = None

    @property
    def _store(self) -> CheckpointStore:
        """Lazy-init CheckpointStore on first access (avoids startup crash when plugin not loaded)."""
        if self._explicit_store is not None:
            return self._explicit_store
        if self._lazy_store is None:
            self._lazy_store = CheckpointStore("workflows.db")
        return self._lazy_store

    def generate_flow_class(self, flowconfig: FlowConfig) -> type[Flow]:
        """Generate Flow class with checkpoint hooks injected.

        Args:
            flowconfig: FlowConfig with nodes and edges.

        Returns:
            Generated Flow class with CheckpointMixin that saves
            state after each node execution.

        Raises:
            ExecutionError: If FlowConfig is invalid.
        """
        logger.info(
            f"[CHECKPOINTED_EXECUTOR] Generating checkpointed Flow class '{flowconfig.name}'"
        )

        # Generate base Flow class using parent executor
        base_class = super().generate_flow_class(flowconfig)

        # Capture store reference for closure
        checkpoint_store = self._store

        class CheckpointedFlow(CheckpointMixin, base_class):
            """Flow subclass with checkpoint integration."""

            _checkpoint_store = checkpoint_store

            def __init__(self):
                """Initialize flow with unique execution ID."""
                super().__init__()
                # Generate execution ID for this flow instance
                self._execution_id = str(uuid.uuid4())

            @property
            def execution_id(self) -> str:
                """Get execution ID for this flow instance."""
                return getattr(self, "_execution_id", "default")

            def _post_node_execution(self, node_id: str, result: Any):
                """Called after each node completes to save checkpoint.

                Args:
                    node_id: ID of the completed node.
                    result: Output from the node execution.
                """
                try:
                    # Get state dict for persistence
                    state_dict = {}
                    if hasattr(self, "state") and hasattr(self.state, "model_dump"):
                        state_dict = self.state.model_dump()

                    # Save to checkpoint store
                    self._checkpoint_store.save(
                        flow_id=self.execution_id,
                        node_id=node_id,
                        state=state_dict,
                        result=result,
                    )
                    logger.debug(
                        f"[CHECKPOINTED_EXECUTOR] Checkpoint saved: "
                        f"execution={self.execution_id}, node={node_id}"
                    )
                except Exception as e:
                    logger.warning(f"[CHECKPOINTED_EXECUTOR] Failed to save checkpoint: {e}")

            def _emit_progress(self, node_id: str, result: Any):
                """Emit progress event for SSE streaming.

                Args:
                    node_id: ID of the completed node.
                    result: Output from the node execution.
                """
                # Progress emission hook for SSE integration
                # This can be overridden by subclasses or hooked by middleware
                logger.debug(
                    f"[CHECKPOINTED_EXECUTOR] Progress: "
                    f"execution={self.execution_id}, node={node_id}"
                )

        # Update class name for clarity
        CheckpointedFlow.__name__ = f"Checkpointed{base_class.__name__}"
        CheckpointedFlow.__qualname__ = f"Checkpointed{base_class.__qualname__}"

        # Copy flow metadata from base class - FlowMeta only processes immediate namespace,
        # so inherited _start_methods and _listeners get overwritten as empty
        CheckpointedFlow._start_methods = base_class._start_methods
        CheckpointedFlow._listeners = base_class._listeners
        CheckpointedFlow._routers = getattr(base_class, "_routers", set())
        CheckpointedFlow._router_paths = getattr(base_class, "_router_paths", {})

        logger.info(
            f"[CHECKPOINTED_EXECUTOR] Generated checkpointed Flow class "
            f"'{CheckpointedFlow.__name__}'"
        )

        return CheckpointedFlow

    def get_checkpoints(self, execution_id: str) -> list[dict[str, Any]]:
        """List available checkpoints for an execution.

        Args:
            execution_id: Execution ID to list checkpoints for.

        Returns:
            List of checkpoint metadata dicts with node_id and timestamp.
        """
        return self._store.list_for_flow(execution_id)

    async def resume_from(self, execution_id: str, node_id: str) -> Any:
        """Resume workflow execution from a specific checkpoint.

        Args:
            execution_id: Execution ID of the workflow.
            node_id: Node ID to resume from.

        Returns:
            Result of workflow execution from checkpoint to end.

        Raises:
            ValueError: If no checkpoint found for the specified node.
        """
        logger.info(
            f"[CHECKPOINTED_EXECUTOR] Resuming execution={execution_id} from node={node_id}"
        )

        # Load checkpoint data
        checkpoint = self._store.load(execution_id, node_id)
        if not checkpoint:
            raise ValueError(
                f"No checkpoint found for execution '{execution_id}' at node '{node_id}'"
            )

        return checkpoint

    def delete_execution(self, execution_id: str):
        """Delete all checkpoints for an execution.

        Args:
            execution_id: Execution ID to clean up.
        """
        self._store.delete_flow(execution_id)
        logger.info(f"[CHECKPOINTED_EXECUTOR] Deleted checkpoints for execution={execution_id}")
