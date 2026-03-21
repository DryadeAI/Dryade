"""Dryade Configuration.

All settings loaded from environment variables with sensible defaults.
Target: ~100 LOC
"""

import logging
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings

_config_logger = logging.getLogger("dryade.config")

# Root of the dryade-core package (dryade-core/ on host, /app in Docker)
_CORE_ROOT = Path(__file__).resolve().parent.parent

# Compute default paths that work in both layouts:
#   Host:   dryade-core/{agents,plugins}
#   Docker: /app/{agents,plugins}
_DEFAULT_AGENTS_DIR = str(_CORE_ROOT / "agents")
_default_plugins = _CORE_ROOT / "plugins"
if not _default_plugins.is_dir():
    _candidate = _CORE_ROOT.parent / "plugins"
    if _candidate.is_dir():
        _default_plugins = _candidate
_DEFAULT_PLUGINS_DIR = str(_default_plugins)

# MCP config: dryade-core/config/ in standalone, config/ in workspace
_default_mcp_config = _CORE_ROOT / "config" / "mcp_servers.yaml"
if not _default_mcp_config.is_file():
    _candidate = _CORE_ROOT.parent / "config" / "mcp_servers.yaml"
    if _candidate.is_file():
        _default_mcp_config = _candidate
_DEFAULT_MCP_CONFIG_PATH = str(_default_mcp_config)

# Fields where empty string in .env should be treated as unset (None),
# not as a literal empty value that fails type parsing.
_EMPTY_STRING_NULLABLE_FIELDS = {
    "jwt_secret",
    "cost_budget_daily",
    "llm_api_key",
    "redis_url",
    "qdrant_url",
    "otel_endpoint",
    "s3_bucket",
    "s3_endpoint",
    "user_plugins_dir",
    "allowlist_path",
}

