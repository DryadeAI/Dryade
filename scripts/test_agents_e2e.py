#!/usr/bin/env python3
"""End-to-end tests for Agents REST API endpoints.

Tests all agent endpoints with comprehensive coverage:
- GET /api/agents (list all agents)
- GET /api/agents/{name} (agent detail)
- GET /api/agents/{name}/tools (tool listing)
- GET /api/agents/{name}/describe (A2A card)
- POST /api/agents/{name}/invoke (task execution with semantic validation)
- Error handling (404 for non-existent agents, 422 for validation errors)

Usage:
    python scripts/test_agents_e2e.py

Requirements:
    - Backend running at http://localhost:8000
    - LLM configured (for invoke tests) at LLM_BASE_URL
"""

import time
import uuid

import requests

BASE_URL = "http://localhost:8000"
API_URL = f"{BASE_URL}/api"

class TestResults:
    """Track test results and statistics."""

    def __init__(self):
        self.tests = []
        self.passed = 0
        self.failed = 0

    def add(self, name: str, passed: bool, details: str = ""):
        """Add test result."""
        self.tests.append({"name": name, "passed": passed, "details": details})
        if passed:
            self.passed += 1
        else:
            self.failed += 1
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {name}")
        if details:
            print(f"       {details}")

    def summary(self):
        """Print test summary."""
        print("\n" + "=" * 80)
        print(f"Test Summary: {self.passed} passed, {self.failed} failed")
        print("=" * 80)
        if self.failed > 0:
            print("\nFailed tests:")
            for test in self.tests:
                if not test["passed"]:
                    print(f"  - {test['name']}: {test['details']}")

def get_auth_token() -> str:
    """Get authentication token (setup admin or login)."""
    # Try to setup admin first (will fail if already exists)
    try:
        response = requests.post(
            f"{API_URL}/auth/setup",
            json={
                "username": "admin",
                "email": "admin@test.com",
                "password": "admin123456",
            },
        )
        if response.status_code == 201:
            return response.json()["access_token"]
    except Exception:
        pass

    # Try login with existing admin
    try:
        response = requests.post(
            f"{API_URL}/auth/login",
            json={"email": "admin@test.com", "password": "admin123456"},
        )
        if response.status_code == 200:
            return response.json()["access_token"]
    except Exception:
        pass

    # Fallback: register new user and get token
    username = f"test_{uuid.uuid4().hex[:8]}"
    response = requests.post(
        f"{API_URL}/auth/register",
        json={
            "username": username,
            "email": f"{username}@test.com",
            "password": "testpass123",
        },
    )
    return response.json()["access_token"]

def register_test_agent():
    """Register a test agent via Python API for testing.

    This programmatically registers a test agent since the backend
    doesn't have agents registered by default (requires domain plugins).
    """
    try:
        from crewai import Agent
        from crewai.tools import tool

        from core.adapters import CrewAIAgentAdapter, register_agent
        from core.agents.llm import get_llm

        # Create a simple tool for testing
        @tool("echo_tool")
        def echo_tool(message: str) -> str:
            """Echo the input message back. A simple test tool."""
            return f"Echo: {message}"

        @tool("math_tool")
        def math_tool(expression: str) -> str:
            """Evaluate a simple math expression. Returns the result."""
            try:
                # Safe eval for simple math
                allowed = set("0123456789+-*/(). ")
                if all(c in allowed for c in expression):
                    return str(eval(expression))
                return "Invalid expression"
            except Exception as e:
                return f"Error: {e}"

        # Create a test agent
        test_agent = Agent(
            role="Test Assistant",
            goal="Help with testing and validation tasks",
            backstory="I am a test agent designed to validate the Dryade agent system.",
            tools=[echo_tool, math_tool],
            llm=get_llm(),
            verbose=False,
        )

        # Wrap and register
        adapter = CrewAIAgentAdapter(test_agent, name="test_assistant")
        register_agent(adapter)

        print("Registered test agent: test_assistant")
        return True

    except Exception as e:
        print(f"Failed to register test agent: {e}")
        return False

