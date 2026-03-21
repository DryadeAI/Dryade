# Copyright (c) 2025-2026 Dryade SAS
# Licensed under the Dryade Enterprise Edition License. See LICENSE_EE.md.

"""Allowlist file watchdog for zero-config plugin hot-reload.

Security model:
    The watchdog NEVER loads plugins directly and NEVER bypasses Ed25519
    signature verification. When the allowlist file changes, the watchdog
    invokes the registered callback (typically ``_hot_reload_plugins``), which
    calls ``reload_allowlist()`` -> ``get_allowed_plugins()`` ->
    ``verify_and_load_allowlist()``. Every reload re-verifies the Ed25519
    signature against the TOFU-pinned PM public key. There is no escape hatch.

    Deleting the allowlist file does NOT unload plugins (it would be a DoS
    vector). Only ``Change.added`` and ``Change.modified`` trigger a reload.

Purpose:
    Replace the requirement for the internal HTTP API (port 9471) with a
    filesystem-based trigger. Core watches ``~/.dryade/allowed-plugins.json``
    (or ``DRYADE_ALLOWLIST_PATH``) for changes. When PM writes a new signed
    allowlist to that path, the watchdog fires and plugins reload
    automatically -- no network connectivity required.

    Port 9471 remains an optional fast-path for enterprise deployments. The
    file watchdog is additive and runs alongside the internal API.

Debounce:
    When both the HTTP push endpoint and the file watchdog are active
    (enterprise), a single ``dryade-pm push`` generates two callbacks. The
    2-second debounce window in ``_fire_callback`` coalesces these into one
    effective reload.

Usage::

    watchdog = get_allowlist_watchdog()
    watchdog.set_callback(hot_reload_fn)
    await watchdog.start()
    # ... application runs ...
    await watchdog.stop()
"""

import asyncio
import logging
import threading
import time
from pathlib import Path
from typing import Callable

try:
    from watchfiles import Change, awatch

    WATCHFILES_AVAILABLE = True
except ImportError:
    WATCHFILES_AVAILABLE = False

logger = logging.getLogger(__name__)

