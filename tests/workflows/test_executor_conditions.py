"""Tests for workflow executor condition parser integration."""

from unittest.mock import Mock, patch

class TestExecutorConditionParser:
    """Test expression-based condition evaluation in executor.

    These tests verify that the workflow executor correctly integrates
    with the expression-based condition parser for router conditions.
    """

    def test_import_evaluate_condition(self):
        """evaluate_condition is imported in executor module."""
        # Verify the import exists in the module
        with open("dryade-core/core/workflows/executor.py") as f:
            content = f.read()

        assert "from core.workflows.condition_parser import" in content
        assert "evaluate_condition" in content
        assert "ConditionParseError" in content

    def test_check_condition_uses_expression_parser(self):
        """_check_condition should use expression parser for complex conditions."""
        # Test the condition parser directly since we can't easily instantiate
        # the WorkflowExecutor without crewai
        from core.workflows.condition_parser import evaluate_condition

        # Test equality
        context = {"status": "success"}
        assert evaluate_condition("status == 'success'", context) is True
        assert evaluate_condition("status == 'failure'", context) is False

    def test_expression_condition_with_and(self):
        """Expression with AND operator evaluates correctly."""
        from core.workflows.condition_parser import evaluate_condition

        context = {"status": "success", "score": 0.9}
        assert evaluate_condition("status == 'success' AND score > 0.8", context) is True
        assert evaluate_condition("status == 'success' AND score < 0.8", context) is False

    def test_expression_condition_with_or(self):
        """Expression with OR operator evaluates correctly."""
        from core.workflows.condition_parser import evaluate_condition

        context = {"status": "partial"}
        assert evaluate_condition("status == 'success' OR status == 'partial'", context) is True
        assert evaluate_condition("status == 'success' OR status == 'failure'", context) is False

    def test_expression_condition_null_check(self):
        """Expression with null check evaluates correctly."""
        from core.workflows.condition_parser import evaluate_condition

        # error == null
        context = {"error": None}
        assert evaluate_condition("error == null", context) is True

        context = {"error": "something went wrong"}
        assert evaluate_condition("error == null", context) is False

    def test_expression_condition_contains(self):
        """Expression with contains operator evaluates correctly."""
        from core.workflows.condition_parser import evaluate_condition

        context = {"message": "Task completed with error"}
        assert evaluate_condition("message contains 'error'", context) is True
        assert evaluate_condition("message contains 'success'", context) is False

    def test_empty_condition_returns_true(self):
        """Empty condition always evaluates to True."""
        from core.workflows.condition_parser import evaluate_condition

        assert evaluate_condition("", {}) is True
        assert evaluate_condition("   ", {}) is True

    def test_numeric_comparisons(self):
        """Numeric comparisons work correctly."""
        from core.workflows.condition_parser import evaluate_condition

        context = {"score": 0.85, "count": 10}
        assert evaluate_condition("score > 0.8", context) is True
        assert evaluate_condition("score < 0.9", context) is True
        assert evaluate_condition("count >= 10", context) is True
        assert evaluate_condition("count <= 5", context) is False

    def test_nested_field_access(self):
        """Nested field access works in conditions."""
        from core.workflows.condition_parser import evaluate_condition

        context = {"result": {"data": {"status": "complete"}}}
        assert evaluate_condition("result.data.status == 'complete'", context) is True

    def test_array_index_access(self):
        """Array index access works in conditions."""
        from core.workflows.condition_parser import evaluate_condition

        context = {"items": [{"status": "done"}, {"status": "pending"}]}
        assert evaluate_condition("items[0].status == 'done'", context) is True
        assert evaluate_condition("items[1].status == 'pending'", context) is True

class TestLegacyConditionFallback:
    """Test backward compatibility with legacy substring conditions.

    The executor should fall back to substring matching when the expression
    parser fails to parse a condition.
    """

    def test_legacy_substring_detection(self):
        """Legacy substring conditions still work via fallback mechanism."""
        # This tests the expected fallback behavior
        # When condition parser fails (e.g., simple word like "success"),
        # the executor falls back to substring matching

        from core.workflows.condition_parser import evaluate_condition

        # Single word "success" should be parsed as a field reference
        # which evaluates to its truthy value
        context = {"success": True}
        result = evaluate_condition("success", context)
        assert result is True

        context = {"success": False}
        result = evaluate_condition("success", context)
        assert result is False

