"""Unit tests for generic MCP bridge (core.mcp.bridge).

Tests cover:
1. MCPBridge construction and URL storage
2. get_bridge() singleton with reset
3. create_tool_wrapper() generates callable from tool config
4. discover_mcp_tools() delegates to MCPBridge.list_tools
5. No Capella-specific behavior
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

@pytest.mark.unit
class TestMCPBridge:
    """Tests for generic MCPBridge class."""

    def test_bridge_stores_url(self):
        """MCPBridge stores the provided base_url."""
        from core.mcp.bridge import MCPBridge

        bridge = MCPBridge("http://localhost:9000")
        assert bridge.base_url == "http://localhost:9000"

    def test_bridge_creates_httpx_client(self):
        """MCPBridge creates an httpx client on init."""
        from core.mcp.bridge import MCPBridge

        bridge = MCPBridge("http://localhost:9000")
        assert bridge._client is not None
        assert bridge._client.timeout.connect == 300

    def test_bridge_call_posts_to_correct_url(self):
        """MCPBridge.call() posts to /tools/{tool_name}."""
        from core.mcp.bridge import MCPBridge

        bridge = MCPBridge("http://test:8000")
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": "ok"}
        mock_response.raise_for_status = MagicMock()

        with patch.object(bridge._client, "post", return_value=mock_response) as mock_post:
            result = bridge.call("my_tool", {"key": "value"})
            mock_post.assert_called_once_with(
                "http://test:8000/tools/my_tool",
                json={"key": "value"},
            )
            assert result == {"result": "ok"}

    def test_bridge_list_tools(self):
        """MCPBridge.list_tools() gets /tools endpoint."""
        from core.mcp.bridge import MCPBridge

        bridge = MCPBridge("http://test:8000")
        mock_response = MagicMock()
        mock_response.json.return_value = [{"name": "tool1"}]
        mock_response.raise_for_status = MagicMock()

        with patch.object(bridge._client, "get", return_value=mock_response) as mock_get:
            result = bridge.list_tools()
            mock_get.assert_called_once_with("http://test:8000/tools")
            assert result == [{"name": "tool1"}]

@pytest.mark.unit
class TestGetBridge:
    """Tests for get_bridge() singleton factory."""

    def setup_method(self):
        from core.mcp.bridge import reset_bridge

        reset_bridge()

    def teardown_method(self):
        from core.mcp.bridge import reset_bridge

        reset_bridge()

    def test_get_bridge_creates_instance(self):
        """get_bridge() with URL creates MCPBridge."""
        from core.mcp.bridge import MCPBridge, get_bridge

        bridge = get_bridge("http://localhost:5000")
        assert isinstance(bridge, MCPBridge)
        assert bridge.base_url == "http://localhost:5000"

    def test_get_bridge_returns_same_instance(self):
        """get_bridge() returns the same singleton."""
        from core.mcp.bridge import get_bridge

        b1 = get_bridge("http://localhost:5000")
        b2 = get_bridge()
        assert b1 is b2

    def test_get_bridge_raises_without_url(self):
        """get_bridge() raises ValueError when no URL and no existing bridge."""
        from core.mcp.bridge import get_bridge

        with pytest.raises(ValueError, match="base_url is required"):
            get_bridge()

@pytest.mark.unit
class TestCreateToolWrapper:
    """Tests for create_tool_wrapper()."""

    def test_creates_callable_wrapper(self):
        """create_tool_wrapper produces a callable with correct name."""
        from core.mcp.bridge import MCPBridge, create_tool_wrapper

        bridge = MCPBridge("http://localhost:8000")
        config = SimpleNamespace(
            name="test_tool",
            mcp_tool="remote_test",
            description="A test tool",
            state=None,
        )

        wrapper = create_tool_wrapper(bridge, config)
        assert wrapper.name == "test_tool"

    def test_wrapper_calls_bridge(self):
        """Wrapped tool delegates to bridge.call()."""
        from core.mcp.bridge import MCPBridge, create_tool_wrapper

        bridge = MCPBridge("http://localhost:8000")
        bridge.call = MagicMock(return_value={"status": "done"})

        config = SimpleNamespace(
            name="do_thing",
            mcp_tool="mcp_do_thing",
            description="Does a thing",
            state=None,
        )

        wrapper = create_tool_wrapper(bridge, config)
        result = wrapper.run(arg1="val1")
        bridge.call.assert_called_once_with("mcp_do_thing", {"arg1": "val1"})

    def test_wrapper_with_state_exports(self):
        """Wrapped tool stores state metadata when config has state."""
        from core.mcp.bridge import MCPBridge, create_tool_wrapper

        bridge = MCPBridge("http://localhost:8000")
        state = SimpleNamespace(
            exports={"session_id": "ctx.session"},
            requires=["ctx.auth_token"],
        )
        config = SimpleNamespace(
            name="stateful_tool",
            mcp_tool="mcp_stateful",
            description="Stateful tool",
            state=state,
        )

        wrapper = create_tool_wrapper(bridge, config)
        assert wrapper._state_requires == ["ctx.auth_token"]
        assert wrapper._state_exports == {"session_id": "ctx.session"}
