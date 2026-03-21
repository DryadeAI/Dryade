"""DryadeOrchestrator - Native orchestration engine.

Replaces CrewAI Process types with Dryade-native orchestration.
Works with ANY framework agent via UniversalAgent interface.

Based on ReActExecutor pattern from core/autonomous/executor.py.

User decisions implemented:
- Capability negotiation pattern (dynamic check)
- Intelligent fallback (LLM decides retry/skip/escalate)
- Default 3 retries, 30s timeout
- Criticality-based failure handling
- Memory usage user controlled
"""

import asyncio
import logging
import re
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from core.adapters.registry import AgentRegistry, get_registry
from core.autonomous.leash import LEASH_STANDARD, LeashConfig
from core.config import get_settings
from core.orchestrator.config import get_orchestration_config
from core.orchestrator.models import (
    ErrorCategory,
    FailureAction,
    OrchestrationMode,
    OrchestrationObservation,
    OrchestrationResult,
    OrchestrationState,
    OrchestrationTask,
    ToolError,
)
from core.orchestrator.observation import ObservationHistory
from core.orchestrator.thinking import OrchestrationThinkingProvider

# NOTE: ReActLoop and FailureHandler imported lazily in __init__ to avoid
# circular imports (they import OrchestrationErrorBoundary from this module).

if TYPE_CHECKING:
    from core.adapters.protocol import AgentCard, UniversalAgent
    from core.orchestrator.checkpoint import CheckpointManager, PersistentCheckpointBackend
    from core.orchestrator.circuit_breaker import CircuitBreaker
    from core.orchestrator.failure_history import (
        AdaptiveRetryStrategy,
        FailureHistoryStore,
        PatternDetector,
    )
    from core.orchestrator.failure_middleware import FailurePipeline
    from core.orchestrator.output_judge import OutputJudge

logger = logging.getLogger(__name__)

__all__ = ["DryadeOrchestrator", "OrchestrationErrorBoundary"]

class OrchestrationErrorBoundary:
    """Error boundary for graceful orchestration failure handling.

    Catches catastrophic errors in the orchestration loop and converts them
    to user-friendly escalation results instead of crashing.

    Example:
        async with OrchestrationErrorBoundary(logger, execution_id) as boundary:
            while True:
                # orchestration loop...
                pass

        if boundary.error:
            return boundary.get_fallback_result()
    """

    def __init__(self, log: logging.Logger | None, execution_id: str):
        """Initialize error boundary.

        Args:
            log: Logger instance (can be None for testing)
            execution_id: Execution ID for tracking
        """
        self.log = log or logging.getLogger(__name__)
        self.execution_id = execution_id
        self.error: Exception | None = None

    async def __aenter__(self) -> "OrchestrationErrorBoundary":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> bool:
        if exc_val is not None:
            self.error = exc_val  # type: ignore[assignment]
            self.log.error(
                f"[ORCHESTRATOR] Error boundary caught: {exc_type.__name__ if exc_type else 'Unknown'}: {exc_val}",
                exc_info=True,
            )
            # Suppress exception - we'll handle gracefully
            return True
        return False

    def get_fallback_result(self) -> OrchestrationResult:
        """Get fallback result after catching error.

        Returns:
            OrchestrationResult with escalation asking user how to proceed
        """
        error_msg = str(self.error) if self.error else "Unknown orchestration error"
        error_type = type(self.error).__name__ if self.error else "UnknownError"
        return OrchestrationResult(
            success=False,
            needs_escalation=True,
            escalation_question=f"I encountered an unexpected error: {error_msg}. Would you like me to try a different approach?",
            reason=f"Orchestration error boundary: {error_type}",
        )

def _emit_event(
    on_agent_event: "Callable[[str, dict], None] | None",
    event_type: str,
    data: dict,
) -> None:
    """Emit an agent lifecycle event if callback is provided."""
    if on_agent_event:
        on_agent_event(event_type, data)

