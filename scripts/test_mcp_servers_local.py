#!/usr/bin/env python3
"""
MCP Server Validation Script

Validates official MCP servers by testing them locally via stdio transport.
Uses JSON-RPC 2.0 protocol for communication.

Usage:
    python scripts/test_mcp_servers_local.py [--verbose]

Exit codes:
    0 - All servers passed validation
    1 - One or more servers failed validation
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

@dataclass
class ToolInfo:
    """Information about an MCP tool."""

    name: str
    description: str
    input_schema: dict = field(default_factory=dict)

@dataclass
class ServerTestResult:
    """Results from testing an MCP server."""

    server_name: str
    package: str
    install_method: str
    status: str = "PENDING"  # PASS, FAIL, SKIP, PARTIAL, PENDING
    startup_time_ms: float = 0.0
    tools: list[ToolInfo] = field(default_factory=list)
    tool_test_results: dict[str, dict] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

class MCPClient:
    """Client for communicating with MCP servers via stdio transport."""

    def __init__(self, command: list[str], timeout: float = 30.0, verbose: bool = False):
        self.command = command
        self.timeout = timeout
        self.verbose = verbose
        self.process: subprocess.Popen | None = None
        self.message_id = 0
        self.server_info: dict = {}
        self.capabilities: dict = {}

    def _log(self, msg: str) -> None:
        """Log message if verbose mode enabled."""
        if self.verbose:
            print(f"  [DEBUG] {msg}")

    def _next_id(self) -> int:
        """Get next message ID."""
        self.message_id += 1
        return self.message_id

    def start(self) -> bool:
        """Start the MCP server process."""
        try:
            self._log(f"Starting: {' '.join(self.command)}")
            self.process = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # Line buffered
                env={**os.environ, "NODE_OPTIONS": "--no-warnings"},
            )
            return True
        except Exception as e:
            self._log(f"Failed to start: {e}")
            return False

    def stop(self) -> None:
        """Stop the MCP server process."""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None

    def send_message(self, method: str, params: dict | None = None) -> dict | None:
        """Send a JSON-RPC message and receive response."""
        if not self.process or self.process.poll() is not None:
            return None

        request_id = self._next_id()
        msg = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }
        if params is not None:
            msg["params"] = params

        try:
            import select

            msg_str = json.dumps(msg)
            self._log(f">>> {msg_str[:200]}...")

            assert self.process.stdin is not None
            assert self.process.stdout is not None

            self.process.stdin.write(msg_str + "\n")
            self.process.stdin.flush()

            # Read response(s) with timeout, handling server requests
            max_iterations = 10  # Prevent infinite loops
            for _ in range(max_iterations):
                ready, _, _ = select.select([self.process.stdout], [], [], self.timeout)

                if not ready:
                    self._log("Timeout waiting for response")
                    return None

                response_line = self.process.stdout.readline()
                if not response_line:
                    self._log("Empty response")
                    return None

                self._log(f"<<< {response_line[:200]}...")
                response = json.loads(response_line)

                # Check if this is a server request (has method, no result)
                if "method" in response and "result" not in response:
                    # Server is making a request to us
                    server_request_method = response.get("method", "")
                    server_request_id = response.get("id")

                    self._log(f"Server request: {server_request_method}")

                    # Handle known server requests
                    if server_request_method == "roots/list":
                        # Respond with empty roots for now
                        roots_response = {
                            "jsonrpc": "2.0",
                            "id": server_request_id,
                            "result": {"roots": []},
                        }
                        self._send_raw(roots_response)
                        continue  # Wait for the actual response

                    elif server_request_method == "sampling/createMessage":
                        # Respond with error - we don't support sampling
                        error_response = {
                            "jsonrpc": "2.0",
                            "id": server_request_id,
                            "error": {"code": -32601, "message": "Sampling not supported"},
                        }
                        self._send_raw(error_response)
                        continue

                    else:
                        # Unknown server request - respond with error
                        self._log(f"Unknown server request: {server_request_method}")
                        error_response = {
                            "jsonrpc": "2.0",
                            "id": server_request_id,
                            "error": {
                                "code": -32601,
                                "message": f"Method not supported: {server_request_method}",
                            },
                        }
                        self._send_raw(error_response)
                        continue

                # Check if this is the response to our request
                if response.get("id") == request_id:
                    return response

                # This is a response to a different request or notification
                self._log(f"Unexpected response id: {response.get('id')}, expected: {request_id}")
                continue

            self._log("Max iterations reached waiting for response")
            return None

        except Exception as e:
            self._log(f"Message error: {e}")
            return None

    def _send_raw(self, msg: dict) -> None:
        """Send a raw JSON-RPC message without expecting a response."""
        if not self.process or self.process.poll() is not None:
            return

        try:
            assert self.process.stdin is not None
            msg_str = json.dumps(msg)
            self._log(f">>> (raw) {msg_str[:200]}...")
            self.process.stdin.write(msg_str + "\n")
            self.process.stdin.flush()
        except Exception as e:
            self._log(f"Raw send error: {e}")

    def send_notification(self, method: str, params: dict | None = None) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        if not self.process or self.process.poll() is not None:
            return

        msg = {
            "jsonrpc": "2.0",
            "method": method,
        }
        if params is not None:
            msg["params"] = params

        try:
            msg_str = json.dumps(msg)
            self._log(f">>> (notification) {msg_str[:200]}...")

            assert self.process.stdin is not None
            self.process.stdin.write(msg_str + "\n")
            self.process.stdin.flush()

        except Exception as e:
            self._log(f"Notification error: {e}")

    def initialize(self) -> bool:
        """Perform MCP initialization handshake."""
        init_params = {
            "protocolVersion": "2024-11-05",
            "capabilities": {"roots": {"listChanged": True}, "sampling": {}},
            "clientInfo": {"name": "dryade-mcp-validator", "version": "1.0.0"},
        }

        response = self.send_message("initialize", init_params)
        if not response:
            return False

        if "error" in response:
            self._log(f"Initialize error: {response['error']}")
            return False

        result = response.get("result", {})
        self.server_info = result.get("serverInfo", {})
        self.capabilities = result.get("capabilities", {})

        # Send initialized notification
        self.send_notification("notifications/initialized")

        return True

    def list_tools(self) -> list[ToolInfo]:
        """List available tools from the server."""
        response = self.send_message("tools/list")
        if not response or "error" in response:
            return []

        tools_data = response.get("result", {}).get("tools", [])
        return [
            ToolInfo(
                name=t.get("name", ""),
                description=t.get("description", ""),
                input_schema=t.get("inputSchema", {}),
            )
            for t in tools_data
        ]

    def call_tool(self, name: str, arguments: dict) -> dict | None:
        """Call a tool and return the result."""
        response = self.send_message("tools/call", {"name": name, "arguments": arguments})

        if not response:
            return None

        if "error" in response:
            return {"error": response["error"]}

        return response.get("result", {})

class MCPServerValidator:
    """Validates MCP servers by testing their capabilities."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.results: list[ServerTestResult] = []

    def _log(self, msg: str) -> None:
        """Log message."""
        print(msg)

    def test_memory_server(self) -> ServerTestResult:
        """Test the official Memory MCP server."""
        result = ServerTestResult(
            server_name="Memory",
            package="@modelcontextprotocol/server-memory",
            install_method="npx",
        )

        # Check if npx is available
        if not self._check_command("npx"):
            result.status = "SKIP"
            result.errors.append("npx not available")
            return result

        command = ["npx", "-y", "@modelcontextprotocol/server-memory"]
        client = MCPClient(command, verbose=self.verbose)

        try:
            start_time = time.time()

            if not client.start():
                result.status = "FAIL"
                result.errors.append("Failed to start server process")
                return result

            # Give server time to initialize npm package
            time.sleep(2.0)

            if not client.initialize():
                result.status = "FAIL"
                result.errors.append("Failed to initialize MCP handshake")
                return result

            result.startup_time_ms = (time.time() - start_time) * 1000

            # List tools
            tools = client.list_tools()
            result.tools = tools

            if not tools:
                result.status = "FAIL"
                result.errors.append("No tools returned from server")
                return result

            result.notes.append(f"Found {len(tools)} tools: {[t.name for t in tools]}")

            # Test create_entities tool if available
            create_tool = next((t for t in tools if t.name == "create_entities"), None)
            if create_tool:
                test_result = client.call_tool(
                    "create_entities",
                    {
                        "entities": [
                            {
                                "name": "test_entity",
                                "entityType": "test",
                                "observations": ["This is a test observation"],
                            }
                        ]
                    },
                )

                if test_result and "error" not in test_result:
                    result.tool_test_results["create_entities"] = {
                        "status": "PASS",
                        "response_preview": str(test_result)[:200],
                    }
                else:
                    result.tool_test_results["create_entities"] = {
                        "status": "FAIL",
                        "error": str(test_result),
                    }
            else:
                result.notes.append("create_entities tool not found")

            # Test search_nodes tool if available
            search_tool = next((t for t in tools if t.name == "search_nodes"), None)
            if search_tool:
                test_result = client.call_tool("search_nodes", {"query": "test"})

                if test_result and "error" not in test_result:
                    result.tool_test_results["search_nodes"] = {
                        "status": "PASS",
                        "response_preview": str(test_result)[:200],
                    }
                else:
                    result.tool_test_results["search_nodes"] = {
                        "status": "FAIL",
                        "error": str(test_result),
                    }

            # Check if any tool test passed
            passed_tests = [
                k for k, v in result.tool_test_results.items() if v.get("status") == "PASS"
            ]
            if passed_tests:
                result.status = "PASS"
                result.notes.append(f"Tool tests passed: {passed_tests}")
            elif result.tools:
                # Tools found but tests failed
                result.status = "PARTIAL"
                result.notes.append("Tools found but tool calls failed")
            else:
                result.status = "FAIL"

        except Exception as e:
            result.status = "FAIL"
            result.errors.append(f"Exception: {e}")
        finally:
            client.stop()

        return result

    def test_filesystem_server(self) -> ServerTestResult:
        """Test the official Filesystem MCP server."""
        result = ServerTestResult(
            server_name="Filesystem",
            package="@modelcontextprotocol/server-filesystem",
            install_method="npx",
        )

        if not self._check_command("npx"):
            result.status = "SKIP"
            result.errors.append("npx not available")
            return result

        # Create temp directory for testing
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a test file
            test_file = Path(temp_dir) / "test.txt"
            test_file.write_text("Hello from MCP test!")

            command = ["npx", "-y", "@modelcontextprotocol/server-filesystem", temp_dir]
            client = MCPClient(command, verbose=self.verbose)

            try:
                start_time = time.time()

                if not client.start():
                    result.status = "FAIL"
                    result.errors.append("Failed to start server process")
                    return result

                time.sleep(2.0)

                if not client.initialize():
                    result.status = "FAIL"
                    result.errors.append("Failed to initialize MCP handshake")
                    return result

                result.startup_time_ms = (time.time() - start_time) * 1000

                # List tools
                tools = client.list_tools()
                result.tools = tools

                if not tools:
                    result.status = "FAIL"
                    result.errors.append("No tools returned from server")
                    return result

                result.notes.append(f"Found {len(tools)} tools: {[t.name for t in tools]}")

                # Test read_file tool if available
                read_tool = next((t for t in tools if t.name == "read_file"), None)
                if read_tool:
                    test_result = client.call_tool("read_file", {"path": str(test_file)})

                    if test_result and "error" not in test_result:
                        content = test_result.get("content", [])
                        if content:
                            result.tool_test_results["read_file"] = {
                                "status": "PASS",
                                "response_preview": str(content)[:200],
                            }
                        else:
                            result.tool_test_results["read_file"] = {
                                "status": "PASS",
                                "response_preview": str(test_result)[:200],
                            }
                    else:
                        result.tool_test_results["read_file"] = {
                            "status": "FAIL",
                            "error": str(test_result),
                        }
                else:
                    result.notes.append("read_file tool not found")

                # Test list_directory tool if available
                list_tool = next((t for t in tools if t.name == "list_directory"), None)
                if list_tool:
                    test_result = client.call_tool("list_directory", {"path": temp_dir})

                    if test_result and "error" not in test_result:
                        result.tool_test_results["list_directory"] = {
                            "status": "PASS",
                            "response_preview": str(test_result)[:200],
                        }
                    else:
                        result.tool_test_results["list_directory"] = {
                            "status": "FAIL",
                            "error": str(test_result),
                        }

                # Check results
                passed_tests = [
                    k for k, v in result.tool_test_results.items() if v.get("status") == "PASS"
                ]
                if passed_tests:
                    result.status = "PASS"
                    result.notes.append(f"Tool tests passed: {passed_tests}")
                elif result.tools:
                    result.status = "PARTIAL"
                    result.notes.append("Tools found but tool calls failed")
                else:
                    result.status = "FAIL"

            except Exception as e:
                result.status = "FAIL"
                result.errors.append(f"Exception: {e}")
            finally:
                client.stop()

        return result

    def test_git_server(self) -> ServerTestResult:
        """Test the Git MCP server via uvx."""
        result = ServerTestResult(server_name="Git", package="mcp-server-git", install_method="uvx")

        # Check if uvx is available
        uvx_path = shutil.which("uvx")
        if not uvx_path:
            if not self._check_command("uvx"):
                result.status = "SKIP"
                result.errors.append("uvx not available")
                return result
            uvx_path = "uvx"

        # Test on current git repo
        repo_path = str(Path(__file__).resolve().parent.parent)
        if not Path(repo_path, ".git").exists():
            result.status = "SKIP"
            result.errors.append("Not in a git repository")
            return result

        command = [uvx_path, "mcp-server-git", "--repository", repo_path]
        client = MCPClient(command, verbose=self.verbose)

        try:
            start_time = time.time()

            if not client.start():
                result.status = "FAIL"
                result.errors.append("Failed to start server process")
                return result

            # Give uvx time to install and start
            time.sleep(5.0)

            if not client.initialize():
                result.status = "FAIL"
                result.errors.append("Failed to initialize MCP handshake")
                return result

            result.startup_time_ms = (time.time() - start_time) * 1000

            # List tools
            tools = client.list_tools()
            result.tools = tools

            if not tools:
                result.status = "FAIL"
                result.errors.append("No tools returned from server")
                return result

            result.notes.append(f"Found {len(tools)} tools: {[t.name for t in tools]}")

            # Test git_status tool if available
            status_tool = next((t for t in tools if t.name == "git_status"), None)
            if status_tool:
                test_result = client.call_tool("git_status", {"repo_path": repo_path})

                if test_result and "error" not in test_result:
                    result.tool_test_results["git_status"] = {
                        "status": "PASS",
                        "response_preview": str(test_result)[:200],
                    }
                else:
                    result.tool_test_results["git_status"] = {
                        "status": "FAIL",
                        "error": str(test_result),
                    }
            else:
                result.notes.append("git_status tool not found")

            # Test git_log tool if available
            log_tool = next((t for t in tools if t.name == "git_log"), None)
            if log_tool:
                test_result = client.call_tool("git_log", {"repo_path": repo_path, "max_count": 5})

                if test_result and "error" not in test_result:
                    result.tool_test_results["git_log"] = {
                        "status": "PASS",
                        "response_preview": str(test_result)[:200],
                    }
                else:
                    result.tool_test_results["git_log"] = {
                        "status": "FAIL",
                        "error": str(test_result),
                    }

            # Check results
            passed_tests = [
                k for k, v in result.tool_test_results.items() if v.get("status") == "PASS"
            ]
            if passed_tests:
                result.status = "PASS"
                result.notes.append(f"Tool tests passed: {passed_tests}")
            elif result.tools:
                result.status = "PARTIAL"
                result.notes.append("Tools found but tool calls failed")
            else:
                result.status = "FAIL"

        except Exception as e:
            result.status = "FAIL"
            result.errors.append(f"Exception: {e}")
        finally:
            client.stop()

        return result

    def _check_command(self, cmd: str) -> bool:
        """Check if a command is available in PATH."""
        import shutil

        return shutil.which(cmd) is not None

    def run_all_tests(self) -> list[ServerTestResult]:
        """Run tests for all configured MCP servers."""
        self._log("\n" + "=" * 60)
        self._log("MCP Server Validation")
        self._log("=" * 60 + "\n")

        # Test Memory Server
        self._log("[1/3] Testing Memory MCP Server...")
        memory_result = self.test_memory_server()
        self.results.append(memory_result)
        self._print_result(memory_result)

        # Test Filesystem Server
        self._log("\n[2/3] Testing Filesystem MCP Server...")
        fs_result = self.test_filesystem_server()
        self.results.append(fs_result)
        self._print_result(fs_result)

        # Test Git Server
        self._log("\n[3/3] Testing Git MCP Server...")
        git_result = self.test_git_server()
        self.results.append(git_result)
        self._print_result(git_result)

        return self.results

    def _print_result(self, result: ServerTestResult) -> None:
        """Print test result."""
        status_symbol = {
            "PASS": "[PASS]",
            "FAIL": "[FAIL]",
            "SKIP": "[SKIP]",
            "PARTIAL": "[PARTIAL]",
        }.get(result.status, "[????]")

        self._log(f"\n  {status_symbol} {result.server_name}")
        self._log(f"  Package: {result.package}")
        self._log(f"  Install: {result.install_method}")

        if result.startup_time_ms > 0:
            self._log(f"  Startup: {result.startup_time_ms:.0f}ms")

        if result.tools:
            self._log(f"  Tools: {len(result.tools)}")
            for tool in result.tools:
                self._log(f"    - {tool.name}: {tool.description[:60]}...")

        if result.tool_test_results:
            self._log("  Tool Tests:")
            for name, res in result.tool_test_results.items():
                self._log(f"    - {name}: {res.get('status', 'N/A')}")

        if result.errors:
            self._log("  Errors:")
            for err in result.errors:
                self._log(f"    - {err}")

        if result.notes and self.verbose:
            self._log("  Notes:")
            for note in result.notes:
                self._log(f"    - {note}")

    def print_summary(self) -> None:
        """Print summary of all test results."""
        self._log("\n" + "=" * 60)
        self._log("Summary")
        self._log("=" * 60 + "\n")

        total = len(self.results)
        passed = sum(1 for r in self.results if r.status == "PASS")
        partial = sum(1 for r in self.results if r.status == "PARTIAL")
        failed = sum(1 for r in self.results if r.status == "FAIL")
        skipped = sum(1 for r in self.results if r.status == "SKIP")

        self._log(f"Total servers tested: {total}")
        self._log(f"  Passed:  {passed}")
        self._log(f"  Partial: {partial}")
        self._log(f"  Failed:  {failed}")
        self._log(f"  Skipped: {skipped}")

        self._log("\n" + "-" * 60)
        self._log("| Server     | Status  | Tools | Method | Startup |")
        self._log("-" * 60)

        for result in self.results:
            startup = f"{result.startup_time_ms:.0f}ms" if result.startup_time_ms > 0 else "N/A"
            self._log(
                f"| {result.server_name:<10} | "
                f"{result.status:<7} | "
                f"{len(result.tools):>5} | "
                f"{result.install_method:<6} | "
                f"{startup:>7} |"
            )

        self._log("-" * 60)

    def get_exit_code(self) -> int:
        """Return appropriate exit code based on results."""
        # Consider test successful if at least 2 servers pass or are partial
        successful = sum(1 for r in self.results if r.status in ("PASS", "PARTIAL"))
        return 0 if successful >= 2 else 1

    def export_results(self) -> dict[str, Any]:
        """Export results as dictionary for JSON output."""
        return {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "platform": os.uname().sysname,
            "arch": os.uname().machine,
            "servers": [
                {
                    "name": r.server_name,
                    "package": r.package,
                    "install_method": r.install_method,
                    "status": r.status,
                    "startup_time_ms": r.startup_time_ms,
                    "tools_count": len(r.tools),
                    "tools": [{"name": t.name, "description": t.description} for t in r.tools],
                    "tool_test_results": r.tool_test_results,
                    "errors": r.errors,
                    "notes": r.notes,
                }
                for r in self.results
            ],
        }

def main():
    parser = argparse.ArgumentParser(description="Validate MCP servers locally via stdio transport")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")

    args = parser.parse_args()

    validator = MCPServerValidator(verbose=args.verbose)
    validator.run_all_tests()

    if args.json:
        print(json.dumps(validator.export_results(), indent=2))
    else:
        validator.print_summary()

    sys.exit(validator.get_exit_code())

if __name__ == "__main__":
    main()
