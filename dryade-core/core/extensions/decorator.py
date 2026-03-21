"""Extension Pipeline Decorator.

Wraps functions with extension pipeline for transparent execution.
Target: ~80 LOC
"""

import logging
import time
import uuid
from collections.abc import Callable
from functools import wraps
from typing import Any

from core.extensions.pipeline import ExtensionRequest, ExtensionResponse, build_pipeline

logger = logging.getLogger(__name__)

def with_extensions(
    operation: str, request_id_key: str = "request_id", conversation_id_key: str = "conversation_id"
):
    """Decorator to apply extension pipeline to async functions.

    Args:
        operation: Operation name (e.g., "agent_execute", "tool_call")
        request_id_key: Key in kwargs for request_id (default: "request_id")
        conversation_id_key: Key in kwargs for conversation_id (default: "conversation_id")

    Usage:
        @with_extensions(operation="agent_execute")
        async def execute(task: str, context: Dict) -> AgentResult:
            # Core execution logic
            return result
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            # Get or generate request_id
            request_id = kwargs.get(request_id_key) or str(uuid.uuid4())
            conversation_id = kwargs.get(conversation_id_key)

            # Build extension pipeline
            pipeline = build_pipeline()

            # Create extension request
            ext_request = ExtensionRequest(
                operation=operation,
                data={"args": args, "kwargs": kwargs},
                context={
                    "request_id": request_id,
                    "conversation_id": conversation_id,
                    "operation": operation,
                },
                metadata={},
            )

            # Core handler wraps original function
            async def core_handler(data: dict[str, Any]) -> Any:
                return await func(*data["args"], **data["kwargs"])

            # Execute through pipeline
            start_time = time.time()
            try:
                response: ExtensionResponse = await pipeline.execute(ext_request, core_handler)

                duration_ms = (time.time() - start_time) * 1000

                # Log extension execution
                logger.info(
                    f"Extensions applied to {operation}: "
                    f"{', '.join(response.extensions_applied)} "
                    f"({duration_ms:.2f}ms)"
                )

                # Store extension execution in database
                await _store_extension_execution(
                    request_id=request_id,
                    conversation_id=conversation_id,
                    extensions_applied=response.extensions_applied,
                    duration_ms=duration_ms,
                    cache_hit=response.cache_hit,
                    healed=response.healed,
                    threats_found=response.threats_found or [],
                )

                # Store timeline entry
                await _store_timeline_entry(
                    request_id=request_id,
                    conversation_id=conversation_id,
                    operation=operation,
                    extensions_applied=response.extensions_applied,
                    duration_ms=duration_ms,
                    cache_hit=response.cache_hit,
                    healed=response.healed,
                    threats_found=response.threats_found or [],
                )

                # Return result with extension metadata
                result = response.result
                if hasattr(result, "metadata") and isinstance(result.metadata, dict):
                    result.metadata["extensions_applied"] = response.extensions_applied
                    result.metadata["extension_duration_ms"] = duration_ms

                return result

            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                logger.error(
                    f"Extension pipeline failed for {operation} after {duration_ms:.2f}ms: {e}",
                    exc_info=True,
                )
                raise

        return wrapper

    return decorator

async def _store_extension_execution(
    request_id: str,
    conversation_id: str | None,
    extensions_applied: list,
    duration_ms: float,
    cache_hit: bool,
    healed: bool,
    threats_found: list,
):
    """Store extension execution in database."""
    try:
        from core.database.models import ExtensionExecution
        from core.database.session import get_session

        async with get_session() as session:
            for ext_name in extensions_applied:
                execution = ExtensionExecution(
                    request_id=request_id,
                    conversation_id=conversation_id,
                    extension_name=ext_name,
                    duration_ms=duration_ms / len(extensions_applied),  # Approximate per-extension
                    cache_hit=cache_hit,
                    healed=healed,
                    threats_found=threats_found,
                    metadata_={},
                )
                session.add(execution)

            await session.commit()

    except Exception as e:
        logger.warning(f"Failed to store extension execution: {e}")

async def _store_timeline_entry(
    request_id: str,
    conversation_id: str | None,
    operation: str,
    extensions_applied: list,
    duration_ms: float,
    cache_hit: bool,
    healed: bool,
    threats_found: list,
):
    """Store timeline entry in database."""
    try:
        from core.database.models import ExtensionTimeline
        from core.database.session import get_session

        async with get_session() as session:
            timeline = ExtensionTimeline(
                request_id=request_id,
                conversation_id=conversation_id,
                operation=operation,
                extensions_applied=extensions_applied,
                total_duration_ms=duration_ms,
                outcomes={
                    "cache_hit": cache_hit,
                    "healed": healed,
                    "threats_found": len(threats_found),
                    "threats": threats_found,
                },
            )
            session.add(timeline)
            await session.commit()

    except Exception as e:
        logger.warning(f"Failed to store timeline entry: {e}")
