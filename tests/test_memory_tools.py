"""Tests for memory block subsystem (Phase 115.3).

Covers:
- MemoryBlockStore CRUD operations
- compile_to_prompt XML generation
- 4 memory tool execution functions (insert, replace, rethink, search)
- Read-only block protection
- Char limit enforcement
- Total budget enforcement
"""

from unittest.mock import MagicMock, patch

import pytest

from core.orchestrator.memory_tools import (
    MemoryBlock,
    MemoryBlockStore,
    execute_memory_insert,
    execute_memory_replace,
    execute_memory_rethink,
    execute_memory_search,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def store():
    """Create a fresh MemoryBlockStore with DB operations mocked out."""
    s = MemoryBlockStore()
    # Patch DB operations to no-op for unit tests
    s._persist_block = MagicMock()
    s._load_from_db = MagicMock(return_value=[])
    s._delete_from_db = MagicMock()
    return s

@pytest.fixture()
def _reset_singleton():
    """Reset the global singleton before/after each test that uses it."""
    import core.orchestrator.memory_tools as mt

    original = mt._memory_block_store
    mt._memory_block_store = None
    yield
    mt._memory_block_store = original

@pytest.fixture()
def _mock_db():
    """Mock get_session for all tool execution functions."""
    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.query.return_value.filter_by.return_value.first.return_value = None
    mock_session.query.return_value.filter_by.return_value.all.return_value = []
    mock_session.query.return_value.filter_by.return_value.delete.return_value = 0

    with patch("core.orchestrator.memory_tools.MemoryBlockStore._persist_block"):
        with patch(
            "core.orchestrator.memory_tools.MemoryBlockStore._load_from_db", return_value=[]
        ):
            with patch("core.orchestrator.memory_tools.MemoryBlockStore._delete_from_db"):
                yield

# ---------------------------------------------------------------------------
# MemoryBlockStore CRUD Tests
# ---------------------------------------------------------------------------

class TestMemoryBlockStoreCRUD:
    """Test basic CRUD operations on MemoryBlockStore."""

    def test_create_and_get_block(self, store):
        """Create a block and verify get_block returns it."""
        block = MemoryBlock(
            agent_id="agent-1",
            label="user_prefs",
            value="Prefers concise responses",
            description="User preferences",
        )
        created = store.create_block(block)

        assert created.label == "user_prefs"
        assert created.value == "Prefers concise responses"

        retrieved = store.get_block("agent-1", "user_prefs")
        assert retrieved is not None
        assert retrieved.value == "Prefers concise responses"
        assert retrieved.description == "User preferences"

    def test_update_block(self, store):
        """Create a block, update its value, and verify the new value."""
        block = MemoryBlock(
            agent_id="agent-1",
            label="notes",
            value="Initial notes",
        )
        store.create_block(block)

        updated = store.update_block("agent-1", "notes", "Updated notes")
        assert updated.value == "Updated notes"

        retrieved = store.get_block("agent-1", "notes")
        assert retrieved.value == "Updated notes"

    def test_update_read_only_block_raises(self, store):
        """Attempting to update a read-only block should raise ValueError."""
        block = MemoryBlock(
            agent_id="agent-1",
            label="system",
            value="System data",
            read_only=True,
        )
        store.create_block(block)

        with pytest.raises(ValueError, match="read-only"):
            store.update_block("agent-1", "system", "new value")

    def test_char_limit_enforcement(self, store):
        """Updating with text exceeding char_limit should raise ValueError."""
        block = MemoryBlock(
            agent_id="agent-1",
            label="small",
            value="hi",
            char_limit=10,
        )
        store.create_block(block)

        with pytest.raises(ValueError, match="char_limit"):
            store.update_block("agent-1", "small", "x" * 20)

    def test_delete_block(self, store):
        """Create a block, delete it, verify get_block returns None."""
        block = MemoryBlock(
            agent_id="agent-1",
            label="temp",
            value="temporary data",
        )
        store.create_block(block)
        assert store.get_block("agent-1", "temp") is not None

        result = store.delete_block("agent-1", "temp")
        assert result is True
        assert store.get_block("agent-1", "temp") is None

    def test_delete_nonexistent_block_returns_false(self, store):
        """Deleting a block that doesn't exist returns False."""
        result = store.delete_block("agent-1", "nonexistent")
        assert result is False

# ---------------------------------------------------------------------------
# compile_to_prompt Tests
# ---------------------------------------------------------------------------

class TestCompileToPrompt:
    """Test XML compilation for system prompt injection."""

    def test_compile_to_prompt(self, store):
        """Compile 2 blocks and verify XML structure."""
        store.create_block(
            MemoryBlock(
                agent_id="agent-1",
                label="prefs",
                value="concise output",
                description="User preferences",
                char_limit=5000,
            )
        )
        store.create_block(
            MemoryBlock(
                agent_id="agent-1",
                label="context",
                value="working on migration",
                description="Current task",
                char_limit=5000,
            )
        )

        xml = store.compile_to_prompt("agent-1")
        assert "<memory_blocks>" in xml
        assert "</memory_blocks>" in xml
        assert "<prefs>" in xml
        assert "<value>concise output</value>" in xml
        assert "<context>" in xml
        assert "<value>working on migration</value>" in xml
        assert "<description>User preferences</description>" in xml
        assert "chars_current=14" in xml  # len("concise output")

    def test_compile_empty(self, store):
        """No blocks -> empty string."""
        result = store.compile_to_prompt("agent-no-blocks")
        assert result == ""

    def test_compile_disabled(self, store):
        """When memory_blocks_enabled=False, returns empty string."""
        store.create_block(MemoryBlock(agent_id="agent-1", label="test", value="data"))
        with patch("core.orchestrator.memory_tools.get_orchestration_config") as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.memory_blocks_enabled = False
            mock_config.return_value = mock_cfg
            result = store.compile_to_prompt("agent-1")
            assert result == ""

# ---------------------------------------------------------------------------
# Memory Tool Execution Function Tests
# ---------------------------------------------------------------------------

class TestMemoryInsert:
    """Test execute_memory_insert function."""

    def test_memory_insert_creates_block(self, _reset_singleton, _mock_db):
        """Inserting into non-existent label creates a new block."""
        import core.orchestrator.memory_tools as mt

        mt._memory_block_store = MemoryBlockStore()
        mt._memory_block_store._persist_block = MagicMock()
        mt._memory_block_store._load_from_db = MagicMock(return_value=[])
        mt._memory_block_store._delete_from_db = MagicMock()

        result = execute_memory_insert(agent_id="agent-1", label="new_block", new_str="Hello world")
        assert result["status"] == "ok"
        assert result["label"] == "new_block"
        assert result["chars"] == len("Hello world")

        # Verify block exists
        block = mt._memory_block_store.get_block("agent-1", "new_block")
        assert block is not None
        assert block.value == "Hello world"

    def test_memory_insert_appends(self, _reset_singleton, _mock_db):
        """Inserting into existing block appends text."""
        import core.orchestrator.memory_tools as mt

        mt._memory_block_store = MemoryBlockStore()
        mt._memory_block_store._persist_block = MagicMock()
        mt._memory_block_store._load_from_db = MagicMock(return_value=[])
        mt._memory_block_store._delete_from_db = MagicMock()

        # Create initial block
        execute_memory_insert(agent_id="agent-1", label="log", new_str="line1")

        # Append
        result = execute_memory_insert(agent_id="agent-1", label="log", new_str="line2")
        assert result["status"] == "ok"

        block = mt._memory_block_store.get_block("agent-1", "log")
        assert block.value == "line1\nline2"

class TestMemoryReplace:
    """Test execute_memory_replace function."""

    def test_memory_replace(self, _reset_singleton, _mock_db):
        """Replace text within a block."""
        import core.orchestrator.memory_tools as mt

        mt._memory_block_store = MemoryBlockStore()
        mt._memory_block_store._persist_block = MagicMock()
        mt._memory_block_store._load_from_db = MagicMock(return_value=[])
        mt._memory_block_store._delete_from_db = MagicMock()

        # Create block with initial text
        execute_memory_insert(agent_id="agent-1", label="data", new_str="old text here")

        result = execute_memory_replace(
            agent_id="agent-1", label="data", old_str="old", new_str="new"
        )
        assert result["status"] == "ok"
        assert result["label"] == "data"

        block = mt._memory_block_store.get_block("agent-1", "data")
        assert block.value == "new text here"

    def test_memory_replace_not_found_raises(self, _reset_singleton, _mock_db):
        """Replacing text that doesn't exist in the block raises ValueError."""
        import core.orchestrator.memory_tools as mt

        mt._memory_block_store = MemoryBlockStore()
        mt._memory_block_store._persist_block = MagicMock()
        mt._memory_block_store._load_from_db = MagicMock(return_value=[])
        mt._memory_block_store._delete_from_db = MagicMock()

        execute_memory_insert(agent_id="agent-1", label="data", new_str="abc")

        with pytest.raises(ValueError, match="not found"):
            execute_memory_replace(agent_id="agent-1", label="data", old_str="xyz", new_str="123")

class TestMemoryRethink:
    """Test execute_memory_rethink function."""

    def test_memory_rethink(self, _reset_singleton, _mock_db):
        """Rethink completely rewrites block contents."""
        import core.orchestrator.memory_tools as mt

        mt._memory_block_store = MemoryBlockStore()
        mt._memory_block_store._persist_block = MagicMock()
        mt._memory_block_store._load_from_db = MagicMock(return_value=[])
        mt._memory_block_store._delete_from_db = MagicMock()

        execute_memory_insert(agent_id="agent-1", label="summary", new_str="old summary")

        result = execute_memory_rethink(
            agent_id="agent-1", label="summary", new_memory="completely new summary"
        )
        assert result["status"] == "ok"
        assert result["chars"] == len("completely new summary")

        block = mt._memory_block_store.get_block("agent-1", "summary")
        assert block.value == "completely new summary"

class TestMemorySearch:
    """Test execute_memory_search function."""

    def test_memory_search(self, _reset_singleton, _mock_db):
        """Search across blocks finds matching content."""
        import core.orchestrator.memory_tools as mt

        mt._memory_block_store = MemoryBlockStore()
        mt._memory_block_store._persist_block = MagicMock()
        mt._memory_block_store._load_from_db = MagicMock(return_value=[])
        mt._memory_block_store._delete_from_db = MagicMock()

        execute_memory_insert(agent_id="agent-1", label="prefs", new_str="User prefers Python")
        execute_memory_insert(
            agent_id="agent-1", label="context", new_str="Working on Rust project"
        )

        result = execute_memory_search(agent_id="agent-1", query="python")
        assert len(result["results"]) == 1
        assert result["results"][0]["label"] == "prefs"
        assert "Python" in result["results"][0]["match"]

    def test_memory_search_no_results(self, _reset_singleton, _mock_db):
        """Search with no matches returns empty results."""
        import core.orchestrator.memory_tools as mt

        mt._memory_block_store = MemoryBlockStore()
        mt._memory_block_store._persist_block = MagicMock()
        mt._memory_block_store._load_from_db = MagicMock(return_value=[])
        mt._memory_block_store._delete_from_db = MagicMock()

        execute_memory_insert(agent_id="agent-1", label="data", new_str="hello world")

        result = execute_memory_search(agent_id="agent-1", query="zzzzz")
        assert len(result["results"]) == 0

class TestTotalBudgetEnforcement:
    """Test total memory budget enforcement."""

    def test_total_budget_enforcement(self, _reset_singleton, _mock_db):
        """Creating blocks that exceed total budget raises ValueError."""
        import core.orchestrator.memory_tools as mt

        mt._memory_block_store = MemoryBlockStore()
        mt._memory_block_store._persist_block = MagicMock()
        mt._memory_block_store._load_from_db = MagicMock(return_value=[])
        mt._memory_block_store._delete_from_db = MagicMock()

        # Patch config to have a low budget
        with patch("core.orchestrator.memory_tools.get_orchestration_config") as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.memory_blocks_enabled = True
            mock_cfg.memory_blocks_max_total_chars = 50
            mock_config.return_value = mock_cfg

            # First block: 30 chars -- should succeed
            block1 = MemoryBlock(agent_id="agent-1", label="b1", value="x" * 30)
            mt._memory_block_store.create_block(block1)

            # Second block: 30 chars -- should exceed budget (30 + 30 = 60 > 50)
            block2 = MemoryBlock(agent_id="agent-1", label="b2", value="y" * 30)
            with pytest.raises(ValueError, match="budget"):
                mt._memory_block_store.create_block(block2)
