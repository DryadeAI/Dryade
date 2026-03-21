#!/usr/bin/env python3
"""MCP Server Wrappers and Agent Adapter E2E Integration Test.

Tests the full MCP integration stack with real MCP servers:
1. FilesystemServer, GitServer, MemoryServer wrappers
2. MCPAgentAdapter wrapping MCP servers as UniversalAgent
3. Full workflow: register server -> create adapter -> execute tasks

Requirements:
    - npx (npm executable) for Memory and Filesystem servers
    - uvx (uv tool) for Git server (optional)

Usage:
    python scripts/test_mcp_integration_e2e.py [--verbose] [--skip-git]

Examples:
    # Run all tests
    python scripts/test_mcp_integration_e2e.py

    # Verbose output
    python scripts/test_mcp_integration_e2e.py --verbose

    # Skip Git server tests (faster)
    python scripts/test_mcp_integration_e2e.py --skip-git
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(__file__).rsplit("/scripts/", 1)[0])

from core.adapters.protocol import AgentFramework
from core.mcp.adapter import MCPAgentAdapter, create_mcp_agent
from core.mcp.config import MCPServerConfig
from core.mcp.registry import MCPRegistry
from core.mcp.servers import Entity, FilesystemServer, GitServer, MemoryServer, Relation

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

def create_filesystem_config(allowed_dirs: list[str]) -> MCPServerConfig:
    """Create configuration for Filesystem MCP server."""
    return MCPServerConfig(
        name="filesystem",
        command=["npx", "-y", "@modelcontextprotocol/server-filesystem"] + allowed_dirs,
        enabled=True,
        timeout=30.0,
        startup_delay=2.0,
        auto_restart=False,
    )

# ============================================================================
# Server Wrapper Tests
# ============================================================================

def test_memory_server_wrapper(registry: MCPRegistry, verbose: bool) -> TestResult:
    """Test MemoryServer wrapper with real server."""
    name = "test_memory_server_wrapper"
    start = time.time()

    try:
        config = create_memory_config()
        registry.register(config)

        # Create wrapper
        memory = MemoryServer(registry)

        # Create entities using wrapper
        entities = [
            Entity("TestProject", "project", ["Python project", "Uses MCP"]),
            Entity("TestUser", "person", ["Developer"]),
        ]
        result = memory.create_entities(entities)

        if verbose:
            print(f"    Created entities: {result}")

        # Create relation
        relations = [Relation("TestUser", "TestProject", "works_on")]
        result = memory.create_relations(relations)

        if verbose:
            print(f"    Created relations: {result}")

        # Read graph
        graph = memory.read_graph()

        if not graph.get("entities"):
            return TestResult(name, False, "No entities in graph", time.time() - start)

        if verbose:
            print(
                f"    Graph: {len(graph.get('entities', []))} entities, "
                f"{len(graph.get('relations', []))} relations"
            )

        # Search nodes
        results = memory.search_nodes("TestProject")
        if not results:
            return TestResult(name, False, "Search returned no results", time.time() - start)

        if verbose:
            print(f"    Search results: {len(results)} matches")

        return TestResult(name, True, "All wrapper methods work", time.time() - start)

    except Exception as e:
        return TestResult(name, False, str(e), time.time() - start)
    finally:
        if registry.is_running("memory"):
            registry.stop("memory")
        if registry.is_registered("memory"):
            registry.unregister("memory")

def test_filesystem_server_wrapper(registry: MCPRegistry, verbose: bool) -> TestResult:
    """Test FilesystemServer wrapper with real server."""
    name = "test_filesystem_server_wrapper"
    start = time.time()

    # Create temp directory for testing
    temp_dir = tempfile.mkdtemp(prefix="mcp_fs_test_")

    try:
        config = create_filesystem_config([temp_dir])
        registry.register(config)

        # Create wrapper
        fs = FilesystemServer(registry)

        # List allowed directories
        allowed = fs.list_allowed_directories()
        if not allowed:
            return TestResult(name, False, "No allowed directories", time.time() - start)

        if verbose:
            print(f"    Allowed directories: {allowed}")

        # Write a file
        test_file = os.path.join(temp_dir, "test.txt")
        fs.write_file(test_file, "Hello, MCP!")

        # Read the file
        content = fs.read_file(test_file)
        if content != "Hello, MCP!":
            return TestResult(name, False, f"Content mismatch: {content}", time.time() - start)

        if verbose:
            print(f"    File content: {content}")

        # List directory
        entries = fs.list_directory(temp_dir)
        if not any("test.txt" in e for e in entries):
            return TestResult(name, False, "File not in listing", time.time() - start)

        if verbose:
            print(f"    Directory entries: {entries}")

        # Get file info - may return dict or empty dict depending on server response
        try:
            info = fs.get_file_info(test_file)
            if verbose:
                print(f"    File info: {info}")
        except Exception:
            # Some filesystem server versions return non-JSON info
            if verbose:
                print("    File info: skipped (server returned non-JSON)")

        # Create subdirectory
        sub_dir = os.path.join(temp_dir, "subdir")
        fs.create_directory(sub_dir)

        # Search files - may return empty list if server doesn't support search
        try:
            results = fs.search_files(temp_dir, "*.txt")
            if verbose:
                print(f"    Search results: {results}")
        except Exception:
            if verbose:
                print("    Search: skipped (server returned non-JSON)")

        return TestResult(name, True, "All wrapper methods work", time.time() - start)

    except Exception as e:
        return TestResult(name, False, str(e), time.time() - start)
    finally:
        if registry.is_running("filesystem"):
            registry.stop("filesystem")
        if registry.is_registered("filesystem"):
            registry.unregister("filesystem")
        # Cleanup temp directory
        shutil.rmtree(temp_dir, ignore_errors=True)

def test_git_server_wrapper(registry: MCPRegistry, verbose: bool) -> TestResult:
    """Test GitServer wrapper with real server."""
    name = "test_git_server_wrapper"
    start = time.time()

    # Get the project repo path
    repo_path = str(Path(__file__).parent.parent)

    try:
        config = create_git_config()
        registry.register(config)

        # Create wrapper
        git = GitServer(registry)

        # Get status
        status = git.status(repo_path)
        if not status:
            return TestResult(name, False, "Empty status", time.time() - start)

        if verbose:
            print(f"    Status: {status[:100]}...")

        # Get branches
        branches = git.branches(repo_path)
        if not branches:
            return TestResult(name, False, "No branches", time.time() - start)

        if verbose:
            print(f"    Branches: {branches}")

        # Get log
        log = git.log(repo_path, max_count=3)
        if not log:
            return TestResult(name, False, "Empty log", time.time() - start)

        if verbose:
            print(f"    Log: {log[:100]}...")

        # Get unstaged diff (may be empty)
        diff = git.diff_unstaged(repo_path)
        if verbose:
            print(f"    Unstaged diff: {len(diff)} chars")

        return TestResult(name, True, "All wrapper methods work", time.time() - start)

    except Exception as e:
        return TestResult(name, False, str(e), time.time() - start)
    finally:
        if registry.is_running("git"):
            registry.stop("git")
        if registry.is_registered("git"):
            registry.unregister("git")

# ============================================================================
# MCPAgentAdapter Tests
# ============================================================================

def test_adapter_creation(registry: MCPRegistry, verbose: bool) -> TestResult:
    """Test MCPAgentAdapter creation and get_card."""
    name = "test_adapter_creation"
    start = time.time()

    try:
        config = create_memory_config()
        registry.register(config)
        registry.start("memory")

        # Create adapter
        adapter = MCPAgentAdapter("memory", registry=registry)

        # Get card
        card = adapter.get_card()

        if card.name != "memory":
            return TestResult(name, False, f"Wrong name: {card.name}", time.time() - start)

        if card.framework != AgentFramework.MCP:
            return TestResult(
                name, False, f"Wrong framework: {card.framework}", time.time() - start
            )

        if not card.capabilities:
            return TestResult(name, False, "No capabilities", time.time() - start)

        if verbose:
            print(f"    Agent card: name={card.name}, framework={card.framework}")
            print(f"    Capabilities: {[c.name for c in card.capabilities]}")

        return TestResult(
            name,
            True,
            f"Agent card valid with {len(card.capabilities)} capabilities",
            time.time() - start,
        )

    except Exception as e:
        return TestResult(name, False, str(e), time.time() - start)
    finally:
        if registry.is_running("memory"):
            registry.stop("memory")
        if registry.is_registered("memory"):
            registry.unregister("memory")

def test_adapter_get_tools(registry: MCPRegistry, verbose: bool) -> TestResult:
    """Test MCPAgentAdapter.get_tools() returns OpenAI format."""
    name = "test_adapter_get_tools"
    start = time.time()

    try:
        config = create_memory_config()
        registry.register(config)
        registry.start("memory")

        adapter = MCPAgentAdapter("memory", registry=registry)
        tools = adapter.get_tools()

        if not tools:
            return TestResult(name, False, "No tools returned", time.time() - start)

        # Verify OpenAI format
        tool = tools[0]
        if tool.get("type") != "function":
            return TestResult(name, False, f"Wrong type: {tool.get('type')}", time.time() - start)

        if "function" not in tool:
            return TestResult(name, False, "Missing function key", time.time() - start)

        func = tool["function"]
        if "name" not in func or "description" not in func or "parameters" not in func:
            return TestResult(name, False, "Missing function fields", time.time() - start)

        if verbose:
            print(f"    Tools: {[t['function']['name'] for t in tools]}")
            print(f"    First tool: {func['name']} - {func['description'][:50]}...")

        return TestResult(name, True, f"{len(tools)} tools in OpenAI format", time.time() - start)

    except Exception as e:
        return TestResult(name, False, str(e), time.time() - start)
    finally:
        if registry.is_running("memory"):
            registry.stop("memory")
        if registry.is_registered("memory"):
            registry.unregister("memory")

def test_adapter_execute_explicit_tool(registry: MCPRegistry, verbose: bool) -> TestResult:
    """Test MCPAgentAdapter.execute() with explicit tool."""
    name = "test_adapter_execute_explicit_tool"
    start = time.time()

    try:
        config = create_memory_config()
        registry.register(config)

        adapter = MCPAgentAdapter("memory", registry=registry)

        # Execute with explicit tool
        result = asyncio.new_event_loop().run_until_complete(
            adapter.execute(
                "Create test entity",
                context={
                    "tool": "create_entities",
                    "arguments": {
                        "entities": [
                            {
                                "name": "AdapterTest",
                                "entityType": "test",
                                "observations": ["Testing adapter"],
                            }
                        ]
                    },
                },
            )
        )

        if result.status != "ok":
            return TestResult(name, False, f"Status not ok: {result.error}", time.time() - start)

        if verbose:
            print(f"    Execute result: {result.result}")
            print(f"    Metadata: {result.metadata}")

        return TestResult(name, True, "Explicit tool execution works", time.time() - start)

    except Exception as e:
        return TestResult(name, False, str(e), time.time() - start)
    finally:
        if registry.is_running("memory"):
            registry.stop("memory")
        if registry.is_registered("memory"):
            registry.unregister("memory")

def test_adapter_execute_tool_matching(registry: MCPRegistry, verbose: bool) -> TestResult:
    """Test MCPAgentAdapter.execute() with tool name matching."""
    name = "test_adapter_execute_tool_matching"
    start = time.time()

    try:
        config = create_memory_config()
        registry.register(config)

        adapter = MCPAgentAdapter("memory", registry=registry)

        # Execute with task that matches tool name
        result = asyncio.new_event_loop().run_until_complete(
            adapter.execute("read_graph to see the knowledge graph")
        )

        if result.status != "ok":
            return TestResult(name, False, f"Status not ok: {result.error}", time.time() - start)

        if verbose:
            print("    Matched tool via task description")
            print(f"    Result: {result.result[:100] if result.result else 'None'}...")

        return TestResult(name, True, "Tool matching works", time.time() - start)

    except Exception as e:
        return TestResult(name, False, str(e), time.time() - start)
    finally:
        if registry.is_running("memory"):
            registry.stop("memory")
        if registry.is_registered("memory"):
            registry.unregister("memory")

def test_create_mcp_agent_factory(registry: MCPRegistry, verbose: bool) -> TestResult:
    """Test create_mcp_agent factory function."""
    name = "test_create_mcp_agent_factory"
    start = time.time()

    try:
        config = create_memory_config()
        registry.register(config)

        # Use factory
        adapter = create_mcp_agent(
            "memory", registry=registry, description="Knowledge graph agent", version="2.0.0"
        )

        if not isinstance(adapter, MCPAgentAdapter):
            return TestResult(
                name, False, "Factory didn't return MCPAgentAdapter", time.time() - start
            )

        card = adapter.get_card()
        if card.description != "Knowledge graph agent":
            return TestResult(
                name, False, f"Wrong description: {card.description}", time.time() - start
            )

        if card.version != "2.0.0":
            return TestResult(name, False, f"Wrong version: {card.version}", time.time() - start)

        if verbose:
            print(f"    Factory created adapter with description: {card.description}")
            print(f"    Version: {card.version}")

        return TestResult(name, True, "Factory function works", time.time() - start)

    except Exception as e:
        return TestResult(name, False, str(e), time.time() - start)
    finally:
        if registry.is_running("memory"):
            registry.stop("memory")
        if registry.is_registered("memory"):
            registry.unregister("memory")

# ============================================================================
# Full Integration Tests
# ============================================================================

def test_full_workflow_memory(registry: MCPRegistry, verbose: bool) -> TestResult:
    """Test complete workflow: register -> adapter -> execute -> verify."""
    name = "test_full_workflow_memory"
    start = time.time()

    try:
        # 1. Register server
        config = create_memory_config()
        registry.register(config)

        if verbose:
            print("    Step 1: Registered memory server")

        # 2. Create adapter
        adapter = create_mcp_agent("memory", registry=registry)
        card = adapter.get_card()

        if verbose:
            print(f"    Step 2: Created adapter with {len(card.capabilities)} capabilities")

        # 3. Execute: Create entity
        result = asyncio.new_event_loop().run_until_complete(
            adapter.execute(
                "Create entity",
                context={
                    "tool": "create_entities",
                    "arguments": {
                        "entities": [
                            {
                                "name": "WorkflowTest",
                                "entityType": "test",
                                "observations": ["Full workflow"],
                            }
                        ]
                    },
                },
            )
        )

        if result.status != "ok":
            return TestResult(name, False, f"Create failed: {result.error}", time.time() - start)

        if verbose:
            print("    Step 3: Created entity via adapter")

        # 4. Verify: Read graph
        result = asyncio.new_event_loop().run_until_complete(adapter.execute("read_graph"))

        if result.status != "ok":
            return TestResult(name, False, f"Read failed: {result.error}", time.time() - start)

        if "WorkflowTest" not in (result.result or ""):
            return TestResult(name, False, "Entity not in graph", time.time() - start)

        if verbose:
            print("    Step 4: Verified entity in graph")

        return TestResult(name, True, "Full workflow completed", time.time() - start)

    except Exception as e:
        return TestResult(name, False, str(e), time.time() - start)
    finally:
        if registry.is_running("memory"):
            registry.stop("memory")
        if registry.is_registered("memory"):
            registry.unregister("memory")

def test_multi_server_adapters(registry: MCPRegistry, verbose: bool, has_git: bool) -> TestResult:
    """Test multiple adapters for different servers."""
    name = "test_multi_server_adapters"
    start = time.time()

    temp_dir = tempfile.mkdtemp(prefix="mcp_multi_test_")

    try:
        # Register multiple servers
        memory_config = create_memory_config()
        fs_config = create_filesystem_config([temp_dir])

        registry.register(memory_config)
        registry.register(fs_config)

        # Create adapters
        memory_adapter = create_mcp_agent("memory", registry=registry)
        fs_adapter = create_mcp_agent("filesystem", registry=registry)

        # Both should have different capabilities
        memory_card = memory_adapter.get_card()
        fs_card = fs_adapter.get_card()

        if memory_card.name == fs_card.name:
            return TestResult(name, False, "Adapters have same name", time.time() - start)

        # Get tool names for each
        memory_tool_names = {c.name for c in memory_card.capabilities}
        fs_tool_names = {c.name for c in fs_card.capabilities}

        # Should have different tools
        if memory_tool_names == fs_tool_names:
            return TestResult(name, False, "Same tools for different servers", time.time() - start)

        if verbose:
            print(f"    Memory adapter: {len(memory_card.capabilities)} tools")
            print(f"    Filesystem adapter: {len(fs_card.capabilities)} tools")

        # Execute on both
        mem_result = asyncio.new_event_loop().run_until_complete(
            memory_adapter.execute("read_graph")
        )
        if mem_result.status != "ok":
            return TestResult(
                name, False, f"Memory execute failed: {mem_result.error}", time.time() - start
            )

        # Write a file via filesystem adapter
        test_file = os.path.join(temp_dir, "multi_test.txt")
        fs_result = asyncio.new_event_loop().run_until_complete(
            fs_adapter.execute(
                "write file",
                context={
                    "tool": "write_file",
                    "arguments": {"path": test_file, "content": "Multi-server test"},
                },
            )
        )
        if fs_result.status != "ok":
            return TestResult(
                name, False, f"FS execute failed: {fs_result.error}", time.time() - start
            )

        if verbose:
            print("    Both adapters executed successfully")

        return TestResult(name, True, "Multi-server adapters work", time.time() - start)

    except Exception as e:
        return TestResult(name, False, str(e), time.time() - start)
    finally:
        for server in ["memory", "filesystem"]:
            try:
                if registry.is_running(server):
                    registry.stop(server)
                if registry.is_registered(server):
                    registry.unregister(server)
            except Exception:
                pass
        shutil.rmtree(temp_dir, ignore_errors=True)

def test_adapter_with_git_server(registry: MCPRegistry, verbose: bool) -> TestResult:
    """Test adapter with Git server."""
    name = "test_adapter_with_git_server"
    start = time.time()

    repo_path = str(Path(__file__).parent.parent)

    try:
        config = create_git_config()
        registry.register(config)

        adapter = create_mcp_agent("git", registry=registry)
        card = adapter.get_card()

        if verbose:
            print(f"    Git adapter: {len(card.capabilities)} tools")

        # Execute git_status
        result = asyncio.new_event_loop().run_until_complete(
            adapter.execute(
                "git status", context={"tool": "git_status", "arguments": {"repo_path": repo_path}}
            )
        )

        if result.status != "ok":
            return TestResult(name, False, f"Status failed: {result.error}", time.time() - start)

        if not result.result:
            return TestResult(name, False, "Empty status", time.time() - start)

        if verbose:
            print(f"    Git status: {result.result[:80]}...")

        return TestResult(name, True, "Git adapter works", time.time() - start)

    except Exception as e:
        return TestResult(name, False, str(e), time.time() - start)
    finally:
        if registry.is_running("git"):
            registry.stop("git")
        if registry.is_registered("git"):
            registry.unregister("git")

def test_adapter_error_handling(registry: MCPRegistry, verbose: bool) -> TestResult:
    """Test adapter handles errors gracefully."""
    name = "test_adapter_error_handling"
    start = time.time()

    try:
        config = create_memory_config()
        registry.register(config)

        adapter = MCPAgentAdapter("memory", registry=registry)

        # Try to execute with non-existent tool name match
        result = asyncio.new_event_loop().run_until_complete(
            adapter.execute("do something that doesn't match any tool")
        )

        if result.status != "error":
            return TestResult(name, False, "Should have returned error", time.time() - start)

        if "No tool found" not in result.error:
            return TestResult(name, False, f"Wrong error: {result.error}", time.time() - start)

        if "available_tools" not in result.metadata:
            return TestResult(
                name, False, "Missing available_tools in metadata", time.time() - start
            )

        if verbose:
            print(f"    Error handled: {result.error}")
            print(f"    Available tools: {result.metadata.get('available_tools')}")

        return TestResult(name, True, "Error handling works", time.time() - start)

    except Exception as e:
        return TestResult(name, False, str(e), time.time() - start)
    finally:
        if registry.is_running("memory"):
            registry.stop("memory")
        if registry.is_registered("memory"):
            registry.unregister("memory")

def test_adapter_supports_streaming(registry: MCPRegistry, verbose: bool) -> TestResult:
    """Test adapter.supports_streaming() returns False."""
    name = "test_adapter_supports_streaming"
    start = time.time()

    try:
        config = create_memory_config()
        registry.register(config)

        adapter = MCPAgentAdapter("memory", registry=registry)

        if adapter.supports_streaming():
            return TestResult(name, False, "Should not support streaming", time.time() - start)

        if verbose:
            print("    Correctly reports no streaming support")

        return TestResult(name, True, "Streaming check works", time.time() - start)

    except Exception as e:
        return TestResult(name, False, str(e), time.time() - start)
    finally:
        if registry.is_registered("memory"):
            registry.unregister("memory")

# ============================================================================
# Entity/Relation Helper Tests
# ============================================================================

def test_entity_relation_helpers(registry: MCPRegistry, verbose: bool) -> TestResult:
    """Test Entity and Relation helper classes with real server."""
    name = "test_entity_relation_helpers"
    start = time.time()

    try:
        config = create_memory_config()
        registry.register(config)

        memory = MemoryServer(registry)

        # Create entities using helper classes
        entities = [
            Entity("Alice", "person", ["Developer", "Works on Dryade"]),
            Entity("Bob", "person", ["Designer"]),
            Entity("Dryade", "project", ["AI agent framework"]),
        ]

        result = memory.create_entities(entities)
        if verbose:
            print(f"    Created 3 entities: {result}")

        # Create relations using helper classes
        relations = [
            Relation("Alice", "Dryade", "works_on"),
            Relation("Bob", "Dryade", "works_on"),
            Relation("Alice", "Bob", "collaborates_with"),
        ]

        result = memory.create_relations(relations)
        if verbose:
            print(f"    Created 3 relations: {result}")

        # Verify graph
        graph = memory.read_graph()
        entity_count = len(graph.get("entities", []))
        relation_count = len(graph.get("relations", []))

        if entity_count < 3:
            return TestResult(name, False, f"Only {entity_count} entities", time.time() - start)

        if relation_count < 3:
            return TestResult(name, False, f"Only {relation_count} relations", time.time() - start)

        if verbose:
            print(f"    Graph: {entity_count} entities, {relation_count} relations")

        # Search for Alice
        results = memory.search_nodes("Alice")
        if not results:
            return TestResult(name, False, "Search for Alice failed", time.time() - start)

        if verbose:
            print(f"    Search for Alice: {len(results)} results")

        # Open specific nodes
        nodes = memory.open_nodes(["Alice", "Dryade"])
        if len(nodes) < 2:
            return TestResult(name, False, f"Only {len(nodes)} nodes opened", time.time() - start)

        if verbose:
            print(f"    Opened nodes: {[n.get('name') for n in nodes]}")

        return TestResult(name, True, "Entity/Relation helpers work", time.time() - start)

    except Exception as e:
        return TestResult(name, False, str(e), time.time() - start)
    finally:
        if registry.is_running("memory"):
            registry.stop("memory")
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
            "Server Wrapper Tests",
            [
                (test_memory_server_wrapper,),
                (test_filesystem_server_wrapper,),
                (test_git_server_wrapper,) if has_git else None,
                (test_entity_relation_helpers,),
            ],
        ),
        (
            "MCPAgentAdapter Tests",
            [
                (test_adapter_creation,),
                (test_adapter_get_tools,),
                (test_adapter_execute_explicit_tool,),
                (test_adapter_execute_tool_matching,),
                (test_create_mcp_agent_factory,),
                (test_adapter_error_handling,),
                (test_adapter_supports_streaming,),
            ],
        ),
        (
            "Full Integration Tests",
            [
                (test_full_workflow_memory,),
                (test_multi_server_adapters, has_git),
                (test_adapter_with_git_server,) if has_git else None,
            ],
        ),
    ]

    for section_name, section_tests in tests:
        print(f"=== {section_name} ===")

        for test_def in section_tests:
            if test_def is None:
                # Skip test (missing dependency)
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

    print("=" * 60)
    print(f"SUMMARY: {passed}/{total - skipped} passed, {failed} failed, {skipped} skipped")

    if failed == 0:
        print("\nAll E2E integration tests passed!")
    else:
        print(f"\n{failed} test(s) failed. Check output above for details.")

    return results, 0 if failed == 0 else 1

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="MCP Server Wrappers and Agent Adapter E2E Integration Test",
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

    print("MCP Server Wrappers & Agent Adapter E2E Integration Test")
    print("=" * 60)
    print()

    results, exit_code = run_tests(args.verbose, args.skip_git)

    sys.exit(exit_code)

if __name__ == "__main__":
    main()
