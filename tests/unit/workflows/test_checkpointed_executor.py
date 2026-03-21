"""Unit tests for CheckpointedWorkflowExecutor.

Tests checkpoint saving, listing, and resume functionality.
"""

from unittest.mock import MagicMock, patch

import pytest

from core.domains.base import FlowConfig
from core.workflows.checkpointed_executor import CheckpointedWorkflowExecutor

class TestCheckpointedWorkflowExecutorInit:
    """Tests for CheckpointedWorkflowExecutor initialization."""

    def test_init_default_store(self):
        """Should create default CheckpointStore when none provided."""
        with patch("core.workflows.checkpointed_executor.CheckpointStore") as mock_store:
            mock_store.return_value = MagicMock()
            executor = CheckpointedWorkflowExecutor()

            assert executor._store is not None
            mock_store.assert_called_once_with("workflows.db")

    def test_init_custom_store(self):
        """Should use provided CheckpointStore."""
        mock_store = MagicMock()
        executor = CheckpointedWorkflowExecutor(checkpoint_store=mock_store)

        assert executor._store is mock_store

    def test_store_attribute_accessible(self):
        """Should have _store attribute accessible."""
        mock_store = MagicMock()
        executor = CheckpointedWorkflowExecutor(checkpoint_store=mock_store)

        assert hasattr(executor, "_store")
        assert executor._store is not None