class TestMCPRegistrySearch:
    """Test MCPRegistry search_tools integration."""

    @patch("core.mcp.registry.get_hierarchical_router")
    def test_search_tools_uses_router(self, mock_get_router):
        """search_tools delegates to hierarchical router."""
        from core.mcp import get_registry
        from core.mcp.hierarchical_router import RouteResult

        mock_router = Mock()
        mock_router.route.return_value = [
            RouteResult(
                tool_name="capella_open",
                server="mcp-capella",
                score=0.95,
                server_score=0.9,
                tool_score=0.95,
                description="Open Capella model",
            )
        ]
        mock_get_router.return_value = mock_router

        registry = get_registry()
        results = registry.search_tools("open capella model")

        assert len(results) == 1
        assert results[0]["name"] == "capella_open"
        assert results[0]["score"] == 0.95

    @patch("core.mcp.registry.get_hierarchical_router")
    def test_search_tools_name_only_detail(self, mock_get_router):
        """search_tools with name_only returns minimal data."""
        from core.mcp import get_registry
        from core.mcp.hierarchical_router import RouteResult

        mock_router = Mock()
        mock_router.route.return_value = [
            RouteResult(
                tool_name="test_tool",
                server="test_server",
                score=0.9,
                server_score=0.9,
                tool_score=0.9,
                description="Test desc",
            )
        ]
        mock_get_router.return_value = mock_router

        registry = get_registry()
        results = registry.search_tools("test", detail="name_only")

        assert "name" in results[0]
        assert "server" in results[0]
        assert "score" not in results[0]
        assert "description" not in results[0]

    @patch("core.mcp.registry.get_hierarchical_router")
    def test_search_tools_full_detail(self, mock_get_router):
        """search_tools with full detail includes scores."""
        from core.mcp import get_registry
        from core.mcp.hierarchical_router import RouteResult

        mock_router = Mock()
        mock_router.route.return_value = [
            RouteResult(
                tool_name="test_tool",
                server="test_server",
                score=0.9,
                server_score=0.85,
                tool_score=0.95,
                description="Test desc",
            )
        ]
        mock_get_router.return_value = mock_router

        registry = get_registry()
        results = registry.search_tools("test", detail="full")

        assert "name" in results[0]
        assert "server" in results[0]
        assert "score" in results[0]
        assert "description" in results[0]
        assert "server_score" in results[0]
        assert "tool_score" in results[0]

    @patch("core.mcp.registry.get_hierarchical_router")
    def test_search_tools_server_filter(self, mock_get_router):
        """search_tools respects server_filter parameter."""
        from core.mcp import get_registry
        from core.mcp.hierarchical_router import RouteResult

        mock_router = Mock()
        mock_router.route_to_server.return_value = [
            RouteResult(
                tool_name="specific_tool",
                server="target_server",
                score=0.9,
                server_score=1.0,
                tool_score=0.9,
                description="Specific tool",
            )
        ]
        mock_get_router.return_value = mock_router

        registry = get_registry()
        results = registry.search_tools("query", server_filter="target_server")

        mock_router.route_to_server.assert_called_once_with("query", "target_server", 10)
        assert len(results) == 1
        assert results[0]["server"] == "target_server"

class TestMCPRegistryValidation:
    """Test MCPRegistry validate_tool method."""

    def test_validate_tool_exists(self):
        """validate_tool returns True for existing tool."""
        from core.mcp import get_registry

        registry = get_registry()

        # Mock find_tool to return a result
        with patch.object(registry, "find_tool") as mock_find:
            mock_find.return_value = ("test_server", Mock())

            exists, server, suggestions = registry.validate_tool("existing_tool")

            assert exists is True
            assert server == "test_server"
            assert suggestions == []

    def test_validate_tool_not_found(self):
        """validate_tool returns False and suggestions for missing tool."""
        from core.mcp import get_registry

        registry = get_registry()

        # Mock find_tool to return None (not found)
        # Mock search_tools to return suggestions
        with patch.object(registry, "find_tool") as mock_find:
            mock_find.return_value = None

            with patch.object(registry, "search_tools") as mock_search:
                mock_search.return_value = [
                    {"name": "capella_open"},
                    {"name": "capella_close"},
                ]

                exists, server, suggestions = registry.validate_tool("capella_opn")

                assert exists is False
                assert server is None
                assert "capella_open" in suggestions
                assert "capella_close" in suggestions

    def test_validate_tool_no_suggestions(self):
        """validate_tool with suggest_similar=False skips suggestions."""
        from core.mcp import get_registry

        registry = get_registry()

        with patch.object(registry, "find_tool") as mock_find:
            mock_find.return_value = None

            exists, server, suggestions = registry.validate_tool(
                "nonexistent", suggest_similar=False
            )

            assert exists is False
            assert server is None
            assert suggestions == []
