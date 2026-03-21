"""Dryade API - Minimal FastAPI wrapper around CrewAI.

Updated to support domain plugin system for generic multi-framework execution.
Target: 80 LOC

Exception Handling:
- Centralized exception handlers for consistent error responses
- Logs all errors with request context before returning to client
- Specific handlers for common errors (ValueError, FileNotFoundError, etc.)
- Generic handler for unexpected errors
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.exc import DatabaseError, IntegrityError, OperationalError

from core.api.middleware import (
    AuthMiddleware,
    LLMContextMiddleware,
    RateLimitMiddleware,
)
from core.api.middleware.request_metrics import RequestMetricsMiddleware
from core.api.models import ErrorResponse
from core.api.routes import (
    a2a_server,
    agents,
    audit_admin,
    auth,
    chat,
    clarify,
    commands,
    consent,
    cost_tracker,
    custom_providers,
    dsar,
    extensions,
    factory,
    flows,
    health,
    knowledge,
    loops,
    marketplace,
    mcp_metrics,
    metrics_api,
    mfa,
    models_config,
    plans,
    plugins,
    projects,
    provider_health,
    provider_registry,
    setup,
    skills,
    transparency,
    users,
    version,
    websocket,
    workflow_scenarios,
    workflows,
)

# Enterprise-only routes (conditional import)
try:
    from core.api.routes import cache, files, healing, safety, sandbox

    ENTERPRISE_ROUTES_AVAILABLE = True
except ImportError:
    ENTERPRISE_ROUTES_AVAILABLE = False
    # Note: logger not available yet, will be logged in lifespan startup

# Security telemetry routes
from core.api.routes import security_telemetry
from core.config import get_settings
from core.logs import create_request_context, get_logger, log_error
from core.mcp.autoload import register_mcp_agents
from core.observability import metrics_router
from core.observability.logging import configure_logging
from core.retention import router as retention_router

settings = get_settings()

# Configure logging at module level so all loggers created at import time
# get the ColoredFormatter applied. The lifespan also calls configure_logging
# as a safety net (idempotent), but this ensures colors are active before
# uvicorn's own logging setup can override handlers.
configure_logging(level=settings.log_level, format=settings.log_format)

logger = get_logger(__name__)

# Log enterprise routes availability after logger is initialized
if not ENTERPRISE_ROUTES_AVAILABLE:
    logger.warning(
        "Enterprise routes not available (missing plugins) - running without enterprise routes"
    )

# ============================================================================
# OpenAPI Tag Descriptions
# ============================================================================
# Each tag corresponds to a route module and provides documentation in /docs
tags_metadata = [
    {
        "name": "auth",
        "description": "Authentication endpoints. User registration, login, token refresh, and initial admin setup.",
    },
    {
        "name": "users",
        "description": "User profile management. View and update user profiles, admin user listing.",
    },
    {
        "name": "chat",
        "description": "Chat execution endpoints. Supports streaming (SSE) and non-streaming modes. Routes messages through CHAT, CREW, FLOW, or PLANNER execution modes.",
    },
    {
        "name": "agents",
        "description": "Agent registry and execution. List registered agents, query capabilities, execute tasks with specific agents.",
    },
    {
        "name": "flows",
        "description": "Predefined workflow execution. Execute multi-step flows like AnalysisFlow or CoverageFlow.",
    },
    {
        "name": "workflows",
        "description": "Workflow management CRUD. Create, update, publish, and execute ReactFlow-based workflows with versioning.",
    },
    {
        "name": "loops",
        "description": "Loop Engine. Create, manage, and monitor scheduled loops for workflows, agents, skills, and orchestrator tasks.",
    },
    {
        "name": "plans",
        "description": "Execution plan management. Save, modify, approve, and re-execute LLM-generated plans.",
    },
    {
        "name": "knowledge",
        "description": "Knowledge base management. Upload documents, query semantic search, manage RAG sources.",
    },
    {
        "name": "cache",
        "description": "Semantic cache management. View statistics, tune thresholds, evict entries. Two-tier: exact hash + semantic embedding.",
    },
    {
        "name": "clarify",
        "description": "Structured clarification forms with preference memory. Generate forms, submit answers, manage preferences.",
    },
    {
        "name": "costs",
        "description": "Cost tracking and analytics. View token usage, cost breakdowns by model/user/conversation.",
    },
    {
        "name": "metrics",
        "description": "Performance metrics. Latency statistics, TTFT tracking, request queue status.",
    },
    {
        "name": "health",
        "description": "Health and readiness probes. Kubernetes-compatible /live, /ready, /health endpoints.",
    },
    {
        "name": "extensions",
        "description": "Extension system status. View middleware pipeline, enable/disable extensions, track execution timeline.",
    },
    {
        "name": "sandbox",
        "description": "Sandbox execution. Configure isolation levels (NONE, PROCESS, CONTAINER, GVISOR) for tool execution.",
    },
    {
        "name": "healing",
        "description": "Self-healing status. Circuit breaker states, retry statistics, error recovery metrics.",
    },
    {
        "name": "files",
        "description": "File safety scanning. ClamAV + YARA malware detection, quarantine management.",
    },
    {
        "name": "safety",
        "description": "Input/output safety. Validation failures, sanitization events, security metrics.",
    },
    {
        "name": "websocket",
        "description": "WebSocket connections. Real-time streaming and bidirectional communication.",
    },
    {
        "name": "domains",
        "description": "Domain plugin information. List registered domains and their agents/tools/crews.",
    },
    {
        "name": "plugins",
        "description": "Plugin system management. List loaded plugins, view plugin details, and check system status.",
    },
    {
        "name": "commands",
        "description": "Slash command system. List and execute /commands from chat interface.",
    },
    {
        "name": "marketplace",
        "description": "Plugin marketplace. Browse available plugins, check tier availability, and install.",
    },
    {
        "name": "system",
        "description": "System information. API version and compatibility data for cross-service checks.",
    },
]

# Filter out enterprise tags if routes not available
if not ENTERPRISE_ROUTES_AVAILABLE:
    enterprise_tags = {"cache", "files", "healing", "sandbox", "safety"}
    tags_metadata = [tag for tag in tags_metadata if tag["name"] not in enterprise_tags]

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events.

    On startup:
    - Validate security configuration (production mode)
    - Initialize CrewAI tracing
    - Load and register enabled domain plugins
    - Initialize MCP connections
    - Warm up LLM if needed

    On shutdown:
    - Close domain connections
    - Cleanup resources
    """
    # Startup

    # Configure logging FIRST - before any logger usage
    configure_logging(level=settings.log_level, format=settings.log_format)

    logger.info("Starting Dryade API...")
    logger.info(f"Environment: {settings.env}")

    # Initialize database tables (creates missing tables, idempotent)
    try:
        from core.database import init_db

        created = init_db()
        if created:
            logger.info(f"Database initialized: created {len(created)} table(s)")
        else:
            logger.info("Database schema up to date")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise  # Fail fast — app can't function without DB

    # Core self-integrity check (informational only -- never blocks startup)
    try:
        from core.ee.integrity_ee import log_integrity_at_startup

        log_integrity_at_startup()
    except Exception as e:
        logger.warning(f"Core integrity check unavailable: {e}")

    # Validate security configuration for production
    try:
        if settings.env == "production":
            logger.info("Validating production configuration...")
            settings.validate_production_config()
    except Exception as e:
        logger.exception(f"Startup validation failed: {e}")
        raise  # Fail fast - don't start server

    # Initialize CrewAI tracing
    try:
        from core.observability import init_crewai_tracing

        if init_crewai_tracing():
            logger.info("CrewAI tracing initialized")
        else:
            logger.warning("CrewAI tracing not available (older CrewAI version?)")
    except Exception as e:
        logger.warning(f"Failed to initialize CrewAI tracing: {e}")

    # Load and register enabled domains
    if settings.enabled_domains:
        from core.domains import get_enabled_domains, load_domain, register_domain

        domain_names = get_enabled_domains(settings.enabled_domains)
        logger.info(f"Loading domains: {domain_names}")

        for domain_name in domain_names:
            try:
                domain_path = f"{settings.domain_config_path}/{domain_name}"
                domain = load_domain(domain_path)
                register_domain(domain)
                logger.info(
                    f"Registered domain: {domain_name} ({len(domain.agents)} agents, {len(domain.tools)} tools)"
                )
            except FileNotFoundError as e:
                logger.warning(f"Domain not found: {domain_name} - {e}")
            except Exception as e:
                logger.error(f"Failed to load domain {domain_name}: {e}")

    logger.info("Adapter routing active - using generic execution flow")

    # Register MCP servers as agents (before plugins, so startup hooks can find them)
    try:
        mcp_count = register_mcp_agents()
        if mcp_count > 0:
            logger.info(f"Registered {mcp_count} MCP server(s) as agents")
        else:
            logger.debug("No MCP servers enabled for agent registration")
    except Exception as e:
        logger.warning(f"MCP agent registration failed: {e}")

    # Pre-warm tool embeddings if Qdrant available (XR-C02)
    try:
        from core.mcp.embeddings import get_tool_embedding_store

        store = get_tool_embedding_store()
        if store.ensure_indexed():
            logger.info("Tool embeddings verified/populated at startup")
    except Exception as e:
        logger.debug(f"Tool embedding pre-warm skipped: {e}")

    # Plugin loading is gated by signed allowlist (see core/allowlist.py)
    from core.ee.plugins_ee import (
        _HAS_PLUGIN_SECURITY,
        PluginConflictError,
        get_plugin_manager,
        load_plugins,
    )
    from core.extensions.pipeline import get_extension_registry

    logger.info("Loading plugins via entry points...")

    # Determine user plugins directory if enabled
    user_plugins_dir = None
    if settings.enable_directory_plugins and settings.user_plugins_dir:
        user_plugins_dir = settings.user_plugins_dir
        logger.info(f"User plugins directory enabled: {user_plugins_dir}")

    try:
        # Discover and load plugins (entry points + directory if configured)
        manager = load_plugins(user_plugins_dir)
        plugins = manager.list_plugins()

        if plugins:
            # Register plugins with extension registry
            registry = get_extension_registry()
            manager.register_all(registry)

            # Run plugin startup hooks (pass app for extension point access)
            manager.startup_all(app=app)

            # Include plugin routers with drain dependency.
            # We use include_router (not app.mount with a sub-app) because
            # FastAPI bakes the router prefix into route paths at definition
            # time.  app.mount() strips the prefix from incoming requests,
            # causing a double-prefix mismatch (404) for every plugin.
            from fastapi import Depends

            from core.ee.plugins_ee import get_plugin_drainer

            def _make_drain_dep(pname: str):
                """Drain lifecycle dependency: reject if draining, track in-flight."""

                async def _drain():
                    drainer = get_plugin_drainer()
                    if not drainer.request_start(pname):
                        from fastapi import HTTPException

                        raise HTTPException(status_code=403, detail="Plugin is shutting down")
                    try:
                        yield
                    finally:
                        drainer.request_end(pname)

                return _drain

            # Initialize bridge for encrypted plugins (if any exist).
            # Bridge middleware is registered at module level via _bridge_middleware_proxy
            # because Starlette forbids adding middleware after the app has started.
            bridge = None
            has_encrypted = any(
                getattr(p, "_dryadepkg_encrypted", False) for p in manager.get_plugins()
            )
            if has_encrypted:
                try:
                    bridge = manager.get_bridge()
                    _bridge_middleware_proxy.set_bridge(bridge)
                    logger.info("Encrypted plugin bridge middleware activated")
                except Exception as e:
                    logger.error(f"Encrypted plugin bridge failed: {e}")
                    # Encrypted plugins cannot mount without bridge — security invariant.
                    # Plaintext plugins will still mount below.

            for plugin in manager.get_plugins():
                router = getattr(plugin, "router", None)
                if router:
                    plugin_name = getattr(plugin, "name", type(plugin).__name__)
                    drain_dep = _make_drain_dep(plugin_name)
                    is_encrypted = getattr(plugin, "_dryadepkg_encrypted", False)
                    if is_encrypted:
                        if bridge is None:
                            logger.warning(
                                f"Skipping encrypted plugin {plugin_name}: bridge not available"
                            )
                            continue
                        # Encrypted marketplace plugin: wrap routes through bridge
                        # so the route table shows /api/ep/{token} instead of
                        # readable plugin paths. Responses are encrypted in transit.
                        wrapped_router = bridge.wrap_router(router, plugin_name)
                        app.include_router(wrapped_router, dependencies=[Depends(drain_dep)])
                        logger.info(
                            f"Mounted encrypted plugin {plugin_name} via bridge (routes obfuscated)"
                        )
                    else:
                        # Custom (plaintext) plugin: mount under /api so routes are
                        # reachable through the nginx/vite proxy (which forwards /api/*).
                        # Plugins whose router prefix already starts with /api are
                        # mounted as-is to avoid double-prefixing.
                        prefix_val = getattr(router, "prefix", "") or ""
                        if prefix_val.startswith("/api"):
                            app.include_router(
                                router, dependencies=[Depends(drain_dep)]
                            )
                        else:
                            app.include_router(
                                router,
                                prefix="/api",
                                dependencies=[Depends(drain_dep)],
                            )
                        logger.info(f"Mounted custom plugin {plugin_name} (plaintext routes)")

            logger.info(f"Loaded {len(plugins)} plugins: {[p['name'] for p in plugins]}")
        else:
            logger.info("No plugins found")

    except PluginConflictError as e:
        logger.error(f"Plugin conflict detected: {e}")
        raise  # Fail startup - conflicts are configuration errors
    except Exception as e:
        logger.warning(f"Plugin loading failed: {e}")

    # Register slash command handlers (dynamic from agent tools)
    from core.commands.handlers import register_all_commands

    register_all_commands()
    logger.info("Registered slash command handlers from agent tools")

    # Register core demonstration agents
    try:
        from agents import register_core_agents

        core_agents = register_core_agents()
        logger.info(f"Registered {len(core_agents)} core agents")
    except ImportError:
        logger.warning("agents package not found, skipping core agent registration")
    except Exception as e:
        logger.warning(f"Failed to register core agents: {e}")

    # Auto-discover agents from agents/ directory
    try:
        from core.adapters.auto_discovery import AgentAutoDiscovery

        discovery = AgentAutoDiscovery(settings.agents_dir)
        discovered = discovery.discover_and_register()
        if discovered:
            logger.info(f"Auto-discovered {len(discovered)} agents")
    except Exception as e:
        logger.warning(f"Agent auto-discovery failed: {e}")

    # Cleanup orphaned "running" executions from previous server runs
    try:
        from datetime import UTC, datetime

        from core.database.models import ScenarioExecutionResult
        from core.database.session import get_session

        with get_session() as db:
            orphaned = db.query(ScenarioExecutionResult).filter_by(status="running").all()
            if orphaned:
                for execution in orphaned:
                    execution.status = "failed"
                    execution.error = "Execution orphaned during server restart"
                    execution.completed_at = datetime.now(UTC)
                db.commit()
                logger.info(f"Cleaned up {len(orphaned)} orphaned executions from previous run")
    except Exception as e:
        logger.warning(f"Failed to cleanup orphaned executions: {e}")

    # Restore knowledge source registry from database
    try:
        from core.knowledge.sources import load_knowledge_registry_from_db

        load_knowledge_registry_from_db()
        logger.info("Knowledge registry loaded from database")
    except Exception as e:
        logger.warning(f"Failed to load knowledge registry from DB: {e}")

    # Loop Engine startup recovery (Phase 194: restore scheduled loops)
    try:
        from core.loops.service import get_loop_service

        loop_service = get_loop_service()
        recovered = await loop_service.startup_recovery()
        app.state.loop_service = loop_service
        logger.info(f"Loop Engine: recovered {recovered} scheduled loop(s)")
    except Exception as e:
        logger.warning(f"Loop Engine startup recovery failed (non-fatal): {e}")

    # Warmup embedding models (avoid first-request latency)
    try:
        from core.knowledge.embedder import get_embedding_service

        svc = get_embedding_service()
        svc._ensure_dense()
        logger.info("Embedder warmup: dense model loaded")
    except Exception as e:
        logger.warning(f"Embedder warmup skipped (will lazy-load on first use): {e}")

    # Start internal API listener (for PM allowlist push with hot-reload)
    import asyncio

    try:
        from core.ee.internal_api import set_hot_reload_callback, start_internal_api
    except ImportError:
        from core.internal_api import set_hot_reload_callback, start_internal_api
    from core.ee.plugins_ee import (
        _load_allowlist,
        get_plugin_drainer,
        reload_allowlist,
    )
    from core.ee.plugins_ee import (
        get_plugin_manager as _get_pm,
    )

    if _HAS_PLUGIN_SECURITY:
        # Capture currently loaded plugin set for diffing during hot-reload
        _current_allowed = _load_allowlist() or frozenset()

        _reload_lock = asyncio.Lock()

        async def _hot_reload_plugins():
            """Hot-reload callback: diff allowlists, drain revoked, unmount, mount new."""
            nonlocal _current_allowed

            async with _reload_lock:
                old_allowed = _current_allowed
                new_allowed_raw = reload_allowlist()
                if new_allowed_raw is None:
                    logger.warning(
                        "Allowlist reload returned None — keeping current plugins (fail-closed)"
                    )
                    return
                new_allowed = new_allowed_raw
                _current_allowed = new_allowed

            revoked = old_allowed - new_allowed
            added = new_allowed - old_allowed

            # Also retry plugins that are in the allowlist but failed to load
            # (e.g. hash mismatch at boot time, now fixed by re-push).
            pm = _get_pm()
            loaded_names = set(pm._plugins.keys())
            failed_retry = (new_allowed & old_allowed) - loaded_names
            if failed_retry:
                added = added | failed_retry
                logger.info(
                    "Retrying %d previously-failed plugins: %s",
                    len(failed_retry),
                    sorted(failed_retry),
                )

            if not revoked and not added:
                logger.info("Allowlist updated but no plugin changes detected")
                return

            drainer = get_plugin_drainer()
            pm = _get_pm()

            # Drain and unmount revoked plugins
            for plugin_name in revoked:
                logger.info(f"Plugin revoked: {plugin_name} -- draining (5s timeout)")
                await drainer.drain(plugin_name, timeout=5.0)
                pm.unmount_plugin(app, plugin_name)
                logger.info(f"Plugin unmounted: {plugin_name}")

            # Discover and mount newly added plugins (live, no restart needed)
            mounted = []
            if added:
                try:
                    from fastapi import Depends

                    from core.ee.plugins_ee import discover_all_plugins
                    from core.extensions.pipeline import get_extension_registry

                    all_plugins = discover_all_plugins(user_plugins_dir)
                    registry = get_extension_registry()

                    def _make_drain_dep(pname: str):
                        async def _drain():
                            d = get_plugin_drainer()
                            if not d.request_start(pname):
                                from fastapi import HTTPException

                                raise HTTPException(403, "Plugin is shutting down")
                            try:
                                yield
                            finally:
                                d.request_end(pname)

                        return _drain

                    for plugin in all_plugins:
                        if plugin.name not in added:
                            continue
                        if pm.get_plugin(plugin.name):
                            continue  # already loaded
                        try:
                            plugin.register(registry)
                            plugin.startup()
                            pm._plugins[plugin.name] = plugin
                            router = getattr(plugin, "router", None)
                            if router:
                                drain_dep = _make_drain_dep(plugin.name)
                                prefix_val = getattr(router, "prefix", "") or ""
                                if prefix_val.startswith("/api"):
                                    app.include_router(
                                        router, dependencies=[Depends(drain_dep)]
                                    )
                                else:
                                    app.include_router(
                                        router,
                                        prefix="/api",
                                        dependencies=[Depends(drain_dep)],
                                    )
                            # Invalidate OpenAPI cache so new routes appear
                            app.openapi_schema = None
                            mounted.append(plugin.name)
                            logger.info(f"Hot-mounted plugin: {plugin.name}")
                        except Exception as e:
                            logger.error(f"Failed to hot-mount plugin {plugin.name}: {e}")
                except Exception as e:
                    logger.error(f"Hot-mount discovery failed: {e}")

            logger.info(
                f"Hot-reload complete. Revoked: {revoked or 'none'}, Mounted: {mounted or 'none'}"
            )

            # Notify connected frontends so they can refresh plugin lists
            try:
                from core.api.routes.websocket import manager as ws_manager

                async with ws_manager._lock:
                    n_clients = len(ws_manager.active)
                if n_clients > 0:
                    await ws_manager.broadcast(
                        {
                            "type": "plugins_changed",
                            "data": {
                                "revoked": list(revoked),
                                "added": list(added),
                            },
                        }
                    )
                    logger.info(f"Broadcast plugins_changed to {n_clients} WebSocket client(s)")
                else:
                    logger.info(
                        "No WebSocket clients connected — skipping plugins_changed broadcast"
                    )
            except Exception as e:
                logger.warning(f"Failed to broadcast plugins_changed: {e}")

        set_hot_reload_callback(_hot_reload_plugins)

        # Start allowlist file watchdog (zero-config hot-reload)
        try:
            from core.ee.allowlist_watchdog_ee import get_allowlist_watchdog

            watchdog = get_allowlist_watchdog()
            watchdog.set_callback(_hot_reload_plugins)
            await watchdog.start()
            logger.info("Allowlist watchdog started (file-based hot-reload)")
        except ImportError:
            logger.debug("Allowlist watchdog not available (community edition)")

    # Start marketplace heartbeat for license revocation checking
    try:
        from core.ee.heartbeat_ee import start_heartbeat

        await start_heartbeat()
    except Exception as e:
        logger.warning(f"Heartbeat startup failed: {e}")

    internal_api_host = settings.internal_api_host
    internal_api_port = settings.internal_api_port
    internal_task = asyncio.create_task(start_internal_api(internal_api_port, internal_api_host))
    logger.info(f"Internal API listener starting on {internal_api_host}:{internal_api_port}")

    # Start provider health monitor (Phase 146 LLM resilience)
    try:
        from core.providers.connectors import get_connector
        from core.providers.resilience.failover_engine import PROVIDER_CIRCUIT_BREAKER
        from core.providers.resilience.health_monitor import ProviderHealthMonitor

        _known_providers = [
            "openai",
            "anthropic",
            "google",
            "mistral",
            "cohere",
            "bedrock",
            "ollama",
            "vllm",
            "huggingface",
        ]
        _connector_registry = {}
        for _provider_id in _known_providers:
            _conn = get_connector(_provider_id)
            if _conn is not None:
                _connector_registry[_provider_id] = _conn

        _health_monitor = ProviderHealthMonitor(PROVIDER_CIRCUIT_BREAKER, _connector_registry)
        await _health_monitor.start()
        app.state.health_monitor = _health_monitor
        logger.info("ProviderHealthMonitor started", providers_registered=len(_connector_registry))
    except Exception as e:
        logger.warning(f"ProviderHealthMonitor startup failed (non-fatal): {e}")
        app.state.health_monitor = None

    # Re-schedule timeout tasks for any pending approval requests from before restart
    try:
        import asyncio

        from core.database.session import get_session_factory
        from core.workflows.approval import ApprovalService

        _approval_session_factory = get_session_factory()
        _approval_db = _approval_session_factory()
        try:
            asyncio.create_task(ApprovalService.scan_pending_on_startup(_approval_db))
            logger.info("Approval pending scan scheduled")
        finally:
            _approval_db.close()
    except Exception as e:
        logger.warning(f"Approval startup scan failed (non-fatal): {e}")

    # Start data retention scheduler (GDPR Article 30 / SOC 2 data lifecycle)
    try:
        from core.retention import start_retention_scheduler

        asyncio.create_task(start_retention_scheduler())
        logger.info("Retention scheduler started (daily purge)")
    except Exception as e:
        logger.warning(f"Retention scheduler startup failed (non-fatal): {e}")

    # Warn about insecure JWT secret
    _jwt = settings.jwt_secret or ""
    if "INSECURE" in _jwt or "change-me" in _jwt.lower() or "dev-secret" in _jwt.lower():
        logger.warning("JWT secret is insecure! Generate a proper secret: openssl rand -hex 32")

    logger.info("Startup validation complete - server ready")

    yield

    # Shutdown
    logger.info("Shutting down Dryade API...")

    # Stop internal API listener
    try:
        internal_task.cancel()
        logger.info("Internal API listener stopped")
    except Exception as e:
        logger.warning(f"Internal API shutdown: {e}")

    # Stop marketplace heartbeat
    try:
        from core.ee.heartbeat_ee import stop_heartbeat

        await stop_heartbeat()
    except Exception as e:
        logger.warning(f"Heartbeat shutdown failed: {e}")

    # Stop allowlist watchdog
    try:
        from core.ee.allowlist_watchdog_ee import get_allowlist_watchdog

        watchdog = get_allowlist_watchdog()
        await watchdog.stop()
        logger.info("Allowlist watchdog stopped")
    except Exception as e:
        logger.warning(f"Allowlist watchdog shutdown: {e}")

    # Stop provider health monitor
    try:
        monitor = getattr(app.state, "health_monitor", None)
        if monitor is not None:
            await monitor.stop()
            logger.info("ProviderHealthMonitor stopped")
    except Exception as e:
        logger.warning(f"ProviderHealthMonitor shutdown: {e}")

    # Shutdown plugins
    try:
        from core.ee.plugins_ee import get_plugin_manager

        manager = get_plugin_manager()
        manager.shutdown_all()
        logger.info("Plugins shut down")
    except Exception as e:
        logger.warning(f"Plugin shutdown failed: {e}")

    # Unregister domains
    if settings.enabled_domains:
        from core.domains import get_enabled_domains, unregister_domain

        for domain_name in get_enabled_domains(settings.enabled_domains):
            try:
                unregister_domain(domain_name)
                logger.info(f"Unregistered domain: {domain_name}")
            except Exception as e:
                logger.warning(f"Failed to unregister domain {domain_name}: {e}")

