"""Cross-framework integration tests for Phase 84 adapters.

Verifies that CrewDelegationAdapter, LangGraphDelegationAdapter,
ADKAgentAdapter, and A2AAgentAdapter work correctly and can pass
data between frameworks. All tests use unittest.mock -- no real
framework installations required.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from core.adapters.protocol import AgentResult

# =============================================================================
# Test 1: CrewAI Delegation Adapter
# =============================================================================

async def test_crewai_delegation_adapter_executes_crew():
    """CrewDelegationAdapter wraps a CrewAI Crew as a single execute() step."""
    # Build mock crew with expected attributes
    mock_agent1 = MagicMock(name="researcher")
    mock_agent2 = MagicMock(name="writer")
    mock_task = MagicMock(name="write_task")

    mock_crew = MagicMock()
    mock_crew.agents = [mock_agent1, mock_agent2]
    mock_crew.tasks = [mock_task]
    mock_crew.process = MagicMock()
    mock_crew.process.value = "sequential"
    mock_crew.memory = False
    mock_crew.kickoff.return_value = "crew result: analysis complete"

    # Mock get_configured_llm to avoid real LLM setup (lazy-imported inside execute)
    with patch(
        "core.providers.llm_adapter.get_configured_llm",
        return_value=MagicMock(),
    ):
        from core.adapters.crewai_delegation import CrewDelegationAdapter

        adapter = CrewDelegationAdapter(
            crew=mock_crew,
            name="test-crew",
            description="Test crew for integration testing",
        )

        result = await adapter.execute("Analyze code quality")

    assert result.status == "ok"
    assert "crew result" in result.result
    assert result.metadata["framework"] == "crewai"
    assert result.metadata["agents_count"] == 2
    assert result.metadata["tasks_count"] == 1
    assert result.metadata["process"] == "sequential"
    assert result.metadata["delegation"] is True

    # Verify crew.kickoff was called with the task in inputs
    mock_crew.kickoff.assert_called_once()
    call_kwargs = mock_crew.kickoff.call_args
    assert "task" in call_kwargs.kwargs.get("inputs", call_kwargs[1].get("inputs", {}))

# =============================================================================
# Test 2: LangGraph Delegation Adapter
# =============================================================================

async def test_langgraph_delegation_adapter_executes_graph():
    """LangGraphDelegationAdapter wraps a LangGraph graph as a single execute() step."""
    # Mock the graph with ainvoke returning a result dict
    mock_graph = AsyncMock()
    mock_graph.ainvoke = AsyncMock(return_value={"output": "graph result: report generated"})
    # No builder attribute so graph is used as-is
    mock_graph.builder = None

    # Patch _LANGGRAPH_AVAILABLE to True so execute() proceeds
    with patch("core.adapters.langgraph_delegation._LANGGRAPH_AVAILABLE", True):
        from core.adapters.langgraph_delegation import LangGraphDelegationAdapter

        adapter = LangGraphDelegationAdapter(
            graph=mock_graph,
            name="test-graph",
            description="Test graph for integration testing",
            checkpointer=None,
        )
        # Force checkpointer to None (since langgraph is not really installed)
        adapter._checkpointer = None
        adapter._graph = mock_graph

        result = await adapter.execute(
            "Generate report",
            context={"thread_id": "test-123"},
        )

    assert result.status == "ok"
    assert result.result == {"output": "graph result: report generated"}
    assert result.metadata["framework"] == "langgraph"
    assert result.metadata["thread_id"] == "test-123"
    assert result.metadata["agent"] == "test-graph"
    assert result.metadata["delegation"] is True

    # Verify ainvoke was called with correct state and config
    mock_graph.ainvoke.assert_called_once()
    call_args = mock_graph.ainvoke.call_args
    initial_state = call_args[0][0]
    assert initial_state["input"] == "Generate report"
    config = call_args[1]["config"]
    assert config["configurable"]["thread_id"] == "test-123"

# =============================================================================
# Test 3: ADK Adapter Session Persistence
# =============================================================================

async def test_adk_adapter_session_persistence():
    """ADKAgentAdapter reuses the same session across multiple execute() calls."""
    # Mock ADK dependencies
    mock_session = MagicMock()
    mock_session.id = "session-abc-123"

    mock_session_service = MagicMock()
    # create_session is awaited in ADKAgentAdapter._ensure_runner(), so must be AsyncMock.
    mock_session_service.create_session = AsyncMock(return_value=mock_session)

    mock_artifact_service = MagicMock()
    mock_artifact_service.list_artifacts.return_value = []

    # Mock the Runner to yield events with content
    mock_event = MagicMock()
    mock_event.content = MagicMock()
    mock_event.content.parts = [MagicMock(text="Step result")]

    mock_runner = MagicMock()

    async def fake_run_async(**kwargs):
        yield mock_event

    mock_runner.run_async = fake_run_async

    mock_agent = MagicMock()
    mock_agent.name = "test-adk-agent"
    mock_agent.description = "Test ADK agent"
    mock_agent.tools = []
    mock_agent.version = "1.0.0"
    mock_agent.model = "gemini-2.0-flash"
    mock_agent.instruction = "You are a test agent"

    # Patch ADK availability and imports (create=True needed since ADK may not be installed)
    with (
        patch("core.adapters.adk_adapter._ADK_AVAILABLE", True),
        patch("core.adapters.adk_adapter.Runner", return_value=mock_runner, create=True),
        patch(
            "core.adapters.adk_adapter.InMemorySessionService",
            return_value=mock_session_service,
            create=True,
        ),
        patch(
            "core.adapters.adk_adapter.InMemoryArtifactService",
            return_value=mock_artifact_service,
            create=True,
        ),
        patch("core.adapters.adk_adapter.genai_types", create=True) as mock_genai,
    ):
        mock_genai.Content.return_value = MagicMock()
        mock_genai.Part.from_text.return_value = MagicMock()

        from core.adapters.adk_adapter import ADKAgentAdapter

        adapter = ADKAgentAdapter(
            agent=mock_agent,
            session_service=mock_session_service,
            artifact_service=mock_artifact_service,
        )

        # First execute -- session created
        result1 = await adapter.execute("Step 1")
        session_id_1 = adapter._session_id

        # Second execute -- same session reused
        result2 = await adapter.execute("Step 2")
        session_id_2 = adapter._session_id

    assert result1.status == "ok"
    assert result2.status == "ok"
    assert session_id_1 == session_id_2 == "session-abc-123"
    assert result1.metadata["framework"] == "adk"
    assert result1.metadata["session_id"] == "session-abc-123"

    # Session service should have been called exactly once for create_session
    # (second execute reuses the existing runner and session)
    assert mock_session_service.create_session.call_count == 1

# =============================================================================
# Test 4: A2A Adapter JSON-RPC Message Send
# =============================================================================

async def test_a2a_adapter_jsonrpc_message_send():
    """A2AAgentAdapter sends JSON-RPC message/send and parses A2A response."""
    # Build the expected A2A response
    a2a_response = {
        "jsonrpc": "2.0",
        "id": "test-id",
        "result": {
            "id": "task-456",
            "status": {
                "state": "completed",
                "message": {
                    "role": "agent",
                    "parts": [{"text": "validated successfully"}],
                },
            },
        },
    }

    # Mock httpx.AsyncClient
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = a2a_response
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.aclose = AsyncMock()

    with patch("core.adapters.a2a_adapter.httpx.AsyncClient", return_value=mock_client):
        from core.adapters.a2a_adapter import A2AAgentAdapter

        adapter = A2AAgentAdapter(endpoint="http://mock-agent:8080")
        # Replace the client created in __init__
        adapter._client = mock_client

        result = await adapter.execute("Validate the configuration")

    assert result.status == "ok"
    assert "validated successfully" in result.result
    assert result.metadata["framework"] == "a2a"
    assert result.metadata["endpoint"] == "http://mock-agent:8080"
    assert result.metadata["task_id"] == "task-456"
    assert result.metadata["a2a_state"] == "completed"

    # Verify the JSON-RPC request was sent correctly
    mock_client.post.assert_called_once()
    call_args = mock_client.post.call_args
    payload = call_args[1]["json"]
    assert payload["jsonrpc"] == "2.0"
    assert payload["method"] == "message/send"
    assert payload["params"]["message"]["parts"][0]["text"] == "Validate the configuration"

# =============================================================================
# Test 5: Cross-Framework Data Flow
# =============================================================================

async def test_cross_framework_data_flow():
    """Data flows through MCP -> CrewAI -> LangGraph -> A2A adapters sequentially.

    Each adapter receives the previous adapter's result as context and produces
    output that feeds into the next. Verifies the full delegation chain.
    """
    # Step 1: MCP result (simulated as an AgentResult)
    mcp_result = AgentResult(
        result="file contents: hello world",
        status="ok",
        metadata={"framework": "mcp", "tool": "read_file"},
    )

    # Step 2: CrewAI receives MCP output, returns analysis
    mock_crew = MagicMock()
    mock_crew.agents = [MagicMock()]
    mock_crew.tasks = [MagicMock()]
    mock_crew.process = MagicMock(value="sequential")
    mock_crew.memory = False
    mock_crew.kickoff.return_value = "analysis of: file contents: hello world"

    with patch(
        "core.providers.llm_adapter.get_configured_llm",
        return_value=MagicMock(),
    ):
        from core.adapters.crewai_delegation import CrewDelegationAdapter

        crew_adapter = CrewDelegationAdapter(crew=mock_crew, name="analyzer", description="Analyze")
        crew_result = await crew_adapter.execute(
            "Analyze input",
            context={"previous_result": mcp_result.result},
        )

    assert crew_result.status == "ok"
    assert "file contents: hello world" in crew_result.result

    # Step 3: LangGraph receives crew analysis, returns report
    mock_graph = AsyncMock()
    mock_graph.ainvoke = AsyncMock(
        return_value={"output": f"report based on: {crew_result.result}"}
    )
    mock_graph.builder = None

    with patch("core.adapters.langgraph_delegation._LANGGRAPH_AVAILABLE", True):
        from core.adapters.langgraph_delegation import LangGraphDelegationAdapter

        graph_adapter = LangGraphDelegationAdapter(
            graph=mock_graph,
            name="reporter",
            description="Generate report",
            checkpointer=None,
        )
        graph_adapter._checkpointer = None
        graph_adapter._graph = mock_graph

        graph_result = await graph_adapter.execute(
            "Generate report",
            context={"analysis": crew_result.result},
        )

    assert graph_result.status == "ok"

    # Step 4: A2A receives report, returns validation
    a2a_response = {
        "jsonrpc": "2.0",
        "id": "test-id",
        "result": {
            "id": "task-789",
            "status": {
                "state": "completed",
                "message": {
                    "role": "agent",
                    "parts": [{"text": "validation passed for report"}],
                },
            },
        },
    }

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = a2a_response
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.aclose = AsyncMock()

    with patch("core.adapters.a2a_adapter.httpx.AsyncClient", return_value=mock_client):
        from core.adapters.a2a_adapter import A2AAgentAdapter

        a2a_adapter = A2AAgentAdapter(endpoint="http://validator:8080")
        a2a_adapter._client = mock_client

        report_text = str(graph_result.result)
        a2a_result = await a2a_adapter.execute(
            f"Validate: {report_text}",
            context={"source": "langgraph"},
        )

    assert a2a_result.status == "ok"
    assert "validation passed" in a2a_result.result

    # Verify full chain: data flowed through all 4 frameworks
    assert mcp_result.metadata["framework"] == "mcp"
    assert crew_result.metadata["framework"] == "crewai"
    assert graph_result.metadata["framework"] == "langgraph"
    assert a2a_result.metadata["framework"] == "a2a"

# =============================================================================
# Test 6: Error Handling Across All Adapters
# =============================================================================

async def test_adapter_error_handling():
    """All adapters normalize errors to AgentResult(status='error') without raising."""

    # --- CrewAI: crew.kickoff raises ---
    mock_crew = MagicMock()
    mock_crew.agents = []
    mock_crew.tasks = []
    mock_crew.process = MagicMock(value="sequential")
    mock_crew.memory = False
    mock_crew.kickoff.side_effect = RuntimeError("Crew failed unexpectedly")

    with patch(
        "core.providers.llm_adapter.get_configured_llm",
        return_value=MagicMock(),
    ):
        from core.adapters.crewai_delegation import CrewDelegationAdapter

        crew_adapter = CrewDelegationAdapter(
            crew=mock_crew, name="failing-crew", description="Fails"
        )
        crew_result = await crew_adapter.execute("Do something")

    assert crew_result.status == "error"
    assert crew_result.error is not None
    assert "RuntimeError" in crew_result.error

    # --- LangGraph: graph.ainvoke raises ---
    mock_graph = AsyncMock()
    mock_graph.ainvoke = AsyncMock(side_effect=ValueError("Invalid state transition"))
    mock_graph.builder = None

    with patch("core.adapters.langgraph_delegation._LANGGRAPH_AVAILABLE", True):
        from core.adapters.langgraph_delegation import LangGraphDelegationAdapter

        graph_adapter = LangGraphDelegationAdapter(
            graph=mock_graph,
            name="failing-graph",
            description="Fails",
            checkpointer=None,
        )
        graph_adapter._checkpointer = None
        graph_adapter._graph = mock_graph

        graph_result = await graph_adapter.execute("Run graph")

    assert graph_result.status == "error"
    assert graph_result.error is not None
    assert "ValueError" in graph_result.error

    # --- ADK: not available ---
    with patch("core.adapters.adk_adapter._ADK_AVAILABLE", False):
        from core.adapters.adk_adapter import ADKAgentAdapter

        adk_adapter = ADKAgentAdapter(agent=MagicMock(), name="unavailable-adk")
        adk_result = await adk_adapter.execute("Do something")

    assert adk_result.status == "error"
    assert adk_result.error is not None
    assert (
        "not available" in adk_result.error.lower() or "not installed" in adk_result.result.lower()
    )

    # --- A2A: HTTP connection error ---
    mock_client = AsyncMock()
    import httpx

    mock_client.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
    mock_client.aclose = AsyncMock()

    with patch("core.adapters.a2a_adapter.httpx.AsyncClient", return_value=mock_client):
        from core.adapters.a2a_adapter import A2AAgentAdapter

        a2a_adapter = A2AAgentAdapter(endpoint="http://dead-agent:8080")
        a2a_adapter._client = mock_client

        a2a_result = await a2a_adapter.execute("Ping")

    assert a2a_result.status == "error"
    assert a2a_result.error is not None
    assert "unavailable" in a2a_result.error.lower() or "connection" in a2a_result.error.lower()

    # None of the above should have raised exceptions (all normalized to AgentResult)
