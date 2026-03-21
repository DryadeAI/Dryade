"""LangGraph Delegation Adapter.

Wraps a LangGraph CompiledStateGraph as a single UniversalAgent.execute()
call with state passing, checkpointing, and node-level event streaming.

The graph executes as one orchestration step.  State flows between nodes
internally; Dryade treats the whole graph as an atomic delegation target.

IMPORTANT PITFALL:
    Never use a synchronous checkpointer (e.g. SqliteSaver) with ainvoke().
    It will deadlock the async event loop (LangGraph issue #1800).
    InMemorySaver is safe for both sync and async execution.

Target: ~180 LOC
"""

import logging
import time
from collections.abc import AsyncIterator, Callable
from typing import Any
from uuid import uuid4

from core.adapters.protocol import (
    AgentCapabilities,
    AgentCard,
    AgentFramework,
    AgentResult,
    UniversalAgent,
)

logger = logging.getLogger("dryade.adapter.langgraph_delegation")

# ---- Import-guarded LangGraph types ----------------------------------------
# The adapter MUST be importable even when langgraph is not installed.
_LANGGRAPH_AVAILABLE = False
_InMemorySaver: type | None = None

try:
    from langgraph.checkpoint.memory import (
        InMemorySaver as _InMemorySaver,  # type: ignore[assignment]
    )

    _LANGGRAPH_AVAILABLE = True
except ImportError:
    pass