app = FastAPI(
    title="Dryade API",
    version="1.0.0",
    description="""
# Dryade - Multi-Agent Orchestration Platform

A production-ready multi-agent platform optimized for Jetson Thor hardware.

## Features

- **Multi-Agent Execution**: Execute complex workflows with CrewAI, LangChain, ADK, or A2A agents
- **Four Execution Modes**: CHAT (direct), CREW (multi-agent), FLOW (predefined), PLANNER (dynamic)
- **Semantic Caching**: Two-tier cache with exact hash matching and embedding-based similarity
- **Self-Healing**: Automatic retry with circuit breakers and LLM reflection for error recovery
- **Sandbox Isolation**: gVisor, Docker, or process isolation for tool execution
- **RAG Pipeline**: Knowledge base with document upload and semantic search

## Authentication

JWT-based authentication (optional). Set JWT_SECRET to enable.

## Streaming

Chat endpoints support SSE streaming. Set `Accept: text/event-stream` header.
""",
    lifespan=lifespan,
    openapi_tags=tags_metadata,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Plugin extension points (exposed via app.state for plugin startup() access)
from core.auth.sharing import register_shareable_type

app.state.register_shareable_type = register_shareable_type

# ============================================================================
# Centralized Exception Handlers
# All errors are logged with request context and recorded in metrics
# ============================================================================

@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """Handle validation errors with 400 Bad Request."""
    from core.api.middleware.error_metrics import record_error

    request_id = getattr(request.state, "request_id", None)
    user_id = getattr(request.state, "user_id", None)

    log_error(
        logger,
        f"Validation error on {request.url.path}",
        error=exc,
        operation=f"{getattr(request, 'method', 'WS')} {request.url.path}",
        context=create_request_context(
            request_id=request_id or "unknown",
            user_id=user_id,
            path=str(request.url.path),
            method=getattr(request, "method", "WS"),
        ),
        include_traceback=False,
    )

    record_error(
        "ValueError",
        request.url.path,
        status_code=400,
        error_message=str(exc),
        request_id=request_id,
        user_id=user_id,
    )

    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=ErrorResponse(
            error=str(exc),
            type="validation_error",
            code="VALIDATION_001",
        ).model_dump(mode="json"),
    )