class TestGenerateFlowClass:
    """Tests for generate_flow_class method."""

    @pytest.fixture
    def mock_checkpoint_store(self):
        """Provide mock CheckpointStore."""
        store = MagicMock()
        store.save = MagicMock()
        store.load = MagicMock(return_value=None)
        store.list_for_flow = MagicMock(return_value=[])
        return store

    @pytest.fixture
    def simple_flowconfig(self):
        """Provide simple FlowConfig for testing."""
        return FlowConfig(
            name="test_flow",
            description="Test workflow",
            nodes=[
                {"id": "start", "type": "start"},
                {"id": "task1", "type": "task", "agent": "test_agent", "task": "Do something"},
                {"id": "end", "type": "end"},
            ],
            edges=[
                {"source": "start", "target": "task1"},
                {"source": "task1", "target": "end"},
            ],
        )

    @pytest.fixture
    def mock_plain_bases(self):
        """Return plain base classes to avoid CrewAI / CheckpointMixin metaclass conflicts.

        WorkflowExecutor.generate_flow_class() returns a crewai.flow.flow.Flow
        subclass whose metaclass conflicts with CheckpointMixin's plain ``type``
        metaclass.  We replace both the parent flow class AND CheckpointMixin
        with plain classes so CheckpointedWorkflowExecutor's class-body logic
        can be exercised without any metaclass machinery from CrewAI or plugins.

        _PlainFlow also carries the CrewAI flow-metadata attributes that
        CheckpointedWorkflowExecutor.generate_flow_class() copies over
        (``_start_methods``, ``_listeners``, ``_routers``, ``_router_paths``).

        Returns:
            tuple[type, type]: (_PlainFlow, _PlainCheckpointMixin)
        """

        class _PlainFlow:
            """Minimal stand-in for a CrewAI Flow subclass."""

            state = None
            # CrewAI flow-metadata that generate_flow_class() copies over
            _start_methods: list = []
            _listeners: dict = {}
            _routers: set = set()
            _router_paths: dict = {}

        class _PlainCheckpointMixin:
            """Minimal stand-in for CheckpointMixin."""

        return _PlainFlow, _PlainCheckpointMixin

    def test_generate_flow_class_returns_class(
        self, mock_checkpoint_store, simple_flowconfig, mock_plain_bases
    ):
        """Should return a Flow class type."""
        _PlainFlow, _PlainMixin = mock_plain_bases
        executor = CheckpointedWorkflowExecutor(checkpoint_store=mock_checkpoint_store)
        with (
            patch(
                "core.workflows.executor.WorkflowExecutor.generate_flow_class",
                return_value=_PlainFlow,
            ),
            patch("core.workflows.checkpointed_executor.CheckpointMixin", _PlainMixin),
        ):
            flow_class = executor.generate_flow_class(simple_flowconfig)

        assert isinstance(flow_class, type)
        assert "Checkpointed" in flow_class.__name__

    def test_generated_class_has_checkpoint_store(
        self, mock_checkpoint_store, simple_flowconfig, mock_plain_bases
    ):
        """Generated class should have _checkpoint_store attribute."""
        _PlainFlow, _PlainMixin = mock_plain_bases
        executor = CheckpointedWorkflowExecutor(checkpoint_store=mock_checkpoint_store)
        with (
            patch(
                "core.workflows.executor.WorkflowExecutor.generate_flow_class",
                return_value=_PlainFlow,
            ),
            patch("core.workflows.checkpointed_executor.CheckpointMixin", _PlainMixin),
        ):
            flow_class = executor.generate_flow_class(simple_flowconfig)

        assert hasattr(flow_class, "_checkpoint_store")
        assert flow_class._checkpoint_store is mock_checkpoint_store

    def test_generated_class_has_execution_id_property(
        self, mock_checkpoint_store, simple_flowconfig, mock_plain_bases
    ):
        """Generated class should have execution_id property defined."""
        _PlainFlow, _PlainMixin = mock_plain_bases
        executor = CheckpointedWorkflowExecutor(checkpoint_store=mock_checkpoint_store)
        with (
            patch(
                "core.workflows.executor.WorkflowExecutor.generate_flow_class",
                return_value=_PlainFlow,
            ),
            patch("core.workflows.checkpointed_executor.CheckpointMixin", _PlainMixin),
        ):
            flow_class = executor.generate_flow_class(simple_flowconfig)

        # Check that execution_id property is defined on the class
        # Note: We can't instantiate the flow without CrewAI's state id requirements
        # but we can verify the class has the property defined
        assert hasattr(flow_class, "execution_id")

    def test_generated_class_has_post_node_execution_method(
        self, mock_checkpoint_store, simple_flowconfig, mock_plain_bases
    ):
        """Generated class should have _post_node_execution method defined."""
        _PlainFlow, _PlainMixin = mock_plain_bases
        executor = CheckpointedWorkflowExecutor(checkpoint_store=mock_checkpoint_store)
        with (
            patch(
                "core.workflows.executor.WorkflowExecutor.generate_flow_class",
                return_value=_PlainFlow,
            ),
            patch("core.workflows.checkpointed_executor.CheckpointMixin", _PlainMixin),
        ):
            flow_class = executor.generate_flow_class(simple_flowconfig)

        # Verify the method is defined on the class
        assert hasattr(flow_class, "_post_node_execution")
        # Check it's callable by looking at the class attribute
        assert callable(getattr(flow_class, "_post_node_execution", None))

    def test_post_node_execution_logic(
        self, mock_checkpoint_store, simple_flowconfig, mock_plain_bases
    ):
        """Test _post_node_execution method calls store.save correctly."""
        _PlainFlow, _PlainMixin = mock_plain_bases
        executor = CheckpointedWorkflowExecutor(checkpoint_store=mock_checkpoint_store)
        with (
            patch(
                "core.workflows.executor.WorkflowExecutor.generate_flow_class",
                return_value=_PlainFlow,
            ),
            patch("core.workflows.checkpointed_executor.CheckpointMixin", _PlainMixin),
        ):
            flow_class = executor.generate_flow_class(simple_flowconfig)

        # Create a mock flow instance to test the method
        mock_flow = MagicMock()
        mock_flow._execution_id = "test-execution-id"
        mock_flow.execution_id = "test-execution-id"
        mock_flow.state = MagicMock()
        mock_flow.state.model_dump.return_value = {"field1": "value1"}
        mock_flow._checkpoint_store = mock_checkpoint_store

        # Call the unbound method with mock self
        flow_class._post_node_execution(mock_flow, "test_node", {"result": "test"})

        mock_checkpoint_store.save.assert_called_once()
        call_args = mock_checkpoint_store.save.call_args
        assert call_args.kwargs["flow_id"] == "test-execution-id"
        assert call_args.kwargs["node_id"] == "test_node"
        assert call_args.kwargs["result"] == {"result": "test"}

class TestGetCheckpoints:
    """Tests for get_checkpoints method."""

    def test_get_checkpoints_returns_list(self):
        """Should return list of checkpoints from store."""
        mock_store = MagicMock()
        mock_store.list_for_flow.return_value = [
            {"node_id": "node1", "timestamp": "2026-01-28T12:00:00"},
            {"node_id": "node2", "timestamp": "2026-01-28T12:01:00"},
        ]

        executor = CheckpointedWorkflowExecutor(checkpoint_store=mock_store)
        result = executor.get_checkpoints("exec-123")

        mock_store.list_for_flow.assert_called_once_with("exec-123")
        assert len(result) == 2
        assert result[0]["node_id"] == "node1"

    def test_get_checkpoints_empty(self):
        """Should return empty list when no checkpoints."""
        mock_store = MagicMock()
        mock_store.list_for_flow.return_value = []

        executor = CheckpointedWorkflowExecutor(checkpoint_store=mock_store)
        result = executor.get_checkpoints("nonexistent")

        assert result == []