class AllowlistWatchdog:
    """Watch the signed allowlist file for changes and trigger hot-reload.

    Uses ``watchfiles`` (inotify/FSEvents/kqueue) for efficient zero-CPU-idle
    watching on all platforms. Falls back to mtime polling when ``watchfiles``
    is unavailable.

    Features:
    - Watches parent directory (not file directly) so it works before the
      allowlist file exists.
    - Ignores ``Change.deleted`` events (DoS prevention).
    - Debounces rapid callbacks (2 s window) to handle simultaneous HTTP push
      + file watchdog firing for the same PM push.
    - Graceful start/stop with asyncio task lifecycle.

    Usage::

        watchdog = AllowlistWatchdog()
        watchdog.set_callback(hot_reload_fn)
        await watchdog.start()
        # ... later ...
        await watchdog.stop()
    """

    POLL_INTERVAL = 2.5  # seconds, for mtime polling fallback
    DEBOUNCE_SECS = 2.0  # seconds, suppress duplicate callbacks in this window
    EXPIRY_CHECK_INTERVAL = 300  # seconds (5 minutes), periodic expiry timer

    def __init__(self, allowlist_path: "Path | None" = None) -> None:
        """Initialise watchdog.

        Args:
            allowlist_path: Explicit path to watch. If ``None``, resolved
                lazily via :func:`core.ee.allowlist_ee.get_allowlist_path` at start
                time (reads ``DRYADE_ALLOWLIST_PATH`` env var).
        """
        self._path = allowlist_path
        self._task: "asyncio.Task | None" = None
        self._expiry_task: "asyncio.Task | None" = None
        # _stop_event is created lazily in start() to avoid event-loop binding
        # issues when the singleton is created before the loop starts.
        self._stop_event: "asyncio.Event | None" = None
        self._running = False
        self._callback: "Callable | None" = None
        self._last_callback_time: float = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_callback(self, callback: Callable) -> None:
        """Register the hot-reload callback.

        The callback will be invoked when the allowlist file changes. It may
        be a plain function or a coroutine function -- both are handled.

        Args:
            callback: Callable to invoke on allowlist change.
        """
        self._callback = callback

    async def start(self) -> None:
        """Start watching the allowlist file.

        No-op if already running. Creates a new stop event per start so the
        watchdog can be restarted cleanly.
        """
        if self._running:
            logger.debug("Allowlist watchdog already running")
            return

        self._stop_event = asyncio.Event()
        self._stop_event.clear()
        self._running = True

        if WATCHFILES_AVAILABLE:
            self._task = asyncio.create_task(self._watch_loop_watchfiles())
            logger.info("Allowlist watchdog started (watchfiles/inotify)")
        else:
            self._task = asyncio.create_task(self._watch_loop_polling())
            logger.info(
                "Allowlist watchdog started (mtime polling every %.1fs)",
                self.POLL_INTERVAL,
            )

        self._expiry_task = asyncio.create_task(self._expiry_check_loop())

    async def stop(self) -> None:
        """Stop watching and clean up the background task."""
        if not self._running:
            return

        if self._stop_event is not None:
            self._stop_event.set()

        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        if self._expiry_task is not None:
            self._expiry_task.cancel()
            try:
                await self._expiry_task
            except asyncio.CancelledError:
                pass
            self._expiry_task = None

        self._running = False
        logger.info("Allowlist watchdog stopped")

    @property
    def is_running(self) -> bool:
        """Return ``True`` if the watchdog is actively watching."""
        return self._running

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_path(self) -> Path:
        """Return the allowlist file path.

        Uses the explicitly supplied path if one was given at construction
        time, otherwise resolves via :func:`core.ee.allowlist_ee.get_allowlist_path`
        (which reads ``DRYADE_ALLOWLIST_PATH`` env var).
        """
        if self._path is not None:
            return self._path
        from core.ee.allowlist_ee import get_allowlist_path

        return get_allowlist_path()

    async def _expiry_check_loop(self) -> None:
        """Periodic loop to check if the loaded allowlist has expired.

        Runs every EXPIRY_CHECK_INTERVAL seconds. When the allowlist expires,
        fires the reload callback which will re-verify (and reject the expired
        allowlist, causing plugins to drain).
        """
        while True:
            await asyncio.sleep(self.EXPIRY_CHECK_INTERVAL)
            try:
                from core.ee.allowlist_ee import get_current_allowlist_data, is_allowlist_expired

                data = get_current_allowlist_data()
                if data and is_allowlist_expired(data):
                    logger.warning(
                        "Loaded allowlist has expired -- triggering reload to drain plugins"
                    )
                    await self._fire_callback()
            except Exception:
                logger.debug("Expiry check error", exc_info=True)

    async def _fire_callback(self) -> None:
        """Invoke the hot-reload callback with debounce protection.

        Skips the callback if one was already fired within ``DEBOUNCE_SECS``
        to suppress duplicate reloads when both the HTTP push endpoint and the
        file watchdog fire for the same PM push operation.
        """
        now = time.monotonic()
        if now - self._last_callback_time < self.DEBOUNCE_SECS:
            logger.debug(
                "Allowlist watchdog: callback debounced (%.1fs since last fire)",
                now - self._last_callback_time,
            )
            return

        self._last_callback_time = now

        if self._callback is None:
            logger.debug("Allowlist watchdog: no callback registered, skipping")
            return

        try:
            result = self._callback()
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            logger.exception("Allowlist hot-reload callback raised an exception")

    async def _watch_loop_watchfiles(self) -> None:
        """Watch loop using ``watchfiles`` (preferred path, inotify/kqueue).

        Watches the *parent directory* and filters events to the specific
        allowlist filename. This handles the case where the file does not yet
        exist at startup (watchfiles requires the watch target to exist; the
        parent dir is created by ``write_allowlist_file()``).
        """
        path = self._get_path()
        watch_target = str(path.parent)

        # Ensure parent directory exists so watchfiles has a valid target.
        path.parent.mkdir(parents=True, exist_ok=True)

        assert self._stop_event is not None  # set in start()

        try:
            async for changes in awatch(
                watch_target,
                debounce=500,
                stop_event=self._stop_event,
                watch_filter=lambda change, filename: Path(filename).name == path.name,
            ):
                # Only reload on added/modified -- never on deleted.
                matching = [
                    (c, p)
                    for c, p in changes
                    if Path(p).name == path.name and c in (Change.added, Change.modified)
                ]
                if matching:
                    logger.info(
                        "Allowlist file changed (%s) -- triggering hot-reload",
                        ", ".join(c.name for c, _ in matching),
                    )
                    await self._fire_callback()

        except asyncio.CancelledError:
            logger.debug("Allowlist watchdog (watchfiles) cancelled")
            raise
        except Exception as exc:
            logger.error("Allowlist watchdog (watchfiles) error: %s", exc)
            self._running = False

    async def _watch_loop_polling(self) -> None:
        """Mtime polling fallback when ``watchfiles`` is unavailable.

        Polls the allowlist file's mtime every ``POLL_INTERVAL`` seconds.
        Uses ``asyncio.wait_for`` + ``asyncio.shield`` so the sleep exits
        immediately when the stop event fires.
        """
        path = self._get_path()
        last_mtime: "float | None" = None

        assert self._stop_event is not None  # set in start()

        while not self._stop_event.is_set():
            try:
                current_mtime = path.stat().st_mtime if path.exists() else None
                # Only fire on modify/create -- never on delete (DoS prevention).
                # A transition to None means the file was removed; skip callback.
                if (
                    last_mtime is not None
                    and current_mtime is not None
                    and current_mtime != last_mtime
                ):
                    logger.info("Allowlist file mtime changed -- triggering hot-reload")
                    await self._fire_callback()
                last_mtime = current_mtime
            except Exception as exc:
                logger.debug("Allowlist watchdog mtime check error: %s", exc)

            try:
                await asyncio.wait_for(
                    asyncio.shield(self._stop_event.wait()),
                    timeout=self.POLL_INTERVAL,
                )
            except asyncio.TimeoutError:
                pass  # Normal loop tick

