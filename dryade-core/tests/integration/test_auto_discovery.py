"""Auto-discovery integration tests for Phase 84.

Verifies that AgentAutoDiscovery.detect_framework() correctly identifies
agent frameworks from dryade.json manifests, marker files, and import
patterns. Also tests scan() behavior including skip patterns.

All tests use tmp_path fixture for self-contained temp directories.
"""

import json

from core.adapters.auto_discovery import AgentAutoDiscovery

# =============================================================================
# Test 1: Detect CrewAI from manifest
# =============================================================================

def test_detect_crewai_from_manifest(tmp_path):
    """dryade.json with framework field is authoritative for detection."""
    agent_dir = tmp_path / "test-crew"
    agent_dir.mkdir()
    manifest = {"framework": "crewai", "name": "test-crew", "version": "1.0"}
    (agent_dir / "dryade.json").write_text(json.dumps(manifest))

    discovery = AgentAutoDiscovery(tmp_path)
    result = discovery.detect_framework(agent_dir)

    assert result == "crewai"

# =============================================================================
# Test 2: Detect CrewAI from marker file
# =============================================================================

def test_detect_crewai_from_marker_file(tmp_path):
    """crew.py marker file triggers crewai detection."""
    agent_dir = tmp_path / "my-crew"
    agent_dir.mkdir()
    (agent_dir / "crew.py").write_text("# CrewAI crew definition")

    discovery = AgentAutoDiscovery(tmp_path)
    result = discovery.detect_framework(agent_dir)

    assert result == "crewai"

# =============================================================================
# Test 3: Detect LangChain/LangGraph from imports
# =============================================================================

def test_detect_langchain_from_imports(tmp_path):
    """langgraph import pattern in __init__.py detects as 'langchain'."""
    agent_dir = tmp_path / "graph-agent"
    agent_dir.mkdir()
    (agent_dir / "__init__.py").write_text(
        "from langgraph.graph import StateGraph\n\ndef create_graph():\n    pass\n"
    )

    discovery = AgentAutoDiscovery(tmp_path)
    result = discovery.detect_framework(agent_dir)

    assert result == "langchain"

# =============================================================================
# Test 4: Detect ADK from imports
# =============================================================================

def test_detect_adk_from_imports(tmp_path):
    """google.adk import pattern in __init__.py detects as 'adk'."""
    agent_dir = tmp_path / "adk-agent"
    agent_dir.mkdir()
    (agent_dir / "__init__.py").write_text(
        "from google.adk import Agent\n\nroot_agent = Agent(name='my_agent')\n"
    )

    discovery = AgentAutoDiscovery(tmp_path)
    result = discovery.detect_framework(agent_dir)

    assert result == "adk"

# =============================================================================
# Test 5: Detect custom fallback
# =============================================================================

def test_detect_custom_fallback(tmp_path):
    """Directories with no framework signals fall back to 'custom'."""
    agent_dir = tmp_path / "custom-agent"
    agent_dir.mkdir()
    (agent_dir / "__init__.py").write_text("class MyAgent:\n    def run(self):\n        pass\n")

    discovery = AgentAutoDiscovery(tmp_path)
    result = discovery.detect_framework(agent_dir)

    assert result == "custom"

# =============================================================================
# Test 6: Scan discovers multiple agents
# =============================================================================

def test_scan_discovers_multiple_agents(tmp_path):
    """scan() finds all agent subdirectories and detects their frameworks."""
    # Agent 1: CrewAI via marker file
    crew_dir = tmp_path / "crew_agent"
    crew_dir.mkdir()
    (crew_dir / "crew.py").write_text("# crew")

    # Agent 2: LangGraph via import pattern
    graph_dir = tmp_path / "graph_agent"
    graph_dir.mkdir()
    (graph_dir / "__init__.py").write_text("from langgraph.graph import StateGraph")

    # Agent 3: Custom fallback
    custom_dir = tmp_path / "custom_agent"
    custom_dir.mkdir()
    (custom_dir / "__init__.py").write_text("class MyAgent: pass")

    discovery = AgentAutoDiscovery(tmp_path)
    results = discovery.scan()

    assert len(results) == 3

    # Build a lookup by name for order-independent assertions
    by_name = {r["name"]: r for r in results}

    assert by_name["crew_agent"]["framework"] == "crewai"
    assert by_name["graph_agent"]["framework"] == "langchain"
    assert by_name["custom_agent"]["framework"] == "custom"

    # Each result should have name, path, framework keys
    for r in results:
        assert "name" in r
        assert "path" in r
        assert "framework" in r

# =============================================================================
# Test 7: Scan skips hidden and pycache directories
# =============================================================================

def test_scan_skips_hidden_and_pycache(tmp_path):
    """scan() skips hidden dirs, underscore-prefixed dirs, and __pycache__."""
    # Directories that should be SKIPPED
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "__init__.py").write_text("")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "cache.pyc").write_text("")
    (tmp_path / "_internal").mkdir()
    (tmp_path / "_internal" / "__init__.py").write_text("")

    # Directory that should be FOUND
    valid_dir = tmp_path / "valid_agent"
    valid_dir.mkdir()
    (valid_dir / "__init__.py").write_text("class Agent: pass")

    discovery = AgentAutoDiscovery(tmp_path)
    results = discovery.scan()

    names = [r["name"] for r in results]
    assert names == ["valid_agent"]
    assert ".hidden" not in names
    assert "__pycache__" not in names
    assert "_internal" not in names

# =============================================================================
# Test 8: Manifest overrides other detection signals
# =============================================================================

def test_manifest_overrides_detection(tmp_path):
    """dryade.json framework field takes priority over marker files."""
    agent_dir = tmp_path / "hybrid-agent"
    agent_dir.mkdir()

    # Marker file says crewai
    (agent_dir / "crew.py").write_text("# This is a crew marker")

    # But manifest says adk (authoritative)
    manifest = {"framework": "adk", "name": "hybrid-agent"}
    (agent_dir / "dryade.json").write_text(json.dumps(manifest))

    discovery = AgentAutoDiscovery(tmp_path)
    result = discovery.detect_framework(agent_dir)

    # Manifest is authoritative -- should return "adk", not "crewai"
    assert result == "adk"
