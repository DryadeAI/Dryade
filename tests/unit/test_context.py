"""Unit tests for context hierarchy extension."""

import pytest

@pytest.mark.unit
class TestContextScope:
    """Tests for ContextScope enum."""

    def test_context_scope_values(self):
        """Test all context scope values exist."""
        from core.extensions.context import ContextScope

        assert ContextScope.CONVERSATION.value == "conversation"
        assert ContextScope.SESSION.value == "session"
        assert ContextScope.PROJECT.value == "project"
        assert ContextScope.USER.value == "user"
        assert ContextScope.GLOBAL.value == "global"

    def test_context_scope_hierarchy_order(self):
        """Test that scopes iterate in order from most to least specific."""
        from core.extensions.context import ContextScope

        scopes = list(ContextScope)
        # The enum should iterate conversation -> session -> project -> user -> global
        assert scopes[0] == ContextScope.CONVERSATION
        assert scopes[-1] == ContextScope.GLOBAL

@pytest.mark.unit
class TestContextStore:
    """Tests for ContextStore class."""

    def test_context_store_creation(self):
        """Test creating a new ContextStore."""
        from core.extensions.context import ContextScope, ContextStore

        store = ContextStore()
        # Should have empty stores for all scopes
        assert len(store._stores) == len(ContextScope)
        for scope in ContextScope:
            assert scope in store._stores
            assert len(store._stores[scope]) == 0

    def test_context_store_set_get_basic(self):
        """Test basic set and get operations."""
        from core.extensions.context import ContextScope, ContextStore

        store = ContextStore()
        store.set("test.key", "test_value", ContextScope.CONVERSATION)

        value = store.get("test.key")
        assert value == "test_value"

    def test_context_store_get_with_scope(self):
        """Test get with specific scope."""
        from core.extensions.context import ContextScope, ContextStore

        store = ContextStore()
        store.set("key", "conv_val", ContextScope.CONVERSATION)
        store.set("key", "global_val", ContextScope.GLOBAL)

        # Get from specific scope
        assert store.get("key", scope=ContextScope.CONVERSATION) == "conv_val"
        assert store.get("key", scope=ContextScope.GLOBAL) == "global_val"
        assert store.get("key", scope=ContextScope.SESSION) is None

    def test_context_hierarchy_cascade(self):
        """Test that get cascades through scope hierarchy."""
        from core.extensions.context import ContextScope, ContextStore

        store = ContextStore()
        # Only set at GLOBAL scope
        store.set("test.cascade", "global_value", ContextScope.GLOBAL)

        # Should find it when cascading from CONVERSATION
        value = store.get("test.cascade")
        assert value == "global_value"

    def test_context_value_isolation(self):
        """Test that values at different scopes are isolated."""
        from core.extensions.context import ContextScope, ContextStore

        store = ContextStore()
        store.set("key", "conv", ContextScope.CONVERSATION)
        store.set("key", "session", ContextScope.SESSION)
        store.set("key", "project", ContextScope.PROJECT)

        # Cascade should find CONVERSATION first (most specific)
        assert store.get("key") == "conv"

        # Direct scope access should get correct value
        assert store.get("key", scope=ContextScope.SESSION) == "session"
        assert store.get("key", scope=ContextScope.PROJECT) == "project"

    def test_get_context_creates_new_if_missing(self):
        """Test get_context creates a new store if none exists."""
        import core.extensions.context as ctx_module
        from core.extensions.context import ContextStore, get_context

        # Reset global context
        ctx_module._context = None

        store = get_context()
        assert isinstance(store, ContextStore)

        # Should return same instance
        store2 = get_context()
        assert store is store2

    def test_set_context_updates_existing(self):
        """Test set_context updates existing store."""
        from core.extensions.context import (
            ContextScope,
            get_context_value,
            set_context,
        )

        # Set a value
        set_context("my.key", "my_value", ContextScope.SESSION)

        # Get it back
        value = get_context_value("my.key")
        assert value == "my_value"

        # Update it
        set_context("my.key", "new_value", ContextScope.SESSION)
        value = get_context_value("my.key")
        assert value == "new_value"

    def test_context_store_delete(self):
        """Test deleting context values."""
        from core.extensions.context import ContextScope, ContextStore

        store = ContextStore()
        store.set("key", "value", ContextScope.CONVERSATION)
        assert store.get("key") == "value"

        store.delete("key")
        assert store.get("key") is None

    def test_context_store_delete_specific_scope(self):
        """Test deleting from specific scope only."""
        from core.extensions.context import ContextScope, ContextStore

        store = ContextStore()
        store.set("key", "conv", ContextScope.CONVERSATION)
        store.set("key", "global", ContextScope.GLOBAL)

        # Delete only from CONVERSATION
        store.delete("key", scope=ContextScope.CONVERSATION)

        # GLOBAL should still exist
        assert store.get("key") == "global"

    def test_context_store_clear_scope(self):
        """Test clearing all values at a scope."""
        from core.extensions.context import ContextScope, ContextStore

        store = ContextStore()
        store.set("key1", "val1", ContextScope.CONVERSATION)
        store.set("key2", "val2", ContextScope.CONVERSATION)
        store.set("key3", "val3", ContextScope.GLOBAL)

        store.clear_scope(ContextScope.CONVERSATION)

        assert store.get("key1", scope=ContextScope.CONVERSATION) is None
        assert store.get("key2", scope=ContextScope.CONVERSATION) is None
        assert store.get("key3", scope=ContextScope.GLOBAL) == "val3"

    def test_context_store_list_keys(self):
        """Test listing keys."""
        from core.extensions.context import ContextScope, ContextStore

        store = ContextStore()
        store.set("key1", "val1", ContextScope.CONVERSATION)
        store.set("key2", "val2", ContextScope.SESSION)

        # List all keys
        all_keys = store.list_keys()
        assert "key1" in all_keys
        assert "key2" in all_keys

        # List keys at specific scope
        conv_keys = store.list_keys(scope=ContextScope.CONVERSATION)
        assert "key1" in conv_keys
        assert "key2" not in conv_keys

    def test_context_store_export(self):
        """Test exporting context as dictionary."""
        from core.extensions.context import ContextScope, ContextStore

        store = ContextStore()
        store.set("key1", "val1", ContextScope.CONVERSATION)
        store.set("key2", "val2", ContextScope.GLOBAL)

        # Export specific scope
        conv_export = store.export(scope=ContextScope.CONVERSATION)
        assert conv_export == {"key1": "val1"}

        # Export all
        all_export = store.export()
        assert "key1" in all_export
        assert "key2" in all_export

    def test_context_store_get_with_scope_returns_tuple(self):
        """Test get_with_scope returns value and scope."""
        from core.extensions.context import ContextScope, ContextStore

        store = ContextStore()
        store.set("key", "value", ContextScope.PROJECT)

        value, scope = store.get_with_scope("key")
        assert value == "value"
        assert scope == ContextScope.PROJECT

    def test_context_store_get_default_value(self):
        """Test get returns default for missing keys."""
        from core.extensions.context import ContextStore

        store = ContextStore()
        assert store.get("nonexistent") is None
        assert store.get("nonexistent", default="default") == "default"

