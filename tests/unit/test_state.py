"""Unit tests for state export/inject protocol."""

import pytest

@pytest.mark.unit
class TestExportStateDecorator:
    """Tests for @export_state decorator.

    Note: The decorator uses the pattern @export_state(export_key="result_key")
    where export_key is what goes into _exports, and result_key is the key
    to look up in the function result dict.
    """

    def test_export_state_decorator_adds_exports(self):
        """Test that export_state decorator adds _exports to result."""
        from core.extensions.state import export_state

        # export_key="result_key" means: export result["result_key"] as "_exports[export_key]"
        @export_state(**{"mbse.session_id": "session_id"})
        def my_tool() -> dict:
            return {"session_id": "sess_123", "status": "ok"}

        result = my_tool()
        assert "_exports" in result
        assert result["_exports"]["mbse.session_id"] == "sess_123"

    def test_export_state_multiple_mappings(self):
        """Test exporting multiple state values."""
        from core.extensions.state import export_state

        @export_state(**{"mbse.session_id": "session_id", "mbse.count": "count"})
        def my_tool() -> dict:
            return {"session_id": "sess_abc", "count": 42, "other": "data"}

        result = my_tool()
        assert result["_exports"]["mbse.session_id"] == "sess_abc"
        assert result["_exports"]["mbse.count"] == 42
        assert "other" not in result["_exports"]

    def test_export_state_skips_none_values(self):
        """Test that None values are not exported."""
        from core.extensions.state import export_state

        @export_state(**{"mbse.session_id": "session_id", "mbse.optional": "optional"})
        def my_tool() -> dict:
            return {"session_id": "sess_123", "optional": None}

        result = my_tool()
        assert "mbse.session_id" in result["_exports"]
        assert "mbse.optional" not in result["_exports"]

    def test_export_state_skips_missing_keys(self):
        """Test that missing keys in result are not exported."""
        from core.extensions.state import export_state

        @export_state(**{"mbse.session_id": "session_id", "mbse.missing": "missing"})
        def my_tool() -> dict:
            return {"session_id": "sess_123"}  # No 'missing' key

        result = my_tool()
        assert "mbse.session_id" in result["_exports"]
        assert "mbse.missing" not in result["_exports"]

    def test_export_state_non_dict_result(self):
        """Test that non-dict results pass through unchanged."""
        from core.extensions.state import export_state

        @export_state(session_id="mbse.session_id")
        def my_tool() -> str:
            return "just a string"

        result = my_tool()
        assert result == "just a string"

    def test_export_state_preserves_metadata(self):
        """Test that decorator sets _state_exports attribute."""
        from core.extensions.state import export_state

        @export_state(**{"mbse.session_id": "session_id"})
        def my_tool() -> dict:
            return {}

        assert hasattr(my_tool, "_state_exports")
        assert my_tool._state_exports == {"mbse.session_id": "session_id"}

@pytest.mark.unit
class TestRequiresStateDecorator:
    """Tests for @requires_state decorator."""

    def test_requires_state_decorator_sets_attribute(self):
        """Test that requires_state sets _state_requires attribute."""
        from core.extensions.state import requires_state

        @requires_state("mbse.session_id", "mbse.model_path")
        def my_tool(session_id=None, model_path=None) -> dict:
            return {"session_id": session_id}

        assert hasattr(my_tool, "_state_requires")
        assert "mbse.session_id" in my_tool._state_requires
        assert "mbse.model_path" in my_tool._state_requires

    def test_requires_state_empty(self):
        """Test requires_state with no requirements."""
        from core.extensions.state import requires_state

        @requires_state()
        def my_tool() -> dict:
            return {}

        assert hasattr(my_tool, "_state_requires")
        assert len(my_tool._state_requires) == 0

