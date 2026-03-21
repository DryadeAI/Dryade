"""Dryade Observability.

Provides tracing, metrics, logging, and OpenTelemetry support.
"""

from core.observability.crewai_tracing import (
    CrewAITracingCallback,
    SpanContext,
    get_current_context,
    init_crewai_tracing,
    register_crewai_tracing,
    traced,
)
from core.observability.logging import (
    STRUCTLOG_AVAILABLE,
    bind_context,
    clear_context,
    configure_logging,
    get_logger,
    log,
)
from core.observability.metrics import (
    record_agent_call,
    record_crew_execution,
    record_request,
    set_active_sessions,
    set_active_websockets,
)
from core.observability.metrics import (
    record_llm_call as record_llm_call_metric,
)
from core.observability.metrics import (
    record_tool_call as record_tool_call_metric,
)
from core.observability.metrics import (
    router as metrics_router,
)
from core.observability.otel import (
    OTEL_AVAILABLE,
    get_tracer,
    init_otel,
    record_llm_metrics,
)
from core.observability.otel import (
    trace_llm_call as otel_trace_llm,
)
from core.observability.otel import (
    trace_tool_call as otel_trace_tool,
)
from core.observability.tracing import (
    LocalTraceSink,
    get_trace_sink,
    trace_agent_complete,
    trace_agent_start,
    trace_crew_complete,
    trace_crew_start,
    trace_event,
    trace_llm_call,
    trace_tool_call,
)

__all__ = [
    # Tracing
    "LocalTraceSink",
    "get_trace_sink",
    "trace_event",
    "trace_crew_start",
    "trace_crew_complete",
    "trace_agent_start",
    "trace_agent_complete",
    "trace_tool_call",
    "trace_llm_call",
    # Metrics
    "metrics_router",
    "record_request",
    "record_crew_execution",
    "record_agent_call",
    "record_tool_call_metric",
    "record_llm_call_metric",
    "set_active_sessions",
    "set_active_websockets",
    # OpenTelemetry
    "init_otel",
    "get_tracer",
    "otel_trace_llm",
    "otel_trace_tool",
    "record_llm_metrics",
    "OTEL_AVAILABLE",
    # Logging
    "configure_logging",
    "get_logger",
    "bind_context",
    "clear_context",
    "log",
    "STRUCTLOG_AVAILABLE",
    # CrewAI Tracing
    "CrewAITracingCallback",
    "SpanContext",
    "init_crewai_tracing",
    "register_crewai_tracing",
    "traced",
    "get_current_context",
]