class Settings(BaseSettings):
    """Application settings loaded from environment.

    User Plugin Directory:
        Set DRYADE_USER_PLUGINS_DIR to enable user plugins.
        Set DRYADE_ENABLE_DIRECTORY_PLUGINS=true to enable.

        Directory structure:
            $DRYADE_USER_PLUGINS_DIR/
                my_plugin/
                    __init__.py  # Must export: plugin = MyPluginClass()

        User plugins are loaded AFTER entry point plugins.
        Conflicts: Entry point plugins take precedence.
    """

    @model_validator(mode="before")
    @classmethod
    def coerce_empty_strings_to_none(cls, values):
        """Treat empty-string env vars as unset for nullable fields.

        Pydantic reads ``KEY=`` from .env as ``""`` which fails type parsing
        for ``float | None``, ``str | None`` with validators, etc.  This
        pre-validator converts ``""`` → ``None`` and logs an error so the
        misconfiguration is visible without crashing the application.
        """
        if not isinstance(values, dict):
            return values
        for field_name in _EMPTY_STRING_NULLABLE_FIELDS:
            val = values.get(field_name)
            if val is not None and isinstance(val, str) and val.strip() == "":
                _config_logger.error(
                    "DRYADE_%s is set to an empty string in .env — "
                    "treating as unset (None). Set a value or comment out the line.",
                    field_name.upper(),
                )
                values[field_name] = None
        return values

    # Core
    env: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "pretty"] = "pretty"  # Default to colored pretty format
    host: str = "0.0.0.0"
    port: int = 8080
    workers: int = 4

    # LLM
    llm_mode: Literal["ollama", "vllm", "openai", "anthropic", "litellm"] = "vllm"
    llm_model: str = "local-llm"
    llm_base_url: str = Field(
        "http://127.0.0.1:8000/v1", description="Base URL for LLM API endpoint (required)"
    )
    llm_api_key: str | None = None
    llm_timeout: int = (
        300  # Default timeout for chat/agents (5 minutes — thinking models need longer)
    )
    llm_planner_timeout: int = 300  # Timeout for plan generation (5 minutes)
    llm_temperature: float = 0.7
    llm_max_tokens: int = 4096
    llm_config_source: Literal["env", "database", "auto"] = Field(
        default="auto",
        description=(
            "Source for LLM configuration. "
            "'env' = always use environment variables (backward compatible), "
            "'database' = always use user's Settings page config, "
            "'auto' = try database first, fall back to env if not configured"
        ),
    )

    # Database
    database_url: str = "postgresql+psycopg://dryade:dryade_dev@localhost:5432/dryade"
    database_ssl_mode: str = Field(
        default="prefer",
        description="PostgreSQL SSL mode (prefer for dev, require for production)",
    )
    redis_url: str | None = Field(
        None, description="Redis URL for caching and rate limiting (optional)"
    )
    redis_enabled: bool = True
    qdrant_url: str | None = Field(None, description="Qdrant vector database URL (optional)")

    # MCP (configure domain-specific MCP servers via DRYADE_MCP_SERVERS JSON)

    # Security
    encryption_key: str | None = Field(
        None,
        description="Encryption key for stored credentials (API keys). "
        "Generate with: openssl rand -hex 32",
    )
    auth_enabled: bool = True
    jwt_secret: str | None = "dev-secret-change-me-0123456789abcdef012345"
    jwt_algorithm: str = "HS256"
    jwt_expiry_hours: int = 24
    mfa_enforcement_enabled: bool = False  # Admin toggle for MFA enforcement
    cors_origins: str = Field(
        default="http://localhost:3000,http://localhost:3001",
        description="Comma-separated list of allowed CORS origins (use localhost for dev)",
    )

    @field_validator("jwt_secret")
    @classmethod
    def validate_jwt_secret(cls, v):
        """Validate JWT_SECRET meets security requirements."""
        if v is None:
            return v  # Optional - will be validated at startup if auth enabled

        if len(v) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters for security")

        # Reject the default value — it is publicly known and must never ship to production.
        # This check uses substring matching so that variations like "dev-secret-change-me-..."
        # are always caught, regardless of suffix.
        _INSECURE_SUBSTRINGS = [
            "dev-secret-change-me",  # exact default prefix — always catch this
            "changeme",  # common placeholder (hyphenated form caught above)
            "password",
        ]
        v_lower = v.lower()
        for insecure in _INSECURE_SUBSTRINGS:
            if insecure in v_lower:
                raise ValueError(
                    f"DRYADE_JWT_SECRET contains the insecure pattern '{insecure}'. "
                    "Set a strong random value: "
                    "export DRYADE_JWT_SECRET=$(openssl rand -hex 32)"
                )

        # Reject exact-match trivially weak values (e.g. "secret", "12345")
        _INSECURE_EXACT = ["secret", "12345", "letmein", "admin", "test"]
        if v_lower in _INSECURE_EXACT:
            raise ValueError(
                f"DRYADE_JWT_SECRET '{v}' is insecure. "
                "Set a strong random value: "
                "export DRYADE_JWT_SECRET=$(openssl rand -hex 32)"
            )

        return v

    # Rate Limiting
    rate_limit_enabled: bool = True
    rate_limit_default_rpm: int = 300
    rate_limit_pro_rpm: int = 600
    rate_limit_admin_rpm: int = 1000

    # Semantic Cache
    semantic_cache_enabled: bool = True
    semantic_cache_ttl: int = 3600
    semantic_cache_threshold: float = 0.85
    semantic_cache_max_size: int = 10000

    # OpenTelemetry
    otel_enabled: bool = False
    otel_endpoint: str | None = Field(
        None, description="OpenTelemetry collector endpoint (optional)"
    )
    otel_service_name: str = "dryade-api"
    otel_insecure: bool = True

    # Uploads
    upload_max_size_mb: float = 10.0
    upload_allowed_types: str = "*"
    s3_bucket: str | None = None
    s3_region: str = "us-east-1"
    s3_endpoint: str | None = None

    # Knowledge/RAG
    knowledge_chunk_size: int = 1000
    knowledge_chunk_overlap: int = 200
    knowledge_top_k: int = 5

    # MCP Tool Routing
    mcp_tool_embedding_model: str = "all-MiniLM-L6-v2"

    # Cost Tracking
    cost_tracking_enabled: bool = True
    cost_budget_daily: float | None = None
    cost_alert_threshold: float = 0.8

    # Sandbox
    sandbox_enabled: bool = True
    sandbox_timeout: int = 30
    sandbox_memory_mb: int = 512

    # MCP
    mcp_config_path: str = Field(
        default=_DEFAULT_MCP_CONFIG_PATH,
        description="Path to MCP server config YAML. Override with DRYADE_MCP_CONFIG_PATH.",
    )

    # Domain Plugin System
    enabled_domains: str = ""  # Comma-separated list of domain plugins (e.g., "github,custom")
    domain_config_path: str = "dryade/domains"  # Path to domain plugins

    # Plugin System
    agents_dir: str = Field(default=_DEFAULT_AGENTS_DIR, description="Path to agents directory")
    plugins_dir: str = Field(default=_DEFAULT_PLUGINS_DIR, description="Path to plugins directory")
    user_plugins_dir: str | None = Field(
        default=None,
        description="Directory for user-created plugins (optional)",
    )
    enable_directory_plugins: bool = Field(
        default=False,
        description="Enable directory-based plugin discovery",
    )
    allowlist_path: str | None = Field(
        default=None,
        description=(
            "Override path to signed allowlist file. "
            "Default: ~/.dryade/allowed-plugins.json. "
            "Set via DRYADE_ALLOWLIST_PATH."
        ),
    )

    # Internal API (Plugin Manager push endpoint)
    internal_api_host: str = Field(
        default="127.0.0.1",
        description="Host for internal API listener. Use 0.0.0.0 in Docker so PM container can reach core.",
    )
    internal_api_port: int = Field(
        default=9471,
        description="Port for internal API listener (PM allowlist push).",
    )

    # Zitadel SSO (optional plugin)
    zitadel_enabled: bool = Field(default=False, description="Enable Zitadel SSO authentication")
    zitadel_issuer: str = Field(
        default="", description="Zitadel issuer URL (e.g., http://localhost:8080)"
    )
    zitadel_project_id: str = Field(default="", description="Zitadel project ID")

    # Multi-MCP Support (JSON format)
    mcp_servers: str = "{}"  # JSON: {"server-name": "http://...", "another": "http://..."}

    # Self-Healing
    self_healing_enabled: bool = True
    retry_max_attempts: int = 3

    # Mock Mode
    mock_mode: bool = False

    # Extensions
    extensions_enabled: bool = True
    safety_validation_enabled: bool = True
    file_safety_enabled: bool = True
    output_sanitization_enabled: bool = True

    # WebSocket Configuration
    ws_buffer_size: int = 100
    ws_ack_timeout_s: float = 30.0
    ws_max_retries: int = 3
    ws_retry_interval_s: float = 5.0
    ws_session_ttl_s: float = 300.0
    ws_handshake_timeout_s: float = 5.0
    ws_heartbeat_s: float = 30.0
    ws_heartbeat_timeout_s: float = 90.0
    ws_rate_limit_burst: int = 60
    ws_rate_limit_per_sec: float = 1.0

    # Request Queue
    max_concurrent_llm: int = 8
    max_queue_size: int = 20
    queue_timeout_s: float = 30.0

    # Neo4j (optional, no DRYADE_ prefix)
    neo4j_uri: str | None = Field(
        default=None,
        validation_alias=AliasChoices("NEO4J_URI", "DRYADE_NEO4J_URI"),
    )
    neo4j_user: str = Field(
        default="neo4j",
        validation_alias=AliasChoices("NEO4J_USER", "DRYADE_NEO4J_USER"),
    )
    neo4j_password: str | None = Field(
        default=None,
        validation_alias=AliasChoices("NEO4J_PASSWORD", "DRYADE_NEO4J_PASSWORD"),
    )

    model_config = {"env_prefix": "DRYADE_", "env_file": ".env", "extra": "ignore"}

    @field_validator("llm_base_url")
    @classmethod
    def validate_llm_base_url(cls, v: str) -> str:
        """Ensure LLM base URL is configured."""
        if not v or v.strip() == "":
            raise ValueError(
                "DRYADE_LLM_BASE_URL must be configured. "
                "Set it in .env or environment variables. "
                "See .env.example for configuration examples."
            )
        return v

    @field_validator("user_plugins_dir")
    @classmethod
    def validate_user_plugins_dir(cls, v: str | None) -> str | None:
        """Validate user plugins directory exists or can be created."""
        if v is None:
            return v

        from pathlib import Path

        from core.logs import get_logger

        logger = get_logger(__name__)

        path = Path(v)
        if not path.exists():
            try:
                path.mkdir(parents=True, exist_ok=True)
                logger.warning(
                    f"Created user plugins directory: {path} "
                    "(add plugins as subdirectories with __init__.py)"
                )
            except Exception as e:
                logger.error(f"Failed to create user plugins directory {path}: {e}")
                raise ValueError(f"Cannot create user plugins directory: {path}") from e
        elif not path.is_dir():
            raise ValueError(f"User plugins path exists but is not a directory: {path}")

        logger.info(f"User plugins directory configured: {path}")
        return v

    def validate_production_config(self) -> None:
        """Validate production-critical configuration at startup."""
        from core.logs import get_logger

        logger = get_logger(__name__)

        errors = []

        # Check JWT configuration if authentication enabled
        if self.auth_enabled:
            if not self.jwt_secret:
                errors.append(
                    "JWT_SECRET required when authentication enabled. "
                    "Generate with: openssl rand -hex 32"
                )
            elif len(self.jwt_secret) < 32:
                errors.append("JWT_SECRET too short (minimum 32 characters)")

        # Check CORS configuration
        if "*" in self.cors_origins:
            logger.warning("CORS origins set to '*' - allows all origins (insecure for production)")

        # Check database SSL is enforced in production
        if self.database_ssl_mode != "require":
            errors.append(
                "DRYADE_DATABASE_SSL_MODE must be 'require' in production. "
                "Set DRYADE_DATABASE_SSL_MODE=require in your environment."
            )
        if "sslmode=require" not in self.database_url and self.database_ssl_mode != "require":
            logger.warning(
                "Production database URL missing sslmode=require parameter. "
                "SSL is enforced via DRYADE_DATABASE_SSL_MODE instead."
            )

        # Check encryption key for credential storage
        if not self.encryption_key:
            logger.warning(
                "DRYADE_ENCRYPTION_KEY not set — using default key. "
                "Set a unique value for production: export DRYADE_ENCRYPTION_KEY=$(openssl rand -hex 32)"
            )

        if errors:
            error_msg = "Production configuration validation failed:\n" + "\n".join(
                f"  - {e}" for e in errors
            )
            logger.error(error_msg)
            raise ValueError(error_msg)

        logger.info("Production configuration validated successfully")

@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance with production validation."""
    settings = Settings()

    # Validate production config if in production environment
    if settings.env == "production":
        settings.validate_production_config()

    return settings