@app.exception_handler(FileNotFoundError)
async def not_found_handler(request: Request, exc: FileNotFoundError):
    """Handle resource not found errors with 404."""
    from core.api.middleware.error_metrics import record_error

    request_id = getattr(request.state, "request_id", None)
    user_id = getattr(request.state, "user_id", None)

    log_error(
        logger,
        f"Resource not found on {request.url.path}",
        error=exc,
        operation=f"{getattr(request, 'method', 'WS')} {request.url.path}",
        context=create_request_context(
            request_id=request_id or "unknown",
            user_id=user_id,
            path=str(request.url.path),
            method=getattr(request, "method", "WS"),
        ),
        include_traceback=False,
    )

    record_error(
        "FileNotFoundError",
        request.url.path,
        status_code=404,
        error_message=str(exc),
        request_id=request_id,
        user_id=user_id,
    )

    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content=ErrorResponse(
            error=str(exc),
            type="not_found",
            code="NOT_FOUND_001",
        ).model_dump(mode="json"),
    )

@app.exception_handler(KeyError)
async def key_error_handler(request: Request, exc: KeyError):
    """Handle missing required keys with 400 Bad Request."""
    from core.api.middleware.error_metrics import record_error

    request_id = getattr(request.state, "request_id", None)
    user_id = getattr(request.state, "user_id", None)

    log_error(
        logger,
        f"Missing required key on {request.url.path}",
        error=exc,
        operation=f"{getattr(request, 'method', 'WS')} {request.url.path}",
        context=create_request_context(
            request_id=request_id or "unknown",
            user_id=user_id,
            path=str(request.url.path),
            method=getattr(request, "method", "WS"),
        ),
        include_traceback=False,
    )

    record_error(
        "KeyError",
        request.url.path,
        status_code=400,
        error_message=str(exc),
        request_id=request_id,
        user_id=user_id,
    )

    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=ErrorResponse(
            error=f"Missing required key: {exc}",
            type="missing_key",
            code="VALIDATION_002",
        ).model_dump(mode="json"),
    )