@pytest.mark.unit
class TestContextScopeDecorator:
    """Tests for context_scope decorator."""

    def test_context_scope_decorator(self):
        """Test context_scope decorator sets scope attribute."""
        from core.extensions.context import ContextScope, context_scope

        @context_scope(ContextScope.SESSION)
        def my_func():
            return "result"

        assert hasattr(my_func, "_context_scope")
        assert my_func._context_scope == ContextScope.SESSION
        assert my_func() == "result"

@pytest.mark.unit
class TestContextAdvanced:
    """Advanced tests for context management."""

    def test_nested_context_scopes(self):
        """Test nested context scopes with inheritance."""
        from core.extensions.context import ContextScope, ContextStore

        store = ContextStore()

        # Set values at different levels
        store.set("global.key", "global_value", ContextScope.GLOBAL)
        store.set("project.key", "project_value", ContextScope.PROJECT)
        store.set("session.key", "session_value", ContextScope.SESSION)
        store.set("conv.key", "conv_value", ContextScope.CONVERSATION)

        # Conversation scope should find all
        assert store.get("global.key") == "global_value"
        assert store.get("project.key") == "project_value"
        assert store.get("session.key") == "session_value"
        assert store.get("conv.key") == "conv_value"

    def test_context_value_inheritance(self):
        """Test that more specific scopes override less specific."""
        from core.extensions.context import ContextScope, ContextStore

        store = ContextStore()

        # Same key at multiple scopes
        store.set("setting", "global_default", ContextScope.GLOBAL)
        store.set("setting", "session_override", ContextScope.SESSION)

        # Should get more specific value
        assert store.get("setting") == "session_override"

        # Clear session, should fall back to global
        store.delete("setting", scope=ContextScope.SESSION)
        assert store.get("setting") == "global_default"

    def test_context_cleanup_on_exit(self):
        """Test context cleanup via clear_scope."""
        from core.extensions.context import ContextScope, ContextStore

        store = ContextStore()

        # Set up conversation context
        store.set("temp1", "val1", ContextScope.CONVERSATION)
        store.set("temp2", "val2", ContextScope.CONVERSATION)
        store.set("persistent", "val3", ContextScope.USER)

        # Clear conversation
        store.clear_scope(ContextScope.CONVERSATION)

        # Conversation keys should be gone
        assert store.get("temp1", scope=ContextScope.CONVERSATION) is None
        assert store.get("temp2", scope=ContextScope.CONVERSATION) is None

        # User key should remain
        assert store.get("persistent") == "val3"

    def test_context_store_thread_safety_pattern(self):
        """Test context store can be used in thread-safe pattern."""
        import threading

        from core.extensions.context import ContextScope, ContextStore

        store = ContextStore()
        results = []

        def worker(worker_id):
            # Each worker sets its own session context
            store.set(f"worker_{worker_id}", f"value_{worker_id}", ContextScope.SESSION)
            value = store.get(f"worker_{worker_id}")
            results.append((worker_id, value))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All workers should have stored their values
        assert len(results) == 5

    def test_context_value_inheritance_cascade(self):
        """Test full cascade through all scope levels."""
        from core.extensions.context import ContextScope, ContextStore

        store = ContextStore()

        # Only set at global
        store.set("cascading_key", "from_global", ContextScope.GLOBAL)

        # Should cascade from conversation down to global
        value, scope = store.get_with_scope("cascading_key")
        assert value == "from_global"
        assert scope == ContextScope.GLOBAL

    def test_export_specific_scope(self):
        """Test exporting a specific scope."""
        from core.extensions.context import ContextScope, ContextStore

        store = ContextStore()
        store.set("key1", "val1", ContextScope.CONVERSATION)
        store.set("key2", "val2", ContextScope.SESSION)

        conv_export = store.export(scope=ContextScope.CONVERSATION)
        assert "key1" in conv_export
        assert "key2" not in conv_export

    def test_export_all_scopes(self):
        """Test exporting all scopes."""
        from core.extensions.context import ContextScope, ContextStore

        store = ContextStore()
        store.set("key1", "val1", ContextScope.CONVERSATION)
        store.set("key2", "val2", ContextScope.SESSION)
        store.set("key3", "val3", ContextScope.GLOBAL)

        full_export = store.export()
        assert "key1" in full_export
        assert "key2" in full_export
        assert "key3" in full_export

    def test_delete_from_all_scopes(self):
        """Test deleting a key from all scopes."""
        from core.extensions.context import ContextScope, ContextStore

        store = ContextStore()
        store.set("key", "val1", ContextScope.CONVERSATION)
        store.set("key", "val2", ContextScope.SESSION)

        # Delete from all scopes
        store.delete("key")

        assert store.get("key") is None

    def test_list_keys_across_scopes(self):
        """Test listing keys across all scopes."""
        from core.extensions.context import ContextScope, ContextStore

        store = ContextStore()
        store.set("conv_key", "val", ContextScope.CONVERSATION)
        store.set("session_key", "val", ContextScope.SESSION)
        store.set("global_key", "val", ContextScope.GLOBAL)

        all_keys = store.list_keys()
        assert "conv_key" in all_keys
        assert "session_key" in all_keys
        assert "global_key" in all_keys

    def test_get_with_scope_missing_key(self):
        """Test get_with_scope with missing key."""
        from core.extensions.context import ContextStore

        store = ContextStore()
        value, scope = store.get_with_scope("nonexistent")

        assert value is None
        assert scope is None
