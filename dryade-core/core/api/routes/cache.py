"""Cache Management Endpoints.

Provides monitoring, tuning, and management for the two-tier semantic cache system.
The cache uses exact matching (Redis) and semantic matching (Qdrant) with an
in-memory fallback when external services are unavailable.

Target: ~150 LOC
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from core.api.models.openapi import response_with_errors
import core.extensions as _extensions
from core.logs import get_logger
from core.utils.time import utcnow

router = APIRouter(tags=["cache"])
logger = get_logger(__name__)

_PLUGIN_UNAVAILABLE = HTTPException(
    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    detail="Semantic cache plugin is not loaded",
)

class CacheTuneRequest(BaseModel):
    """Request to dynamically update cache configuration at runtime."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "similarity_threshold": 0.85,
                "exact_ttl_seconds": 3600,
                "semantic_ttl_seconds": 86400,
                "enabled": True,
            }
        }
    )

    similarity_threshold: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Cosine similarity threshold for semantic matching (0.0-1.0). Higher values require closer matches.",
    )
    exact_ttl_seconds: int | None = Field(
        None,
        ge=60,
        le=86400,
        description="Time-to-live for exact match cache entries (60-86400 seconds)",
    )
    semantic_ttl_seconds: int | None = Field(
        None,
        ge=300,
        le=604800,
        description="Time-to-live for semantic match cache entries (300-604800 seconds)",
    )
    enabled: bool | None = Field(
        None, description="Enable or disable the semantic cache (acts as circuit breaker)"
    )

class CacheSizeInfo(BaseModel):
    """Cache size and utilization information across all tiers."""

    qdrant_vectors: int = Field(0, description="Number of vector embeddings stored in Qdrant")
    redis_keys: int = Field(0, description="Number of exact-match keys in Redis")
    memory_entries: int = Field(0, description="Number of entries in the in-memory fallback cache")
    max_entries: int = Field(10000, description="Maximum configured cache entries")
    utilization_pct: float = Field(0.0, description="Cache utilization as percentage (0.0-100.0)")