@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    """Handle database constraint violations with 409 Conflict."""
    from core.api.middleware.error_metrics import record_error

    request_id = getattr(request.state, "request_id", None)
    user_id = getattr(request.state, "user_id", None)

    log_error(
        logger,
        f"Database integrity error on {request.url.path}",
        error=exc,
        operation=f"{getattr(request, 'method', 'WS')} {request.url.path}",
        context=create_request_context(
            request_id=request_id or "unknown",
            user_id=user_id,
            path=str(request.url.path),
            method=getattr(request, "method", "WS"),
        ),
    )

    record_error(
        "IntegrityError",
        request.url.path,
        status_code=409,
        error_message="Database constraint violation",
        request_id=request_id,
        user_id=user_id,
    )

    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content=ErrorResponse(
            error="Database constraint violation",
            type="integrity_error",
            code="CONFLICT_001",
        ).model_dump(mode="json"),
    )

@app.exception_handler(OperationalError)
async def operational_error_handler(request: Request, exc: OperationalError):
    """Handle database operational errors with 503 Service Unavailable."""
    from core.api.middleware.error_metrics import record_error

    request_id = getattr(request.state, "request_id", None)
    user_id = getattr(request.state, "user_id", None)

    log_error(
        logger,
        f"Database operational error on {request.url.path}",
        error=exc,
        operation=f"{getattr(request, 'method', 'WS')} {request.url.path}",
        context=create_request_context(
            request_id=request_id or "unknown",
            user_id=user_id,
            path=str(request.url.path),
            method=getattr(request, "method", "WS"),
        ),
    )

    record_error(
        "OperationalError",
        request.url.path,
        status_code=503,
        error_message="Database unavailable",
        request_id=request_id,
        user_id=user_id,
    )

    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=ErrorResponse(
            error="Database unavailable",
            type="database_error",
            code="SERVER_002",
        ).model_dump(mode="json"),
    )

