# Copyright (c) 2025-2026 Dryade SAS
# Licensed under the Dryade Enterprise Edition License. See LICENSE_EE.md.
"""Marketplace heartbeat for license revocation checking.

SECURITY EXCEPTION: Core normally never calls external services. This heartbeat
is the ONE documented exception for license revocation checking. Without it, a
revoked license continues working as long as the allowlist file exists on disk.

Behavior:
  - Fires every 6 hours as async background task
  - "revoked" response from marketplace disables all plugins immediately
  - 7+ consecutive days without successful heartbeat disables all plugins
  - Successful heartbeat resets the unreachable counter
  - NEVER blocks plugin loading or API responses
  - Disabled when no DRYADE_MARKETPLACE_URL is configured (dev/community)
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# Configuration
HEARTBEAT_INTERVAL_HOURS = 6
STARTUP_GRACE_MINUTES = 5
MAX_UNREACHABLE_DAYS = 7

# State
_last_heartbeat_success: datetime | None = None
_consecutive_failures: int = 0
_revoked: bool = False
_heartbeat_task: asyncio.Task | None = None
_disable_callback = None

def get_marketplace_url() -> str | None:
    """Return marketplace URL from env, or None if not configured."""
    return os.environ.get("DRYADE_MARKETPLACE_URL")

def get_instance_id() -> str:
    """Return instance ID from env or generate a stable one."""
    return os.environ.get("DRYADE_INSTANCE_ID", "dev-instance")

def is_revoked() -> bool:
    """Return True if the license has been revoked by marketplace."""
    return _revoked

def set_disable_callback(callback) -> None:
    """Register the callback to disable all plugins on revocation."""
    global _disable_callback
    _disable_callback = callback

async def _disable_all_plugins(reason: str) -> None:
    """Disable all plugins via the registered callback."""
    global _revoked
    _revoked = True
    logger.critical("Disabling all plugins: %s", reason)
    if _disable_callback is not None:
        try:
            result = _disable_callback(reason)
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            logger.exception("Plugin disable callback failed")

async def _do_heartbeat() -> bool:
    """Perform a single heartbeat check. Returns True on success."""
    global _last_heartbeat_success, _consecutive_failures, _revoked

    url = get_marketplace_url()
    if not url:
        return True  # No marketplace configured -- always OK

    try:
        import httpx

        endpoint = f"{url.rstrip('/')}/api/license/status"
        params = {"instance_id": get_instance_id()}

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(endpoint, params=params)
            resp.raise_for_status()
            data = resp.json()

        status = data.get("status", "unknown")

        if status == "revoked":
            await _disable_all_plugins(
                f"License revoked by marketplace (status={status})"
            )
            return False

        if status == "suspended":
            logger.warning("License suspended -- plugins remain active for now")

        # Success -- reset counters
        _last_heartbeat_success = datetime.now(timezone.utc)
        _consecutive_failures = 0
        logger.debug("Heartbeat success: status=%s", status)
        return True

    except Exception as exc:
        _consecutive_failures += 1
        logger.warning(
            "Heartbeat failed (attempt %d): %s", _consecutive_failures, exc
        )

        # Check if we've exceeded max unreachable time
        if _last_heartbeat_success is not None:
            elapsed = datetime.now(timezone.utc) - _last_heartbeat_success
            if elapsed > timedelta(days=MAX_UNREACHABLE_DAYS):
                await _disable_all_plugins(
                    f"Marketplace unreachable for {elapsed.days} days "
                    f"(max {MAX_UNREACHABLE_DAYS})"
                )
                return False

        return False

async def _heartbeat_loop() -> None:
    """Background heartbeat loop -- runs every HEARTBEAT_INTERVAL_HOURS."""
    global _last_heartbeat_success

    # Grace period: let plugins load first
    await asyncio.sleep(STARTUP_GRACE_MINUTES * 60)

    # Assume success at startup (don't kill plugins on first boot)
    _last_heartbeat_success = datetime.now(timezone.utc)

    while True:
        if _revoked:
            logger.info("Heartbeat loop exiting -- license revoked")
            return

        await _do_heartbeat()
        await asyncio.sleep(HEARTBEAT_INTERVAL_HOURS * 3600)

async def start_heartbeat() -> None:
    """Start the heartbeat background task if marketplace URL is configured."""
    global _heartbeat_task

    if get_marketplace_url() is None:
        logger.info("No DRYADE_MARKETPLACE_URL -- heartbeat disabled")
        return

    if _heartbeat_task is not None and not _heartbeat_task.done():
        return

    _heartbeat_task = asyncio.create_task(_heartbeat_loop())
    logger.info("Marketplace heartbeat started (every %dh)", HEARTBEAT_INTERVAL_HOURS)

async def stop_heartbeat() -> None:
    """Stop the heartbeat background task."""
    global _heartbeat_task
    if _heartbeat_task is not None:
        _heartbeat_task.cancel()
        try:
            await _heartbeat_task
        except asyncio.CancelledError:
            pass
        _heartbeat_task = None
        logger.info("Marketplace heartbeat stopped")

def reset_state() -> None:
    """Reset all heartbeat state -- for testing only."""
    global _last_heartbeat_success, _consecutive_failures, _revoked
    global _heartbeat_task, _disable_callback
    _last_heartbeat_success = None
    _consecutive_failures = 0
    _revoked = False
    _heartbeat_task = None
    _disable_callback = None
