"""Structured Logging with structlog.

Provides JSON-formatted logs for production observability.
Target: ~50 LOC
"""

import logging
import re
import sys

try:
    import structlog

    STRUCTLOG_AVAILABLE = True
except ImportError:
    STRUCTLOG_AVAILABLE = False

from core.config import get_settings


class ColoredFormatter(logging.Formatter):
    """Custom formatter that adds colors to log output."""

    # ANSI color codes
    LEVEL_COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }

    # Colors for specific log prefixes
    PREFIX_COLORS = {
        "[CHAT API]": "\033[94m",  # Bright Blue
        "[ROUTER]": "\033[95m",  # Bright Magenta
        "[PLANNER]": "\033[93m",  # Bright Yellow
        "[FLOW]": "\033[96m",  # Bright Cyan
        "[REACTFLOW]": "\033[92m",  # Bright Green
        "[STREAM]": "\033[97m",  # White
        "[FLOWS API]": "\033[91m",  # Bright Red
        "[CLASSIFIER]": "\033[35m",  # Magenta
        "[ORCHESTRATOR]": "\033[1;36m",  # Bold Cyan
        "[THINKING]": "\033[1;35m",  # Bold Magenta
    }

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # Colors for key=value parameter highlighting
    KEY_COLOR = "\033[36m"  # Cyan for parameter names
    VALUE_COLOR = "\033[1m"  # Bold for parameter values
    PIPE_COLOR = "\033[2;37m"  # Dim white for pipe separators

    # Matches key=value where value is quoted string or non-whitespace/comma/pipe
    _KV_RE = re.compile(r'\b([a-z_]\w*)=(\'[^\']*\'|"[^"]*"|[^\s,|]+)')

    def format(self, record):
        """Format log record with colors and timestamps.

        Args:
            record: LogRecord to format

        Returns:
            Formatted log string with ANSI colors
        """
        # Format the base message
        log_msg = super().format(record)

        # Add timestamp in dim color
        import datetime

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        colored_timestamp = f"{self.DIM}{timestamp}{self.RESET}"

        # Color the log level
        level_color = self.LEVEL_COLORS.get(record.levelname, "")
        colored_level = f"{level_color}{record.levelname:8}{self.RESET}"

        # Color the logger name
        colored_name = f"{self.DIM}{record.name}{self.RESET}"

        # Highlight key=value parameters on plain text BEFORE any ANSI injection
        # to avoid the regex capturing ANSI escape codes as part of values
        colored_msg = self._KV_RE.sub(
            lambda m: f"{self.KEY_COLOR}{m.group(1)}{self.RESET}={self.VALUE_COLOR}{m.group(2)}{self.RESET}",
            log_msg,
        )

        # Color pipe separators (on plain-ish text, before prefix coloring)
        colored_msg = colored_msg.replace(" | ", f" {self.PIPE_COLOR}|{self.RESET} ")

        # Color any prefixes in the message
        for prefix, color in self.PREFIX_COLORS.items():
            if prefix in colored_msg:
                colored_msg = colored_msg.replace(prefix, f"{self.BOLD}{color}{prefix}{self.RESET}")

        # Color success/error markers
        colored_msg = colored_msg.replace("✓", f"\033[92m✓{self.RESET}")  # Green checkmark
        colored_msg = colored_msg.replace("✗", f"\033[91m✗{self.RESET}")  # Red X
        colored_msg = colored_msg.replace(">>>", f"\033[93m>>>{self.RESET}")  # Yellow arrows
        colored_msg = colored_msg.replace("===", f"\033[96m==={self.RESET}")  # Cyan equals

        return f"{colored_timestamp} {colored_level} {colored_name} - {colored_msg}"

class HealthCheckFilter(logging.Filter):
    """Suppress health check endpoint access log lines from uvicorn.access.

    Kubernetes probes (/live, /ready) and monitoring polls (/health, /metrics)
    emit an access log line on every poll. At 10s intervals, this creates
    ~360/hour log lines of no operational value. This filter removes them.
    """

    SUPPRESSED_PATHS: frozenset[str] = frozenset(
        {
            "/health",
            "/live",
            "/ready",
            "/metrics",
        }
    )

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        return not any(path in message for path in self.SUPPRESSED_PATHS)