@app.exception_handler(DatabaseError)
async def database_error_handler(request: Request, exc: DatabaseError):
    """Handle general database errors with 500 Internal Server Error."""
    from core.api.middleware.error_metrics import record_error

    request_id = getattr(request.state, "request_id", None)
    user_id = getattr(request.state, "user_id", None)

    log_error(
        logger,
        f"Database error on {request.url.path}",
        error=exc,
        operation=f"{getattr(request, 'method', 'WS')} {request.url.path}",
        context=create_request_context(
            request_id=request_id or "unknown",
            user_id=user_id,
            path=str(request.url.path),
            method=getattr(request, "method", "WS"),
        ),
    )

    record_error(
        "DatabaseError",
        request.url.path,
        status_code=500,
        error_message="Database error",
        request_id=request_id,
        user_id=user_id,
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error="Database error",
            type="database_error",
            code="SERVER_004",
        ).model_dump(mode="json"),
    )

@app.exception_handler(TimeoutError)
async def timeout_error_handler(request: Request, exc: TimeoutError):
    """Handle timeout errors with 408 Request Timeout."""
    from core.api.middleware.error_metrics import record_error

    request_id = getattr(request.state, "request_id", None)
    user_id = getattr(request.state, "user_id", None)

    log_error(
        logger,
        f"Request timeout on {request.url.path}",
        error=exc,
        operation=f"{getattr(request, 'method', 'WS')} {request.url.path}",
        context=create_request_context(
            request_id=request_id or "unknown",
            user_id=user_id,
            path=str(request.url.path),
            method=getattr(request, "method", "WS"),
        ),
        include_traceback=False,
    )

    record_error(
        "TimeoutError",
        request.url.path,
        status_code=408,
        error_message="Request timeout",
        request_id=request_id,
        user_id=user_id,
    )

    return JSONResponse(
        status_code=status.HTTP_408_REQUEST_TIMEOUT,
        content=ErrorResponse(
            error="Request timeout",
            type="timeout",
            code="SERVER_003",
        ).model_dump(mode="json"),
    )

