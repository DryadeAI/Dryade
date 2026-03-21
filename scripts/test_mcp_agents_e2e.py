#!/usr/bin/env python3
"""E2E test script for MCP agent auto-registration.

Verifies that MCP servers configured in mcp_servers.yaml appear
in the /api/agents endpoint with correct framework and metadata.

Prerequisites:
- API server running at localhost:8000
- At least one MCP server enabled in config/mcp_servers.yaml

Usage:
    python scripts/test_mcp_agents_e2e.py [--base-url URL]
    python scripts/test_mcp_agents_e2e.py --help
"""

import argparse
import sys
from pathlib import Path

import requests
import yaml

def load_mcp_config() -> dict:
    """Load MCP server configuration."""
    config_path = Path("config/mcp_servers.yaml")
    if not config_path.exists():
        print(f"ERROR: Config not found at {config_path}")
        sys.exit(1)

    with open(config_path) as f:
        return yaml.safe_load(f) or {}

def get_enabled_servers(config: dict) -> list[str]:
    """Get list of enabled MCP server names."""
    servers = config.get("servers", {})
    return [name for name, cfg in servers.items() if cfg.get("enabled", False)]

def test_mcp_agents_in_api(base_url: str):
    """Test that MCP agents appear in /api/agents."""
    print("\n" + "=" * 60)
    print("MCP Agent Auto-Registration E2E Test")
    print("=" * 60)

    config = load_mcp_config()
    enabled_servers = get_enabled_servers(config)

    print(f"\nEnabled MCP servers in config: {enabled_servers or '(none)'}")

    # Get agents from API
    url = f"{base_url}/api/agents"
    print(f"\nFetching agents from: {url}")

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        agents = response.json()
    except requests.RequestException as e:
        print(f"ERROR: Failed to fetch agents: {e}")
        sys.exit(1)

    print(f"Total agents returned: {len(agents)}")

    # Filter MCP agents
    mcp_agents = [a for a in agents if a.get("framework") == "mcp"]
    print(f"MCP agents found: {len(mcp_agents)}")

    # Test results
    tests_passed = 0
    tests_failed = 0

    # Test 1: Check enabled servers are registered
    print("\n--- Test 1: Enabled servers are registered ---")
    for server_name in enabled_servers:
        expected_agent_name = f"mcp-{server_name}"
        found = any(a["name"] == expected_agent_name for a in mcp_agents)
        if found:
            print(f"  [PASS] {expected_agent_name} found in agents")
            tests_passed += 1
        else:
            print(f"  [FAIL] {expected_agent_name} NOT found in agents")
            tests_failed += 1

    if not enabled_servers:
        print("  [SKIP] No servers enabled - enable servers in config to test")

    # Test 2: Check MCP agents have correct framework
    print("\n--- Test 2: MCP agents have framework='mcp' ---")
    for agent in mcp_agents:
        if agent.get("framework") == "mcp":
            print(f"  [PASS] {agent['name']} has framework='mcp'")
            tests_passed += 1
        else:
            print(f"  [FAIL] {agent['name']} has framework='{agent.get('framework')}'")
            tests_failed += 1

    if not mcp_agents:
        print("  [SKIP] No MCP agents found")

    # Test 3: Check MCP agents have mcp- prefix
    print("\n--- Test 3: MCP agents have mcp- prefix ---")
    for agent in mcp_agents:
        if agent["name"].startswith("mcp-"):
            print(f"  [PASS] {agent['name']} starts with 'mcp-'")
            tests_passed += 1
        else:
            print(f"  [FAIL] {agent['name']} does NOT start with 'mcp-'")
            tests_failed += 1

    if not mcp_agents:
        print("  [SKIP] No MCP agents found")

    # Test 4: Check MCP agents have descriptions
    print("\n--- Test 4: MCP agents have descriptions ---")
    for agent in mcp_agents:
        description = agent.get("description", "")
        if description:
            # Truncate long descriptions
            display_desc = description[:50] + "..." if len(description) > 50 else description
            print(f"  [PASS] {agent['name']} has description: '{display_desc}'")
            tests_passed += 1
        else:
            print(f"  [FAIL] {agent['name']} has no description")
            tests_failed += 1

    if not mcp_agents:
        print("  [SKIP] No MCP agents found")

    # Test 5: Verify no duplicate agents
    print("\n--- Test 5: No duplicate MCP agents ---")
    agent_names = [a["name"] for a in mcp_agents]
    duplicates = [name for name in set(agent_names) if agent_names.count(name) > 1]
    if not duplicates:
        print("  [PASS] No duplicate MCP agents found")
        tests_passed += 1
    else:
        print(f"  [FAIL] Duplicate agents found: {duplicates}")
        tests_failed += 1

    # Test 6: Check agent response structure
    print("\n--- Test 6: Agent response structure is valid ---")
    required_fields = ["name", "description", "framework"]
    for agent in mcp_agents:
        missing = [f for f in required_fields if f not in agent]
        if not missing:
            print(f"  [PASS] {agent['name']} has all required fields")
            tests_passed += 1
        else:
            print(f"  [FAIL] {agent['name']} missing fields: {missing}")
            tests_failed += 1

    if not mcp_agents:
        print("  [SKIP] No MCP agents found")

    # Print agent details
    if mcp_agents:
        print("\n--- MCP Agent Details ---")
        for agent in mcp_agents:
            print(f"\n  {agent['name']}:")
            print(f"    Framework: {agent.get('framework')}")
            print(f"    Description: {agent.get('description', '(none)')[:60]}...")
            print(f"    Capabilities: {len(agent.get('capabilities', []))} available")
            print(f"    Version: {agent.get('version', '(unknown)')}")

    # Summary
    print("\n" + "=" * 60)
    print(f"SUMMARY: {tests_passed} passed, {tests_failed} failed")
    print("=" * 60)

    if tests_failed > 0:
        print("\nSome tests FAILED!")
        sys.exit(1)

    if not enabled_servers:
        print("\nWARNING: No MCP servers enabled. Enable some in config/mcp_servers.yaml to test.")
        print("Example: Set 'enabled: true' for 'memory' server")

    if not mcp_agents and enabled_servers:
        print("\nWARNING: MCP servers enabled but no agents found.")
        print("Ensure API server was started AFTER enabling servers.")

    print("\nAll tests PASSED!")
    return True

def test_api_health(base_url: str) -> bool:
    """Check if API is healthy before running tests."""
    try:
        response = requests.get(f"{base_url}/health", timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False

def main():
    parser = argparse.ArgumentParser(description="E2E test for MCP agent auto-registration")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="API base URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--skip-health-check",
        action="store_true",
        help="Skip initial API health check",
    )
    args = parser.parse_args()

    print(f"Testing MCP agents at: {args.base_url}")

    # Check API health first
    if not args.skip_health_check:
        print("Checking API health...")
        if not test_api_health(args.base_url):
            print(f"\nERROR: API not responding at {args.base_url}")
            print("Please start the API server first:")
            print("  uvicorn core.api.main:app --reload")
            sys.exit(1)
        print("API is healthy.")

    test_mcp_agents_in_api(args.base_url)

if __name__ == "__main__":
    main()