def configure_logging(
    level: str | None = None,
    format: str | None = None,
) -> None:
    """Configure structured logging for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        format: Output format ("json" or "pretty")
    """
    settings = get_settings()
    log_level = level or settings.log_level
    log_format = format or settings.log_format

    # Configure base logging with colors (unless JSON format)
    if log_format == "json":
        # JSON format - no colors, simple format
        logging.basicConfig(
            level=getattr(logging, log_level),
            stream=sys.stdout,
            format="%(message)s",
        )
    else:
        # Pretty format - use colored formatter
        # Remove any existing handlers first
        root_logger = logging.getLogger()
        if root_logger.handlers:
            for handler in root_logger.handlers:
                root_logger.removeHandler(handler)

        # Create handler with colored formatter
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(ColoredFormatter("%(message)s"))
        root_logger.addHandler(handler)
        root_logger.setLevel(getattr(logging, log_level))

        # Ensure uvicorn loggers use our colored formatter instead of their
        # own default handlers (uvicorn calls dictConfig on startup which can
        # override the root logger handlers we just set up).
        _health_filter = HealthCheckFilter()
        for uv_logger_name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
            uv_logger = logging.getLogger(uv_logger_name)
            uv_logger.handlers = [handler]  # Use same colored handler
            uv_logger.propagate = False  # Don't double-log via root
            uv_logger.addFilter(_health_filter)  # Suppress health check polls

    if not STRUCTLOG_AVAILABLE:
        return

    # structlog emits through stdlib LoggerFactory. When using "pretty" format,
    # ConsoleRenderer already produces fully-formatted lines (timestamp + level
    # + event + logger). These must NOT pass through ColoredFormatter again,
    # or we get double timestamps and garbled output like "1Z [info     ]".
    #
    # Solution: give structlog its own handler with a bare "%(message)s"
    # formatter so the ConsoleRenderer output is emitted verbatim.
    if log_format != "json":
        structlog_handler = logging.StreamHandler(sys.stdout)
        structlog_handler.setFormatter(logging.Formatter("%(message)s"))
    else:
        structlog_handler = None  # JSON uses the root handler

    # Configure structlog processors
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_logger_name,
    ]

    if log_format == "json":
        processors = shared_processors + [
            structlog.processors.JSONRenderer(),
        ]
    else:
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Attach a dedicated handler to structlog's stdlib loggers so they bypass
    # ColoredFormatter. structlog.stdlib.LoggerFactory uses logging.getLogger()
    # internally, so the root handler's ColoredFormatter would double-format.
    # We intercept by setting propagate=False on the structlog-managed logger
    # and giving it the bare handler.
    if structlog_handler is not None:
        # structlog stdlib loggers inherit from root; we can't prevent that
        # generically. Instead, we use ProcessorFormatter integration so
        # structlog does formatting and stdlib just outputs.
        pass  # The structlog factory uses stdlib getLogger -- see note below

    # NOTE: The remaining double-formatting happens because most of the codebase
    # uses `logging.getLogger(__name__)` (stdlib) rather than `structlog.get_logger()`.
    # Those stdlib loggers go through ColoredFormatter correctly.
    # Only modules using `structlog.get_logger()` or `from core.observability.logging
    # import get_logger` would see ConsoleRenderer output routed through
    # ColoredFormatter. The fix is to ensure structlog uses ProcessorFormatter.
    if log_format != "json" and structlog_handler is not None:
        # Replace the structlog configure to use foreign_pre_chain + ProcessorFormatter
        # so stdlib logging records also get structlog formatting, while structlog
        # records bypass ColoredFormatter.
        structlog_handler.setFormatter(
            structlog.stdlib.ProcessorFormatter(
                processors=[
                    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    structlog.dev.ConsoleRenderer(colors=True),
                ],
                foreign_pre_chain=shared_processors,
            )
        )

        # Reconfigure structlog to NOT render -- let ProcessorFormatter do it
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.stdlib.add_log_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
            ],
            wrapper_class=structlog.stdlib.BoundLogger,
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )

        # Replace root handler with ProcessorFormatter handler so ALL logs
        # (both structlog and stdlib) get consistent formatting
        root_logger = logging.getLogger()
        root_logger.handlers = [structlog_handler]

def get_logger(name: str = "dryade"):
    """Get a structured logger instance.

    Args:
        name: Logger name (module/component name)

    Returns:
        Configured logger instance
    """
    if STRUCTLOG_AVAILABLE:
        return structlog.get_logger(name)
    else:
        return logging.getLogger(name)

# Convenience function for adding context
def bind_context(**kwargs):
    """Bind context variables for structured logging."""
    if STRUCTLOG_AVAILABLE:
        structlog.contextvars.bind_contextvars(**kwargs)

def clear_context():
    """Clear all context variables."""
    if STRUCTLOG_AVAILABLE:
        structlog.contextvars.clear_contextvars()

# Pre-configured application logger
log = get_logger("dryade")

# =============================================================================
# Error Context Helpers
# =============================================================================

def bind_error_context(
    error_type: str,
    operation: str,
    **extra_context,
) -> None:
    """Bind error context for subsequent log calls.

    Args:
        error_type: Type of error (ValidationError, ExecutionError, etc.)
        operation: What operation was being attempted
        **extra_context: Additional context (agent_name, workflow_id, etc.)
    """
    if STRUCTLOG_AVAILABLE:
        structlog.contextvars.bind_contextvars(
            error_type=error_type,
            operation=operation,
            **extra_context,
        )

def log_error(
    logger,
    message: str,
    error: Exception | None = None,
    *,
    error_code: str | None = None,
    operation: str | None = None,
    context: dict | None = None,
    include_traceback: bool = True,
) -> None:
    """Log error with structured context.

    Args:
        logger: Logger instance
        message: Error message
        error: Exception instance (optional)
        error_code: Error code from exceptions.py
        operation: What operation failed
        context: Additional context dict
        include_traceback: Whether to include stack trace
    """
    log_context = {
        "error_code": error_code,
        "operation": operation,
        **(context or {}),
    }

    if error:
        log_context["error_type"] = type(error).__name__
        log_context["error_message"] = str(error)

        # Include DryadeError attributes if present
        if hasattr(error, "to_dict"):
            error_dict = error.to_dict()
            log_context.update(
                {
                    "error_code": error_dict.get("code"),
                    "suggestion": error_dict.get("suggestion"),
                }
            )

    if include_traceback and error:
        if STRUCTLOG_AVAILABLE:
            logger.exception(message, **log_context)
        else:
            logger.exception(f"{message} | context={log_context}")
    else:
        if STRUCTLOG_AVAILABLE:
            logger.error(message, **log_context)
        else:
            logger.error(f"{message} | context={log_context}")

def create_request_context(
    request_id: str,
    user_id: str | None = None,
    path: str | None = None,
    method: str | None = None,
) -> dict:
    """Create standard request context dict.

    Returns dict suitable for binding or passing to log calls.
    """
    return {
        "request_id": request_id,
        "user_id": user_id,
        "path": path,
        "method": method,
    }
