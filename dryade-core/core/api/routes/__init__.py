"""API routes package."""

from core.api.routes import (
    a2a_server,
    agents,
    auth,
    chat,
    clarify,
    cost_tracker,
    custom_providers,
    extensions,
    flows,
    health,
    knowledge,
    metrics_api,
    models_config,
    plans,
    plugins,
    projects,
    provider_health,
    provider_registry,
    skills,
    users,
    websocket,
    workflow_scenarios,
    workflows,
)

# Note: Enterprise routes (cache, files, healing, safety, sandbox) are imported
# conditionally in main.py when enterprise plugins are absent.
# Free-core routes (clarify, cost_tracker) are imported unconditionally (Phase 191).

__all__ = [
    "a2a_server",
    "health",
    "chat",
    "agents",
    "clarify",
    "cost_tracker",
    "custom_providers",
    "flows",
    "websocket",
    "knowledge",
    "extensions",
    "plans",
    "workflows",
    "workflow_scenarios",
    "metrics_api",
    "models_config",
    "plugins",
    "projects",
    "provider_health",
    "provider_registry",
    "auth",
    "users",
    "skills",
]