@pytest.mark.unit
class TestResolveState:
    """Tests for resolve_state function."""

    def test_resolve_state_basic(self):
        """Test basic state resolution from context."""
        from core.extensions.state import requires_state, resolve_state

        @requires_state("mbse.session_id")
        def my_tool(session_id=None) -> dict:
            return {"session_id": session_id}

        context = {"mbse.session_id": "sess_from_context"}
        args = {}

        resolved = resolve_state(my_tool, args, context)
        assert resolved["session_id"] == "sess_from_context"

    def test_resolve_state_does_not_override_provided(self):
        """Test that provided args are not overridden."""
        from core.extensions.state import requires_state, resolve_state

        @requires_state("mbse.session_id")
        def my_tool(session_id=None) -> dict:
            return {}

        context = {"mbse.session_id": "from_context"}
        args = {"session_id": "from_args"}

        resolved = resolve_state(my_tool, args, context)
        assert resolved["session_id"] == "from_args"

    def test_resolve_state_with_no_requirements(self):
        """Test resolve_state with function that has no requirements."""
        from core.extensions.state import resolve_state

        def plain_tool(arg1=None) -> dict:
            return {}

        args = {"arg1": "value"}
        context = {"mbse.session_id": "sess_123"}

        resolved = resolve_state(plain_tool, args, context)
        assert resolved == args

    def test_resolve_state_missing_context_value(self):
        """Test resolve_state when context value is missing."""
        from core.extensions.state import requires_state, resolve_state

        @requires_state("mbse.session_id")
        def my_tool(session_id=None) -> dict:
            return {}

        context = {}  # No session_id in context
        args = {}

        resolved = resolve_state(my_tool, args, context)
        # Should not add missing value
        assert "session_id" not in resolved

    def test_resolve_state_extracts_param_name_from_key(self):
        """Test that param name is extracted from dotted key."""
        from core.extensions.state import requires_state, resolve_state

        @requires_state("mbse.deeply.nested.value")
        def my_tool(value=None) -> dict:
            return {}

        context = {"mbse.deeply.nested.value": "the_value"}
        args = {}

        resolved = resolve_state(my_tool, args, context)
        assert resolved["value"] == "the_value"

@pytest.mark.unit
class TestExtractExports:
    """Tests for extract_exports function."""

    def test_extract_exports_from_single_result(self):
        """Test extracting exports from a single result."""
        from core.extensions.state import extract_exports

        results = [{"session_id": "sess_123", "_exports": {"mbse.session_id": "sess_123"}}]

        exports = extract_exports(results)
        assert exports["mbse.session_id"] == "sess_123"

    def test_extract_exports_from_multiple_results(self):
        """Test extracting exports from multiple results."""
        from core.extensions.state import extract_exports

        results = [
            {"_exports": {"mbse.session_id": "sess_1"}},
            {"_exports": {"mbse.model_path": "/path/to/model"}},
        ]

        exports = extract_exports(results)
        assert exports["mbse.session_id"] == "sess_1"
        assert exports["mbse.model_path"] == "/path/to/model"

    def test_extract_exports_ignores_results_without_exports(self):
        """Test that results without _exports are ignored."""
        from core.extensions.state import extract_exports

        results = [
            {"data": "value"},  # No _exports
            {"_exports": {"key": "value"}},
            {"other": "data"},  # No _exports
        ]

        exports = extract_exports(results)
        assert exports == {"key": "value"}

    def test_extract_exports_ignores_none_values(self):
        """Test that None values in exports are ignored."""
        from core.extensions.state import extract_exports

        results = [{"_exports": {"key1": "value1", "key2": None}}]

        exports = extract_exports(results)
        assert "key1" in exports
        assert "key2" not in exports

    def test_extract_exports_empty_results(self):
        """Test extract_exports with empty results list."""
        from core.extensions.state import extract_exports

        exports = extract_exports([])
        assert exports == {}

    def test_extract_exports_non_dict_results(self):
        """Test that non-dict results are handled."""
        from core.extensions.state import extract_exports

        results = [
            "string_result",
            123,
            {"_exports": {"key": "value"}},
        ]

        exports = extract_exports(results)
        assert exports == {"key": "value"}