# =============================================================================
# Global Singleton
# =============================================================================

_watchdog: "AllowlistWatchdog | None" = None
_watchdog_lock = threading.Lock()

def get_allowlist_watchdog() -> AllowlistWatchdog:
    """Return the global ``AllowlistWatchdog`` singleton.

    Thread-safe double-checked locking. The singleton is created lazily so
    it is safe to import this module before the asyncio event loop starts.

    Returns:
        The application-wide :class:`AllowlistWatchdog` instance.
    """
    global _watchdog
    if _watchdog is None:
        with _watchdog_lock:
            if _watchdog is None:
                _watchdog = AllowlistWatchdog()
    return _watchdog

# =============================================================================
# Convenience Functions
# =============================================================================

async def start_allowlist_watchdog() -> None:
    """Start the global allowlist watchdog.

    Convenience wrapper for application startup code.
    Idempotent -- safe to call multiple times.
    """
    watchdog = get_allowlist_watchdog()
    await watchdog.start()

async def stop_allowlist_watchdog() -> None:
    """Stop the global allowlist watchdog.

    Convenience wrapper for application shutdown code.
    Idempotent -- safe to call if watchdog is not running.
    """
    watchdog = get_allowlist_watchdog()
    await watchdog.stop()

def is_allowlist_watching_available() -> bool:
    """Return ``True`` if ``watchfiles`` is installed (inotify/kqueue available).

    When ``False``, the watchdog falls back to mtime polling.

    Returns:
        ``True`` if native file watching is available.
    """
    return WATCHFILES_AVAILABLE
