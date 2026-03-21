"""Health check utilities for dependency verification.

Provides individual health checkers for all service dependencies:
- Database (PostgreSQL)
- Redis (cache)
- Qdrant (vector database)
- Neo4j (graph database)
- Plugin health checks (registered dynamically by plugins)

Each checker returns a HealthStatus with health state, message, and latency.
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from prometheus_client import Gauge

from core.config import get_settings
from core.logs import get_logger

if TYPE_CHECKING:
    from core.ee.plugins_ee import PluginHealthCheck
from core.utils.time import utcnow

logger = get_logger(__name__)

# Backup recency constants
BACKUP_TIMESTAMP_FILE = Path.home() / ".dryade" / "last-backup-timestamp"
BACKUP_STALE_THRESHOLD_HOURS = 48

# Prometheus metric for backup age
backup_age_hours = Gauge("dryade_backup_age_hours", "Hours since last database backup")

# =============================================================================
# Plugin Health Registry
# =============================================================================

class PluginHealthRegistry:
    """Registry for plugin health checks.

    Plugins register their health checks here during startup.
    The health system queries this registry when performing health checks.
    """

    _instance: "PluginHealthRegistry | None" = None

    def __init__(self):
        self._checks: dict[str, PluginHealthCheck] = {}
        self._plugin_names: dict[str, str] = {}  # check_key -> plugin_name

    @classmethod
    def get_instance(cls) -> "PluginHealthRegistry":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, plugin_name: str, check: "PluginHealthCheck") -> None:
        """Register a plugin health check.

        Args:
            plugin_name: Name of the plugin registering the check
            check: Health check definition
        """
        key = f"{plugin_name}.{check.name}"
        self._checks[key] = check
        self._plugin_names[key] = plugin_name
        logger.debug(f"Registered health check: {key} ({check.category})")

    def unregister(self, plugin_name: str) -> None:
        """Unregister all health checks for a plugin.

        Args:
            plugin_name: Name of the plugin to unregister
        """
        keys_to_remove = [k for k, p in self._plugin_names.items() if p == plugin_name]
        for key in keys_to_remove:
            del self._checks[key]
            del self._plugin_names[key]
        if keys_to_remove:
            logger.debug(
                f"Unregistered {len(keys_to_remove)} health checks for plugin: {plugin_name}"
            )

    async def check_all(self) -> dict[str, "HealthStatus"]:
        """Run all registered plugin health checks.

        Returns:
            Dictionary mapping check key to HealthStatus
        """
        results = {}

        for key, check in self._checks.items():
            try:
                healthy, message, latency_ms = await asyncio.wait_for(
                    check.check_fn(),
                    timeout=check.timeout_seconds,
                )
                results[key] = HealthStatus(healthy, message, latency_ms)
            except TimeoutError:
                results[key] = HealthStatus(
                    False, f"Health check timed out after {check.timeout_seconds}s"
                )
            except Exception as e:
                logger.error(f"Plugin health check {key} failed: {e}")
                results[key] = HealthStatus(False, f"Check error: {str(e)}")

        return results

    def get_check_info(self) -> dict[str, dict]:
        """Get metadata about all registered checks.

        Returns:
            Dictionary with check metadata (category, description, plugin)
        """
        return {
            key: {
                "plugin": self._plugin_names[key],
                "category": check.category,
                "description": check.description,
            }
            for key, check in self._checks.items()
        }

def get_plugin_health_registry() -> PluginHealthRegistry:
    """Get the plugin health registry singleton."""
    return PluginHealthRegistry.get_instance()

from enum import Enum

class HealthStatusLevel(str, Enum):
    """Health status levels for graceful degradation.

    HEALTHY: Service is fully operational
    DEGRADED: Service has reduced functionality but is usable
    UNHEALTHY: Service is not operational
    """

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"

class HealthStatus:
    """Health check result with status, message, and metrics.

    Supports both boolean healthy flag (backward compatible) and
    HealthStatusLevel enum for finer-grained degradation states.
    """

    def __init__(
        self,
        healthy: bool,
        message: str,
        latency_ms: float | None = None,
        status_level: HealthStatusLevel | None = None,
        suggestion: str | None = None,
    ):
        """Create a health check result.

        Args:
            healthy: Whether the service is healthy (backward compatible)
            message: Human-readable status message
            latency_ms: Response latency in milliseconds (optional)
            status_level: Finer-grained status level (HEALTHY, DEGRADED, UNHEALTHY)
            suggestion: Actionable suggestion for resolution (optional)
        """
        self.healthy = healthy
        self.message = message
        self.latency_ms = latency_ms
        self.timestamp = utcnow().isoformat()
        self.suggestion = suggestion

        # Derive status_level from healthy if not provided
        if status_level is not None:
            self.status_level = status_level
        else:
            self.status_level = (
                HealthStatusLevel.HEALTHY if healthy else HealthStatusLevel.UNHEALTHY
            )

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        result = {
            "healthy": self.healthy,
            "status": self.status_level.value,
            "message": self.message,
            "latency_ms": self.latency_ms,
            "timestamp": self.timestamp,
        }
        if self.suggestion:
            result["suggestion"] = self.suggestion
        return result

    @classmethod
    def healthy_status(cls, message: str, latency_ms: float | None = None) -> "HealthStatus":
        """Create a healthy status result."""
        return cls(
            healthy=True,
            message=message,
            latency_ms=latency_ms,
            status_level=HealthStatusLevel.HEALTHY,
        )

    @classmethod
    def degraded_status(
        cls, message: str, suggestion: str | None = None, latency_ms: float | None = None
    ) -> "HealthStatus":
        """Create a degraded status result."""
        return cls(
            healthy=True,
            message=message,
            latency_ms=latency_ms,
            status_level=HealthStatusLevel.DEGRADED,
            suggestion=suggestion,
        )

    @classmethod
    def unhealthy_status(cls, message: str, suggestion: str | None = None) -> "HealthStatus":
        """Create an unhealthy status result."""
        return cls(
            healthy=False,
            message=message,
            status_level=HealthStatusLevel.UNHEALTHY,
            suggestion=suggestion,
        )

async def check_database() -> HealthStatus:
    """Check database connectivity with graceful degradation.

    Executes a simple query to verify database is accessible.
    Returns degraded status on slow response, unhealthy on error.

    Returns:
        HealthStatus with connection status, latency, and suggestion if needed
    """
    try:
        from sqlalchemy import text

        from core.database.session import get_engine

        start = utcnow()
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        latency = (utcnow() - start).total_seconds() * 1000

        if latency > 500:
            logger.warning(f"Database health check slow: {latency:.2f}ms")
            return HealthStatus.degraded_status(
                f"Database slow: {latency:.0f}ms",
                suggestion="Consider database optimization or scaling",
                latency_ms=latency,
            )

        return HealthStatus.healthy_status("Database connection OK", latency)
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return HealthStatus.unhealthy_status(
            f"Database error: {str(e)}",
            suggestion="Check database connection settings and server status",
        )

async def check_redis() -> HealthStatus:
    """Check Redis connectivity with graceful degradation.

    Pings Redis server to verify it's accessible.
    Returns degraded status on slow response or connection issues (non-critical).

    Returns:
        HealthStatus with connection status, latency, and suggestion if needed
    """
    settings = get_settings()
    if not settings.redis_url:
        return HealthStatus.healthy_status("Redis not configured (optional)")

    try:
        import redis

        start = utcnow()
        client = redis.from_url(settings.redis_url, socket_connect_timeout=2)
        client.ping()
        client.close()
        latency = (utcnow() - start).total_seconds() * 1000

        if latency > 500:
            logger.warning(f"Redis health check slow: {latency:.2f}ms")
            return HealthStatus.degraded_status(
                f"Redis slow: {latency:.0f}ms",
                suggestion="Check Redis server performance or network latency",
                latency_ms=latency,
            )

        return HealthStatus.healthy_status("Redis connection OK", latency)
    except Exception as e:
        # Redis is optional - return degraded, not unhealthy
        logger.warning(f"Redis health check failed: {e}")
        return HealthStatus.degraded_status(
            f"Redis unavailable: {str(e)}",
            suggestion="Check Redis server status and connection settings",
        )

async def check_qdrant() -> HealthStatus:
    """Check Qdrant connectivity with graceful degradation.

    Lists collections to verify Qdrant is accessible.
    Returns degraded status on slow response or connection issues (non-critical).

    Returns:
        HealthStatus with connection status, latency, and suggestion if needed
    """
    settings = get_settings()
    if not settings.qdrant_url:
        return HealthStatus.healthy_status("Qdrant not configured (optional)")

    try:
        from qdrant_client import QdrantClient

        start = utcnow()
        client = QdrantClient(url=settings.qdrant_url, timeout=2)
        # Simple health check - list collections
        client.get_collections()
        latency = (utcnow() - start).total_seconds() * 1000

        if latency > 500:
            logger.warning(f"Qdrant health check slow: {latency:.2f}ms")
            return HealthStatus.degraded_status(
                f"Qdrant slow: {latency:.0f}ms",
                suggestion="Check Qdrant server performance or network latency",
                latency_ms=latency,
            )

        return HealthStatus.healthy_status("Qdrant connection OK", latency)
    except Exception as e:
        # Qdrant is optional for some features - return degraded, not unhealthy
        logger.warning(f"Qdrant health check failed: {e}")
        return HealthStatus.degraded_status(
            f"Qdrant unavailable: {str(e)}",
            suggestion="Check Qdrant server status. Vector search features may be unavailable.",
        )

async def check_neo4j() -> HealthStatus:
    """Check Neo4j connectivity with graceful degradation.

    Executes a simple query to verify Neo4j is accessible.
    Returns degraded status on issues (optional dependency for graph features).

    Returns:
        HealthStatus with connection status, latency, and suggestion if needed
    """
    # Get Neo4j configuration from centralized Settings
    settings = get_settings()
    neo4j_uri = settings.neo4j_uri
    neo4j_user = settings.neo4j_user
    neo4j_password = settings.neo4j_password

    if not neo4j_uri:
        return HealthStatus.healthy_status("Neo4j not configured (optional)")

    try:
        from neo4j import GraphDatabase

        start = utcnow()
        driver = GraphDatabase.driver(
            neo4j_uri, auth=(neo4j_user, neo4j_password), connection_timeout=2
        )
        with driver.session() as session:
            session.run("RETURN 1").single()
        driver.close()
        latency = (utcnow() - start).total_seconds() * 1000

        if latency > 500:
            logger.warning(f"Neo4j health check slow: {latency:.2f}ms")
            return HealthStatus.degraded_status(
                f"Neo4j slow: {latency:.0f}ms",
                suggestion="Check Neo4j server performance or network latency",
                latency_ms=latency,
            )

        return HealthStatus.healthy_status("Neo4j connection OK", latency)
    except Exception as e:
        # Neo4j is optional - return degraded, not unhealthy
        logger.warning(f"Neo4j health check failed: {e}")
        return HealthStatus.degraded_status(
            f"Neo4j unavailable: {str(e)}",
            suggestion="Check Neo4j server status. Graph features may be unavailable.",
        )

async def check_backup_recency() -> HealthStatus:
    """Check database backup recency.

    Reads the timestamp file written by `make db-backup` and checks
    if the last backup is within the acceptable threshold (48 hours).

    Returns:
        HealthStatus: HEALTHY if recent backup, DEGRADED if stale or missing
    """
    try:
        if not BACKUP_TIMESTAMP_FILE.exists():
            backup_age_hours.set(-1)
            return HealthStatus.degraded_status(
                "No backup timestamp found",
                suggestion="Run `make db-backup` to create an initial database backup",
            )

        timestamp_str = BACKUP_TIMESTAMP_FILE.read_text().strip()
        last_backup = datetime.fromisoformat(timestamp_str)

        # Make timezone-aware if naive
        if last_backup.tzinfo is None:
            from datetime import timezone

            last_backup = last_backup.replace(tzinfo=timezone.utc)

        age_hours = (utcnow() - last_backup).total_seconds() / 3600
        backup_age_hours.set(round(age_hours, 2))

        if age_hours > BACKUP_STALE_THRESHOLD_HOURS:
            return HealthStatus.degraded_status(
                f"Last backup {age_hours:.1f}h ago (threshold: {BACKUP_STALE_THRESHOLD_HOURS}h)",
                suggestion="Run `make db-backup` to create a fresh database backup",
            )

        return HealthStatus.healthy_status(f"Last backup {age_hours:.1f}h ago")
    except Exception as e:
        logger.warning(f"Backup recency check failed: {e}")
        backup_age_hours.set(-1)
        return HealthStatus.degraded_status(
            f"Backup check error: {str(e)}",
            suggestion="Verify ~/.dryade/last-backup-timestamp contains a valid ISO timestamp",
        )

async def check_all_dependencies(include_plugins: bool = True) -> dict[str, HealthStatus]:
    """Run all health checks in parallel.

    Checks all service dependencies and returns their status.
    Each check has a 2-second timeout.

    Args:
        include_plugins: Whether to include plugin health checks (default True)

    Returns:
        Dictionary mapping service name to HealthStatus
    """
    # Core infrastructure checks
    results = {
        "database": await check_database(),
        "redis": await check_redis(),
        "qdrant": await check_qdrant(),
        "neo4j": await check_neo4j(),
        "backup": await check_backup_recency(),
    }

    # Include plugin health checks
    if include_plugins:
        registry = get_plugin_health_registry()
        plugin_checks = await registry.check_all()
        results.update(plugin_checks)

    return results

async def check_plugin_dependencies() -> dict[str, HealthStatus]:
    """Run only plugin health checks.

    Returns:
        Dictionary mapping check key (plugin.check_name) to HealthStatus
    """
    registry = get_plugin_health_registry()
    return await registry.check_all()

async def get_overall_health(include_plugins: bool = True) -> dict:
    """Get overall system health with aggregated status.

    Aggregates all health check results into an overall status:
    - HEALTHY: All checks pass with HEALTHY status
    - DEGRADED: Some checks have DEGRADED status, none UNHEALTHY
    - UNHEALTHY: Any check has UNHEALTHY status

    Args:
        include_plugins: Whether to include plugin health checks (default True)

    Returns:
        Dictionary with overall status and component details
    """
    results = await check_all_dependencies(include_plugins)

    # Aggregate status levels
    status_levels = [r.status_level for r in results.values()]

    if all(s == HealthStatusLevel.HEALTHY for s in status_levels):
        overall = HealthStatusLevel.HEALTHY
    elif any(s == HealthStatusLevel.UNHEALTHY for s in status_levels):
        overall = HealthStatusLevel.UNHEALTHY
    else:
        overall = HealthStatusLevel.DEGRADED

    # Count by status level
    healthy_count = sum(1 for s in status_levels if s == HealthStatusLevel.HEALTHY)
    degraded_count = sum(1 for s in status_levels if s == HealthStatusLevel.DEGRADED)
    unhealthy_count = sum(1 for s in status_levels if s == HealthStatusLevel.UNHEALTHY)

    return {
        "status": overall.value,
        "healthy": overall != HealthStatusLevel.UNHEALTHY,
        "counts": {
            "healthy": healthy_count,
            "degraded": degraded_count,
            "unhealthy": unhealthy_count,
            "total": len(results),
        },
        "components": {name: result.to_dict() for name, result in results.items()},
    }
