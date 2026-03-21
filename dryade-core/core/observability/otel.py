"""OpenTelemetry Native Observability.

Industry-standard tracing for LLM applications.
Target: ~100 LOC

Compatible with: Jaeger, Zipkin, Datadog, Grafana, etc.

See: https://opentelemetry.io/blog/2024/llm-observability/
"""

import os
import time
from functools import wraps
from typing import Any

# Try to import OpenTelemetry, gracefully degrade if not available
try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.trace import Status, StatusCode, Tracer

    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False
    trace = None
    Tracer = None

# Semantic conventions for LLM observability
# See: https://opentelemetry.io/docs/specs/semconv/gen-ai/
LLM_SYSTEM = "gen_ai.system"
LLM_REQUEST_MODEL = "gen_ai.request.model"
LLM_REQUEST_MAX_TOKENS = "gen_ai.request.max_tokens"
LLM_REQUEST_TEMPERATURE = "gen_ai.request.temperature"
LLM_RESPONSE_MODEL = "gen_ai.response.model"
LLM_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
LLM_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"

# Internal tracer
_tracer: Any | None = None

def init_otel(service_name: str = "dryade", endpoint: str | None = None) -> bool:
    """Initialize OpenTelemetry tracing.

    Args:
        service_name: Service name for traces
        endpoint: OTLP endpoint (default from OTEL_EXPORTER_OTLP_ENDPOINT)

    Returns:
        True if initialized successfully, False otherwise
    """
    global _tracer

    if not OTEL_AVAILABLE:
        return False

    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create(
            {
                "service.name": service_name,
                "service.version": "1.0.0",
            }
        )

        provider = TracerProvider(resource=resource)

        # Set up OTLP exporter if endpoint provided
        otlp_endpoint = endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
        if otlp_endpoint:
            exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
            provider.add_span_processor(BatchSpanProcessor(exporter))

        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer("dryade.llm")

        return True

    except Exception:
        return False

def get_tracer():
    """Get the OpenTelemetry tracer."""
    global _tracer
    if _tracer is None and OTEL_AVAILABLE:
        _tracer = trace.get_tracer("dryade.llm")
    return _tracer

def trace_llm_call(model: str | None = None):
    """Decorator to trace LLM calls with OpenTelemetry.

    Usage:
        @trace_llm_call(model="mistral")
        async def generate_response(prompt: str) -> str:
            ...
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            tracer = get_tracer()

            if tracer is None:
                # OTel not available, just execute
                return await func(*args, **kwargs)

            with tracer.start_as_current_span(
                f"llm.{func.__name__}", kind=trace.SpanKind.CLIENT
            ) as span:
                # Set model attribute
                if model:
                    span.set_attribute(LLM_REQUEST_MODEL, model)

                # Set request attributes from kwargs
                if "max_tokens" in kwargs:
                    span.set_attribute(LLM_REQUEST_MAX_TOKENS, kwargs["max_tokens"])
                if "temperature" in kwargs:
                    span.set_attribute(LLM_REQUEST_TEMPERATURE, kwargs["temperature"])

                start_time = time.time()

                try:
                    result = await func(*args, **kwargs)

                    # Set response attributes
                    if isinstance(result, dict) and "usage" in result:
                        usage = result["usage"]
                        span.set_attribute(LLM_USAGE_INPUT_TOKENS, usage.get("input_tokens", 0))
                        span.set_attribute(LLM_USAGE_OUTPUT_TOKENS, usage.get("output_tokens", 0))

                    span.set_status(Status(StatusCode.OK))
                    return result

                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise

                finally:
                    duration_ms = (time.time() - start_time) * 1000
                    span.set_attribute("duration_ms", duration_ms)

        return wrapper

    return decorator

def trace_tool_call(tool_name: str):
    """Decorator to trace tool calls."""

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            tracer = get_tracer()

            if tracer is None:
                return await func(*args, **kwargs)

            with tracer.start_as_current_span(
                f"tool.{tool_name}", kind=trace.SpanKind.INTERNAL
            ) as span:
                span.set_attribute("tool.name", tool_name)

                start_time = time.time()

                try:
                    result = await func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise
                finally:
                    span.set_attribute("duration_ms", (time.time() - start_time) * 1000)

        return wrapper

    return decorator

def record_llm_metrics(
    model: str, input_tokens: int, output_tokens: int, duration_ms: float, status: str = "ok"
):
    """Record LLM metrics as span events."""
    tracer = get_tracer()
    if tracer is None:
        return

    current_span = trace.get_current_span()
    if current_span:
        current_span.add_event(
            "llm_call",
            attributes={
                LLM_RESPONSE_MODEL: model,
                LLM_USAGE_INPUT_TOKENS: input_tokens,
                LLM_USAGE_OUTPUT_TOKENS: output_tokens,
                "duration_ms": duration_ms,
                "status": status,
            },
        )
