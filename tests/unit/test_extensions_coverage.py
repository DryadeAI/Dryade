"""Tests for extensions module coverage gaps.

Covers:
- core.extensions.decorator (with_extensions)
- core.extensions.request_queue (RequestQueue, with_llm_slot)
- core.extensions.latency_tracker (LatencyTracker, LatencyRecord)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# core.extensions.latency_tracker tests
# ---------------------------------------------------------------------------

class TestLatencyRecord:
    """Tests for LatencyRecord dataclass."""

    def test_creation(self):
        """LatencyRecord initializes correctly."""
        from core.extensions.latency_tracker import LatencyRecord

        rec = LatencyRecord(
            timestamp="2025-01-01T00:00:00",
            conversation_id="c1",
            mode="chat",
            total_ms=100.0,
            ttft_ms=10.0,
            cache_lookup_ms=5.0,
            llm_call_ms=85.0,
            cache_hit=False,
        )
        assert rec.mode == "chat"
        assert rec.total_ms == 100.0
        assert rec.cache_hit is False

class TestLatencyTracker:
    """Tests for LatencyTracker."""

    def test_record_basic(self):
        """record() stores a LatencyRecord."""
        from core.extensions.latency_tracker import LatencyTracker

        tracker = LatencyTracker()
        tracker.record(
            conversation_id="c1",
            mode="chat",
            total_ms=100.0,
        )
        assert len(tracker.records) == 1
        assert tracker.records[0].mode == "chat"
        assert tracker.records[0].total_ms == 100.0

    def test_record_rolling_window(self):
        """record() trims records beyond max_records."""
        from core.extensions.latency_tracker import LatencyTracker

        tracker = LatencyTracker(max_records=5)
        for i in range(10):
            tracker.record(conversation_id=None, mode="chat", total_ms=float(i))
        assert len(tracker.records) == 5
        # Keeps the latest 5
        assert tracker.records[0].total_ms == 5.0

    def test_record_slow_request_warning(self):
        """record() logs warning for slow requests."""
        from core.extensions.latency_tracker import LatencyTracker

        tracker = LatencyTracker(slow_threshold_ms=100.0)
        # Should not raise even for slow requests
        tracker.record(conversation_id=None, mode="chat", total_ms=200.0)
        assert len(tracker.records) == 1

    def test_get_stats_empty(self):
        """get_stats() returns zeros when no records."""
        from core.extensions.latency_tracker import LatencyTracker

        tracker = LatencyTracker()
        stats = tracker.get_stats()
        assert stats["count"] == 0
        assert stats["avg_ms"] == 0

    def test_get_stats_with_records(self):
        """get_stats() returns correct statistics."""
        from core.extensions.latency_tracker import LatencyTracker

        tracker = LatencyTracker()
        for i in range(100):
            tracker.record(
                conversation_id=None,
                mode="chat",
                total_ms=float(i + 1),
                ttft_ms=float(i) * 0.1,
                cache_hit=(i % 2 == 0),
            )
        stats = tracker.get_stats()
        assert stats["count"] == 100
        assert stats["cache_hit_rate"] == 0.5
        assert "total_latency" in stats
        assert stats["total_latency"]["avg_ms"] == pytest.approx(50.5)
        assert stats["total_latency"]["min_ms"] == 1.0
        assert stats["total_latency"]["max_ms"] == 100.0
        assert stats["ttft"] is not None

    def test_get_stats_filtered_by_mode(self):
        """get_stats() filters by mode."""
        from core.extensions.latency_tracker import LatencyTracker

        tracker = LatencyTracker()
        tracker.record(conversation_id=None, mode="chat", total_ms=10.0)
        tracker.record(conversation_id=None, mode="crew", total_ms=20.0)
        tracker.record(conversation_id=None, mode="chat", total_ms=30.0)

        stats = tracker.get_stats(mode="chat")
        assert stats["count"] == 2

        stats = tracker.get_stats(mode="crew")
        assert stats["count"] == 1

    def test_get_stats_no_ttft(self):
        """get_stats() returns None ttft when no ttft records."""
        from core.extensions.latency_tracker import LatencyTracker

        tracker = LatencyTracker()
        tracker.record(conversation_id=None, mode="chat", total_ms=10.0)
        stats = tracker.get_stats()
        assert stats["ttft"] is None

    def test_get_stats_last_n(self):
        """get_stats() respects last_n parameter."""
        from core.extensions.latency_tracker import LatencyTracker

        tracker = LatencyTracker()
        for i in range(20):
            tracker.record(conversation_id=None, mode="chat", total_ms=float(i))
        stats = tracker.get_stats(last_n=5)
        assert stats["count"] == 5

class TestLatencyTrackerGlobals:
    """Tests for global latency tracker functions."""

    def test_get_latency_tracker(self):
        """get_latency_tracker returns singleton."""
        # Reset global
        import core.extensions.latency_tracker as lt
        from core.extensions.latency_tracker import LatencyTracker, get_latency_tracker

        lt._tracker = None
        tracker = get_latency_tracker()
        assert isinstance(tracker, LatencyTracker)
        assert get_latency_tracker() is tracker
        lt._tracker = None

    def test_record_latency_convenience(self):
        """record_latency convenience function works."""
        import core.extensions.latency_tracker as lt
        from core.extensions.latency_tracker import record_latency

        lt._tracker = None
        record_latency(conversation_id=None, mode="chat", total_ms=50.0)
        assert len(lt._tracker.records) == 1
        lt._tracker = None

    def test_get_latency_stats_convenience(self):
        """get_latency_stats convenience function works."""
        import core.extensions.latency_tracker as lt
        from core.extensions.latency_tracker import get_latency_stats, record_latency

        lt._tracker = None
        record_latency(conversation_id=None, mode="chat", total_ms=50.0)
        stats = get_latency_stats()
        assert stats["count"] == 1
        lt._tracker = None

# ---------------------------------------------------------------------------
# core.extensions.request_queue tests
# ---------------------------------------------------------------------------

class TestQueueStats:
    """Tests for QueueStats dataclass."""

    def test_creation(self):
        """QueueStats initializes correctly."""
        from core.extensions.request_queue import QueueStats

        stats = QueueStats(
            active_requests=2,
            queued_requests=3,
            max_concurrent=8,
            max_queue_size=20,
            total_processed=100,
            total_rejected=5,
            avg_wait_ms=15.5,
        )
        assert stats.active_requests == 2
        assert stats.total_rejected == 5

class TestRequestQueue:
    """Tests for RequestQueue."""

    def test_creation_defaults(self):
        """RequestQueue uses defaults from env or hardcoded."""
        from core.extensions.request_queue import RequestQueue

        q = RequestQueue(max_concurrent=4, max_queue_size=10, queue_timeout_s=5.0)
        assert q.max_concurrent == 4
        assert q.max_queue_size == 10
        assert q.queue_timeout_s == 5.0

    @pytest.mark.asyncio
    async def test_acquire_release(self):
        """acquire/release basic cycle works."""
        from core.extensions.request_queue import RequestQueue

        q = RequestQueue(max_concurrent=2, max_queue_size=5, queue_timeout_s=5.0)
        acquired = await q.acquire()
        assert acquired is True
        stats = await q.get_stats()
        assert stats.active_requests == 1
        await q.release()
        stats = await q.get_stats()
        assert stats.active_requests == 0
        assert stats.total_processed == 1

    @pytest.mark.asyncio
    async def test_acquire_queue_full_rejected(self):
        """acquire returns False when queue is full."""
        from core.extensions.request_queue import RequestQueue

        q = RequestQueue(max_concurrent=1, max_queue_size=0, queue_timeout_s=1.0)
        # Fill the single slot
        await q.acquire()
        # Next acquire should be rejected (queue_size=0, so it can't wait)
        result = await q.acquire()
        assert result is False
        stats = await q.get_stats()
        assert stats.total_rejected == 1
        await q.release()

    @pytest.mark.asyncio
    async def test_acquire_timeout(self):
        """acquire returns False on timeout."""
        from core.extensions.request_queue import RequestQueue

        q = RequestQueue(max_concurrent=1, max_queue_size=5, queue_timeout_s=0.1)
        # Fill the single slot
        await q.acquire()
        # Next acquire should timeout (0.1s)
        result = await q.acquire(timeout=0.1)
        assert result is False
        stats = await q.get_stats()
        assert stats.total_rejected == 1
        await q.release()

    @pytest.mark.asyncio
    async def test_get_stats(self):
        """get_stats returns correct snapshot."""
        from core.extensions.request_queue import RequestQueue

        q = RequestQueue(max_concurrent=4, max_queue_size=10, queue_timeout_s=5.0)
        stats = await q.get_stats()
        assert stats.active_requests == 0
        assert stats.queued_requests == 0
        assert stats.max_concurrent == 4
        assert stats.max_queue_size == 10
        assert stats.avg_wait_ms == 0.0

class TestRequestQueueGlobals:
    """Tests for global request queue functions."""

    def test_get_request_queue(self):
        """get_request_queue returns singleton."""
        from core.extensions.request_queue import (
            RequestQueue,
            get_request_queue,
            reset_request_queue,
        )

        reset_request_queue()
        q = get_request_queue()
        assert isinstance(q, RequestQueue)
        assert get_request_queue() is q
        reset_request_queue()

    def test_reset_request_queue(self):
        """reset_request_queue clears singleton."""
        from core.extensions.request_queue import get_request_queue, reset_request_queue

        q1 = get_request_queue()
        reset_request_queue()
        q2 = get_request_queue()
        assert q1 is not q2
        reset_request_queue()

    @pytest.mark.asyncio
    async def test_with_llm_slot_success(self):
        """with_llm_slot acquires slot, runs coro, releases."""
        from core.extensions.request_queue import reset_request_queue, with_llm_slot

        reset_request_queue()

        async def my_coro():
            return "result"

        result = await with_llm_slot(my_coro())
        assert result == "result"
        reset_request_queue()

    @pytest.mark.asyncio
    async def test_with_llm_slot_rejected(self):
        """with_llm_slot raises RuntimeError when queue full."""
        import core.extensions.request_queue as rq
        from core.extensions.request_queue import RequestQueue, reset_request_queue, with_llm_slot

        reset_request_queue()
        # Use a queue with 0 max_queue_size and 1 concurrent
        rq._queue = RequestQueue(max_concurrent=1, max_queue_size=0, queue_timeout_s=0.1)
        # Fill the slot
        await rq._queue.acquire()

        async def my_coro():
            return "should not reach"

        with pytest.raises(RuntimeError, match="queue full"):
            await with_llm_slot(my_coro())
        await rq._queue.release()
        reset_request_queue()

# ---------------------------------------------------------------------------
# core.extensions.decorator tests
# ---------------------------------------------------------------------------

class TestWithExtensionsDecorator:
    """Tests for with_extensions decorator."""

    @pytest.mark.asyncio
    async def test_decorator_wraps_function(self):
        """with_extensions wraps async function and executes through pipeline."""
        from core.extensions.decorator import with_extensions

        @with_extensions(operation="test_op")
        async def my_func(x: int) -> int:
            return x * 2

        # Mock the pipeline and storage functions
        with (
            patch("core.extensions.decorator.build_pipeline") as mock_build,
            patch("core.extensions.decorator._store_extension_execution", new_callable=AsyncMock),
            patch("core.extensions.decorator._store_timeline_entry", new_callable=AsyncMock),
        ):
            mock_pipeline = MagicMock()
            mock_response = MagicMock()
            mock_response.result = 10
            mock_response.extensions_applied = ["ext1"]
            mock_response.cache_hit = False
            mock_response.healed = False
            mock_response.threats_found = []
            mock_pipeline.execute = AsyncMock(return_value=mock_response)
            mock_build.return_value = mock_pipeline

            result = await my_func(5)
            assert result == 10
            mock_pipeline.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_decorator_pipeline_error(self):
        """with_extensions raises when pipeline fails."""
        from core.extensions.decorator import with_extensions

        @with_extensions(operation="test_op")
        async def my_func() -> int:
            return 42

        with patch("core.extensions.decorator.build_pipeline") as mock_build:
            mock_pipeline = MagicMock()
            mock_pipeline.execute = AsyncMock(side_effect=RuntimeError("pipeline crash"))
            mock_build.return_value = mock_pipeline

            with pytest.raises(RuntimeError, match="pipeline crash"):
                await my_func()

# ---------------------------------------------------------------------------
# core.extensions.pipeline tests
# ---------------------------------------------------------------------------

class TestExtensionRegistry:
    """Tests for ExtensionRegistry."""

    def test_register_and_get(self):
        """register stores config, get retrieves it."""
        from core.extensions.pipeline import ExtensionConfig, ExtensionRegistry, ExtensionType

        reg = ExtensionRegistry()
        config = ExtensionConfig(
            name="test_ext",
            type=ExtensionType.INPUT_VALIDATION,
            enabled=True,
            priority=10,
        )
        reg.register(config)
        assert reg.get("test_ext") is config
        assert reg.get("nonexistent") is None

    def test_get_enabled(self):
        """get_enabled returns only enabled extensions sorted by priority."""
        from core.extensions.pipeline import ExtensionConfig, ExtensionRegistry, ExtensionType

        reg = ExtensionRegistry()
        reg.register(
            ExtensionConfig(name="b", type=ExtensionType.SANDBOX, enabled=True, priority=20)
        )
        reg.register(
            ExtensionConfig(
                name="a", type=ExtensionType.INPUT_VALIDATION, enabled=True, priority=10
            )
        )
        reg.register(
            ExtensionConfig(name="c", type=ExtensionType.SELF_HEALING, enabled=False, priority=5)
        )
        enabled = reg.get_enabled()
        assert len(enabled) == 2
        assert enabled[0].name == "a"  # priority 10 first
        assert enabled[1].name == "b"  # priority 20 second

    def test_get_by_type(self):
        """get_by_type filters by extension type."""
        from core.extensions.pipeline import ExtensionConfig, ExtensionRegistry, ExtensionType

        reg = ExtensionRegistry()
        reg.register(
            ExtensionConfig(name="a", type=ExtensionType.SANDBOX, enabled=True, priority=10)
        )
        reg.register(
            ExtensionConfig(name="b", type=ExtensionType.SANDBOX, enabled=True, priority=20)
        )
        reg.register(
            ExtensionConfig(name="c", type=ExtensionType.SELF_HEALING, enabled=True, priority=30)
        )
        sandbox = reg.get_by_type(ExtensionType.SANDBOX)
        assert len(sandbox) == 2

    @pytest.mark.asyncio
    async def test_startup_shutdown(self):
        """startup/shutdown call hooks on enabled extensions."""
        from core.extensions.pipeline import ExtensionConfig, ExtensionRegistry, ExtensionType

        reg = ExtensionRegistry()
        on_start = MagicMock()
        on_stop = MagicMock()
        reg.register(
            ExtensionConfig(
                name="a",
                type=ExtensionType.INPUT_VALIDATION,
                enabled=True,
                priority=10,
                on_startup=on_start,
                on_shutdown=on_stop,
            )
        )
        await reg.startup()
        on_start.assert_called_once()
        await reg.shutdown()
        on_stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_startup_exception_swallowed(self):
        """startup does not raise when hook fails."""
        from core.extensions.pipeline import ExtensionConfig, ExtensionRegistry, ExtensionType

        reg = ExtensionRegistry()
        reg.register(
            ExtensionConfig(
                name="bad",
                type=ExtensionType.INPUT_VALIDATION,
                enabled=True,
                priority=10,
                on_startup=MagicMock(side_effect=RuntimeError("boom")),
            )
        )
        await reg.startup()  # Should not raise

class TestExtensionPipeline:
    """Tests for ExtensionPipeline."""

    @pytest.mark.asyncio
    async def test_disabled_pipeline_bypasses(self):
        """Pipeline passes through when disabled."""
        from core.extensions.pipeline import ExtensionPipeline, ExtensionRegistry, ExtensionRequest

        reg = ExtensionRegistry()
        pipeline = ExtensionPipeline(reg)
        pipeline._enabled = False

        async def handler(data):
            return data["value"]

        request = ExtensionRequest(operation="test", data={"value": 42}, context={}, metadata={})
        response = await pipeline.execute(request, handler)
        assert response.result == 42
        assert response.extensions_applied == []

    @pytest.mark.asyncio
    async def test_pipeline_with_extensions(self):
        """Pipeline applies extensions in order."""
        from core.extensions.pipeline import (
            ExtensionConfig,
            ExtensionPipeline,
            ExtensionRegistry,
            ExtensionRequest,
            ExtensionType,
        )

        reg = ExtensionRegistry()
        reg.register(
            ExtensionConfig(
                name="validator",
                type=ExtensionType.INPUT_VALIDATION,
                enabled=True,
                priority=10,
            )
        )

        pipeline = ExtensionPipeline(reg)
        pipeline._enabled = True

        async def handler(data):
            return data["value"]

        request = ExtensionRequest(operation="test", data={"value": 99}, context={}, metadata={})
        response = await pipeline.execute(request, handler)
        assert response.result == 99
        assert "validator" in response.extensions_applied