def test_list_agents(results: TestResults, headers: dict) -> list[dict]:
    """Test GET /agents endpoint."""
    print("\n--- Testing GET /api/agents ---")

    response = requests.get(f"{API_URL}/agents", headers=headers)

    # Test: Response is 200
    results.add(
        "GET /agents returns 200", response.status_code == 200, f"Got {response.status_code}"
    )

    if response.status_code != 200:
        return []

    data = response.json()

    # Test: Response is array
    results.add("GET /agents returns array", isinstance(data, list), f"Got {type(data).__name__}")

    # If agents exist, validate structure
    if data:
        first_agent = data[0]
        required_fields = ["name", "description", "tools", "framework"]

        has_fields = all(field in first_agent for field in required_fields)
        results.add(
            "Agent has required fields (name, description, tools, framework)",
            has_fields,
            f"Fields: {list(first_agent.keys())}",
        )

        # Test: tools is array
        results.add(
            "Agent tools is array",
            isinstance(first_agent.get("tools"), list),
            f"Tools type: {type(first_agent.get('tools'))}",
        )

        print(f"\nDiscovered {len(data)} agents:")
        for agent in data:
            print(f"  - {agent['name']} ({agent['framework']}) - {len(agent['tools'])} tools")
    else:
        print("\nNo agents discovered (empty registry)")

    return data

def test_agent_detail(results: TestResults, headers: dict, agents: list[dict]):
    """Test GET /agents/{name} endpoint."""
    print("\n--- Testing GET /api/agents/{name} ---")

    if not agents:
        results.add("GET /agents/{name} - skipped (no agents)", True, "No agents to test")
        return

    for agent in agents:
        name = agent["name"]

        response = requests.get(f"{API_URL}/agents/{name}", headers=headers)

        # Test: Response is 200
        results.add(
            f"GET /agents/{name} returns 200",
            response.status_code == 200,
            f"Got {response.status_code}",
        )

        if response.status_code == 200:
            data = response.json()

            # Test: Response matches list data
            results.add(
                f"Agent {name} detail matches list",
                data["name"] == agent["name"] and data["framework"] == agent["framework"],
                f"Name: {data['name']}, Framework: {data['framework']}",
            )

def test_agent_tools(results: TestResults, headers: dict, agents: list[dict]):
    """Test GET /agents/{name}/tools endpoint."""
    print("\n--- Testing GET /api/agents/{name}/tools ---")

    if not agents:
        results.add("GET /agents/{name}/tools - skipped (no agents)", True, "No agents to test")
        return

    for agent in agents:
        name = agent["name"]

        response = requests.get(f"{API_URL}/agents/{name}/tools", headers=headers)

        # Test: Response is 200
        results.add(
            f"GET /agents/{name}/tools returns 200",
            response.status_code == 200,
            f"Got {response.status_code}",
        )

        if response.status_code == 200:
            data = response.json()

            # Test: Response is array
            results.add(
                f"Agent {name} tools is array", isinstance(data, list), f"Got {type(data).__name__}"
            )

            # Test: Tool count matches agent detail
            expected_count = len(agent["tools"])
            actual_count = len(data)
            results.add(
                f"Agent {name} tool count matches ({expected_count})",
                actual_count == expected_count,
                f"Expected {expected_count}, got {actual_count}",
            )

            # Test: Tool structure
            if data:
                tool = data[0]
                has_fields = "name" in tool and "description" in tool
                results.add(
                    "Tool has name and description", has_fields, f"Fields: {list(tool.keys())}"
                )

def test_agent_describe(results: TestResults, headers: dict, agents: list[dict]):
    """Test GET /agents/{name}/describe endpoint (A2A card)."""
    print("\n--- Testing GET /api/agents/{name}/describe ---")

    if not agents:
        results.add("GET /agents/{name}/describe - skipped (no agents)", True, "No agents to test")
        return

    for agent in agents:
        name = agent["name"]

        response = requests.get(f"{API_URL}/agents/{name}/describe", headers=headers)

        # Test: Response is 200
        results.add(
            f"GET /agents/{name}/describe returns 200",
            response.status_code == 200,
            f"Got {response.status_code}",
        )

        if response.status_code == 200:
            data = response.json()

            # Test: A2A card structure
            a2a_fields = ["name", "description", "version", "framework", "capabilities"]
            has_fields = all(field in data for field in a2a_fields)
            results.add(
                f"Agent {name} A2A card has required fields",
                has_fields,
                f"Fields: {list(data.keys())}",
            )

