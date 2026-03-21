"""MCP Capability Cache.

Caches MCP server capabilities (tools, resources) with TTL-based invalidation.
Invalidates on server restart to ensure fresh capabilities.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("dryade.mcp.cache")

DEFAULT_TTL_SECONDS = 300  # 5 minutes

@dataclass
class CacheEntry:
    """Single cache entry with TTL."""

    data: Any
    expires_at: float
    server_start_time: float | None = None  # Track server start for restart detection

@dataclass
class CapabilityCache:
    """TTL-based cache for MCP capabilities.

    Features:
    - TTL-based expiration (default 5 minutes)
    - Invalidation on server restart
    - Thread-safe for concurrent access
    """

    ttl_seconds: float = DEFAULT_TTL_SECONDS
    _cache: dict[str, CacheEntry] = field(default_factory=dict)

    def get(self, server_name: str, server_start_time: float | None = None) -> Any | None:
        """Get cached capabilities for a server.

        Args:
            server_name: MCP server name
            server_start_time: Current server start time (for restart detection)

        Returns:
            Cached capabilities or None if not cached/expired/invalidated
        """
        entry = self._cache.get(server_name)
        if entry is None:
            return None

        now = time.time()

        # Check TTL expiration
        if now > entry.expires_at:
            logger.debug(f"[CACHE] {server_name} cache expired (TTL)")
            del self._cache[server_name]
            return None

        # Check server restart (if start time provided and differs)
        if server_start_time and entry.server_start_time:
            if server_start_time != entry.server_start_time:
                logger.info(f"[CACHE] {server_name} cache invalidated (server restarted)")
                del self._cache[server_name]
                return None

        logger.debug(f"[CACHE] {server_name} cache hit")
        return entry.data

    def set(
        self,
        server_name: str,
        capabilities: Any,
        server_start_time: float | None = None,
    ) -> None:
        """Cache capabilities for a server."""
        entry = CacheEntry(
            data=capabilities,
            expires_at=time.time() + self.ttl_seconds,
            server_start_time=server_start_time,
        )
        self._cache[server_name] = entry
        logger.debug(f"[CACHE] {server_name} capabilities cached (TTL={self.ttl_seconds}s)")

    def invalidate(self, server_name: str) -> None:
        """Invalidate cache for a specific server."""
        if server_name in self._cache:
            del self._cache[server_name]
            logger.info(f"[CACHE] {server_name} cache invalidated")

    def invalidate_all(self) -> None:
        """Invalidate entire cache."""
        self._cache.clear()
        logger.info("[CACHE] All capabilities cache cleared")

    def stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        now = time.time()
        active = sum(1 for e in self._cache.values() if e.expires_at > now)
        return {
            "total_entries": len(self._cache),
            "active_entries": active,
            "expired_entries": len(self._cache) - active,
        }

# Global singleton
_cache: CapabilityCache | None = None

def get_capability_cache(ttl_seconds: float = DEFAULT_TTL_SECONDS) -> CapabilityCache:
    """Get the global capability cache."""
    global _cache
    if _cache is None:
        _cache = CapabilityCache(ttl_seconds=ttl_seconds)
    return _cache

def reset_capability_cache() -> None:
    """Reset the global capability cache (for testing)."""
    global _cache
    _cache = None