class TestResumeFrom:
    """Tests for resume_from method."""

    @pytest.mark.asyncio
    async def test_resume_from_loads_checkpoint(self):
        """Should load checkpoint from store."""
        mock_store = MagicMock()
        mock_store.load.return_value = {
            "state": {"field1": "value1"},
            "result": {"output": "test"},
            "timestamp": "2026-01-28T12:00:00",
        }

        executor = CheckpointedWorkflowExecutor(checkpoint_store=mock_store)
        result = await executor.resume_from("exec-123", "node1")

        mock_store.load.assert_called_once_with("exec-123", "node1")
        assert result["state"]["field1"] == "value1"

    @pytest.mark.asyncio
    async def test_resume_from_raises_on_missing_checkpoint(self):
        """Should raise ValueError when checkpoint not found."""
        mock_store = MagicMock()
        mock_store.load.return_value = None

        executor = CheckpointedWorkflowExecutor(checkpoint_store=mock_store)

        with pytest.raises(ValueError, match="No checkpoint found"):
            await executor.resume_from("exec-123", "nonexistent")

class TestDeleteExecution:
    """Tests for delete_execution method."""

    def test_delete_execution_calls_store(self):
        """Should call store.delete_flow."""
        mock_store = MagicMock()
        executor = CheckpointedWorkflowExecutor(checkpoint_store=mock_store)

        executor.delete_execution("exec-123")

        mock_store.delete_flow.assert_called_once_with("exec-123")

class TestIntegration:
    """Integration tests with real CheckpointStore.

    These tests require the ``plugins.checkpoint`` plugin to be installed
    (present in ``dryade-plugins/starter/checkpoint/``).  They are skipped
    automatically when the plugin is not available in the current checkout.
    """

    @pytest.fixture
    def temp_db(self, tmp_path):
        """Provide temporary database path."""
        return str(tmp_path / "test_checkpoints.db")

    @pytest.fixture(autouse=True)
    def _require_checkpoint_plugin(self):
        """Skip this test class if plugins.checkpoint.store is not importable."""
        pytest.importorskip(
            "plugins.checkpoint.store",
            reason="plugins.checkpoint plugin not present in this checkout",
        )

    def test_full_checkpoint_lifecycle(self, temp_db):
        """Test save, list, load, delete cycle using store directly."""
        from plugins.checkpoint.store import CheckpointStore

        store = CheckpointStore(temp_db)
        executor = CheckpointedWorkflowExecutor(checkpoint_store=store)

        execution_id = "test-execution-id"

        # Save checkpoint directly via store
        store.save(
            flow_id=execution_id,
            node_id="start",
            state={"started_at": "2026-01-28T12:00:00"},
            result="started",
        )

        # List checkpoints via executor
        checkpoints = executor.get_checkpoints(execution_id)
        assert len(checkpoints) == 1
        assert checkpoints[0]["node_id"] == "start"

        # Delete execution
        executor.delete_execution(execution_id)
        checkpoints = executor.get_checkpoints(execution_id)
        assert len(checkpoints) == 0

    def test_checkpoint_store_integration(self, temp_db):
        """Test executor properly integrates with CheckpointStore."""
        from plugins.checkpoint.store import CheckpointStore

        store = CheckpointStore(temp_db)
        executor = CheckpointedWorkflowExecutor(checkpoint_store=store)

        # Verify store is properly assigned
        assert executor._store is store

        # Test flow class generation creates class with store reference
        flowconfig = FlowConfig(
            name="store_test",
            description="Test store integration",
            nodes=[
                {"id": "start", "type": "start"},
                {"id": "end", "type": "end"},
            ],
            edges=[{"source": "start", "target": "end"}],
        )

        with patch(
            "core.workflows.executor.WorkflowExecutor.generate_flow_class",
            return_value=type("_PlainFlow", (), {}),
        ):
            flow_class = executor.generate_flow_class(flowconfig)
        assert flow_class._checkpoint_store is store
