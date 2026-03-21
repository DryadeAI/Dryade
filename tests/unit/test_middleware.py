"""Tests for core.orchestrator.middleware -- Phase 115.4.

Covers MiddlewareChain hook execution, error isolation, and singleton.
"""

import pytest

from core.orchestrator.middleware import (
    MiddlewareChain,
    RoutingContext,
    ToolCallContext,
    ToolCallResult,
    get_middleware_chain,
)

def _make_routing_ctx(**kwargs) -> RoutingContext:
    defaults = {
        "goal": "test goal",
        "model_tier": "frontier",
        "meta_action_hint": False,
    }
    defaults.update(kwargs)
    return RoutingContext(**defaults)

def _make_tool_ctx(**kwargs) -> ToolCallContext:
    defaults = {
        "tool_name": "test_tool",
        "arguments": {},
        "agent_name": "test_agent",
        "is_self_mod": False,
    }
    defaults.update(kwargs)
    return ToolCallContext(**defaults)

class TestPreRouting:
    @pytest.mark.asyncio
    async def test_empty_chain_passthrough(self):
        chain = MiddlewareChain()
        ctx = _make_routing_ctx()
        result = await chain.run_pre_routing(ctx)
        assert result is ctx

    @pytest.mark.asyncio
    async def test_modifies_ctx(self):
        chain = MiddlewareChain()

        async def set_tier(ctx):
            ctx.model_tier = "test"
            return ctx

        chain.add_pre_routing(set_tier)
        ctx = _make_routing_ctx()
        result = await chain.run_pre_routing(ctx)
        assert result.model_tier == "test"

    @pytest.mark.asyncio
    async def test_hook_error_isolation(self):
        chain = MiddlewareChain()
        call_order = []

        async def bad_hook(ctx):
            call_order.append("bad")
            raise ValueError("boom")

        async def good_hook(ctx):
            call_order.append("good")
            ctx.model_tier = "survived"
            return ctx

        chain.add_pre_routing(bad_hook)
        chain.add_pre_routing(good_hook)
        ctx = _make_routing_ctx()
        result = await chain.run_pre_routing(ctx)
        assert call_order == ["bad", "good"]
        assert result.model_tier == "survived"

    @pytest.mark.asyncio
    async def test_hook_order(self):
        chain = MiddlewareChain()
        order = []

        async def hook_a(ctx):
            order.append("a")
            return None

        async def hook_b(ctx):
            order.append("b")
            return None

        chain.add_pre_routing(hook_a)
        chain.add_pre_routing(hook_b)
        await chain.run_pre_routing(_make_routing_ctx())
        assert order == ["a", "b"]

class TestPostRouting:
    @pytest.mark.asyncio
    async def test_fire_and_forget(self):
        chain = MiddlewareChain()
        called = []

        async def observer(ctx, thought):
            called.append((ctx.goal, thought))

        chain.add_post_routing(observer)
        ctx = _make_routing_ctx(goal="test")
        await chain.run_post_routing(ctx, "fake_thought")
        assert len(called) == 1
        assert called[0] == ("test", "fake_thought")

class TestPreToolCall:
    @pytest.mark.asyncio
    async def test_modifies_tool_name(self):
        chain = MiddlewareChain()

        async def rename(ctx):
            ctx.tool_name = "renamed"
            return ctx

        chain.add_pre_tool_call(rename)
        ctx = _make_tool_ctx()
        result = await chain.run_pre_tool_call(ctx)
        assert result.tool_name == "renamed"

class TestPostToolCall:
    @pytest.mark.asyncio
    async def test_receives_result(self):
        chain = MiddlewareChain()
        captured = []

        async def log_result(ctx, result):
            captured.append((ctx.tool_name, result.success))

        chain.add_post_tool_call(log_result)
        ctx = _make_tool_ctx(tool_name="read_file")
        result = ToolCallResult(success=True, result="ok")
        await chain.run_post_tool_call(ctx, result)
        assert captured == [("read_file", True)]

class TestClear:
    @pytest.mark.asyncio
    async def test_clear(self):
        chain = MiddlewareChain()
        called = []

        async def hook(ctx):
            called.append(1)
            return None

        chain.add_pre_routing(hook)
        chain.clear()
        await chain.run_pre_routing(_make_routing_ctx())
        assert called == []

class TestSingleton:
    def test_singleton(self):
        # Reset singleton for test isolation
        import core.orchestrator.middleware as mod

        mod._middleware_chain = None
        c1 = get_middleware_chain()
        c2 = get_middleware_chain()
        assert c1 is c2
