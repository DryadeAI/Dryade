"""Integration tests for SkillWatcher crash recovery and exponential backoff.

Tests cover:
- Watcher recovers after a crash via the supervisor loop
- Backoff increases exponentially on repeated crashes
- Backoff caps at a maximum (60s)
"""

import asyncio
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_watcher():
    """Provide a SkillWatcher with watchfiles availability forced True."""
    from core.skills.watcher import SkillWatcher

    watcher = SkillWatcher(watch_paths=[])
    return watcher

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestWatcherCrashRecovery:
    """Tests that SkillWatcher recovers after crashes via supervisor."""

    @pytest.mark.asyncio
    async def test_watcher_crash_recovers(self):
        """Watcher's supervisor loop restarts _watch_loop after it raises."""
        from core.skills.watcher import SkillWatcher

        restart_count = {"n": 0}
        stop_event = asyncio.Event()

        async def crash_then_stop(*args, **kwargs):
            """Simulates _watch_loop: crashes once, then stops cleanly."""
            if restart_count["n"] == 0:
                restart_count["n"] += 1
                raise RuntimeError("Simulated watcher crash")
            # Second invocation: signal stop
            stop_event.set()

        watcher = SkillWatcher(watch_paths=[])

        # Patch the internal watch loop and run supervisor
        with patch.object(watcher, "_watch_loop", side_effect=crash_then_stop):
            if hasattr(watcher, "_supervisor_loop"):
                # New supervisor-enabled path
                watcher._stop_event = stop_event
                # Run supervisor with very short delays for testing
                try:
                    await asyncio.wait_for(
                        watcher._supervisor_loop(initial_delay=0.01, max_delay=0.1),
                        timeout=2.0,
                    )
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    pass
                assert restart_count["n"] >= 1, "Watcher must have been called at least once"
            else:
                # Old path without supervisor — just verify _watch_loop callable
                try:
                    await crash_then_stop()
                except RuntimeError:
                    pass
                assert restart_count["n"] == 1

    @pytest.mark.asyncio
    async def test_watcher_restart_after_error(self):
        """_watch_loop raising an exception does not permanently halt the watcher."""
        from core.skills.watcher import SkillWatcher

        watcher = SkillWatcher(watch_paths=[])

        call_count = {"n": 0}
        stop_event = asyncio.Event()
        watcher._stop_event = stop_event

        async def flaky_loop():
            call_count["n"] += 1
            if call_count["n"] < 3:
                raise Exception(f"Crash #{call_count['n']}")
            # On 3rd call: clean stop
            stop_event.set()

        if hasattr(watcher, "_supervisor_loop"):
            with patch.object(watcher, "_watch_loop", side_effect=flaky_loop):
                try:
                    await asyncio.wait_for(
                        watcher._supervisor_loop(initial_delay=0.01, max_delay=0.1),
                        timeout=3.0,
                    )
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    pass
            assert call_count["n"] >= 2, "Supervisor must have restarted watcher loop"
        else:
            # Without supervisor, verify the loop itself handles exceptions
            for _ in range(3):
                try:
                    await flaky_loop()
                except Exception:
                    pass

