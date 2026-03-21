"""File watcher for skill hot reload.

Uses watchfiles library for efficient cross-platform file watching.
Notifies skill registry when SKILL.md files change.

Crash recovery: The SkillWatcher includes a supervisor loop with exponential
backoff so that transient failures in the underlying file-watching library
don't permanently halt hot-reload functionality.
"""

import asyncio
import logging
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

try:
    from watchfiles import Change, awatch

    WATCHFILES_AVAILABLE = True
except ImportError:
    WATCHFILES_AVAILABLE = False

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

class SkillWatcher:
    """Watch skill directories for changes.

    Features:
    - Async file watching with debounce
    - Automatic registry refresh on SKILL.md changes
    - Graceful degradation if watchfiles not available

    Usage:
        watcher = SkillWatcher()
        await watcher.start()
        # ... application runs ...
        await watcher.stop()
    """

    SKILL_FILE = "SKILL.md"
    DEBOUNCE_MS = 500  # Debounce rapid changes

    # Supervisor backoff settings
    INITIAL_BACKOFF_S: float = 1.0  # Initial retry delay after crash
    BACKOFF_FACTOR: float = 2.0  # Multiply delay by this on each failure
    MAX_BACKOFF_S: float = 60.0  # Cap — never wait longer than this
    RESET_THRESHOLD_S: float = 60.0  # Reset backoff if watch ran longer than this

    def __init__(self, watch_paths: list[Path] | None = None):
        """Initialize skill watcher.

        Args:
            watch_paths: Paths to watch (uses registry paths if None)
        """
        self._watch_paths = watch_paths
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._running = False

    def _get_watch_paths(self) -> list[Path]:
        """Get paths to watch.

        Uses registry search paths if not explicitly configured.
        """
        if self._watch_paths:
            return self._watch_paths

        from core.skills.registry import get_skill_registry

        registry = get_skill_registry()
        return registry.get_search_paths()

    async def start(self) -> None:
        """Start watching skill directories.

        No-op if watchfiles not available or already running.
        Uses supervisor loop with exponential backoff for crash recovery.
        """
        if not WATCHFILES_AVAILABLE:
            logger.warning("watchfiles not installed, skill hot reload disabled")
            return

        if self._running:
            logger.debug("Skill watcher already running")
            return

        self._stop_event.clear()
        self._running = True
        self._task = asyncio.create_task(
            self._supervisor_loop(
                initial_delay=self.INITIAL_BACKOFF_S,
                max_delay=self.MAX_BACKOFF_S,
                reset_threshold=self.RESET_THRESHOLD_S,
            )
        )
        logger.info("Skill watcher started (supervisor with exponential backoff)")

    async def stop(self) -> None:
        """Stop watching skill directories."""
        if not self._running:
            return

        self._stop_event.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        self._running = False
        logger.info("Skill watcher stopped")

    @property
    def is_running(self) -> bool:
        """Check if watcher is running."""
        return self._running

    async def _watch_loop(self) -> None:
        """Main watch loop.

        Monitors skill directories and triggers refresh on changes.
        """
        from core.skills.registry import get_skill_registry

        watch_paths = self._get_watch_paths()
        # Filter to existing paths (watchfiles requires existing paths)
        existing_paths = [str(p) for p in watch_paths if p.exists()]

        if not existing_paths:
            logger.warning("No existing skill paths to watch")
            return

        logger.debug(f"Watching paths: {existing_paths}")

        try:
            async for changes in awatch(
                *existing_paths,
                debounce=self.DEBOUNCE_MS,
                stop_event=self._stop_event,
            ):
                # Filter to SKILL.md changes
                skill_changes = [
                    (change, path) for change, path in changes if path.endswith(self.SKILL_FILE)
                ]

                if skill_changes:
                    logger.info(f"Skill changes detected: {len(skill_changes)} file(s)")
                    for change, path in skill_changes:
                        change_type = (
                            Change(change).name if isinstance(change, int) else change.name
                        )
                        logger.debug(f"  {change_type}: {path}")

                    # Trigger registry refresh
                    registry = get_skill_registry()
                    registry.refresh()

        except asyncio.CancelledError:
            logger.debug("Skill watcher cancelled")
            raise
        except Exception as e:
            logger.error(f"Skill watcher error: {e}")
            # Don't set _running = False here — supervisor handles restart
            raise

    async def _supervisor_loop(
        self,
        initial_delay: float = INITIAL_BACKOFF_S,
        max_delay: float = MAX_BACKOFF_S,
        reset_threshold: float = RESET_THRESHOLD_S,
    ) -> None:
        """Supervisor loop with exponential backoff for crash recovery.

        Runs _watch_loop() continuously. On crash:
        - Waits `delay` seconds before restarting (up to max_delay)
        - Doubles delay on each consecutive failure (backoff factor 2x)
        - Resets delay to initial if last run lasted longer than reset_threshold

        Args:
            initial_delay: First retry wait time in seconds (default 1s)
            max_delay: Maximum wait time between retries (default 60s)
            reset_threshold: Reset backoff if run lasted longer than this (default 60s)
        """
        delay = initial_delay

        while not self._stop_event.is_set():
            start_ts = time.monotonic()
            try:
                await self._watch_loop()
                # _watch_loop returned cleanly (stop_event triggered or no paths)
                break
            except asyncio.CancelledError:
                logger.debug("Skill watcher supervisor cancelled")
                raise
            except Exception as e:
                elapsed = time.monotonic() - start_ts
                logger.error(
                    f"Skill watcher crashed after {elapsed:.1f}s: {e} — restarting in {delay:.1f}s"
                )

                # Reset backoff if the run was long enough (stable run)
                if elapsed >= reset_threshold:
                    logger.info(
                        f"Skill watcher ran for {elapsed:.1f}s before crash — "
                        "resetting backoff to initial delay"
                    )
                    delay = initial_delay
                else:
                    # Wait before restarting
                    try:
                        await asyncio.sleep(delay)
                    except asyncio.CancelledError:
                        raise

                    # Increase delay for next crash (exponential backoff, capped)
                    delay = min(delay * 2, max_delay)

        self._running = False
        logger.info("Skill watcher supervisor exited")

# =============================================================================
# Global Watcher Management
# =============================================================================

_watcher: SkillWatcher | None = None
_watcher_lock = threading.Lock()

def get_skill_watcher() -> SkillWatcher:
    """Get or create global skill watcher.

    Returns:
        Singleton SkillWatcher instance
    """
    global _watcher
    if _watcher is None:
        with _watcher_lock:
            if _watcher is None:
                _watcher = SkillWatcher()
    return _watcher

async def start_skill_watcher() -> None:
    """Start the global skill watcher.

    Convenience function for application startup.
    """
    watcher = get_skill_watcher()
    await watcher.start()

async def stop_skill_watcher() -> None:
    """Stop the global skill watcher.

    Convenience function for application shutdown.
    """
    watcher = get_skill_watcher()
    await watcher.stop()

def is_hot_reload_available() -> bool:
    """Check if skill hot reload is available.

    Returns:
        True if watchfiles is installed
    """
    return WATCHFILES_AVAILABLE
