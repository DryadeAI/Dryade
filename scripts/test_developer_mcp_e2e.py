#!/usr/bin/env python3
"""E2E test script for Developer Productivity MCP servers.

Tests server wiring, adapter creation, and basic validation for:
1. GitHub MCP (requires GITHUB_TOKEN for full tests)
2. Context7 MCP (HTTP transport)
3. Playwright MCP (requires browser for full tests)
4. Linear MCP (requires LINEAR_API_TOKEN for full tests)

Usage:
    # Test all servers (registration and adapter only)
    python scripts/test_developer_mcp_e2e.py

    # Test specific server
    python scripts/test_developer_mcp_e2e.py --server context7

    # Skip servers requiring auth
    python scripts/test_developer_mcp_e2e.py --no-auth

    # Full test including live connections (slower)
    python scripts/test_developer_mcp_e2e.py --live

    # Verbose output
    python scripts/test_developer_mcp_e2e.py --verbose

Examples:
    # Quick test (default - no live connections)
    python scripts/test_developer_mcp_e2e.py

    # Full test with GitHub (requires GITHUB_TOKEN)
    GITHUB_TOKEN=xxx python scripts/test_developer_mcp_e2e.py --server github --live
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# Add project root to path
sys.path.insert(0, str(__file__).rsplit("/scripts/", 1)[0])

from core.adapters.protocol import AgentFramework
from core.mcp import MCPRegistry
from core.mcp.adapter import SERVER_DESCRIPTIONS, create_mcp_agent
from core.mcp.config import MCPServerTransport
from core.mcp.servers.context7 import create_context7_server
from core.mcp.servers.github import create_github_server
from core.mcp.servers.linear import create_linear_server
from core.mcp.servers.playwright import create_playwright_server

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ============================================================================
# Test Result Types
# ============================================================================

@dataclass
class TestResult:
    """Result of a test suite for one server."""

    name: str
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    duration: float = 0.0

    def pass_test(self, test_name: str) -> None:
        """Record a passed test."""
        self.passed += 1
        print(f"  [PASS] {test_name}")

    def fail_test(self, test_name: str, error: str) -> None:
        """Record a failed test."""
        self.failed += 1
        self.errors.append(f"{test_name}: {error}")
        print(f"  [FAIL] {test_name} - {error}")

    def skip_test(self, test_name: str, reason: str) -> None:
        """Record a skipped test."""
        self.skipped += 1
        print(f"  [SKIP] {test_name} - {reason}")

    @property
    def total(self) -> int:
        """Total number of tests."""
        return self.passed + self.failed + self.skipped

    @property
    def success(self) -> bool:
        """Whether all non-skipped tests passed."""
        return self.failed == 0

# ============================================================================
# Dependency Checks
# ============================================================================

def check_dependencies() -> dict[str, bool]:
    """Check availability of required dependencies."""
    deps = {
        "npx": shutil.which("npx") is not None,
        "github_token": bool(os.environ.get("GITHUB_TOKEN")),
        "linear_token": bool(os.environ.get("LINEAR_API_TOKEN")),
    }

    # Verify npx works
    if deps["npx"]:
        try:
            subprocess.run(
                ["npx", "--version"],
                capture_output=True,
                timeout=5,
                check=True,
            )
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
            deps["npx"] = False

    return deps

# ============================================================================
# Test Functions
# ============================================================================

def test_server_registration(
    registry: MCPRegistry,
    server_name: str,
    create_fn: Any,
    expected_transport: MCPServerTransport,
    result: TestResult,
) -> bool:
    """Test server registration and configuration.

    Returns True if server registered successfully.
    """
    try:
        create_fn(registry)

        # Test 1: Server registered
        if registry.is_registered(server_name):
            result.pass_test("server_registered")
        else:
            result.fail_test("server_registered", "Not in registry")
            return False

        # Test 2: Config has correct transport
        config = registry.get_config(server_name)
        if config.transport == expected_transport:
            result.pass_test(f"transport_type ({config.transport.value})")
        else:
            result.fail_test(
                "transport_type",
                f"Expected {expected_transport.value}, got {config.transport.value}",
            )

        return True
    except Exception as e:
        result.fail_test("server_registration", str(e))
        return False

def test_adapter_creation(
    registry: MCPRegistry,
    server_name: str,
    result: TestResult,
) -> bool:
    """Test adapter creation and card metadata.

    Returns True if adapter created successfully.
    """
    try:
        # Mock list_tools to avoid lazy server start during get_card()
        original_list_tools = registry.list_tools
        registry.list_tools = lambda name: []

        adapter = create_mcp_agent(server_name, registry=registry)

        # Test 1: Adapter has correct server name
        if adapter._server_name == server_name:
            result.pass_test(f"adapter_server_name ({server_name})")
        else:
            result.fail_test(
                "adapter_server_name",
                f"Expected {server_name}, got {adapter._server_name}",
            )

        # Test 2: Card name is namespaced
        card = adapter.get_card()
        expected_card_name = f"mcp-{server_name}"
        if card.name == expected_card_name:
            result.pass_test(f"card_name ({card.name})")
        else:
            result.fail_test("card_name", f"Expected {expected_card_name}, got {card.name}")

        # Test 3: Card has MCP framework
        if card.framework == AgentFramework.MCP:
            result.pass_test("card_framework (MCP)")
        else:
            result.fail_test("card_framework", f"Expected MCP, got {card.framework}")

        # Test 4: Card has server-specific description
        if server_name in SERVER_DESCRIPTIONS:
            expected_desc = SERVER_DESCRIPTIONS[server_name]
            if expected_desc in card.description:
                result.pass_test("card_description (contains keywords)")
            else:
                result.fail_test(
                    "card_description",
                    "Missing expected description",
                )
        else:
            result.pass_test("card_description (default)")

        # Test 5: Card metadata has server info
        if card.metadata.get("mcp_server") == server_name:
            result.pass_test(f"card_metadata_server ({server_name})")
        else:
            result.fail_test(
                "card_metadata_server",
                f"Expected {server_name}, got {card.metadata.get('mcp_server')}",
            )

        # Restore original list_tools
        registry.list_tools = original_list_tools

        return True
    except Exception as e:
        result.fail_test("adapter_creation", str(e))
        return False

def test_context7(verbose: bool = False, live: bool = False) -> TestResult:
    """Test Context7 MCP server."""
    result = TestResult("Context7")
    start = time.time()
    print("\n--- Testing Context7 MCP Server ---")

    registry = MCPRegistry()

    # Registration tests
    if not test_server_registration(
        registry,
        "context7",
        create_context7_server,
        MCPServerTransport.HTTP,
        result,
    ):
        result.duration = time.time() - start
        return result

    # Adapter tests
    test_adapter_creation(registry, "context7", result)

    # Live tests (if requested)
    if live:
        result.skip_test("live_connection", "Context7 live tests not implemented (use unit tests)")

    result.duration = time.time() - start
    return result

def test_github(verbose: bool = False, live: bool = False) -> TestResult:
    """Test GitHub MCP server."""
    result = TestResult("GitHub")
    start = time.time()
    print("\n--- Testing GitHub MCP Server ---")

    registry = MCPRegistry()

    # Registration tests
    if not test_server_registration(
        registry,
        "github",
        create_github_server,
        MCPServerTransport.STDIO,
        result,
    ):
        result.duration = time.time() - start
        return result

    # Adapter tests
    test_adapter_creation(registry, "github", result)

    # Live tests (if requested)
    if live:
        if not os.environ.get("GITHUB_TOKEN"):
            result.skip_test("live_connection", "GITHUB_TOKEN not set")
        else:
            try:
                registry.start("github")
                tools = registry.list_tools("github")
                if tools:
                    result.pass_test(f"live_list_tools ({len(tools)} tools)")
                else:
                    result.fail_test("live_list_tools", "No tools returned")
            except Exception as e:
                result.fail_test("live_connection", str(e))
            finally:
                try:
                    registry.shutdown()
                except Exception:
                    pass

    result.duration = time.time() - start
    return result

def test_playwright(verbose: bool = False, live: bool = False) -> TestResult:
    """Test Playwright MCP server."""
    result = TestResult("Playwright")
    start = time.time()
    print("\n--- Testing Playwright MCP Server ---")

    registry = MCPRegistry()

    # Registration tests
    if not test_server_registration(
        registry,
        "playwright",
        create_playwright_server,
        MCPServerTransport.STDIO,
        result,
    ):
        result.duration = time.time() - start
        return result

    # Adapter tests
    test_adapter_creation(registry, "playwright", result)

    # Live tests (if requested)
    if live:
        try:
            registry.start("playwright")
            tools = registry.list_tools("playwright")
            if tools:
                result.pass_test(f"live_list_tools ({len(tools)} tools)")
            else:
                result.fail_test("live_list_tools", "No tools returned")
        except Exception as e:
            result.fail_test("live_connection", str(e))
        finally:
            try:
                registry.shutdown()
            except Exception:
                pass

    result.duration = time.time() - start
    return result

def test_linear(verbose: bool = False, live: bool = False) -> TestResult:
    """Test Linear MCP server."""
    result = TestResult("Linear")
    start = time.time()
    print("\n--- Testing Linear MCP Server ---")

    registry = MCPRegistry()

    # Registration tests
    if not test_server_registration(
        registry,
        "linear",
        create_linear_server,
        MCPServerTransport.STDIO,
        result,
    ):
        result.duration = time.time() - start
        return result

    # Adapter tests
    test_adapter_creation(registry, "linear", result)

    # Live tests (if requested)
    if live:
        if not os.environ.get("LINEAR_API_TOKEN"):
            result.skip_test("live_connection", "LINEAR_API_TOKEN not set")
        else:
            try:
                registry.start("linear")
                tools = registry.list_tools("linear")
                if tools:
                    result.pass_test(f"live_list_tools ({len(tools)} tools)")
                else:
                    result.fail_test("live_list_tools", "No tools returned")
            except Exception as e:
                result.fail_test("live_connection", str(e))
            finally:
                try:
                    registry.shutdown()
                except Exception:
                    pass

    result.duration = time.time() - start
    return result

def test_multi_server_registration() -> TestResult:
    """Test all 4 servers can register together without conflict."""
    result = TestResult("MultiServer")
    start = time.time()
    print("\n--- Testing Multi-Server Registration ---")

    registry = MCPRegistry()

    # Mock list_tools to avoid lazy server start during get_card()
    registry.list_tools = lambda name: []

    try:
        # Register all 4 servers
        create_github_server(registry)
        create_context7_server(registry)
        create_playwright_server(registry)
        create_linear_server(registry)

        # Test 1: All 4 servers registered
        servers = list(registry.list_servers())
        if len(servers) == 4:
            result.pass_test(f"all_servers_registered ({len(servers)} servers)")
        else:
            result.fail_test("all_servers_registered", f"Expected 4, got {len(servers)}")

        # Test 2: Server names are unique
        expected = {"github", "context7", "playwright", "linear"}
        if set(servers) == expected:
            result.pass_test("unique_server_names")
        else:
            result.fail_test(
                "unique_server_names",
                f"Expected {expected}, got {set(servers)}",
            )

        # Test 3: Adapters can be created for all
        adapters_created = 0
        for name in servers:
            try:
                adapter = create_mcp_agent(name, registry=registry)
                if adapter:
                    adapters_created += 1
            except Exception:
                pass

        if adapters_created == 4:
            result.pass_test(f"all_adapters_created ({adapters_created})")
        else:
            result.fail_test(
                "all_adapters_created",
                f"Expected 4, got {adapters_created}",
            )

        # Test 4: All cards have unique names
        card_names = set()
        for name in servers:
            adapter = create_mcp_agent(name, registry=registry)
            card = adapter.get_card()
            card_names.add(card.name)

        if len(card_names) == 4:
            result.pass_test(f"unique_card_names ({card_names})")
        else:
            result.fail_test("unique_card_names", f"Got duplicates: {card_names}")

    except Exception as e:
        result.fail_test("multi_server_registration", str(e))

    result.duration = time.time() - start
    return result

# ============================================================================
# Main
# ============================================================================

def main() -> int:
    """Run E2E tests for developer productivity MCP servers."""
    parser = argparse.ArgumentParser(description="E2E test for Developer Productivity MCP servers")
    parser.add_argument(
        "--server",
        choices=["github", "context7", "playwright", "linear", "all"],
        default="all",
        help="Test specific server (default: all)",
    )
    parser.add_argument(
        "--no-auth",
        action="store_true",
        help="Skip servers requiring authentication (even with --live)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run live connection tests (slower, may require auth)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    print("=" * 60)
    print("Developer Productivity MCP - E2E Test")
    print(f"Time: {datetime.now().isoformat()}")
    print("=" * 60)

    # Check dependencies
    deps = check_dependencies()
    print("\nDependencies:")
    print(f"  npx: {'OK' if deps['npx'] else 'MISSING'}")
    print(f"  GITHUB_TOKEN: {'SET' if deps['github_token'] else 'NOT SET'}")
    print(f"  LINEAR_API_TOKEN: {'SET' if deps['linear_token'] else 'NOT SET'}")

    if not deps["npx"] and args.live:
        print("\nWARNING: npx not available, live tests for STDIO servers will fail")

    results: list[TestResult] = []

    # Map of server name to test function
    test_map = {
        "github": test_github,
        "context7": test_context7,
        "playwright": test_playwright,
        "linear": test_linear,
    }

    if args.server == "all":
        # Test multi-server registration first
        results.append(test_multi_server_registration())

        # Test each server
        for name, test_fn in test_map.items():
            results.append(test_fn(args.verbose, args.live))
    else:
        # Test single server
        results.append(test_map[args.server](args.verbose, args.live))

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    total_passed = 0
    total_failed = 0
    total_skipped = 0

    for r in results:
        status = "PASS" if r.success else "FAIL"
        print(
            f"{r.name}: {status} "
            f"({r.passed} passed, {r.failed} failed, {r.skipped} skipped) "
            f"[{r.duration:.1f}s]"
        )
        total_passed += r.passed
        total_failed += r.failed
        total_skipped += r.skipped

        for error in r.errors:
            print(f"  - {error}")

    print(f"\nTotal: {total_passed} passed, {total_failed} failed, {total_skipped} skipped")

    return 0 if total_failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