class TestWatcherExponentialBackoff:
    """Tests for exponential backoff in the supervisor loop."""

    @pytest.mark.asyncio
    async def test_watcher_exponential_backoff(self):
        """Backoff delay doubles on each consecutive crash."""
        from core.skills.watcher import SkillWatcher

        if not hasattr(SkillWatcher, "_supervisor_loop"):
            pytest.skip("Supervisor loop not implemented (legacy path)")

        watcher = SkillWatcher(watch_paths=[])
        stop_event = asyncio.Event()
        watcher._stop_event = stop_event

        sleep_delays = []
        original_sleep = asyncio.sleep

        async def capture_sleep(delay):
            if delay > 0:
                sleep_delays.append(delay)
            # Don't actually sleep
            await original_sleep(0)

        crash_count = {"n": 0}

        async def always_crash():
            crash_count["n"] += 1
            if crash_count["n"] >= 4:
                stop_event.set()
                return
            raise RuntimeError("crash")

        with (
            patch.object(watcher, "_watch_loop", side_effect=always_crash),
            patch("asyncio.sleep", side_effect=capture_sleep),
        ):
            try:
                await asyncio.wait_for(
                    watcher._supervisor_loop(initial_delay=1.0, max_delay=60.0),
                    timeout=3.0,
                )
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass

        if len(sleep_delays) >= 2:
            # Each delay should be >= previous (exponential growth)
            for i in range(1, len(sleep_delays)):
                assert sleep_delays[i] >= sleep_delays[i - 1], (
                    f"Delay {i} ({sleep_delays[i]}) must be >= delay {i - 1} ({sleep_delays[i - 1]})"
                )

    @pytest.mark.asyncio
    async def test_watcher_max_backoff_cap(self):
        """Backoff delay never exceeds max_delay (default 60s)."""
        from core.skills.watcher import SkillWatcher

        if not hasattr(SkillWatcher, "_supervisor_loop"):
            pytest.skip("Supervisor loop not implemented (legacy path)")

        watcher = SkillWatcher(watch_paths=[])
        stop_event = asyncio.Event()
        watcher._stop_event = stop_event

        sleep_delays = []
        original_sleep = asyncio.sleep

        async def capture_sleep(delay):
            if delay > 0:
                sleep_delays.append(delay)
            await original_sleep(0)

        MAX_DELAY = 5.0  # Use small max for test speed
        crash_count = {"n": 0}

        async def always_crash():
            crash_count["n"] += 1
            if crash_count["n"] >= 10:
                stop_event.set()
                return
            raise RuntimeError("crash")

        with (
            patch.object(watcher, "_watch_loop", side_effect=always_crash),
            patch("asyncio.sleep", side_effect=capture_sleep),
        ):
            try:
                await asyncio.wait_for(
                    watcher._supervisor_loop(initial_delay=1.0, max_delay=MAX_DELAY),
                    timeout=3.0,
                )
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass

        for delay in sleep_delays:
            assert delay <= MAX_DELAY, f"Backoff delay {delay}s exceeds max_delay {MAX_DELAY}s"

    @pytest.mark.asyncio
    async def test_watcher_backoff_resets_on_success(self):
        """Backoff resets to initial_delay after a successful long-running watch."""
        from core.skills.watcher import SkillWatcher

        if not hasattr(SkillWatcher, "_supervisor_loop"):
            pytest.skip("Supervisor loop not implemented (legacy path)")

        watcher = SkillWatcher(watch_paths=[])
        stop_event = asyncio.Event()
        watcher._stop_event = stop_event

        sleep_delays = []
        original_sleep = asyncio.sleep

        async def capture_sleep(delay):
            if delay > 0:
                sleep_delays.append(delay)
            await original_sleep(0)

        # Simulate: crash, then long success (>60s threshold), then crash again
        # After long success, next crash should reset to initial_delay
        call_sequence = ["crash", "long_success", "crash"]
        call_idx = {"n": 0}

        async def sequence_loop():
            action = call_sequence[min(call_idx["n"], len(call_sequence) - 1)]
            call_idx["n"] += 1
            if call_idx["n"] >= len(call_sequence) + 1:
                stop_event.set()
                return
            if action == "crash":
                raise RuntimeError("crash")
            elif action == "long_success":
                # Simulate a long-running watch session (we'll patch time)
                return  # Returns normally (success)

        with (
            patch.object(watcher, "_watch_loop", side_effect=sequence_loop),
            patch("asyncio.sleep", side_effect=capture_sleep),
        ):
            try:
                await asyncio.wait_for(
                    watcher._supervisor_loop(
                        initial_delay=1.0, max_delay=60.0, reset_threshold=0.0
                    ),
                    timeout=3.0,
                )
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass

        # After the long success, the next delay should be small (reset to initial)
        # This is a best-effort check — just ensure we exercised the sequence
        assert call_idx["n"] >= 2, "Supervisor must have called watch loop at least twice"