class CacheStatsResponse(BaseModel):
    """Comprehensive cache statistics including hit rates, performance, and service health."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total_queries": 1000,
                "exact_hits": 200,
                "semantic_hits": 300,
                "fallback_hits": 50,
                "misses": 450,
                "hit_rate": 0.55,
                "avg_lookup_time_ms": 5.2,
                "avg_embedding_time_ms": 25.0,
                "memory_cache_size": 150,
                "services": {"redis": True, "qdrant": True},
                "config": {"enabled": True, "similarity_threshold": 0.85},
                "timestamp": "2026-01-14T00:00:00Z",
            }
        }
    )

    total_queries: int = Field(..., description="Total number of cache lookups performed")
    exact_hits: int = Field(..., description="Number of exact match cache hits (hash-based, Redis)")
    semantic_hits: int = Field(
        ..., description="Number of semantic similarity cache hits (vector-based, Qdrant)"
    )
    fallback_hits: int = Field(..., description="Number of hits from in-memory fallback cache")
    misses: int = Field(..., description="Number of cache misses requiring LLM call")
    hit_rate: float = Field(..., description="Overall cache hit rate (0.0-1.0)")
    avg_lookup_time_ms: float = Field(
        ..., description="Average time to check cache in milliseconds"
    )
    avg_embedding_time_ms: float = Field(
        ..., description="Average time to generate embeddings in milliseconds"
    )
    memory_cache_size: int = Field(..., description="Current size of the in-memory fallback cache")
    services: dict[str, bool] = Field(
        ..., description="Service availability status (redis, qdrant)"
    )
    config: dict[str, Any] = Field(..., description="Current cache configuration")
    timestamp: str = Field(..., description="Timestamp when stats were collected (ISO 8601)")
    # Streaming-specific stats
    streaming_hits: int = Field(0, description="Cache hits for streaming requests")
    streaming_misses: int = Field(0, description="Cache misses for streaming requests")
    streaming_hit_rate: float = Field(0.0, description="Hit rate for streaming requests (0.0-1.0)")
    # Cache size info
    cache_size: CacheSizeInfo | None = Field(
        None, description="Detailed cache size information by tier"
    )

class CacheTuneResponse(BaseModel):
    """Response after updating cache configuration."""

    message: str = Field(..., description="Status message confirming the update")
    updates: dict[str, Any] = Field(..., description="Dictionary of updated configuration values")
    current_config: dict[str, Any] = Field(
        ..., description="Current cache configuration after updates"
    )
    note: str = Field(..., description="Important note about persistence of changes")

class CacheClearResponse(BaseModel):
    """Response after clearing the cache."""

    message: str = Field(..., description="Status message confirming cache was cleared")
    entries_cleared: int = Field(
        ..., description="Number of memory cache entries that were cleared"
    )
    timestamp: str = Field(..., description="Timestamp when cache was cleared (ISO 8601)")

class CacheEvictResponse(BaseModel):
    """Response after evicting cache entries."""

    message: str = Field(..., description="Status message with eviction summary")
    requested: int = Field(..., description="Number of entries requested to evict")
    evicted: int = Field(..., description="Number of entries actually evicted")
    size_before: dict[str, Any] = Field(..., description="Cache size before eviction by tier")
    size_after: dict[str, Any] = Field(..., description="Cache size after eviction by tier")
    timestamp: str = Field(..., description="Timestamp when eviction occurred (ISO 8601)")

class CacheHealthResponse(BaseModel):
    """Cache health status response."""

    healthy: bool = Field(
        ..., description="True if cache is functional (at least memory fallback works)"
    )
    degraded: bool = Field(
        ..., description="True if external services (Redis/Qdrant) are unavailable"
    )
    services: dict[str, str] = Field(..., description="Health status of each service tier")
    enabled: bool = Field(..., description="Whether semantic caching is enabled")
    hit_rate: float = Field(..., description="Current cache hit rate (0.0-1.0)")
    total_queries: int = Field(..., description="Total queries processed since startup")
    timestamp: str = Field(..., description="Timestamp when health was checked (ISO 8601)")

@router.get(
    "/stats",
    response_model=CacheStatsResponse,
    responses=response_with_errors(500, 503),
)
async def get_cache_stats():
    """Get comprehensive cache statistics.

    Returns:
    - Hit/miss counts by type (exact, semantic, fallback)
    - Performance metrics (lookup times, embedding times)
    - Service availability (Redis, Qdrant)
    - Current configuration

    Use this endpoint for:
    - Monitoring cache effectiveness
    - Identifying performance bottlenecks
    - Verifying service health
    """
    if not _extensions.get_semantic_cache:
        raise _PLUGIN_UNAVAILABLE
    try:
        cache = _extensions.get_semantic_cache()
        stats = cache.get_stats()

        # Get cache size info
        size_info = await cache.get_cache_size()
        max_entries = size_info.get("max_entries", 10000)
        qdrant_count = size_info.get("qdrant_vectors", 0)
        utilization = (qdrant_count / max_entries * 100) if max_entries > 0 else 0.0

        cache_size = CacheSizeInfo(
            qdrant_vectors=qdrant_count,
            redis_keys=size_info.get("redis_keys", 0),
            memory_entries=size_info.get("memory_entries", 0),
            max_entries=max_entries,
            utilization_pct=round(utilization, 2),
        )

        return CacheStatsResponse(
            total_queries=stats["total_queries"],
            exact_hits=stats["exact_hits"],
            semantic_hits=stats["semantic_hits"],
            fallback_hits=stats["fallback_hits"],
            misses=stats["misses"],
            hit_rate=stats["hit_rate"],
            avg_lookup_time_ms=stats["avg_lookup_time_ms"],
            avg_embedding_time_ms=stats["avg_embedding_time_ms"],
            memory_cache_size=stats["memory_cache_size"],
            services=stats["services"],
            config=stats["config"],
            timestamp=utcnow().isoformat(),
            # Streaming-specific stats
            streaming_hits=stats.get("streaming_hits", 0),
            streaming_misses=stats.get("streaming_misses", 0),
            streaming_hit_rate=stats.get("streaming_hit_rate", 0.0),
            # Cache size info
            cache_size=cache_size,
        )
    except Exception as e:
        logger.error(f"Failed to get cache stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve cache statistics: {str(e)}",
        ) from e

@router.post(
    "/tune",
    response_model=CacheTuneResponse,
    responses=response_with_errors(400, 500),
)
async def tune_cache(request: CacheTuneRequest) -> CacheTuneResponse:
    """Update cache configuration dynamically.

    Allows runtime tuning of the two-tier cache system:
    - Similarity threshold: Adjust semantic matching sensitivity (higher = stricter)
    - TTL values: Control cache entry retention for exact and semantic matches
    - Enable/disable flag: Circuit breaker for disabling cache entirely

    Configuration changes take effect immediately but are NOT persisted.
    To persist changes, update environment variables or config file.
    """
    if not _extensions.get_cache_config:
        raise _PLUGIN_UNAVAILABLE
    try:
        config = _extensions.get_cache_config()

        # Validate and apply changes
        updates = {}

        if request.similarity_threshold is not None:
            if not (0.0 <= request.similarity_threshold <= 1.0):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="similarity_threshold must be between 0.0 and 1.0",
                )
            config.similarity_threshold = request.similarity_threshold
            updates["similarity_threshold"] = request.similarity_threshold
            logger.info(f"Updated similarity_threshold to {request.similarity_threshold}")

        if request.exact_ttl_seconds is not None:
            config.exact_ttl_seconds = request.exact_ttl_seconds
            updates["exact_ttl_seconds"] = request.exact_ttl_seconds
            logger.info(f"Updated exact_ttl_seconds to {request.exact_ttl_seconds}")

        if request.semantic_ttl_seconds is not None:
            config.semantic_ttl_seconds = request.semantic_ttl_seconds
            updates["semantic_ttl_seconds"] = request.semantic_ttl_seconds
            logger.info(f"Updated semantic_ttl_seconds to {request.semantic_ttl_seconds}")

        if request.enabled is not None:
            config.enabled = request.enabled
            updates["enabled"] = request.enabled
            logger.info(f"Cache {'enabled' if request.enabled else 'disabled'}")

        # Return current configuration
        return CacheTuneResponse(
            message="Configuration updated successfully",
            updates=updates,
            current_config={
                "enabled": config.enabled,
                "similarity_threshold": config.similarity_threshold,
                "exact_ttl_seconds": config.exact_ttl_seconds,
                "semantic_ttl_seconds": config.semantic_ttl_seconds,
                "embedding_model": config.embedding_model,
            },
            note="Changes are not persisted. Update environment variables to persist.",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to tune cache: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update cache configuration: {str(e)}",
        ) from e

@router.delete(
    "/clear",
    response_model=CacheClearResponse,
    responses=response_with_errors(500, 503),
)
async def clear_cache() -> CacheClearResponse:
    """Clear all cached entries from all tiers.

    Removes entries from all cache tiers:
    - Redis response cache (exact matches)
    - Qdrant vector embeddings (semantic matches)
    - In-memory fallback cache

    Use with caution: This forces cache misses for all queries
    until the cache is repopulated through normal usage.
    """
    if not _extensions.get_semantic_cache:
        raise _PLUGIN_UNAVAILABLE
    try:
        cache = _extensions.get_semantic_cache()

        # Get stats before clearing
        stats_before = cache.get_stats()
        entries_before = stats_before["memory_cache_size"]

        # Clear all caches
        success = cache.clear()

        if success:
            logger.info(f"Cache cleared successfully (removed {entries_before} memory entries)")
            return CacheClearResponse(
                message="Cache cleared successfully",
                entries_cleared=entries_before,
                timestamp=utcnow().isoformat(),
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to clear cache"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to clear cache: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear cache: {str(e)}",
        ) from e

@router.post(
    "/evict",
    response_model=CacheEvictResponse,
    responses=response_with_errors(400, 500, 503),
)
async def evict_cache(
    count: int = Query(
        100, ge=1, le=10000, description="Number of oldest entries to evict from cache"
    ),
) -> CacheEvictResponse:
    """Manually evict oldest cache entries.

    Evicts the oldest entries from all cache tiers (Qdrant, Redis, memory).
    Use this to proactively free cache space or during maintenance windows.
    The actual number evicted may be less than requested if the cache has
    fewer entries.
    """
    if not _extensions.get_semantic_cache:
        raise _PLUGIN_UNAVAILABLE
    try:
        cache = _extensions.get_semantic_cache()

        # Get size before eviction
        size_before = await cache.get_cache_size()

        # Perform eviction
        total_evicted = await cache.evict_oldest(count)

        # Get size after eviction
        size_after = await cache.get_cache_size()

        logger.info(f"Manual cache eviction: requested={count}, evicted={total_evicted}")

        return CacheEvictResponse(
            message=f"Evicted {total_evicted} cache entries",
            requested=count,
            evicted=total_evicted,
            size_before=size_before,
            size_after=size_after,
            timestamp=utcnow().isoformat(),
        )

    except Exception as e:
        logger.error(f"Failed to evict cache entries: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to evict cache entries: {str(e)}",
        ) from e

@router.get(
    "/health",
    response_model=CacheHealthResponse,
    responses=response_with_errors(500, 503),
)
async def cache_health() -> CacheHealthResponse:
    """Check cache service health.

    Returns health status for all cache tiers and services. The cache is
    considered healthy if the in-memory fallback is operational (always true).
    Degraded status indicates external services (Redis/Qdrant) are unavailable.

    Use this endpoint for monitoring and alerting on cache health.
    """
    if not _extensions.get_semantic_cache:
        raise _PLUGIN_UNAVAILABLE
    try:
        cache = _extensions.get_semantic_cache()
        stats = cache.get_stats()

        # Determine health status
        redis_ok = stats["services"]["redis"]
        qdrant_ok = stats["services"]["qdrant"]
        memory_ok = stats["memory_cache_size"] >= 0

        healthy = memory_ok  # Always healthy if in-memory fallback works
        degraded = not (redis_ok and qdrant_ok)

        return CacheHealthResponse(
            healthy=healthy,
            degraded=degraded,
            services={
                "redis": "healthy" if redis_ok else "unavailable",
                "qdrant": "healthy" if qdrant_ok else "unavailable",
                "memory_fallback": "healthy" if memory_ok else "unhealthy",
            },
            enabled=stats["config"]["enabled"],
            hit_rate=stats["hit_rate"],
            total_queries=stats["total_queries"],
            timestamp=utcnow().isoformat(),
        )

    except Exception as e:
        logger.error(f"Failed to check cache health: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check cache health: {str(e)}",
        ) from e
