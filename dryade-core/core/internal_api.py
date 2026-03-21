"""DEPRECATED: Import from core.ee instead.

This module exists only for backward compatibility.
Will be removed in v1.1.

The internal API for Plugin Manager communication is an enterprise
feature. See https://dryade.ai/pricing for details.
"""

import logging
import warnings
from collections.abc import Callable

warnings.warn(
    "Importing from core.internal_api is deprecated. Use core.ee.internal_api instead.",
    DeprecationWarning,
    stacklevel=2,
)

logger = logging.getLogger(__name__)

# Re-export from enterprise edition for backward compat
try:
    from core.ee.internal_api import (  # noqa: F401
        get_last_allowlist_update,
        internal_app,
        receive_allowlist,
        set_hot_reload_callback,
        start_internal_api,
        stop_internal_api,
    )
except ImportError:
    # Community edition stubs (no core.ee available)

    def set_hot_reload_callback(callback: Callable) -> None:
        """Set the hot-reload callback (enterprise feature).

        In the community edition, this is a no-op.
        """
        pass

    def get_last_allowlist_update() -> dict | None:
        """Get the last allowlist update info (enterprise feature).

        In the community edition, returns None (no marketplace polling).
        """
        return None

    async def start_internal_api(port: int = 9471, host: str = "127.0.0.1") -> None:
        """Start the internal API server (enterprise feature).

        In the community edition, this is a no-op.

        Args:
            port: Port to listen on (ignored in community edition).
            host: Host to bind to (ignored in community edition).
        """
        logger.debug("Internal API is an enterprise feature - skipping")

    async def stop_internal_api() -> None:
        """Stop the internal API server (enterprise feature).

        In the community edition, this is a no-op.
        """
        pass