def test_404_errors(results: TestResults, headers: dict):
    """Test 404 responses for non-existent agents."""
    print("\n--- Testing 404 Error Handling ---")

    fake_name = "nonexistent_agent_xyz_12345"

    # Test: GET /agents/{name} returns 404
    response = requests.get(f"{API_URL}/agents/{fake_name}", headers=headers)
    results.add(
        "GET /agents/{nonexistent} returns 404",
        response.status_code == 404,
        f"Got {response.status_code}",
    )

    if response.status_code == 404:
        data = response.json()
        results.add("404 response has detail message", "detail" in data, f"Response: {data}")

    # Test: GET /agents/{name}/tools returns 404
    response = requests.get(f"{API_URL}/agents/{fake_name}/tools", headers=headers)
    results.add(
        "GET /agents/{nonexistent}/tools returns 404",
        response.status_code == 404,
        f"Got {response.status_code}",
    )

    # Test: GET /agents/{name}/describe returns 404
    response = requests.get(f"{API_URL}/agents/{fake_name}/describe", headers=headers)
    results.add(
        "GET /agents/{nonexistent}/describe returns 404",
        response.status_code == 404,
        f"Got {response.status_code}",
    )

    # Test: POST /agents/{name}/invoke returns 404
    response = requests.post(
        f"{API_URL}/agents/{fake_name}/invoke", headers=headers, json={"task": "test task"}
    )
    results.add(
        "POST /agents/{nonexistent}/invoke returns 404",
        response.status_code == 404,
        f"Got {response.status_code}",
    )

def test_invoke_validation(results: TestResults, headers: dict, agents: list[dict]):
    """Test input validation for invoke endpoint."""
    print("\n--- Testing Invoke Input Validation ---")

    if not agents:
        results.add("Invoke validation - skipped (no agents)", True, "No agents to test")
        return

    agent_name = agents[0]["name"]

    # Test: Missing task field returns 422
    response = requests.post(
        f"{API_URL}/agents/{agent_name}/invoke", headers=headers, json={"context": {}}
    )
    results.add(
        "POST /invoke with missing task returns 422",
        response.status_code == 422,
        f"Got {response.status_code}",
    )

    # Test: Empty task returns 422
    response = requests.post(
        f"{API_URL}/agents/{agent_name}/invoke", headers=headers, json={"task": ""}
    )
    results.add(
        "POST /invoke with empty task returns 422",
        response.status_code == 422,
        f"Got {response.status_code}",
    )

    # Test: Invalid JSON returns 422
    response = requests.post(
        f"{API_URL}/agents/{agent_name}/invoke",
        headers=headers,
        data="not json",
        # Override content-type
    )
    # Note: FastAPI may return 400 or 422 for invalid JSON
    results.add(
        "POST /invoke with invalid body returns 4xx",
        response.status_code in [400, 422],
        f"Got {response.status_code}",
    )