class DryadeOrchestrator:
    """Native orchestration engine - replaces CrewAI Process types.

    Features:
    - Works with ANY framework via UniversalAgent
    - Supports SEQUENTIAL, PARALLEL, HIERARCHICAL, ADAPTIVE modes
    - Uses LeashConfig for resource constraints
    - Integrates with SSE event system
    - Capability negotiation (validates agent supports features before calling)
    - Intelligent fallback (LLM decides retry/skip/escalate)
    - Criticality-based failure handling
    - User-controlled memory usage

    Example:
        orchestrator = DryadeOrchestrator()
        result = await orchestrator.orchestrate(
            goal="Analyze this document and create a summary",
            mode=OrchestrationMode.ADAPTIVE,
        )
    """

    def __init__(
        self,
        thinking_provider: OrchestrationThinkingProvider | None = None,
        agent_registry: AgentRegistry | None = None,
        leash: LeashConfig | None = None,
    ):
        """Initialize orchestrator.

        Args:
            thinking_provider: LLM reasoning provider. Defaults to new instance.
            agent_registry: Agent registry. Defaults to global registry.
            leash: Resource constraints. Defaults to LEASH_STANDARD.

        Note: Skills are NOT orchestrated - they're executed via bash tool (OpenClaw pattern).
              This orchestrator coordinates framework agents only.
        """
        self.thinking = thinking_provider or OrchestrationThinkingProvider()
        self.agents = agent_registry or get_registry()
        self.leash = leash or LEASH_STANDARD
        self._circuit_breaker: "CircuitBreaker | None" = None
        self._soft_failure_detector: "SoftFailureDetector | None" = None
        self._output_judge: "OutputJudge | None" = None
        self._checkpoint_manager: "CheckpointManager | None" = None
        self._persistent_backend: "PersistentCheckpointBackend | None" = None
        self._failure_history_store: "FailureHistoryStore | None" = None
        self._adaptive_retry: "AdaptiveRetryStrategy | None" = None
        self._pattern_detector: "PatternDetector | None" = None
        self._failure_pipeline: "FailurePipeline | None" = None

        # Extracted handler classes (Phase 181-11 decomposition)
        # Lazy imports to avoid circular dependency (react_loop/failure_handler
        # import OrchestrationErrorBoundary and _emit_event from this module).
        from core.orchestrator.failure_handler import FailureHandler
        from core.orchestrator.react_loop import ReActLoop
        from core.orchestrator.retry_executor import RetryExecutor

        self._react_loop = ReActLoop(self)
        self._failure_handler = FailureHandler(self)
        self._retry_executor = RetryExecutor(self)

    async def cleanup(self):
        """Release resources held by this orchestrator instance.

        Closes LLM httpx clients to prevent connection pool exhaustion
        after sequential agent invocations (BUG-011).
        """
        llm = getattr(self.thinking, "_cached_llm", None) or getattr(
            self.thinking, "_explicit_llm", None
        )
        if llm is not None and hasattr(llm, "aclose"):
            try:
                await llm.aclose()
            except Exception:
                pass
        elif llm is not None and hasattr(llm, "close"):
            try:
                llm.close()
            except Exception:
                pass

    @property
    def circuit_breaker(self) -> "CircuitBreaker":
        """Lazily create CircuitBreaker on first access."""
        if self._circuit_breaker is None:
            from core.orchestrator.circuit_breaker import CircuitBreaker

            self._circuit_breaker = CircuitBreaker()
        return self._circuit_breaker

    @property
    def soft_failure_detector(self) -> "SoftFailureDetector":
        """Lazily create SoftFailureDetector on first access."""
        if self._soft_failure_detector is None:
            from core.orchestrator.soft_failure_detector import SoftFailureDetector

            self._soft_failure_detector = SoftFailureDetector()
        return self._soft_failure_detector

    @property
    def output_judge(self) -> "OutputJudge":
        """Lazily create OutputJudge on first access."""
        if self._output_judge is None:
            from core.orchestrator.output_judge import OutputJudge

            cfg = get_orchestration_config()
            self._output_judge = OutputJudge(
                thinking_provider=self.thinking,
                score_threshold=cfg.judge_score_threshold,
            )
        return self._output_judge

    @property
    def checkpoint_manager(self) -> "CheckpointManager":
        """Lazily create CheckpointManager on first access."""
        if self._checkpoint_manager is None:
            from core.orchestrator.checkpoint import CheckpointManager

            cfg = get_orchestration_config()
            self._checkpoint_manager = CheckpointManager(
                max_snapshots=cfg.checkpoint_max_snapshots,
            )
        return self._checkpoint_manager

    @property
    def persistent_checkpoint_backend(self) -> "PersistentCheckpointBackend":
        """Lazily create PersistentCheckpointBackend on first access."""
        if self._persistent_backend is None:
            from core.orchestrator.checkpoint import PersistentCheckpointBackend

            self._persistent_backend = PersistentCheckpointBackend()
        return self._persistent_backend

    @property
    def failure_history_store(self) -> "FailureHistoryStore":
        """Lazily create FailureHistoryStore on first access."""
        if self._failure_history_store is None:
            from core.orchestrator.failure_history import FailureHistoryStore

            cfg = get_orchestration_config()
            self._failure_history_store = FailureHistoryStore()
            # Purge old records on first access
            purged = self._failure_history_store.purge_old_records(
                retention_days=cfg.failure_history_retention_days,
            )
            if purged > 0:
                logger.info("[ORCHESTRATOR] Purged %d old failure history records", purged)
        return self._failure_history_store

    @property
    def adaptive_retry_strategy(self) -> "AdaptiveRetryStrategy":
        """Lazily create AdaptiveRetryStrategy on first access."""
        if self._adaptive_retry is None:
            from core.orchestrator.failure_history import AdaptiveRetryStrategy

            self._adaptive_retry = AdaptiveRetryStrategy(store=self.failure_history_store)
        return self._adaptive_retry

    @property
    def pattern_detector(self) -> "PatternDetector":
        """Lazily create PatternDetector on first access."""
        if self._pattern_detector is None:
            from core.orchestrator.failure_history import PatternDetector

            self._pattern_detector = PatternDetector(store=self.failure_history_store)
        return self._pattern_detector

    @property
    def failure_pipeline(self) -> "FailurePipeline":
        """Lazily create FailurePipeline on first access."""
        if self._failure_pipeline is None:
            from core.orchestrator.failure_middleware import get_failure_pipeline

            self._failure_pipeline = get_failure_pipeline()
        return self._failure_pipeline

    async def _handle_capability_gap(
        self, task_description: str, context: dict[str, Any]
    ) -> str | None:
        """Attempt fast-path factory creation when a capability gap is detected.

        Uses scaffold-only fast path (< 2s) for in-flow creation.
        Full testing runs in background after scaffold completes.

        Called from _handle_failure() when agent-not-found is detected,
        BEFORE the standard escalation path fires.

        Args:
            task_description: The task that failed due to missing capability.
            context: Execution context dict (must contain conversation_id).

        Returns:
            Human-readable result message if creation succeeded, None otherwise.
        """
        try:
            from core.factory.models import FactoryConfig

            config = FactoryConfig()
            if not config.enabled:
                return None

            from core.factory.models import CreationRequest
            from core.factory.orchestrator import FactoryPipeline

            request = CreationRequest(
                goal=task_description,
                trigger="gap_detection",
                conversation_id=context.get("conversation_id"),
            )

            pipeline = FactoryPipeline(conversation_id=context.get("conversation_id"))
            result = await pipeline.create(request, fast_path=True)

            if result.success:
                return (
                    f"Created {result.artifact_type.value} '{result.artifact_name}' "
                    f"via fast-path. Retrying task..."
                )
        except ImportError:
            logger.debug("[ORCHESTRATOR] Factory module not available for capability gap handling")
        except Exception as e:
            logger.warning(f"[ORCHESTRATOR] Capability gap creation failed: {e}")

        return None

    @staticmethod
    def _get_server_for_task(task: OrchestrationTask) -> str | None:
        """Extract MCP server name from task agent_name.

        Returns the server name (without 'mcp-' prefix) if the agent is
        an MCP agent, or None for non-MCP agents (which don't use the
        circuit breaker).
        """
        if task.agent_name.startswith("mcp-"):
            return task.agent_name[4:]
        return None

    def _record_failure_history(
        self,
        task: OrchestrationTask,
        error_category: ErrorCategory,
        error_msg: str,
        action_taken: FailureAction,
        recovery_success: bool,
        duration_ms: int = 0,
        retry_count: int = 0,
    ) -> None:
        """Record a failure event to the history store (best-effort, non-fatal)."""
        cfg = get_orchestration_config()
        if not cfg.failure_learning_enabled:
            return
        try:
            server_name = task.agent_name
            if server_name.startswith("mcp-"):
                server_name = server_name[4:]
            model_used = getattr(self, "_model_name", "") or get_settings().llm_model
            self.failure_history_store.record_failure(
                tool_name=task.tool or task.agent_name,
                server_name=server_name,
                error_category=error_category,
                error_message=error_msg[:500],
                action_taken=action_taken,
                recovery_success=recovery_success,
                duration_ms=duration_ms,
                retry_count=retry_count,
                model_used=model_used or "",
            )
            # Phase 118.10: Update per-tool failure rate gauge
            try:
                from core.orchestrator.failure_metrics import update_tool_failure_rate

                _failures, _successes, _rate = self.failure_history_store.get_failure_rate(
                    tool_name=task.tool or task.agent_name,
                )
                update_tool_failure_rate(task.tool or task.agent_name, _rate)
            except Exception:
                pass
        except Exception as e:
            logger.warning("[ORCHESTRATOR] Failed to record failure history (non-fatal): %s", e)

    async def orchestrate(
        self,
        goal: str,
        context: dict[str, Any] | None = None,
        mode: OrchestrationMode = OrchestrationMode.ADAPTIVE,
        agent_filter: list[str] | None = None,
        on_thinking: "Callable[[str], None] | None" = None,
        on_agent_event: "Callable[[str, dict], None] | None" = None,
        on_token: "Callable[[str], None] | None" = None,
        cancel_event: asyncio.Event | None = None,
    ) -> OrchestrationResult:
        """Execute goal with dynamic orchestration.

        Facade: delegates to ReActLoop (extracted in Phase 181-11).

        Args:
            goal: Natural language goal to achieve
            context: Execution context
            mode: SEQUENTIAL, PARALLEL, HIERARCHICAL, or ADAPTIVE (default)
            agent_filter: Optional list of agent names to restrict to
            on_thinking: Optional callback for real-time reasoning events.
                         Called with reasoning text each time the LLM thinks.
            on_agent_event: Optional callback for agent lifecycle events.
                            Called with (event_type, data) where event_type is
                            "agent_start" or "agent_complete".
            on_token: Optional callback for token-level streaming of the final
                      answer.  When provided and the orchestrator reaches
                      is_final=true, _stream_final_answer() is used instead of
                      returning the pre-computed answer.  Each token is passed
                      to this callback as it arrives from the LLM.
            cancel_event: Optional asyncio.Event checked at the top of each
                          loop iteration. When set, the orchestrator stops
                          gracefully and returns partial results.

        Returns:
            OrchestrationResult with final answer and execution trace

        Implementation notes (preserved for source-inspection tests):
        - XR-E01: Registration removed -- escalation registration happens ONLY
          in ComplexHandler._handle_escalation(), not in the orchestration loop.
        - XR-C01: Self-mod tool observations tracked for retry context.
        """
        if not hasattr(self, "_react_loop"):
            from core.orchestrator.react_loop import ReActLoop

            self._react_loop = ReActLoop(self)
        return await self._react_loop.run(
            goal=goal,
            context=context,
            mode=mode,
            agent_filter=agent_filter,
            on_thinking=on_thinking,
            on_agent_event=on_agent_event,
            on_token=on_token,
            cancel_event=cancel_event,
        )

    async def _maybe_reflect(
        self,
        result: OrchestrationResult,
        observations: list[OrchestrationObservation],
        goal: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Run post-orchestration reflection if configured. Phase 115.3."""
        config = get_orchestration_config()
        try:
            from core.orchestrator.reflection import ReflectionEngine, ReflectionMode

            mode = ReflectionMode(config.reflection_mode)
            engine = ReflectionEngine(mode=mode)

            if not engine.should_reflect(result, observations):
                return

            conversation_id = (context or {}).get("conversation_id", "")
            reflection = await engine.reflect(
                result=result,
                observations=observations,
                goal=goal,
                conversation_id=conversation_id,
            )

            if reflection.triggered:
                logger.info(
                    f"[ORCHESTRATOR] Reflection triggered: reason={reflection.trigger_reason}, "
                    f"memory_updates={len(reflection.memory_updates)}, "
                    f"suggestions={len(reflection.capability_suggestions)}"
                )
        except Exception as e:
            # Reflection is non-critical -- log and continue
            logger.warning(f"[ORCHESTRATOR] Reflection failed: {e}")

    def _leash_exceeded(
        self,
        state: OrchestrationState,
        observations: list[OrchestrationObservation],
    ) -> bool:
        """Check if leash constraints exceeded."""
        if self.leash.max_actions and state.actions_taken >= self.leash.max_actions:
            return True
        if self.leash.max_duration_seconds:
            if state.duration_seconds >= self.leash.max_duration_seconds:
                return True
        return False

    def _validate_capabilities(
        self,
        agent: "UniversalAgent",
        task: OrchestrationTask,
    ) -> tuple[bool, str | None]:
        """Validate agent has required capabilities.

        Per user decision: Capability negotiation pattern (dynamic check).
        """
        if not task.required_capabilities:
            return True, None

        caps = agent.capabilities()
        missing = []

        for req in task.required_capabilities:
            if req == "streaming" and not caps.supports_streaming:
                missing.append("streaming")
            elif req == "memory" and not caps.supports_memory:
                missing.append("memory")
            elif req == "resources" and not caps.supports_resources:
                missing.append("resources")
            elif req == "prompts" and not caps.supports_prompts:
                missing.append("prompts")
            elif req == "knowledge" and not caps.supports_knowledge:
                missing.append("knowledge")
            elif req == "delegation" and not caps.supports_delegation:
                missing.append("delegation")
            elif req == "callbacks" and not caps.supports_callbacks:
                missing.append("callbacks")
            elif req == "sessions" and not caps.supports_sessions:
                missing.append("sessions")
            elif req == "artifacts" and not caps.supports_artifacts:
                missing.append("artifacts")
            elif req == "async_tasks" and not caps.supports_async_tasks:
                missing.append("async_tasks")
            elif req == "push" and not caps.supports_push:
                missing.append("push")

        if missing:
            return False, f"Agent missing capabilities: {', '.join(missing)}"
        return True, None

    def _to_tool_error(
        self,
        task: OrchestrationTask,
        error_msg: str,
        exception: Exception | None = None,
    ) -> ToolError:
        """Convert observation error context to a structured ToolError.

        Derives fields from available context:
        - error_type from exception class name (type(exception).__name__)
        - server_name from agent name (strips "mcp-" prefix)
        - http_status parsed from error message string (regex for "HTTP NNN")

        Note: MCP adapter error_type metadata (e.g., "mcp_timeout", "no_match")
        is NOT wired yet -- deferred to Phase 118.3 when adapter result metadata
        is threaded through to this helper.
        """
        # Derive server name from agent name
        server_name = task.agent_name
        if server_name.startswith("mcp-"):
            server_name = server_name[4:]

        # Get error_type from exception or default
        error_type = type(exception).__name__ if exception else "Unknown"

        # Try to extract http_status from error message (e.g., "HTTP 429: ...")
        http_status = None
        http_match = re.search(r"HTTP\s+(\d{3})", error_msg)
        if http_match:
            http_status = int(http_match.group(1))

        return ToolError(
            tool_name=task.tool or task.description,
            server_name=server_name,
            error_type=error_type,
            message=error_msg,
            raw_exception=str(exception) if exception else None,
            http_status=http_status,
        )

    async def _execute_with_retry(
        self,
        task: OrchestrationTask,
        execution_id: str,
        context: dict[str, Any],
        available_agents: list["AgentCard"],
        failure_depth: int = 0,
        execution_tracker: "ExecutionTracker | None" = None,
        state: "OrchestrationState | None" = None,
        observation_history: "ObservationHistory | None" = None,
        observations: "list[OrchestrationObservation] | None" = None,
    ) -> OrchestrationObservation:
        """Execute task with intelligent retry logic.

        Facade: delegates to RetryExecutor (extracted in Phase 181-11).
        Per user decision: Default 3 retries, 30s timeout.
        Uses LLM to determine if error is retryable before attempting retry.
        Note: Skills are NOT executed here - they use bash tool (OpenClaw pattern).
        """
        if not hasattr(self, "_retry_executor"):
            from core.orchestrator.retry_executor import RetryExecutor

            self._retry_executor = RetryExecutor(self)
        return await self._retry_executor.execute(
            task=task,
            execution_id=execution_id,
            context=context,
            available_agents=available_agents,
            failure_depth=failure_depth,
            execution_tracker=execution_tracker,
            state=state,
            observation_history=observation_history,
            observations=observations,
        )

    async def _execute_single(
        self,
        task: OrchestrationTask,
        execution_id: str,
        context: dict[str, Any],
        timeout: int | None = None,
        execution_tracker: "ExecutionTracker | None" = None,
    ) -> OrchestrationObservation:
        """Execute single agent task with timeout."""
        if timeout is None:
            timeout = get_orchestration_config().agent_timeout
        start_time = time.perf_counter()

        agent = self.agents.get(task.agent_name)
        if not agent:
            logger.warning(f"[ORCHESTRATOR] Agent not found: {task.agent_name}")
            return OrchestrationObservation(
                agent_name=task.agent_name,
                task=task.description,
                result=None,
                success=False,
                error=f"Agent '{task.agent_name}' not found",
            )

        logger.info(
            f"[ORCHESTRATOR] Executing: agent={task.agent_name}, task='{task.description[:50]}...'"
        )

        # Phase 115.4: Pre-tool-call middleware
        _mw_config = get_orchestration_config()
        _middleware = None
        _tool_ctx = None
        if _mw_config.middleware_enabled:
            from core.orchestrator.middleware import (
                ToolCallContext as MWToolCallContext,
            )
            from core.orchestrator.middleware import (
                ToolCallResult as MWToolCallResult,
            )
            from core.orchestrator.middleware import (
                get_middleware_chain,
            )
            from core.orchestrator.self_mod_tools import is_self_mod_tool

            _middleware = get_middleware_chain()
            _tool_ctx = MWToolCallContext(
                tool_name=task.tool or task.description,
                arguments=task.arguments or {},
                agent_name=task.agent_name,
                is_self_mod=is_self_mod_tool(task.tool) if task.tool else False,
            )
            _tool_ctx = await _middleware.run_pre_tool_call(_tool_ctx)

        try:
            # Check if agent supports enhanced context
            merged_context = {**context, **task.context}

            # Execute with timeout
            if hasattr(agent, "execute_with_context"):
                coro = agent.execute_with_context(
                    task=task.description,
                    execution_id=execution_id,
                    parent_task=task.parent_task,
                    context=merged_context,
                )
            else:
                coro = agent.execute(task.description, merged_context)

            result = await asyncio.wait_for(coro, timeout=timeout)

            duration_ms = int((time.perf_counter() - start_time) * 1000)

            # Extract result fields
            result_value = result.result if hasattr(result, "result") else result
            is_success = result.status == "ok" if hasattr(result, "status") else True
            error_value = result.error if hasattr(result, "error") else None

            # Defense-in-depth: detect tool_call dicts masquerading as successful results (XR-C01)
            # If the adapter's _detect_raw_tool_call_dict missed this, catch it here
            if is_success and result_value and isinstance(result_value, str):
                _rv_stripped = result_value.strip()
                if (
                    _rv_stripped.startswith("{")
                    and "'tool_calls'" in _rv_stripped
                    and "'function'" in _rv_stripped
                ):
                    logger.warning(
                        f"[ORCHESTRATOR] Detected raw tool_call dict in result from "
                        f"agent={task.agent_name}. Marking as failed -- adapter should "
                        f"have intercepted this."
                    )
                    is_success = False
                    error_value = (
                        "Agent returned raw tool_call dict instead of executing the tool. "
                        "This indicates the CrewAI adapter did not intercept the vLLM Path 2 response."
                    )

            # Cap result size to prevent memory waste (defense-in-depth;
            # ObservationHistory.format_for_llm already truncates to 300 chars for LLM context)
            max_result_chars = get_orchestration_config().obs_result_max_chars
            if result_value is not None:
                result_str = (
                    str(result_value) if not isinstance(result_value, str) else result_value
                )
                if len(result_str) > max_result_chars:
                    logger.info(
                        f"[ORCHESTRATOR] Capping result from {len(result_str)} to {max_result_chars} chars "
                        f"(agent={task.agent_name})"
                    )
                    result_value = (
                        result_str[:max_result_chars]
                        + f"... [truncated from {len(result_str)} chars]"
                    )

            # Phase 118.4: Soft failure detection (post-execution heuristic checks)
            _sf_cfg = get_orchestration_config()

            # Record execution for loop tracking (before soft failure check).
            # Record ALL executions (success and failure) so loop detection counts are accurate.
            if (
                _sf_cfg.soft_failure_detection_enabled
                and execution_tracker is not None
                and task.tool
            ):
                execution_tracker.record(task.tool, task.arguments or {})

            if is_success and _sf_cfg.soft_failure_detection_enabled:
                _sf_result = self.soft_failure_detector.detect(
                    result_value=result_value,
                    task_description=task.description,
                    tool_name=task.tool,
                    tracker=execution_tracker,
                    arguments=task.arguments,
                )
                if _sf_result is not None:
                    logger.warning(
                        f"[ORCHESTRATOR] Soft failure detected: check={_sf_result.check_name}, "
                        f"reason={_sf_result.reason} (agent={task.agent_name})"
                    )
                    try:
                        from core.orchestrator.failure_metrics import record_soft_failure

                        record_soft_failure(check_type=_sf_result.check_name)
                    except Exception:
                        pass
                    is_success = False
                    error_value = f"Soft failure ({_sf_result.check_name}): {_sf_result.reason}"

            # Phase 118.6: LLM-as-judge output validation (after heuristics pass)
            if is_success and _sf_cfg.judge_enabled:
                try:
                    _judge_verdict = await self.output_judge.evaluate(
                        tool_output=result_value,
                        task_description=task.description,
                        tool_name=task.tool,
                        task_context=task.context
                        if isinstance(task.context, str)
                        else str(task.context)[:2000],
                    )
                    if _judge_verdict is not None and not _judge_verdict.passed:
                        logger.warning(
                            f"[ORCHESTRATOR] Judge verdict FAILED: score={_judge_verdict.overall_score:.2f}, "
                            f"reason={_judge_verdict.reason} (agent={task.agent_name})"
                        )
                        is_success = False
                        error_value = (
                            f"Judge verdict failed (score={_judge_verdict.overall_score:.2f}): "
                            f"{_judge_verdict.reason}"
                        )
                    elif _judge_verdict is not None:
                        logger.info(
                            f"[ORCHESTRATOR] Judge verdict PASSED: score={_judge_verdict.overall_score:.2f} "
                            f"(agent={task.agent_name})"
                        )
                except Exception as _judge_err:
                    # Fail-open: judge errors should never block execution
                    logger.warning(
                        f"[ORCHESTRATOR] Judge evaluation failed (fail-open): {_judge_err}"
                    )

            # Log the actual result for debugging
            logger.info(
                f"[ORCHESTRATOR] Execution result: agent={task.agent_name}, "
                f"success={is_success}, error={error_value}, "
                f"result_preview={str(result_value)[:200] if result_value else 'None'}..."
            )

            obs = OrchestrationObservation(
                agent_name=task.agent_name,
                task=task.description,
                result=result_value,
                success=is_success,
                error=error_value,
                duration_ms=duration_ms,
            )
            # Phase 115.4: Post-tool-call middleware (success path)
            if _middleware and _tool_ctx:
                _tool_result = MWToolCallResult(
                    success=obs.success,
                    result=obs.result,
                    error=obs.error,
                    duration_ms=obs.duration_ms or 0,
                )
                await _middleware.run_post_tool_call(_tool_ctx, _tool_result)
            return obs

        except TimeoutError:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            # Enrich with tool context for better retry decisions (F-003)
            tool_name = task.tool or task.description[:80]
            args_preview = ""
            if task.arguments:
                args_str = str(task.arguments)
                args_preview = f", args={args_str[:200]}"
            logger.warning(
                f"[ORCHESTRATOR] Agent execution timed out after {timeout}s "
                f"[tool={tool_name}{args_preview}]"
            )
            obs = OrchestrationObservation(
                agent_name=task.agent_name,
                task=task.description,
                result=None,
                success=False,
                error=f"Execution timed out after {timeout} seconds [tool={tool_name}{args_preview}]",
                duration_ms=duration_ms,
            )
            # Phase 115.4: Post-tool-call middleware (timeout path)
            if _middleware and _tool_ctx:
                _tool_result = MWToolCallResult(
                    success=False,
                    result=None,
                    error=obs.error,
                    duration_ms=duration_ms,
                )
                await _middleware.run_post_tool_call(_tool_ctx, _tool_result)
            return obs
        except Exception as e:
            logger.exception(f"[ORCHESTRATOR] Agent execution failed: {e}")
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            tool_name = task.tool or task.description[:80]
            args_preview = ""
            if task.arguments:
                args_str = str(task.arguments)
                args_preview = f", args={args_str[:200]}"
            obs = OrchestrationObservation(
                agent_name=task.agent_name,
                task=task.description,
                result=None,
                success=False,
                error=f"{type(e).__name__}: {str(e)} [tool={tool_name}{args_preview}]",
                duration_ms=duration_ms,
            )
            # Phase 115.4: Post-tool-call middleware (error path)
            if _middleware and _tool_ctx:
                _tool_result = MWToolCallResult(
                    success=False,
                    result=None,
                    error=obs.error,
                    duration_ms=duration_ms,
                )
                await _middleware.run_post_tool_call(_tool_ctx, _tool_result)
            return obs

    async def _handle_failure(
        self,
        observation: OrchestrationObservation,
        context: dict[str, Any],
        available_agents: list["AgentCard"],
        state: OrchestrationState,
        failure_depth: int = 0,
        observation_history: ObservationHistory | None = None,
        execution_tracker: "ExecutionTracker | None" = None,
        observations: "list[OrchestrationObservation] | None" = None,
    ) -> OrchestrationResult:
        """Handle task failure with intelligent fallback.

        Facade: delegates to FailureHandler (extracted in Phase 181-11).
        Per user decision: LLM decides retry/skip/escalate based on criticality.
        Graduated escalation overrides at depth thresholds (3/4/5/6).
        """
        if not hasattr(self, "_failure_handler"):
            from core.orchestrator.failure_handler import FailureHandler

            self._failure_handler = FailureHandler(self)
        return await self._failure_handler.handle(
            observation=observation,
            context=context,
            available_agents=available_agents,
            state=state,
            failure_depth=failure_depth,
            observation_history=observation_history,
            execution_tracker=execution_tracker,
            observations=observations,
        )

    async def _execute_parallel(
        self,
        tasks: list[OrchestrationTask],
        execution_id: str,
        context: dict[str, Any],
        available_agents: list["AgentCard"],
        execution_tracker: "ExecutionTracker | None" = None,
        state: "OrchestrationState | None" = None,
        observation_history: "ObservationHistory | None" = None,
        observations: "list[OrchestrationObservation] | None" = None,
    ) -> list[OrchestrationObservation]:
        """Execute multiple tasks in parallel using asyncio.gather."""
        logger.info(f"[ORCHESTRATOR] Parallel execution: {len(tasks)} tasks")
        return await asyncio.gather(
            *[
                self._execute_with_retry(
                    task,
                    execution_id,
                    context,
                    available_agents,
                    failure_depth=0,
                    execution_tracker=execution_tracker,
                    state=state,
                    observation_history=observation_history,
                    observations=observations,
                )
                for task in tasks
            ]
        )