@pytest.mark.unit
class TestStateMetadata:
    """Tests for state metadata functions."""

    def test_get_state_metadata(self):
        """Test getting state metadata from decorated function."""
        from core.extensions.state import export_state, get_state_metadata, requires_state

        @export_state(**{"mbse.session_id": "session_id"})
        @requires_state("mbse.model_path")
        def my_tool():
            return {}

        metadata = get_state_metadata(my_tool)
        assert "exports" in metadata
        assert "requires" in metadata
        assert metadata["exports"] == {"mbse.session_id": "session_id"}
        assert "mbse.model_path" in metadata["requires"]

    def test_get_state_metadata_plain_function(self):
        """Test get_state_metadata on function without decorators."""
        from core.extensions.state import get_state_metadata

        def plain_func():
            return {}

        metadata = get_state_metadata(plain_func)
        assert metadata["exports"] == {}
        assert metadata["requires"] == []

    def test_has_state_decorators(self):
        """Test has_state_decorators function."""
        from core.extensions.state import export_state, has_state_decorators, requires_state

        @export_state(key="value")
        def with_export():
            pass

        @requires_state("key")
        def with_requires():
            pass

        def without_decorators():
            pass

        assert has_state_decorators(with_export) is True
        assert has_state_decorators(with_requires) is True
        assert has_state_decorators(without_decorators) is False

@pytest.mark.unit
class TestMultiValueStateStore:
    """Tests for MultiValueStateStore class."""

    def test_multi_value_store_creation(self):
        """Test creating a new MultiValueStateStore."""
        from core.extensions.state import MultiValueStateStore

        store = MultiValueStateStore()
        assert len(store._store) == 0

    def test_multi_value_store_export_single(self):
        """Test exporting a single value."""
        from core.extensions.state import MultiValueStateStore

        store = MultiValueStateStore()
        store.export("mbse.session_id", "sess_123", "tool_a")

        value = store.get("mbse.session_id")
        assert value == "sess_123"

    def test_multi_value_store_conflict_detection(self):
        """Test conflict detection with multiple values."""
        from core.extensions.state import MultiValueStateStore

        store = MultiValueStateStore()
        store.export("mbse.session_id", "sess_1", "tool_a")
        store.export("mbse.session_id", "sess_2", "tool_b")

        # get() returns None when conflict exists
        value = store.get("mbse.session_id")
        assert value is None

        # has_pending_conflict() should return True
        assert store.has_pending_conflict("mbse.session_id") is True

    def test_multi_value_store_check_conflict(self):
        """Test check_conflict returns StateConflict."""
        from core.extensions.state import MultiValueStateStore

        store = MultiValueStateStore()
        store.export("key", "val1", "src1")
        store.export("key", "val2", "src2")

        conflict = store.check_conflict("key", required_by="my_tool")
        assert conflict is not None
        assert conflict.state_key == "key"
        assert len(conflict.candidates) == 2
        assert conflict.required_by == "my_tool"

    def test_multi_value_store_resolve_conflict(self):
        """Test resolving a conflict."""
        from core.extensions.state import MultiValueStateStore

        store = MultiValueStateStore()
        store.export("key", "val1", "src1")
        store.export("key", "val2", "src2")

        # Resolve by selecting val1
        result = store.resolve_conflict("key", "val1")
        assert result is True

        # Now get should return the selected value
        value = store.get("key")
        assert value == "val1"

        # Conflict should be resolved
        assert store.has_pending_conflict("key") is False

    def test_multi_value_store_resolve_invalid_value(self):
        """Test that resolving with invalid value returns False."""
        from core.extensions.state import MultiValueStateStore

        store = MultiValueStateStore()
        store.export("key", "val1", "src1")

        result = store.resolve_conflict("key", "not_a_candidate")
        assert result is False

    def test_multi_value_store_clear(self):
        """Test clearing state values."""
        from core.extensions.state import MultiValueStateStore

        store = MultiValueStateStore()
        store.export("key1", "val1", "src1")
        store.export("key2", "val2", "src2")

        store.clear("key1")
        assert store.get("key1") is None
        assert store.get("key2") == "val2"

        store.clear()  # Clear all
        assert store.get("key2") is None

    def test_multi_value_store_to_dict(self):
        """Test exporting store to dictionary."""
        from core.extensions.state import MultiValueStateStore

        store = MultiValueStateStore()
        store.export("key1", "val1", "src1")
        store.export("key2", "val2", "src2")

        result = store.to_dict()
        assert result["key1"] == "val1"
        assert result["key2"] == "val2"

    def test_multi_value_store_get_all_conflicts(self):
        """Test getting all pending conflicts."""
        from core.extensions.state import MultiValueStateStore

        store = MultiValueStateStore()
        store.export("key1", "val1a", "src1")
        store.export("key1", "val1b", "src2")
        store.export("key2", "val2", "src1")  # No conflict

        conflicts = store.get_all_conflicts()
        assert len(conflicts) == 1
        assert conflicts[0].state_key == "key1"