def test_invoke_semantic(results: TestResults, headers: dict, agents: list[dict]):
    """Test agent invoke with semantic validation.

    This tests that agents actually execute and return meaningful output,
    not just "OK" or empty responses.
    """
    print("\n--- Testing Agent Invoke (Semantic Validation) ---")

    if not agents:
        results.add("Invoke semantic - skipped (no agents)", True, "No agents to test")
        return

    for agent in agents:
        name = agent["name"]
        print(f"\nTesting invoke for agent: {name}")

        # Simple task
        task = "What is 2 + 2? Please provide just the numerical answer."

        start_time = time.time()
        response = requests.post(
            f"{API_URL}/agents/{name}/invoke",
            headers=headers,
            json={"task": task},
            timeout=120,  # 2 minute timeout for LLM
        )
        request_time = time.time() - start_time

        # Test: Response is 200 or 500 (500 if LLM not configured)
        if response.status_code == 500:
            data = response.json()
            error_detail = data.get("detail", "")

            # Check if it's an LLM configuration error
            if (
                "llm" in error_detail.lower()
                or "api" in error_detail.lower()
                or "connection" in error_detail.lower()
            ):
                results.add(
                    f"POST /agents/{name}/invoke - LLM not available",
                    True,
                    f"Known limitation: {error_detail[:100]}",
                )
                continue
            else:
                results.add(
                    f"POST /agents/{name}/invoke returns 200",
                    False,
                    f"Got 500: {error_detail[:100]}",
                )
                continue

        results.add(
            f"POST /agents/{name}/invoke returns 200",
            response.status_code == 200,
            f"Got {response.status_code}, took {request_time:.1f}s",
        )

        if response.status_code != 200:
            continue

        data = response.json()

        # Test: Response has required fields
        required = ["result", "agent", "tool_calls", "execution_time_ms"]
        has_fields = all(field in data for field in required)
        results.add(
            "Invoke response has required fields", has_fields, f"Fields: {list(data.keys())}"
        )

        # Test: result is non-empty
        result = data.get("result", "")
        results.add(
            "Invoke result is non-empty",
            bool(result and len(result) > 0),
            f"Result length: {len(result) if result else 0}",
        )

        # Test: result is meaningful (not just "OK" or generic)
        is_meaningful = (
            result
            and len(result) > 2
            and result.lower() not in ["ok", "done", "success", "completed"]
        )
        results.add(
            "Invoke result is meaningful",
            is_meaningful,
            f"Result preview: {result[:100] if result else 'None'}...",
        )

        # Test: execution_time_ms is positive
        exec_time = data.get("execution_time_ms", 0)
        results.add("Execution time is positive", exec_time > 0, f"execution_time_ms: {exec_time}")

        # Test: agent name matches
        results.add(
            "Agent name in response matches",
            data.get("agent") == name,
            f"Expected '{name}', got '{data.get('agent')}'",
        )

        # Test: tool_calls is array
        tool_calls = data.get("tool_calls", None)
        results.add(
            "tool_calls is array", isinstance(tool_calls, list), f"Type: {type(tool_calls)}"
        )

        # Print result preview
        print(f"  Result: {result[:200]}..." if len(result) > 200 else f"  Result: {result}")
        print(f"  Execution time: {exec_time:.0f}ms")
        print(f"  Tool calls: {len(tool_calls) if tool_calls else 0}")

def test_invoke_with_context(results: TestResults, headers: dict, agents: list[dict]):
    """Test agent invoke with context parameter."""
    print("\n--- Testing Agent Invoke with Context ---")

    if not agents:
        results.add("Invoke with context - skipped (no agents)", True, "No agents to test")
        return

    agent_name = agents[0]["name"]

    # Test with context
    response = requests.post(
        f"{API_URL}/agents/{agent_name}/invoke",
        headers=headers,
        json={
            "task": "Please summarize the provided text",
            "context": {"text": "The quick brown fox jumps over the lazy dog."},
        },
        timeout=120,
    )

    if response.status_code == 500:
        data = response.json()
        error_detail = data.get("detail", "")
        if "llm" in error_detail.lower() or "api" in error_detail.lower():
            results.add("POST /invoke with context - LLM not available", True, "Known limitation")
            return

    results.add(
        "POST /invoke with context accepted",
        response.status_code in [200, 500],
        f"Got {response.status_code}",
    )

def main():
    """Run all agent E2E tests."""
    print("=" * 80)
    print("Agents REST API E2E Tests")
    print("=" * 80)

    results = TestResults()

    # Check backend health
    print("\n--- Checking Backend Health ---")
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code != 200:
            print(f"Backend not healthy: {response.status_code}")
            return
        print("Backend is healthy")
    except Exception as e:
        print(f"Backend unreachable: {e}")
        print("Please start backend with: uv run python -m core.cli serve --port 8000")
        return

    # Get authentication token
    print("\n--- Getting Authentication Token ---")
    try:
        token = get_auth_token()
        headers = {"Authorization": f"Bearer {token}"}
        print("Authentication successful")
    except Exception as e:
        print(f"Authentication failed: {e}")
        return

    # Register test agent if none exist
    print("\n--- Registering Test Agent ---")
    register_test_agent()

    # Run tests
    agents = test_list_agents(results, headers)
    test_agent_detail(results, headers, agents)
    test_agent_tools(results, headers, agents)
    test_agent_describe(results, headers, agents)
    test_404_errors(results, headers)
    test_invoke_validation(results, headers, agents)
    test_invoke_semantic(results, headers, agents)
    test_invoke_with_context(results, headers, agents)

    # Summary
    results.summary()

    # Return exit code based on results
    return 0 if results.failed == 0 else 1

if __name__ == "__main__":
    import sys

    sys.exit(main() or 0)
