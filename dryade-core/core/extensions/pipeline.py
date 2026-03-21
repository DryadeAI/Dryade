"""Extension Pipeline and Registry.

Composes all extensions into a unified pipeline with proper ordering:
1. Safety Input Validation
2. Semantic Cache Check
3. Self-Healing Wrapper
4. Sandbox Execution
5. File Safety Scan
6. Safety Output Sanitization

Target: ~140 LOC
"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

class ExtensionType(str, Enum):
    """Extension types in execution order."""

    INPUT_VALIDATION = "input_validation"
    SEMANTIC_CACHE = "semantic_cache"
    SELF_HEALING = "self_healing"
    SANDBOX = "sandbox"
    FILE_SAFETY = "file_safety"
    OUTPUT_SANITIZATION = "output_sanitization"

@dataclass
class ExtensionConfig:
    """Extension configuration."""

    name: str
    type: ExtensionType
    enabled: bool
    priority: int  # Lower number = higher priority (runs earlier)
    on_startup: Callable | None = None
    on_shutdown: Callable | None = None

@dataclass
class ExtensionRequest:
    """Request passed through extension pipeline."""

    operation: str  # Operation name (e.g., "agent_execute", "tool_call")
    data: dict[str, Any]
    context: dict[str, Any]
    metadata: dict[str, Any]

@dataclass
class ExtensionResponse:
    """Response from extension pipeline."""

    result: Any
    metadata: dict[str, Any]
    extensions_applied: list[str]
    cache_hit: bool = False
    healed: bool = False
    sandboxed: bool = False
    threats_found: list[str] = None

class ExtensionRegistry:
    """Registry of available extensions.

    Manages extension lifecycle and configuration.
    """

    def __init__(self):
        """Initialize an empty extension registry."""
        self._extensions: dict[str, ExtensionConfig] = {}

    def register(self, config: ExtensionConfig):
        """Register an extension."""
        self._extensions[config.name] = config
        logger.info(
            f"Registered extension: {config.name} (type={config.type}, priority={config.priority})"
        )

    def get(self, name: str) -> ExtensionConfig | None:
        """Get extension by name."""
        return self._extensions.get(name)

    def get_enabled(self) -> list[ExtensionConfig]:
        """Get all enabled extensions sorted by priority."""
        enabled = [ext for ext in self._extensions.values() if ext.enabled]
        return sorted(enabled, key=lambda x: x.priority)

    def get_by_type(self, ext_type: ExtensionType) -> list[ExtensionConfig]:
        """Get extensions by type."""
        return [ext for ext in self._extensions.values() if ext.type == ext_type]

    async def startup(self):
        """Run startup hooks for all enabled extensions."""
        for ext in self.get_enabled():
            if ext.on_startup:
                try:
                    logger.info(f"Starting extension: {ext.name}")
                    if asyncio.iscoroutinefunction(ext.on_startup):
                        await ext.on_startup()
                    else:
                        ext.on_startup()
                except Exception as e:
                    logger.error(f"Failed to start extension {ext.name}: {e}")

    async def shutdown(self):
        """Run shutdown hooks for all enabled extensions."""
        for ext in self.get_enabled():
            if ext.on_shutdown:
                try:
                    logger.info(f"Stopping extension: {ext.name}")
                    if asyncio.iscoroutinefunction(ext.on_shutdown):
                        await ext.on_shutdown()
                    else:
                        ext.on_shutdown()
                except Exception as e:
                    logger.error(f"Failed to stop extension {ext.name}: {e}")

class ExtensionPipeline:
    """Extension pipeline that composes extensions in proper order.

    Uses middleware pattern - each extension wraps the next.

    Usage:
        pipeline = ExtensionPipeline(registry)
        request = ExtensionRequest(operation="execute", data={...})
        response = await pipeline.execute(request, core_handler)
    """

    def __init__(self, registry: ExtensionRegistry):
        """Initialize the extension pipeline.

        Args:
            registry: Extension registry containing available extensions.
        """
        self.registry = registry

        from core.config import get_settings

        self._enabled = get_settings().extensions_enabled

    async def execute(self, request: ExtensionRequest, core_handler: Callable) -> ExtensionResponse:
        """Execute request through extension pipeline.

        Args:
            request: Extension request
            core_handler: Core execution function

        Returns:
            ExtensionResponse with results and metadata
        """
        if not self._enabled:
            # Extensions disabled - execute directly
            result = await core_handler(request.data)
            return ExtensionResponse(result=result, metadata={}, extensions_applied=[])

        # Build middleware chain
        extensions = self.registry.get_enabled()
        extensions_applied = []

        # Compose extensions (reverse order so first extension wraps last)
        handler = core_handler
        for ext in reversed(extensions):
            # Wrap handler with extension middleware
            handler = self._wrap_extension(ext, handler, extensions_applied)

        # Execute pipeline
        try:
            result = await handler(request.data)
            return ExtensionResponse(
                result=result, metadata=request.metadata, extensions_applied=extensions_applied
            )
        except Exception as e:
            logger.error(f"Extension pipeline failed: {e}")
            raise

    def _wrap_extension(
        self, ext: ExtensionConfig, next_handler: Callable, extensions_applied: list[str]
    ) -> Callable:
        """Wrap handler with extension middleware.

        Args:
            ext: Extension configuration
            next_handler: Next handler in chain
            extensions_applied: List to track applied extensions

        Returns:
            Wrapped handler
        """

        async def wrapped(data: dict[str, Any]) -> Any:
            # Track extension application
            extensions_applied.append(ext.name)
            logger.debug(f"Applying extension: {ext.name}")

            # Apply extension-specific logic
            if ext.type == ExtensionType.INPUT_VALIDATION:
                # Input validation happens before execution
                # For now, pass through (validation handled at API layer)
                result = await next_handler(data)

            elif ext.type == ExtensionType.SEMANTIC_CACHE:
                # Cache check happens in semantic_cache wrapper
                # Agents already use cached_llm_call, so pass through
                result = await next_handler(data)

            elif ext.type == ExtensionType.SELF_HEALING:
                # Self-healing wraps execution with retry logic
                # For now, pass through (healing handled at tool layer)
                result = await next_handler(data)

            elif ext.type == ExtensionType.SANDBOX:
                # Sandbox execution happens at tool layer
                # Tools use execute_in_sandbox, so pass through
                result = await next_handler(data)

            elif ext.type == ExtensionType.FILE_SAFETY:
                # File safety scanning happens at file operation layer
                # FileSafetyGuard.can_edit() checks safety, so pass through
                result = await next_handler(data)

            elif ext.type == ExtensionType.OUTPUT_SANITIZATION:
                # Output sanitization happens after execution
                # For now, pass through (sanitization handled at API layer)
                result = await next_handler(data)

            else:
                # Unknown extension type - pass through
                result = await next_handler(data)

            return result

        return wrapped

# Global registry
_extension_registry: ExtensionRegistry | None = None

def get_extension_registry() -> ExtensionRegistry:
    """Get or create global extension registry."""
    global _extension_registry
    if _extension_registry is None:
        _extension_registry = ExtensionRegistry()
        _register_default_extensions()
    return _extension_registry

def _register_default_extensions():
    """Register default extensions.

    NOTE: In plugin architecture, extensions are registered by plugins
    via PluginManager.register_all(). This function is intentionally
    minimal - it only registers core infrastructure extensions.

    Optional extensions (semantic_cache, sandbox, file_safety, etc.)
    should be registered by their respective plugins in plugins/ directory.
    """
    # No default extensions registered here.
    # Plugins register their extensions via PluginManager.register_all(registry)
    # during application startup in core/api/main.py.
    pass

def build_pipeline(registry: ExtensionRegistry | None = None) -> ExtensionPipeline:
    """Build extension pipeline from registry.

    Args:
        registry: Extension registry (uses global if not provided)

    Returns:
        Configured extension pipeline
    """
    if registry is None:
        registry = get_extension_registry()

    return ExtensionPipeline(registry)
