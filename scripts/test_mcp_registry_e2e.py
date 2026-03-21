#!/usr/bin/env python3
"""MCP Registry E2E Integration Test.

Tests MCPRegistry with real MCP servers (Memory, Git).
Validates end-to-end communication including server startup,
tool discovery, tool execution, and graceful shutdown.

Requirements:
    - npx (npm executable) for Memory server
    - uvx (uv tool) for Git server (optional)

Usage:
    python scripts/test_mcp_registry_e2e.py [--verbose] [--skip-git]

Examples:
    # Run all tests
    python scripts/test_mcp_registry_e2e.py

    # Verbose output
    python scripts/test_mcp_registry_e2e.py --verbose

    # Skip Git server tests (faster)
    python scripts/test_mcp_registry_e2e.py --skip-git
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass

# Add project root to path for imports
sys.path.insert(0, str(__file__).rsplit("/scripts/", 1)[0])

from core.mcp.config import MCPServerConfig
from core.mcp.registry import MCPRegistry

# ============================================================================
# Test Result Types
# ============================================================================

@dataclass
class TestResult:
    """Result of a single test."""

    name: str
    passed: bool
    message: str
    duration: float
    skipped: bool = False

# ============================================================================
# Test Infrastructure
# ============================================================================

def check_dependencies() -> dict[str, bool]:
    """Check availability of required dependencies."""
    deps = {
        "npx": shutil.which("npx") is not None,
        "uvx": shutil.which("uvx") is not None,
    }

    # Verify npx works (not just exists)
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

    # Verify uvx works
    if deps["uvx"]:
        try:
            subprocess.run(
                ["uvx", "--version"],
                capture_output=True,
                timeout=5,
                check=True,
            )
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
            deps["uvx"] = False

    return deps

def create_memory_config() -> MCPServerConfig:
    """Create configuration for Memory MCP server."""
    return MCPServerConfig(
        name="memory",
        command=["npx", "-y", "@modelcontextprotocol/server-memory"],
        enabled=True,
        timeout=30.0,
        startup_delay=2.0,
        auto_restart=False,
    )

def create_git_config() -> MCPServerConfig:
    """Create configuration for Git MCP server."""
    return MCPServerConfig(
        name="git",
        command=["uvx", "mcp-server-git"],
        enabled=True,
        timeout=30.0,
        startup_delay=2.0,
        auto_restart=False,
    )

# ============================================================================
# Test Functions
# ============================================================================

def test_memory_server_lifecycle(registry: MCPRegistry, verbose: bool) -> TestResult:
    """Test Memory server lifecycle: start, list tools, stop."""
    name = "test_memory_server_lifecycle"
    start = time.time()

    try:
        config = create_memory_config()
        registry.register(config)

        # Start
        registry.start("memory")
        if not registry.is_running("memory"):
            return TestResult(name, False, "Server did not start", time.time() - start)

        # List tools
        tools = registry.list_tools("memory")
        if not tools:
            return TestResult(name, False, "No tools returned", time.time() - start)

        if verbose:
            print(f"    Memory tools: {[t.name for t in tools]}")

        # Stop
        registry.stop("memory")
        if registry.is_running("memory"):
            return TestResult(name, False, "Server did not stop", time.time() - start)

        return TestResult(name, True, f"Found {len(tools)} tools", time.time() - start)

    except Exception as e:
        return TestResult(name, False, str(e), time.time() - start)
    finally:
        # Ensure cleanup
        registry.unregister("memory") if registry.is_registered("memory") else None

def test_memory_create_entity(registry: MCPRegistry, verbose: bool) -> TestResult:
    """Test Memory server: create entity and verify."""
    name = "test_memory_create_entity"
    start = time.time()

    try:
        config = create_memory_config()
        registry.register(config)
        registry.start("memory")

        # Create entity using tool call
        result = registry.call_tool(
            "memory",
            "create_entities",
            {
                "entities": [
                    {
                        "name": "test_entity",
                        "entityType": "test_type",
                        "observations": ["This is a test observation"],
                    }
                ]
            },
        )

        if result.isError:
            return TestResult(name, False, f"Error: {result.content}", time.time() - start)

        if verbose:
            print(f"    Created entity: {result.content[0].text if result.content else 'OK'}")

        return TestResult(name, True, "Entity created successfully", time.time() - start)

    except Exception as e:
        return TestResult(name, False, str(e), time.time() - start)
    finally:
        if registry.is_running("memory"):
            registry.stop("memory")
        if registry.is_registered("memory"):
            registry.unregister("memory")

def test_memory_read_graph(registry: MCPRegistry, verbose: bool) -> TestResult:
    """Test Memory server: read graph after creating entity."""
    name = "test_memory_read_graph"
    start = time.time()

    try:
        config = create_memory_config()
        registry.register(config)
        registry.start("memory")

        # First create an entity
        registry.call_tool(
            "memory",
            "create_entities",
            {
                "entities": [
                    {
                        "name": "graph_test_entity",
                        "entityType": "test",
                        "observations": ["Testing graph read"],
                    }
                ]
            },
        )

        # Now read the graph
        result = registry.call_tool("memory", "read_graph", {})

        if result.isError:
            return TestResult(name, False, f"Error: {result.content}", time.time() - start)

        if verbose:
            content = result.content[0].text if result.content else "None"
            print(f"    Graph content: {content[:100]}...")

        return TestResult(name, True, "Graph read successful", time.time() - start)

    except Exception as e:
        return TestResult(name, False, str(e), time.time() - start)
    finally:
        if registry.is_running("memory"):
            registry.stop("memory")
        if registry.is_registered("memory"):
            registry.unregister("memory")

def test_git_server_lifecycle(registry: MCPRegistry, verbose: bool) -> TestResult:
    """Test Git server lifecycle: start, list tools, stop."""
    name = "test_git_server_lifecycle"
    start = time.time()

    try:
        config = create_git_config()
        registry.register(config)

        # Start
        registry.start("git")
        if not registry.is_running("git"):
            return TestResult(name, False, "Server did not start", time.time() - start)

        # List tools
        tools = registry.list_tools("git")
        if not tools:
            return TestResult(name, False, "No tools returned", time.time() - start)

        if verbose:
            print(f"    Git tools: {[t.name for t in tools]}")

        # Stop
        registry.stop("git")
        if registry.is_running("git"):
            return TestResult(name, False, "Server did not stop", time.time() - start)

        return TestResult(name, True, f"Found {len(tools)} tools", time.time() - start)

    except Exception as e:
        return TestResult(name, False, str(e), time.time() - start)
    finally:
        if registry.is_registered("git"):
            try:
                if registry.is_running("git"):
                    registry.stop("git")
            except Exception:
                pass
            registry.unregister("git")

def test_multi_server_concurrent(registry: MCPRegistry, verbose: bool, has_git: bool) -> TestResult:
    """Test running multiple servers simultaneously."""
    name = "test_multi_server_concurrent"
    start = time.time()

    if not has_git:
        return TestResult(name, True, "Skipped (no uvx)", time.time() - start, skipped=True)

    try:
        memory_config = create_memory_config()
        git_config = create_git_config()

        registry.register(memory_config)
        registry.register(git_config)

        # Start both
        registry.start("memory")
        registry.start("git")

        # Both should be running
        if not registry.is_running("memory") or not registry.is_running("git"):
            return TestResult(name, False, "One or both servers not running", time.time() - start)

        # Get tools from both
        memory_tools = registry.list_tools("memory")
        git_tools = registry.list_tools("git")

        if verbose:
            print(f"    Memory: {len(memory_tools)} tools, Git: {len(git_tools)} tools")

        return TestResult(
            name,
            True,
            f"Both servers running ({len(memory_tools)}+{len(git_tools)} tools)",
            time.time() - start,
        )

    except Exception as e:
        return TestResult(name, False, str(e), time.time() - start)
    finally:
        for server in ["memory", "git"]:
            try:
                if registry.is_running(server):
                    registry.stop(server)
                if registry.is_registered(server):
                    registry.unregister(server)
            except Exception:
                pass

def test_find_tool_across_servers(
    registry: MCPRegistry, verbose: bool, has_git: bool
) -> TestResult:
    """Test finding specific tool across servers."""
    name = "test_find_tool_across_servers"
    start = time.time()

    if not has_git:
        return TestResult(name, True, "Skipped (no uvx)", time.time() - start, skipped=True)

    try:
        memory_config = create_memory_config()
        git_config = create_git_config()

        registry.register(memory_config)
        registry.register(git_config)
        registry.start("memory")
        registry.start("git")

        # Find a Memory tool
        result = registry.find_tool("create_entities")
        if result is None:
            return TestResult(name, False, "create_entities not found", time.time() - start)

        server, tool = result
        if server != "memory":
            return TestResult(name, False, f"Wrong server: {server}", time.time() - start)

        if verbose:
            print(f"    Found {tool.name} on {server}")

        # Find a Git tool
        result = registry.find_tool("git_log")
        if result is None:
            return TestResult(name, False, "git_log not found", time.time() - start)

        server, tool = result
        if server != "git":
            return TestResult(name, False, f"Wrong server: {server}", time.time() - start)

        if verbose:
            print(f"    Found {tool.name} on {server}")

        return TestResult(name, True, "Tools found on correct servers", time.time() - start)

    except Exception as e:
        return TestResult(name, False, str(e), time.time() - start)
    finally:
        for server in ["memory", "git"]:
            try:
                if registry.is_running(server):
                    registry.stop(server)
                if registry.is_registered(server):
                    registry.unregister(server)
            except Exception:
                pass

def test_call_tool_by_name(registry: MCPRegistry, verbose: bool) -> TestResult:
    """Test auto-route tool call."""
    name = "test_call_tool_by_name"
    start = time.time()

    try:
        config = create_memory_config()
        registry.register(config)
        registry.start("memory")

        # Call tool without specifying server
        result = registry.call_tool_by_name(
            "create_entities",
            {
                "entities": [
                    {
                        "name": "auto_route_test",
                        "entityType": "test",
                        "observations": ["Auto-routed"],
                    }
                ]
            },
        )

        if result.isError:
            return TestResult(name, False, f"Error: {result.content}", time.time() - start)

        if verbose:
            print("    Auto-routed to memory: OK")

        return TestResult(name, True, "Auto-routing worked", time.time() - start)

    except Exception as e:
        return TestResult(name, False, str(e), time.time() - start)
    finally:
        if registry.is_running("memory"):
            registry.stop("memory")
        if registry.is_registered("memory"):
            registry.unregister("memory")

def test_health_summary(registry: MCPRegistry, verbose: bool) -> TestResult:
    """Test health reporting structure."""
    name = "test_health_summary"
    start = time.time()

    try:
        config = create_memory_config()
        registry.register(config)
        registry.start("memory")

        summary = registry.get_health_summary()

        # Verify structure
        required_keys = ["servers", "total_registered", "total_running", "total_healthy"]
        for key in required_keys:
            if key not in summary:
                return TestResult(name, False, f"Missing key: {key}", time.time() - start)

        # Verify server info
        if "memory" not in summary["servers"]:
            return TestResult(name, False, "memory not in servers", time.time() - start)

        server_info = summary["servers"]["memory"]
        for key in ["status", "restart_count", "tool_count"]:
            if key not in server_info:
                return TestResult(name, False, f"Missing server key: {key}", time.time() - start)

        if verbose:
            print(
                f"    Summary: {summary['total_registered']} registered, "
                f"{summary['total_running']} running, "
                f"{summary['total_healthy']} healthy"
            )
            print(f"    Memory: {server_info}")

        return TestResult(
            name,
            True,
            f"Health structure valid, {server_info['tool_count']} tools",
            time.time() - start,
        )

    except Exception as e:
        return TestResult(name, False, str(e), time.time() - start)
    finally:
        if registry.is_running("memory"):
            registry.stop("memory")
        if registry.is_registered("memory"):
            registry.unregister("memory")

def test_lazy_start_pattern(registry: MCPRegistry, verbose: bool) -> TestResult:
    """Test lazy start: call_tool auto-starts server."""
    name = "test_lazy_start_pattern"
    start = time.time()

    try:
        config = create_memory_config()
        registry.register(config)

        # Verify not running yet
        if registry.is_running("memory"):
            return TestResult(
                name, False, "Server already running before call", time.time() - start
            )

        # Call tool - should auto-start
        result = registry.call_tool(
            "memory",
            "create_entities",
            {
                "entities": [
                    {
                        "name": "lazy_start_test",
                        "entityType": "test",
                        "observations": ["Lazy started"],
                    }
                ]
            },
        )

        # Verify now running
        if not registry.is_running("memory"):
            return TestResult(
                name, False, "Server not running after lazy start", time.time() - start
            )

        if result.isError:
            return TestResult(
                name, False, f"Tool call error: {result.content}", time.time() - start
            )

        if verbose:
            print("    Lazy start successful: server auto-started on tool call")

        return TestResult(name, True, "Lazy start pattern works", time.time() - start)

    except Exception as e:
        return TestResult(name, False, str(e), time.time() - start)
    finally:
        if registry.is_running("memory"):
            registry.stop("memory")
        if registry.is_registered("memory"):
            registry.unregister("memory")

def test_graceful_shutdown(registry: MCPRegistry, verbose: bool) -> TestResult:
    """Test clean shutdown of all servers."""
    name = "test_graceful_shutdown"
    start = time.time()

    try:
        config = create_memory_config()
        registry.register(config)
        registry.start("memory")

        if not registry.is_running("memory"):
            return TestResult(name, False, "Server not started", time.time() - start)

        # Shutdown
        registry.shutdown()

        # Verify transports cleared
        if len(registry._transports) > 0:
            return TestResult(name, False, "Transports not cleared", time.time() - start)

        if verbose:
            print("    Graceful shutdown: all servers stopped")

        return TestResult(name, True, "Shutdown cleared all transports", time.time() - start)

    except Exception as e:
        return TestResult(name, False, str(e), time.time() - start)
    finally:
        if registry.is_registered("memory"):
            registry.unregister("memory")

# ============================================================================
# Test Runner
# ============================================================================

def run_tests(verbose: bool, skip_git: bool) -> tuple[list[TestResult], int]:
    """Run all E2E tests and return results."""
    results: list[TestResult] = []
    deps = check_dependencies()

    if not deps["npx"]:
        print("ERROR: npx not available. Cannot run E2E tests.")
        print("Install Node.js and npm, then try again.")
        return results, 1

    has_git = deps["uvx"] and not skip_git

    if skip_git:
        print("Skipping Git server tests (--skip-git)")
    elif not deps["uvx"]:
        print("Warning: uvx not available, Git server tests will be skipped")

    print()

    # Create fresh registry for each test
    def run_test(test_fn: Callable, *args) -> TestResult:
        registry = MCPRegistry()
        try:
            return test_fn(registry, verbose, *args) if args else test_fn(registry, verbose)
        finally:
            # Cleanup any leftover servers
            registry.shutdown()

    # Define test suite
    tests = [
        (
            "Memory Server",
            [
                (test_memory_server_lifecycle,),
                (test_memory_create_entity,),
                (test_memory_read_graph,),
                (test_lazy_start_pattern,),
                (test_health_summary,),
                (test_call_tool_by_name,),
                (test_graceful_shutdown,),
            ],
        ),
        (
            "Git Server",
            [
                (test_git_server_lifecycle,) if has_git else None,
            ],
        ),
        (
            "Multi-Server",
            [
                (test_multi_server_concurrent, has_git),
                (test_find_tool_across_servers, has_git),
            ],
        ),
    ]

    for section_name, section_tests in tests:
        print(f"=== {section_name} Tests ===")

        for test_def in section_tests:
            if test_def is None:
                print("  SKIP  test_git_server_lifecycle (uvx not available)")
                results.append(
                    TestResult("test_git_server_lifecycle", True, "Skipped", 0, skipped=True)
                )
                continue

            test_fn = test_def[0]
            extra_args = test_def[1:] if len(test_def) > 1 else ()

            result = run_test(test_fn, *extra_args)
            results.append(result)

            status = "SKIP" if result.skipped else ("PASS" if result.passed else "FAIL")
            print(f"  {status}  {result.name} ({result.duration:.2f}s) - {result.message}")

        print()

    # Summary
    passed = sum(1 for r in results if r.passed and not r.skipped)
    failed = sum(1 for r in results if not r.passed)
    skipped = sum(1 for r in results if r.skipped)
    total = len(results)

    print("=" * 50)
    print(f"SUMMARY: {passed}/{total - skipped} passed, {failed} failed, {skipped} skipped")

    return results, 0 if failed == 0 else 1

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="MCP Registry E2E Integration Test",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print detailed output",
    )
    parser.add_argument(
        "--skip-git",
        action="store_true",
        help="Skip Git server tests (faster)",
    )

    args = parser.parse_args()

    print("MCP Registry E2E Integration Test")
    print("=" * 50)
    print()

    results, exit_code = run_tests(args.verbose, args.skip_git)

    sys.exit(exit_code)

if __name__ == "__main__":
    main()