@app.exception_handler(RuntimeError)
async def runtime_error_handler(request: Request, exc: RuntimeError):
    """Handle runtime errors with 500 Internal Server Error."""
    from core.api.middleware.error_metrics import record_error

    request_id = getattr(request.state, "request_id", None)
    user_id = getattr(request.state, "user_id", None)

    log_error(
        logger,
        f"Runtime error on {request.url.path}",
        error=exc,
        operation=f"{getattr(request, 'method', 'WS')} {request.url.path}",
        context=create_request_context(
            request_id=request_id or "unknown",
            user_id=user_id,
            path=str(request.url.path),
            method=getattr(request, "method", "WS"),
        ),
    )

    record_error(
        "RuntimeError",
        request.url.path,
        status_code=500,
        error_message=str(exc),
        request_id=request_id,
        user_id=user_id,
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error=str(exc),
            type="runtime_error",
            code="SERVER_001",
        ).model_dump(mode="json"),
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Catch-all handler for unexpected errors with 500 Internal Server Error."""
    from core.api.middleware.error_metrics import record_error

    request_id = getattr(request.state, "request_id", None)
    user_id = getattr(request.state, "user_id", None)

    log_error(
        logger,
        f"Unhandled exception on {request.url.path}",
        error=exc,
        operation=f"{getattr(request, 'method', 'WS')} {request.url.path}",
        context=create_request_context(
            request_id=request_id or "unknown",
            user_id=user_id,
            path=str(request.url.path),
            method=getattr(request, "method", "WS"),
        ),
    )

    record_error(
        type(exc).__name__,
        request.url.path,
        status_code=500,
        error_message=str(exc),
        request_id=request_id,
        user_id=user_id,
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error="Internal server error",
            type="internal_error",
            code="SERVER_001",
        ).model_dump(mode="json"),
    )

# ============================================================================
# Middleware Stack
# ============================================================================

class _BridgeMiddlewareProxy:
    """Lazy proxy for the encrypted plugin bridge middleware.

    Registered at module level (before app starts) to satisfy Starlette's
    constraint that middleware cannot be added after the ASGI app is running.
    The real bridge is injected during lifespan() via set_bridge().

    When no bridge is set, requests pass through unchanged — no security
    impact because encrypted plugin routes are never mounted without a bridge.
    """

    def __init__(self):
        self._middleware_fn = None

    def set_bridge(self, bridge) -> None:
        """Activate the bridge middleware. Called from lifespan()."""
        self._middleware_fn = bridge.create_middleware()

    async def __call__(self, request, call_next):
        if self._middleware_fn is not None:
            return await self._middleware_fn(request, call_next)
        return await call_next(request)

_bridge_middleware_proxy = _BridgeMiddlewareProxy()

# Middleware stack (order matters - last added = first executed on request)
# Request flow: RequestMetrics → CORS → LLMContext → Auth → RateLimit → BridgeProxy → Handler
app.middleware("http")(_bridge_middleware_proxy)
app.add_middleware(
    RateLimitMiddleware,
    requests_per_minute=settings.rate_limit_default_rpm,
    pro_rpm=settings.rate_limit_pro_rpm,
    admin_rpm=settings.rate_limit_admin_rpm,
)
# LLMContextMiddleware must be added BEFORE AuthMiddleware so it runs AFTER AuthMiddleware
# (because middleware added later runs earlier in the request chain)
app.add_middleware(LLMContextMiddleware)
app.add_middleware(
    AuthMiddleware,
    exclude=[
        "/health",
        "/api/health",
        "/api/health/detailed",
        "/api/health/metrics",
        "/api/ready",
        "/api/live",
        "/ready",
        "/live",
        "/metrics",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/api/auth/register",
        "/api/auth/login",
        "/api/auth/refresh",
        "/api/auth/setup",
        "/api/auth/mfa/validate",
        "/api/auth/mfa/recovery",
        "/api/setup",
        "/api/version",
        "/.well-known/agent.json",
        "/.well-known/agent-card.json",
    ],
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestMetricsMiddleware)

# ============================================================================
# API Routes
# ============================================================================
# All API routes use /api prefix (v1 implicit)
# Future API versions would use /api/v2, /api/v3, etc.
# Health probes at root for Kubernetes compatibility: /health, /ready, /live

# Health routes (no auth required)
app.include_router(health.router)
# Duplicate under /api for frontend proxying
app.include_router(health.router, prefix="/api")

# Version endpoint (no auth - used by marketplace for compatibility checks)
app.include_router(version.router)

# Prometheus metrics endpoint (raw format for Prometheus scraper at /metrics)
# Intentionally excluded from auth middleware (see AuthMiddleware exclude list above)
app.include_router(metrics_router)

# Setup wizard routes (no auth - runs before user has configured instance)
app.include_router(setup.router, prefix="/api/setup", tags=["setup"])

# Auth routes (public endpoints for login/register)
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(mfa.router, prefix="/api/auth/mfa", tags=["mfa"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(models_config.router, prefix="/api/models", tags=["models"])
app.include_router(provider_registry.router, prefix="/api/providers", tags=["providers"])
app.include_router(provider_health.router, tags=["provider-health"])
app.include_router(
    custom_providers.router, prefix="/api/custom-providers", tags=["custom-providers"]
)

# API routes
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(projects.router, prefix="/api", tags=["projects"])
app.include_router(agents.router, prefix="/api/agents", tags=["agents"])
app.include_router(factory.router, prefix="/api/factory", tags=["factory"])
app.include_router(flows.router, prefix="/api/flows", tags=["flows"])
app.include_router(knowledge.router, prefix="/api/knowledge", tags=["knowledge"])
app.include_router(loops.router, prefix="/api", tags=["loops"])
app.include_router(plans.router, prefix="/api", tags=["plans"])
app.include_router(workflows.router, prefix="/api", tags=["workflows"])
app.include_router(workflow_scenarios.router, prefix="/api", tags=["workflow-scenarios"])
app.include_router(metrics_api.router, prefix="/api/metrics", tags=["metrics"])
app.include_router(mcp_metrics.router, tags=["mcp"])
app.include_router(extensions.router)
app.include_router(plugins.router, tags=["plugins"])
app.include_router(marketplace.router, prefix="/api/marketplace", tags=["marketplace"])
app.include_router(commands.router, tags=["commands"])
app.include_router(skills.router, tags=["skills"])

# Free-core routes (Phase 191: migrated from plugins, unconditionally available)
app.include_router(clarify.router, prefix="/api/clarify", tags=["clarify"])
app.include_router(cost_tracker.router, prefix="/api/costs", tags=["costs"])

# Admin audit routes (SOC 2 / GDPR compliance)
app.include_router(audit_admin.router, prefix="/api/admin/audit", tags=["audit"])

# GDPR DSAR routes (data export + right to erasure)
app.include_router(dsar.router, prefix="/api", tags=["dsar"])

# EU AI Act transparency routes (public disclosure + admin decision audit)
app.include_router(transparency.router, prefix="/api", tags=["transparency"])

# Cookie consent routes (ePrivacy Directive)
app.include_router(consent.router, prefix="/api/consent", tags=["consent"])

# Enterprise-only routes
if ENTERPRISE_ROUTES_AVAILABLE:
    app.include_router(cache.router, prefix="/api/cache", tags=["cache"])
    app.include_router(files.router, prefix="/api/files", tags=["files"])
    app.include_router(healing.router, prefix="/api/healing", tags=["healing"])
    app.include_router(sandbox.router, prefix="/api/sandbox", tags=["sandbox"])
    app.include_router(safety.router, prefix="/api/safety", tags=["safety"])

# Data retention admin routes (GDPR / SOC 2)
app.include_router(retention_router, prefix="/api/admin/retention", tags=["retention"])

# Security telemetry routes
app.include_router(security_telemetry.router, prefix="/api", tags=["security"])

# WebSocket routes
app.include_router(websocket.router, tags=["websocket"])

# A2A Protocol -- discovery is public, JSON-RPC requires auth
app.include_router(a2a_server.discovery_router)
app.include_router(a2a_server.jsonrpc_router, tags=["a2a"])

# Add domains info endpoint
@app.get("/api/domains", tags=["domains"])
async def list_domains():
    """List all registered domains and their status."""
    from core.domains import get_domain
    from core.domains import list_domains as get_domain_list

    domains = []
    for domain_name in get_domain_list():
        domain = get_domain(domain_name)
        if domain:
            domains.append(
                {
                    "name": domain.name,
                    "description": domain.description,
                    "version": domain.version,
                    "agents": len(domain.agents),
                    "tools": len(domain.tools),
                    "crews": len(domain.crews),
                    "flows": len(domain.flows),
                }
            )

    return {
        "enabled_domains": settings.enabled_domains,
        "domains": domains,
    }

# Add error metrics endpoint
@app.get("/metrics/errors", tags=["metrics"])
async def get_error_metrics():
    """Get error metrics for monitoring and debugging.

    Returns counts of errors by endpoint and error type.
    """
    from core.api.middleware.error_metrics import get_error_summary

    return {
        "error_counts": get_error_summary(),
        "description": "Error counts by endpoint:error_type",
    }

# ============================================================================
# Root and API Info Endpoints
# ============================================================================

@app.get("/", include_in_schema=False)
async def root():
    """Redirect to API documentation."""
    return RedirectResponse(url="/docs")

@app.get("/api", tags=["health"])
async def api_info():
    """API version and endpoint summary.

    Returns basic API information including version, documentation URLs,
    and health endpoint location.
    """
    return {
        "name": "Dryade API",
        "version": "1.0.0",
        "docs": "/docs",
        "openapi": "/openapi.json",
        "health": "/health",
    }
