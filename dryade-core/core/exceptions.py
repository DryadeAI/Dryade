"""Unified Exception Hierarchy for Dryade.

All custom exceptions inherit from DryadeError base class.
This module provides structured error handling with:
- Machine-readable error codes
- Context dictionaries for debugging
- Actionable suggestions for resolution
- API serialization via to_dict()

Error code prefixes:
- DRYADE_ERR: Generic Dryade errors
- VALIDATION_xxx: Input validation failures
- NOT_FOUND_xxx: Resource not found errors
- CONFIG_xxx: Configuration errors
- EXEC_xxx: Execution errors
- ADAPTER_xxx: Framework adapter issues
- MCP_xxx: MCP protocol/transport issues
- PLUGIN_xxx: Plugin system errors
- AUTH_xxx: Authentication failures
- AUTHZ_xxx: Authorization/permission errors
"""

from __future__ import annotations

from typing import Any

class DryadeError(Exception):
    """Base exception for all Dryade errors.

    All custom exceptions in Dryade inherit from this class,
    providing a consistent structure for error handling.

    Attributes:
        message: Human-readable error description
        error_code: Machine-readable error code (e.g., "ADAPTER_001")
        context: Dict with debugging context (agent_name, operation, etc.)
        suggestion: Actionable suggestion for resolution
    """

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        context: dict[str, Any] | None = None,
        suggestion: str | None = None,
    ):
        """Initialize DryadeError.

        Args:
            message: Human-readable error description
            error_code: Machine-readable error code
            context: Dict with debugging context
            suggestion: Actionable suggestion for resolution
        """
        self.message = message
        self.error_code = error_code or "DRYADE_ERR"
        self.context = context or {}
        self.suggestion = suggestion
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        """Format the error message with code and suggestion."""
        parts = [f"[{self.error_code}] {self.message}"]
        if self.suggestion:
            parts.append(f"Suggestion: {self.suggestion}")
        return " | ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        """Convert to API-safe dict representation.

        Returns:
            Dictionary with error, code, context, and suggestion keys.
        """
        return {
            "error": self.message,
            "code": self.error_code,
            "context": self.context,
            "suggestion": self.suggestion,
        }

# =============================================================================
# Domain-specific Exception Classes
# =============================================================================

class ValidationError(DryadeError):
    """Input validation failures.

    Raised when user input or data fails validation checks.
    """

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        context: dict[str, Any] | None = None,
        suggestion: str | None = None,
    ):
        super().__init__(
            message=message,
            error_code=error_code or "VALIDATION_001",
            context=context,
            suggestion=suggestion or "Check the input data format and constraints.",
        )

class NotFoundError(DryadeError):
    """Resource not found errors.

    Raised when a requested resource cannot be located.
    """

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        context: dict[str, Any] | None = None,
        suggestion: str | None = None,
    ):
        super().__init__(
            message=message,
            error_code=error_code or "NOT_FOUND_001",
            context=context,
            suggestion=suggestion or "Verify the resource exists and check the identifier.",
        )

class ConfigurationError(DryadeError):
    """Missing or invalid configuration.

    Raised when required configuration is missing or malformed.
    """

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        context: dict[str, Any] | None = None,
        suggestion: str | None = None,
    ):
        super().__init__(
            message=message,
            error_code=error_code or "CONFIG_001",
            context=context,
            suggestion=suggestion or "Check environment variables and configuration files.",
        )

class ExecutionError(DryadeError):
    """Runtime execution failures.

    Base class for errors that occur during execution.
    """

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        context: dict[str, Any] | None = None,
        suggestion: str | None = None,
    ):
        super().__init__(
            message=message,
            error_code=error_code or "EXEC_001",
            context=context,
            suggestion=suggestion or "Check logs for details and retry the operation.",
        )

class AdapterError(DryadeError):
    """Framework adapter issues.

    Raised when there are problems with agent framework adapters.
    """

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        context: dict[str, Any] | None = None,
        suggestion: str | None = None,
    ):
        super().__init__(
            message=message,
            error_code=error_code or "ADAPTER_001",
            context=context,
            suggestion=suggestion or "Check adapter configuration and framework compatibility.",
        )

class MCPError(DryadeError):
    """MCP protocol/transport issues.

    Base class for all MCP-related errors.
    """

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        context: dict[str, Any] | None = None,
        suggestion: str | None = None,
    ):
        super().__init__(
            message=message,
            error_code=error_code or "MCP_001",
            context=context,
            suggestion=suggestion or "Check MCP server status and configuration.",
        )

class PluginError(DryadeError):
    """Plugin system errors.

    Base class for plugin-related errors.
    """

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        context: dict[str, Any] | None = None,
        suggestion: str | None = None,
    ):
        super().__init__(
            message=message,
            error_code=error_code or "PLUGIN_001",
            context=context,
            suggestion=suggestion or "Check plugin installation and configuration.",
        )

class AuthenticationError(DryadeError):
    """Authentication failures.

    Raised when authentication fails or credentials are invalid.
    """

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        context: dict[str, Any] | None = None,
        suggestion: str | None = None,
    ):
        super().__init__(
            message=message,
            error_code=error_code or "AUTH_001",
            context=context,
            suggestion=suggestion or "Check credentials and try again.",
        )

class AuthorizationError(DryadeError):
    """Permission denied errors.

    Raised when a user lacks permission for an operation.
    """

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        context: dict[str, Any] | None = None,
        suggestion: str | None = None,
    ):
        super().__init__(
            message=message,
            error_code=error_code or "AUTHZ_001",
            context=context,
            suggestion=suggestion or "Contact your administrator for access.",
        )

# =============================================================================
# Specific Exception Subclasses
# =============================================================================

class AgentExecutionError(AdapterError):
    """Raised when agent execution fails.

    Specific error for agent execution failures with agent context.

    Attributes:
        agent_name: Name of the agent that failed
        details: Additional error details
    """

    def __init__(
        self,
        message: str,
        agent_name: str | None = None,
        details: dict[str, Any] | None = None,
        error_code: str | None = None,
        context: dict[str, Any] | None = None,
        suggestion: str | None = None,
    ):
        """Initialize AgentExecutionError.

        Args:
            message: Error message describing the failure
            agent_name: Name of the agent that failed
            details: Optional additional error details
            error_code: Machine-readable error code
            context: Dict with debugging context
            suggestion: Actionable suggestion for resolution
        """
        self.agent_name = agent_name
        self.details = details or {}

        # Build context
        ctx = context or {}
        if agent_name:
            ctx["agent_name"] = agent_name
        if details:
            ctx.update(details)

        # Format message with agent name if provided
        formatted_message = f"[{agent_name}] {message}" if agent_name else message

        super().__init__(
            message=formatted_message,
            error_code=error_code or "ADAPTER_EXEC_001",
            context=ctx,
            suggestion=suggestion or f"Check agent '{agent_name}' configuration and logs.",
        )

class MCPTransportError(MCPError):
    """Error during MCP transport communication.

    Raised when transport-level communication with MCP server fails.

    Attributes:
        code: MCP error code (from MCPErrorCode enum)
    """

    def __init__(
        self,
        message: str,
        code: int | None = None,
        error_code: str | None = None,
        context: dict[str, Any] | None = None,
        suggestion: str | None = None,
    ):
        """Initialize MCPTransportError.

        Args:
            message: Error message
            code: MCP protocol error code
            error_code: Machine-readable error code
            context: Dict with debugging context
            suggestion: Actionable suggestion for resolution
        """
        self.code = code or -32603  # Default to INTERNAL_ERROR

        ctx = context or {}
        ctx["mcp_code"] = self.code

        super().__init__(
            message=message,
            error_code=error_code or "MCP_TRANSPORT_001",
            context=ctx,
            suggestion=suggestion or "Check MCP server process and network connectivity.",
        )

class MCPTimeoutError(MCPTransportError):
    """Timeout waiting for MCP server response.

    Raised when an MCP request times out.
    """

    def __init__(
        self,
        message: str = "Timeout waiting for server response",
        code: int | None = None,
        error_code: str | None = None,
        context: dict[str, Any] | None = None,
        suggestion: str | None = None,
    ):
        super().__init__(
            message=message,
            code=code or -32603,  # INTERNAL_ERROR
            error_code=error_code or "MCP_TIMEOUT_001",
            context=context,
            suggestion=suggestion or "Increase timeout or check server responsiveness.",
        )

class MCPRegistryError(MCPError):
    """Error in MCP registry operations.

    Raised for registry-specific errors such as:
    - Server not found
    - Server already registered
    - Server not running (when required)
    """

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        context: dict[str, Any] | None = None,
        suggestion: str | None = None,
    ):
        super().__init__(
            message=message,
            error_code=error_code or "MCP_REGISTRY_001",
            context=context,
            suggestion=suggestion or "Check server registration and status.",
        )

class TranslationError(ExecutionError):
    """Error during workflow translation.

    Raised when workflow translation from ReactFlow to executable format fails.
    """

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        context: dict[str, Any] | None = None,
        suggestion: str | None = None,
    ):
        super().__init__(
            message=message,
            error_code=error_code or "EXEC_TRANSLATE_001",
            context=context,
            suggestion=suggestion or "Check workflow node configuration and connections.",
        )

class WorkflowExecutionError(ExecutionError):
    """Error during workflow execution.

    Raised when a workflow fails during execution.
    """

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        context: dict[str, Any] | None = None,
        suggestion: str | None = None,
    ):
        super().__init__(
            message=message,
            error_code=error_code or "EXEC_WORKFLOW_001",
            context=context,
            suggestion=suggestion or "Check workflow configuration and agent availability.",
        )

class PluginValidationError(PluginError):
    """Raised when plugin validation fails.

    User-facing message is generic. Detailed info in logs only.
    This prevents information leakage about validation internals.

    Attributes:
        plugin_name: Name of the plugin that failed validation
        internal_reason: Detailed reason (logged, not shown to user)
    """

    def __init__(
        self,
        plugin_name: str,
        internal_reason: str,
        error_code: str | None = None,
        context: dict[str, Any] | None = None,
        suggestion: str | None = None,
    ):
        """Initialize PluginValidationError.

        Args:
            plugin_name: Name of the plugin
            internal_reason: Detailed reason (logged, not shown to user)
            error_code: Machine-readable error code
            context: Dict with debugging context
            suggestion: Actionable suggestion for resolution
        """
        self.plugin_name = plugin_name
        self.internal_reason = internal_reason

        ctx = context or {}
        ctx["plugin_name"] = plugin_name
        # Note: internal_reason is NOT added to context for security

        # Generic user-facing message - truncated plugin name as reference
        message = f"Plugin validation failed. Contact support. Reference: {plugin_name[:8]}"

        super().__init__(
            message=message,
            error_code=error_code or "PLUGIN_VALIDATION_001",
            context=ctx,
            suggestion=suggestion or "Contact support with the reference code.",
        )

class PluginConflictError(PluginError):
    """Raised when two plugins conflict (same name or route)."""

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        context: dict[str, Any] | None = None,
        suggestion: str | None = None,
    ):
        super().__init__(
            message=message,
            error_code=error_code or "PLUGIN_CONFLICT_001",
            context=context,
            suggestion=suggestion or "Remove one of the conflicting plugins.",
        )

class PluginVersionError(PluginError):
    """Raised when plugin is incompatible with core version.

    Attributes:
        plugin_name: Name of the incompatible plugin
        plugin_constraint: Version constraint from the plugin
        core_version: Current core version
    """

    def __init__(
        self,
        plugin_name: str,
        plugin_constraint: str,
        core_version: str,
        error_code: str | None = None,
        context: dict[str, Any] | None = None,
        suggestion: str | None = None,
    ):
        """Initialize PluginVersionError.

        Args:
            plugin_name: Name of the incompatible plugin
            plugin_constraint: Version constraint from the plugin
            core_version: Current core version
            error_code: Machine-readable error code
            context: Dict with debugging context
            suggestion: Actionable suggestion for resolution
        """
        self.plugin_name = plugin_name
        self.plugin_constraint = plugin_constraint
        self.core_version = core_version

        ctx = context or {}
        ctx["plugin_name"] = plugin_name
        ctx["plugin_constraint"] = plugin_constraint
        ctx["core_version"] = core_version

        message = (
            f"Plugin '{plugin_name}' requires core {plugin_constraint}, but core is {core_version}."
        )

        super().__init__(
            message=message,
            error_code=error_code or "PLUGIN_VERSION_001",
            context=ctx,
            suggestion=suggestion or "Update the plugin or use a compatible core version.",
        )

class SecurityError(AuthorizationError):
    """Raised when security validation fails.

    Used for certificate pinning failures, tampering detection, etc.
    """

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        context: dict[str, Any] | None = None,
        suggestion: str | None = None,
    ):
        super().__init__(
            message=message,
            error_code=error_code or "AUTHZ_SECURITY_001",
            context=context,
            suggestion=suggestion or "Check security configuration and certificates.",
        )

class AccessDeniedError(AuthorizationError):
    """Raised when access to a resource or feature is denied.

    Generic access denial error for permission checks. Does not expose
    tier information - provides generic "access denied" message.

    Attributes:
        plugin_name: Name of the plugin access was denied for (optional)
        reason: Generic reason for denial (optional)
    """

    def __init__(
        self,
        plugin_name: str | None = None,
        reason: str | None = None,
        error_code: str | None = None,
        context: dict[str, Any] | None = None,
        suggestion: str | None = None,
    ):
        """Initialize AccessDeniedError.

        Args:
            plugin_name: Name of the plugin access was denied for
            reason: Generic reason for denial
            error_code: Machine-readable error code
            context: Dict with debugging context
            suggestion: Actionable suggestion for resolution
        """
        self.plugin_name = plugin_name
        self.reason = reason

        # Build context from attributes
        ctx = context or {}
        if plugin_name:
            ctx["plugin_name"] = plugin_name

        # Build generic message - no tier/license info exposed
        if plugin_name and reason:
            message = f"Access denied for '{plugin_name}': {reason}"
        elif plugin_name:
            message = f"Access denied for '{plugin_name}'"
        elif reason:
            message = f"Access denied: {reason}"
        else:
            message = "Access denied"

        super().__init__(
            message=message,
            error_code=error_code or "AUTHZ_ACCESS_001",
            context=ctx,
            suggestion=suggestion or "Contact your administrator for access.",
        )

class WorkflowPausedForApproval(Exception):
    """Sentinel exception raised when a workflow hits an approval node.

    NOT an error — signals the workflow route handler to persist state
    and set execution status to 'paused'. Caught outside flow.kickoff_async().
    """

    def __init__(self, approval_request_id: int):
        self.approval_request_id = approval_request_id
        super().__init__(f"Workflow paused for approval (request_id={approval_request_id})")

# =============================================================================
# Module Exports
# =============================================================================

__all__ = [
    # Base class
    "DryadeError",
    # Domain-specific classes
    "ValidationError",
    "NotFoundError",
    "ConfigurationError",
    "ExecutionError",
    "AdapterError",
    "MCPError",
    "PluginError",
    "AuthenticationError",
    "AuthorizationError",
    # Specific subclasses
    "AgentExecutionError",
    "MCPTransportError",
    "MCPTimeoutError",
    "MCPRegistryError",
    "TranslationError",
    "WorkflowExecutionError",
    "PluginValidationError",
    "PluginConflictError",
    "PluginVersionError",
    "SecurityError",
    "AccessDeniedError",
    "WorkflowPausedForApproval",
]