@pytest.mark.unit
class TestGlobalStateStore:
    """Tests for global state store functions."""

    def test_get_state_store(self):
        """Test getting global state store."""
        from core.extensions.state import MultiValueStateStore, get_state_store, reset_state_store

        reset_state_store()  # Start fresh
        store = get_state_store()
        assert isinstance(store, MultiValueStateStore)

        # Should return same instance
        store2 = get_state_store()
        assert store is store2

    def test_reset_state_store(self):
        """Test resetting global state store."""
        from core.extensions.state import get_state_store, reset_state_store

        store1 = get_state_store()
        store1.export("key", "value", "src")

        reset_state_store()
        store2 = get_state_store()

        # Should be a new instance
        assert store1 is not store2
        assert store2.get("key") is None

@pytest.mark.unit
class TestStateAdvanced:
    """Advanced tests for state management."""

    def test_state_rollback_capabilities(self):
        """Test state rollback by clearing and restoring."""
        from core.extensions.state import MultiValueStateStore

        store = MultiValueStateStore()
        store.export("key1", "val1", "src1")
        store.export("key2", "val2", "src2")

        # Save state
        snapshot = store.to_dict()

        # Modify state
        store.export("key3", "val3", "src3")
        assert store.get("key3") == "val3"

        # Rollback by clearing and restoring
        store.clear()
        for key, value in snapshot.items():
            store.export(key, value, "rollback")

        assert store.get("key1") == "val1"
        assert store.get("key2") == "val2"
        assert store.get("key3") is None

    def test_concurrent_state_access(self):
        """Test concurrent state access pattern."""
        import threading

        from core.extensions.state import MultiValueStateStore

        store = MultiValueStateStore()
        results = []

        def writer(thread_id):
            store.export(f"key_{thread_id}", f"val_{thread_id}", f"src_{thread_id}")
            value = store.get(f"key_{thread_id}")
            results.append(value)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All writes should succeed
        assert len(results) == 5
        assert all(r is not None for r in results)

    def test_state_persistence_via_serialization(self):
        """Test state can be serialized and deserialized."""
        import json

        from core.extensions.state import MultiValueStateStore

        store = MultiValueStateStore()
        store.export("key1", "val1", "src1")
        store.export("key2", 123, "src2")

        # Serialize
        data = store.to_dict()
        serialized = json.dumps(data)

        # Deserialize
        deserialized = json.loads(serialized)

        assert deserialized["key1"] == "val1"
        assert deserialized["key2"] == 123

    def test_state_initialization_and_updates(self):
        """Test state initialization and incremental updates."""
        from core.extensions.state import MultiValueStateStore

        store = MultiValueStateStore()

        # Initialize
        store.export("counter", 0, "init")
        assert store.get("counter") == 0

        # Update
        store.clear("counter")
        store.export("counter", 1, "update1")
        assert store.get("counter") == 1

        store.clear("counter")
        store.export("counter", 2, "update2")
        assert store.get("counter") == 2

    def test_resolve_conflict_removes_from_pending(self):
        """Test that resolving a conflict removes it from pending list."""
        from core.extensions.state import MultiValueStateStore

        store = MultiValueStateStore()
        store.export("key", "val1", "src1")
        store.export("key", "val2", "src2")

        # Should have conflict
        assert store.has_pending_conflict("key") is True

        # Resolve
        store.resolve_conflict("key", "val1")

        # Should no longer have conflict
        assert store.has_pending_conflict("key") is False
        assert len(store.get_all_conflicts()) == 0

    def test_check_conflict_returns_none_for_no_conflict(self):
        """Test check_conflict returns None when no conflict exists."""
        from core.extensions.state import MultiValueStateStore

        store = MultiValueStateStore()
        store.export("key", "val", "src")

        conflict = store.check_conflict("key", "my_tool")
        assert conflict is None

    def test_export_state_decorator_with_nested_dict(self):
        """Test export_state with nested dictionary results."""
        from core.extensions.state import export_state

        @export_state(**{"mbse.data": "nested"})
        def my_tool() -> dict:
            return {"nested": {"inner": "value"}, "other": "data"}

        result = my_tool()
        assert result["_exports"]["mbse.data"]["inner"] == "value"

    def test_resolve_state_with_multiple_requirements(self):
        """Test resolve_state with multiple state requirements."""
        from core.extensions.state import requires_state, resolve_state

        @requires_state("mbse.session_id", "mbse.model_path", "mbse.layer")
        def my_tool(session_id=None, model_path=None, layer=None) -> dict:
            return {}

        context = {
            "mbse.session_id": "sess_123",
            "mbse.model_path": "/path",
            "mbse.layer": "LA",
        }
        args = {}

        resolved = resolve_state(my_tool, args, context)

        assert resolved["session_id"] == "sess_123"
        assert resolved["model_path"] == "/path"
        assert resolved["layer"] == "LA"

    def test_extract_exports_merges_from_multiple(self):
        """Test that extract_exports merges exports from multiple results."""
        from core.extensions.state import extract_exports

        results = [
            {"_exports": {"key1": "val1", "key2": "val2"}},
            {"_exports": {"key3": "val3"}},
        ]

        exports = extract_exports(results)

        assert exports["key1"] == "val1"
        assert exports["key2"] == "val2"
        assert exports["key3"] == "val3"

    def test_state_conflict_candidate_structure(self):
        """Test StateConflict candidate structure."""
        from core.extensions.state import MultiValueStateStore

        store = MultiValueStateStore()
        store.export("key", "val1", "source_a")
        store.export("key", "val2", "source_b")

        conflict = store.check_conflict("key", "my_tool")

        assert len(conflict.candidates) == 2
        # Candidates should have value and source
        assert all("value" in c or "val" in str(c) for c in conflict.candidates)

    def test_to_dict_excludes_conflicts(self):
        """Test to_dict only returns resolved values, not conflicts."""
        from core.extensions.state import MultiValueStateStore

        store = MultiValueStateStore()
        store.export("resolved_key", "val", "src")
        store.export("conflict_key", "val1", "src1")
        store.export("conflict_key", "val2", "src2")

        result = store.to_dict()

        # Should include resolved
        assert "resolved_key" in result

        # Should not include unresolved conflict
        assert result.get("conflict_key") is None

    def test_export_state_decorator_chaining(self):
        """Test export_state can be chained with other decorators."""
        from core.extensions.state import export_state, requires_state

        @export_state(**{"output.result": "result"})
        @requires_state("input.value")
        def my_tool(value=None) -> dict:
            return {"result": f"processed_{value}"}

        # Should have both decorators applied
        assert hasattr(my_tool, "_state_exports")
        assert hasattr(my_tool, "_state_requires")

    def test_get_state_metadata_combines_both_decorators(self):
        """Test get_state_metadata returns both exports and requires."""
        from core.extensions.state import export_state, get_state_metadata, requires_state

        @export_state(**{"out.key": "key"})
        @requires_state("in.key")
        def my_tool():
            return {}

        metadata = get_state_metadata(my_tool)

        assert "out.key" in metadata["exports"]
        assert "in.key" in metadata["requires"]