class LangGraphDelegationAdapter(UniversalAgent):
    """Wrap a LangGraph CompiledStateGraph as a single UniversalAgent.

    Enables the orchestrator to delegate to a LangGraph state graph where
    typed state flows between nodes.  Supports checkpoint-based resume
    via thread_id and node-level SSE streaming.

    Usage::

        from langgraph.graph import StateGraph
        graph = build_my_graph()          # returns CompiledStateGraph
        adapter = LangGraphDelegationAdapter(
            graph=graph,
            name="research-pipeline",
            description="Multi-step research graph",
        )
        result = await adapter.execute("Analyse market trends")
    """

    def __init__(
        self,
        graph: Any,
        name: str,
        description: str,
        checkpointer: Any | None = None,
        sse_emitter: Callable[[dict[str, Any]], None] | None = None,
    ):
        """Initialise with a LangGraph CompiledStateGraph.

        Args:
            graph: CompiledStateGraph instance (typed as Any for import-guard)
            name: Identifier for this delegation unit
            description: What the graph does
            checkpointer: Optional checkpointer.  If *None* and langgraph is
                available, InMemorySaver is used as safe async-compatible default.
            sse_emitter: Optional callback receiving ``{"type", "node", "data"}``
                dicts for each node-level update during streaming execution.
        """
        self._name = name
        self._description = description
        self._sse_emitter = sse_emitter

        # Resolve checkpointer --------------------------------------------------
        if checkpointer is not None:
            self._checkpointer = checkpointer
        elif _LANGGRAPH_AVAILABLE and _InMemorySaver is not None:
            self._checkpointer = _InMemorySaver()
        else:
            self._checkpointer = None

        # If a checkpointer is available, try to recompile the graph with it.
        # CompiledStateGraphs keep a reference to their builder, so
        # ``graph.builder.compile(checkpointer=...)`` returns a new compiled
        # graph with checkpoint support.  If the graph does not expose a
        # builder (e.g. already compiled without one), fall back gracefully.
        if self._checkpointer is not None and hasattr(graph, "builder"):
            try:
                self._graph = graph.builder.compile(checkpointer=self._checkpointer)
                logger.debug(
                    "Recompiled graph '%s' with checkpointer %s",
                    name,
                    type(self._checkpointer).__name__,
                )
            except Exception:
                logger.warning(
                    "Could not recompile graph '%s' with checkpointer; using graph as-is",
                    name,
                    exc_info=True,
                )
                self._graph = graph
        else:
            self._graph = graph

    # -- UniversalAgent interface -----------------------------------------------

    def get_card(self) -> AgentCard:
        """Return agent discovery card."""
        return AgentCard(
            name=self._name,
            description=self._description,
            version="1.0",
            framework=AgentFramework.LANGCHAIN,
            metadata={
                "is_langgraph": True,
                "has_checkpointer": self._checkpointer is not None,
                "delegation": True,
            },
        )

    async def execute(self, task: str, context: dict[str, Any] | None = None) -> AgentResult:
        """Execute the graph as a single orchestration step.

        Args:
            task: Natural language task description
            context: Optional dict merged into the initial state.  May contain
                ``thread_id`` for checkpoint resume.

        Returns:
            AgentResult with graph output and execution metadata.
        """
        if not _LANGGRAPH_AVAILABLE:
            return AgentResult(
                result=None,
                status="error",
                error="langgraph is not installed",
                metadata={"framework": "langgraph", "agent": self._name},
            )

        start = time.time()
        ctx = context or {}
        thread_id = ctx.pop("thread_id", None) or str(uuid4())
        config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
        initial_state: dict[str, Any] = {"input": task, **ctx}

        try:
            if self._sse_emitter is not None:
                result, nodes_executed = await self._execute_streaming(initial_state, config)
            else:
                result = await self._graph.ainvoke(initial_state, config=config)
                nodes_executed = None

            execution_time_ms = (time.time() - start) * 1000

            metadata: dict[str, Any] = {
                "framework": "langgraph",
                "agent": self._name,
                "thread_id": thread_id,
                "delegation": True,
                "execution_time_ms": execution_time_ms,
            }
            if nodes_executed is not None:
                metadata["nodes_executed"] = nodes_executed

            return AgentResult(result=result, status="ok", metadata=metadata)

        except Exception as e:
            execution_time_ms = (time.time() - start) * 1000
            logger.exception("LangGraph execution failed for '%s': %s", self._name, e)
            return AgentResult(
                result=None,
                status="error",
                error=f"Graph execution failed: {type(e).__name__}",
                metadata={
                    "framework": "langgraph",
                    "agent": self._name,
                    "thread_id": thread_id,
                    "delegation": True,
                    "execution_time_ms": execution_time_ms,
                },
            )

    def get_tools(self) -> list[dict[str, Any]]:
        """Return empty list -- graph handles tools internally."""
        return []

    def supports_streaming(self) -> bool:
        """LangGraph graphs always support streaming via astream."""
        return True

    async def execute_stream(
        self, task: str, context: dict[str, Any] | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield node-level updates via ``graph.astream(stream_mode="updates")``.

        Each yielded dict has ``{"node": <name>, "data": <update>}``.
        """
        if not _LANGGRAPH_AVAILABLE:
            return

        ctx = context or {}
        thread_id = ctx.pop("thread_id", None) or str(uuid4())
        config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
        initial_state: dict[str, Any] = {"input": task, **ctx}

        async for update in self._graph.astream(
            initial_state, config=config, stream_mode="updates"
        ):
            for node_name, node_data in update.items():
                yield {"node": node_name, "data": node_data}

    def capabilities(self) -> AgentCapabilities:
        """Return LangGraph-specific capabilities."""
        return AgentCapabilities(
            supports_streaming=True,
            supports_delegation=True,
            supports_callbacks=True,
            framework_specific={
                "is_langgraph": True,
                "has_checkpointer": self._checkpointer is not None,
                "supports_delegation": True,
            },
        )

    # -- Internal helpers -------------------------------------------------------

    async def _execute_streaming(
        self,
        initial_state: dict[str, Any],
        config: dict[str, Any],
    ) -> tuple[Any, list[str]]:
        """Stream node updates and emit SSE events.

        Returns:
            A tuple of (final_state, list_of_node_names_executed).
        """
        nodes_executed: list[str] = []
        last_state: Any = None

        async for update in self._graph.astream(
            initial_state, config=config, stream_mode="updates"
        ):
            for node_name, node_data in update.items():
                nodes_executed.append(node_name)
                last_state = node_data

                if self._sse_emitter is not None:
                    self._sse_emitter(
                        {
                            "type": "agent_progress",
                            "node": node_name,
                            "data": node_data,
                        }
                    )

        return last_state, nodes_executed
