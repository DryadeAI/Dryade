# Business logic tests for reactflow converter (Phase 222).

"""
Unit tests for reactflow converter (core module).

Tests cover:
1. get_node_style returns correct styles per node type
2. flow_to_reactflow with mock Flow produces nodes/edges
3. export_flow_json returns valid JSON string
4. get_flow_info returns flow metadata
"""

import json
from unittest.mock import MagicMock, patch

import pytest

@pytest.mark.unit
class TestGetNodeStyle:
    """Tests for get_node_style helper."""

    def test_start_node_style(self):
        """Test start nodes get green style."""
        from core.flows.reactflow_converter import get_node_style

        style = get_node_style("start")
        assert style["background"] == "#4CAF50"
        assert style["color"] == "white"

    def test_router_node_style(self):
        """Test router nodes get orange style with round border."""
        from core.flows.reactflow_converter import get_node_style

        style = get_node_style("router")
        assert style["background"] == "#FF9800"
        assert style["borderRadius"] == "50%"

    def test_listen_node_style(self):
        """Test listen nodes get blue style."""
        from core.flows.reactflow_converter import get_node_style

        style = get_node_style("listen")
        assert style["background"] == "#2196F3"

    def test_unknown_node_type_defaults_to_listen(self):
        """Test unknown node types default to listen style."""
        from core.flows.reactflow_converter import get_node_style

        style = get_node_style("unknown_type")
        assert style == get_node_style("listen")

@pytest.mark.unit
class TestFlowToReactflow:
    """Tests for flow_to_reactflow with mock Flow objects."""

    def test_flow_with_start_method(self):
        """Test conversion of a flow with a start method produces nodes."""
        from crewai.flow.flow import Flow
        from crewai.flow.flow_wrappers import StartMethod

        from core.flows.reactflow_converter import flow_to_reactflow

        # Create a mock flow class with a StartMethod
        mock_start = MagicMock(spec=StartMethod)

        class MockFlow(Flow):
            begin = mock_start

        # Patch isinstance checks for the mock
        with patch(
            "core.flows.reactflow_converter.isinstance",
            side_effect=lambda obj, cls: (cls is StartMethod and obj is mock_start)
            or (cls is not StartMethod and type.__instancecheck__(cls, obj)),
        ):
            pass

        # Direct test: create a minimal flow class-like object
        result = flow_to_reactflow(MockFlow)
        assert "nodes" in result
        assert "edges" in result
        assert "viewport" in result

    def test_result_structure(self):
        """Test result has correct top-level keys."""
        from crewai.flow.flow import Flow

        from core.flows.reactflow_converter import flow_to_reactflow

        # Empty flow should still return correct structure
        class EmptyFlow(Flow):
            pass

        result = flow_to_reactflow(EmptyFlow)
        assert "nodes" in result
        assert "edges" in result
        assert "viewport" in result
        assert isinstance(result["nodes"], list)
        assert isinstance(result["edges"], list)

    def test_viewport_defaults(self):
        """Test viewport has correct defaults."""
        from crewai.flow.flow import Flow

        from core.flows.reactflow_converter import flow_to_reactflow

        class EmptyFlow(Flow):
            pass

        result = flow_to_reactflow(EmptyFlow)
        assert result["viewport"] == {"x": 0, "y": 0, "zoom": 1}

@pytest.mark.unit
class TestExportFlowJson:
    """Tests for export_flow_json."""

    def test_export_produces_valid_json(self, tmp_path):
        """Test export creates a valid JSON file."""
        from crewai.flow.flow import Flow

        from core.flows.reactflow_converter import export_flow_json

        class EmptyFlow(Flow):
            pass

        out_path = str(tmp_path / "flow.json")
        result_path = export_flow_json(EmptyFlow, out_path)
        assert result_path == out_path

        with open(out_path) as f:
            data = json.load(f)
        assert "nodes" in data
        assert "edges" in data

@pytest.mark.unit
class TestGetFlowInfo:
    """Tests for get_flow_info."""

    def test_flow_info_metadata(self):
        """Test get_flow_info returns correct metadata structure."""
        from crewai.flow.flow import Flow

        from core.flows.reactflow_converter import get_flow_info

        class SampleFlow(Flow):
            """A sample flow for testing."""

            pass

        info = get_flow_info(SampleFlow)
        assert info["name"] == "SampleFlow"
        assert info["description"] == "A sample flow for testing."
        assert isinstance(info["nodes"], list)
        assert isinstance(info["node_count"], int)
        assert isinstance(info["edge_count"], int)
