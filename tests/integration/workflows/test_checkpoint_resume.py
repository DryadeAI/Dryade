"""Integration tests for workflow checkpoint and resume functionality."""

import tempfile
from pathlib import Path

import pytest
from plugins.checkpoint.store import CheckpointStore

from core.workflows.checkpointed_executor import CheckpointedWorkflowExecutor
from core.workflows.schema import WorkflowSchema

class TestCheckpointedExecutor:
    @pytest.fixture
    def temp_db(self):
        """Create temporary database for checkpoints."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            yield f.name
        Path(f.name).unlink(missing_ok=True)

    @pytest.fixture
    def simple_workflow(self):
        """Simple 3-node workflow for testing."""
        return WorkflowSchema.model_validate(
            {
                "version": "1.0.0",
                "nodes": [
                    {"id": "start", "type": "start", "position": {"x": 0, "y": 0}},
                    {
                        "id": "task1",
                        "type": "task",
                        "data": {"agent": "devops_engineer", "task": "Test task 1"},
                        "position": {"x": 100, "y": 0},
                    },
                    {"id": "end", "type": "end", "position": {"x": 200, "y": 0}},
                ],
                "edges": [
                    {"id": "e1", "source": "start", "target": "task1"},
                    {"id": "e2", "source": "task1", "target": "end"},
                ],
            }
        )

    def test_executor_creates_checkpoints(self, temp_db, simple_workflow):
        """Executor should save checkpoint after each node."""
        store = CheckpointStore(temp_db)
        executor = CheckpointedWorkflowExecutor(checkpoint_store=store)

        flowconfig = simple_workflow.to_flowconfig()
        FlowClass = executor.generate_flow_class(flowconfig)

        assert hasattr(FlowClass, "_save_checkpoint")

    def test_checkpoint_contains_state(self, temp_db):
        """Checkpoint should contain workflow state."""
        store = CheckpointStore(temp_db)
        flow_id = "test-exec-123"

        store.save(
            flow_id=flow_id,
            node_id="task1",
            state={"result": "test output", "progress": 50},
        )

        checkpoint = store.load(flow_id, "task1")
        assert checkpoint is not None
        assert checkpoint["state"]["result"] == "test output"
        assert checkpoint["state"]["progress"] == 50

    def test_list_checkpoints(self, temp_db):
        """Should list all checkpoints for an execution."""
        store = CheckpointStore(temp_db)
        flow_id = "test-exec-456"

        for node_id in ["start", "task1", "task2"]:
            store.save(
                flow_id=flow_id,
                node_id=node_id,
                state={"node": node_id},
            )

        checkpoints = store.list_for_flow(flow_id)
        assert len(checkpoints) == 3
        node_ids = {c["node_id"] for c in checkpoints}
        assert node_ids == {"start", "task1", "task2"}

    @pytest.mark.asyncio
    async def test_resume_from_checkpoint(self, temp_db, simple_workflow):
        """Executor should be able to resume from checkpoint."""
        store = CheckpointStore(temp_db)
        executor = CheckpointedWorkflowExecutor(checkpoint_store=store)
        flow_id = "test-resume-789"

        store.save(
            flow_id=flow_id,
            node_id="task1",
            state={"task1_output": "intermediate result"},
        )

        checkpoint = await executor.resume_from(flow_id, "task1")
        assert checkpoint is not None
        assert checkpoint["state"]["task1_output"] == "intermediate result"

class TestCheckpointStore:
    @pytest.fixture
    def temp_db(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            yield f.name
        Path(f.name).unlink(missing_ok=True)

    def test_store_creates_tables(self, temp_db):
        """Store should create necessary tables on init."""
        store = CheckpointStore(temp_db)
        store.save("exec1", "node1", {"test": "data"})

    def test_store_handles_json_state(self, temp_db):
        """Store should serialize complex state to JSON."""
        store = CheckpointStore(temp_db)

        complex_state = {
            "nested": {"key": "value"},
            "list": [1, 2, 3],
            "number": 42,
            "boolean": True,
        }

        store.save("exec1", "node1", complex_state)
        loaded = store.load("exec1", "node1")

        assert loaded["state"] == complex_state

    def test_store_overwrites_same_checkpoint(self, temp_db):
        """Saving same node twice should overwrite."""
        store = CheckpointStore(temp_db)

        store.save("exec1", "node1", {"version": 1})
        store.save("exec1", "node1", {"version": 2})

        loaded = store.load("exec1", "node1")
        assert loaded["state"]["version"] == 2

        checkpoints = store.list_for_flow("exec1")
        node1_checkpoints = [c for c in checkpoints if c["node_id"] == "node1"]
        assert len(node1_checkpoints) == 1

    def test_store_isolates_executions(self, temp_db):
        """Different executions should have isolated checkpoints."""
        store = CheckpointStore(temp_db)

        store.save("exec1", "node1", {"exec": "1"})
        store.save("exec2", "node1", {"exec": "2"})

        cp1 = store.load("exec1", "node1")
        cp2 = store.load("exec2", "node1")

        assert cp1["state"]["exec"] == "1"
        assert cp2["state"]["exec"] == "2"
