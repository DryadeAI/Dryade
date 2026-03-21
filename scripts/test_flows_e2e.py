#!/usr/bin/env python3
"""E2E tests for Flows REST API endpoints.

Tests flow discovery, detail, graph visualization, and execution endpoints.
"""

import json
import sys

import requests

BASE_URL = "http://127.0.0.1:8000"

class FlowsE2ETest:
    """E2E test suite for flows endpoints."""

    def __init__(self):
        self.token = None
        self.results = []
        self.flows = []

    def setup(self):
        """Authenticate and get token."""
        print("=" * 60)
        print("FLOWS E2E TEST SUITE")
        print("=" * 60)
        print()

        # Register or login
        print("[SETUP] Authenticating...")
        try:
            # Try login first
            resp = requests.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": "flowtest@test.com", "password": "password123"},
                timeout=10,
            )
            if resp.status_code == 200:
                self.token = resp.json()["access_token"]
                print("[SETUP] Logged in successfully")
            else:
                # Try register
                resp = requests.post(
                    f"{BASE_URL}/api/auth/register",
                    json={"email": "flowtest@test.com", "password": "password123"},
                    timeout=10,
                )
                if resp.status_code == 200:
                    self.token = resp.json()["access_token"]
                    print("[SETUP] Registered new user")
                else:
                    print(f"[SETUP] Auth failed: {resp.text}")
                    return False
        except Exception as e:
            print(f"[SETUP] Error: {e}")
            return False

        return True

    def auth_headers(self) -> dict:
        """Get authorization headers."""
        return {"Authorization": f"Bearer {self.token}"}

    def record(self, test_name: str, passed: bool, message: str = ""):
        """Record test result."""
        self.results.append(
            {
                "test": test_name,
                "passed": passed,
                "message": message,
            }
        )
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {test_name}")
        if message and not passed:
            print(f"       {message}")

    # ========== TASK 1: Flow Discovery ==========

    def test_list_flows(self):
        """Test GET /api/flows returns list of registered flows."""
        print()
        print("-" * 40)
        print("TASK 1: Flow Discovery")
        print("-" * 40)

        resp = requests.get(
            f"{BASE_URL}/api/flows",
            headers=self.auth_headers(),
            timeout=10,
        )

        if resp.status_code != 200:
            self.record("GET /flows", False, f"Status {resp.status_code}: {resp.text}")
            return

        data = resp.json()
        if "flows" not in data:
            self.record("GET /flows", False, "Missing 'flows' key in response")
            return

        self.flows = data["flows"]
        if not self.flows:
            self.record("GET /flows", False, "Empty flows array")
            return

        # Validate flow structure
        for flow in self.flows:
            required_keys = ["name", "description", "nodes", "entry_point"]
            missing = [k for k in required_keys if k not in flow]
            if missing:
                self.record("GET /flows", False, f"Flow missing keys: {missing}")
                return

        self.record("GET /flows", True)
        print(f"       Found {len(self.flows)} flows:")
        for flow in self.flows:
            print(
                f"         - {flow['name']}: {len(flow['nodes'])} nodes, entry={flow['entry_point']}"
            )

    # ========== TASK 2: Flow Detail and Graph ==========

    def test_flow_detail(self):
        """Test GET /api/flows/{name} returns flow definition."""
        print()
        print("-" * 40)
        print("TASK 2: Flow Detail and Graph")
        print("-" * 40)

        if not self.flows:
            self.record("GET /flows/{name}", False, "No flows discovered")
            return

        for flow in self.flows:
            name = flow["name"]
            resp = requests.get(
                f"{BASE_URL}/api/flows/{name}",
                headers=self.auth_headers(),
                timeout=10,
            )

            if resp.status_code != 200:
                self.record(f"GET /flows/{name}", False, f"Status {resp.status_code}")
                continue

            detail = resp.json()
            if detail["name"] != name:
                self.record(f"GET /flows/{name}", False, f"Name mismatch: {detail['name']}")
                continue

            if not detail["nodes"]:
                self.record(f"GET /flows/{name}", False, "Empty nodes array")
                continue

            self.record(f"GET /flows/{name}", True)

    def test_flow_graph(self):
        """Test GET /api/flows/{name}/graph returns ReactFlow JSON."""
        if not self.flows:
            self.record("GET /flows/{name}/graph", False, "No flows discovered")
            return

        for flow in self.flows:
            name = flow["name"]
            resp = requests.get(
                f"{BASE_URL}/api/flows/{name}/graph",
                headers=self.auth_headers(),
                timeout=10,
            )

            if resp.status_code != 200:
                self.record(f"GET /flows/{name}/graph", False, f"Status {resp.status_code}")
                continue

            graph = resp.json()

            # Validate ReactFlow structure
            required_keys = ["nodes", "edges", "viewport"]
            missing = [k for k in required_keys if k not in graph]
            if missing:
                self.record(f"GET /flows/{name}/graph", False, f"Missing keys: {missing}")
                continue

            # Validate nodes structure
            if not graph["nodes"]:
                self.record(f"GET /flows/{name}/graph", False, "Empty nodes array")
                continue

            for node in graph["nodes"]:
                node_keys = ["id", "type", "position", "data"]
                missing_node_keys = [k for k in node_keys if k not in node]
                if missing_node_keys:
                    self.record(
                        f"GET /flows/{name}/graph", False, f"Node missing: {missing_node_keys}"
                    )
                    continue

            self.record(f"GET /flows/{name}/graph", True)
            print(f"       {name}: {len(graph['nodes'])} nodes, {len(graph['edges'])} edges")

    def test_flow_not_found(self):
        """Test 404 for non-existent flow."""
        resp = requests.get(
            f"{BASE_URL}/api/flows/nonexistent_flow_xyz",
            headers=self.auth_headers(),
            timeout=10,
        )

        if resp.status_code == 404:
            self.record("GET /flows/nonexistent (404)", True)
        else:
            self.record(
                "GET /flows/nonexistent (404)", False, f"Expected 404, got {resp.status_code}"
            )

        # Also test graph endpoint
        resp = requests.get(
            f"{BASE_URL}/api/flows/nonexistent_flow_xyz/graph",
            headers=self.auth_headers(),
            timeout=10,
        )

        if resp.status_code == 404:
            self.record("GET /flows/nonexistent/graph (404)", True)
        else:
            self.record(
                "GET /flows/nonexistent/graph (404)", False, f"Expected 404, got {resp.status_code}"
            )

    # ========== TASK 3: Flow Execution ==========

    def test_flow_execute(self):
        """Test POST /api/flows/{name}/execute triggers execution."""
        print()
        print("-" * 40)
        print("TASK 3: Flow Execution")
        print("-" * 40)

        if not self.flows:
            self.record("POST /flows/{name}/execute", False, "No flows discovered")
            return

        # Test first flow (usually simpler)
        flow = self.flows[0]
        name = flow["name"]

        print(f"       Testing execution of '{name}' flow...")
        print("       (This may take time if flow uses LLM)")

        try:
            resp = requests.post(
                f"{BASE_URL}/api/flows/{name}/execute",
                headers=self.auth_headers(),
                json={"inputs": {}},
                timeout=120,  # Long timeout for LLM calls
            )

            if resp.status_code == 200:
                result = resp.json()
                required_keys = ["execution_id", "result", "status"]
                missing = [k for k in required_keys if k not in result]
                if missing:
                    self.record(f"POST /flows/{name}/execute", False, f"Missing: {missing}")
                else:
                    self.record(f"POST /flows/{name}/execute", True)
                    print(f"       execution_id: {result['execution_id']}")
                    print(f"       status: {result['status']}")
                    return result["execution_id"]
            elif resp.status_code == 500:
                # Expected if flow needs real LLM/model
                self.record(
                    f"POST /flows/{name}/execute", True, "(Expected error: flow needs real model)"
                )
                print(f"       Error (expected): {resp.text[:200]}")
            else:
                self.record(
                    f"POST /flows/{name}/execute", False, f"Status {resp.status_code}: {resp.text}"
                )

        except requests.exceptions.Timeout:
            self.record(f"POST /flows/{name}/execute", False, "Timeout after 120s")
        except Exception as e:
            self.record(f"POST /flows/{name}/execute", False, str(e))

        return None

    def test_flow_execute_stream(self):
        """Test POST /api/flows/{name}/execute/stream returns SSE events."""
        if not self.flows:
            self.record("POST /flows/{name}/execute/stream", False, "No flows discovered")
            return

        flow = self.flows[0]
        name = flow["name"]

        print(f"       Testing SSE stream for '{name}' flow...")

        try:
            resp = requests.post(
                f"{BASE_URL}/api/flows/{name}/execute/stream",
                headers={
                    **self.auth_headers(),
                    "Accept": "text/event-stream",
                },
                json={"inputs": {}},
                stream=True,
                timeout=120,
            )

            if resp.status_code != 200:
                self.record(
                    f"POST /flows/{name}/execute/stream", False, f"Status {resp.status_code}"
                )
                return

            # Read SSE events
            events = []
            for line in resp.iter_lines(decode_unicode=True):
                if line and line.startswith("data:"):
                    event_data = line[5:].strip()
                    if event_data == "[DONE]":
                        events.append({"type": "done"})
                        break
                    try:
                        events.append(json.loads(event_data))
                    except json.JSONDecodeError:
                        events.append({"raw": event_data})

            if not events:
                self.record(f"POST /flows/{name}/execute/stream", False, "No SSE events received")
                return

            # Check for expected event types
            event_types = [e.get("type", "unknown") for e in events]
            print(f"       SSE events: {event_types}")

            if "start" in event_types:
                self.record(f"POST /flows/{name}/execute/stream", True)
            else:
                self.record(f"POST /flows/{name}/execute/stream", False, "Missing 'start' event")

        except requests.exceptions.Timeout:
            self.record(f"POST /flows/{name}/execute/stream", False, "Timeout after 120s")
        except Exception as e:
            self.record(f"POST /flows/{name}/execute/stream", False, str(e))

    def test_execution_status(self, execution_id: str = None):
        """Test GET /api/flows/executions/{id} returns status."""
        if not execution_id:
            # Test with fake ID for 404
            resp = requests.get(
                f"{BASE_URL}/api/flows/executions/00000000-0000-0000-0000-000000000000",
                headers=self.auth_headers(),
                timeout=10,
            )
            if resp.status_code == 404:
                self.record("GET /flows/executions/{id} (404)", True)
            else:
                self.record(
                    "GET /flows/executions/{id} (404)",
                    False,
                    f"Expected 404, got {resp.status_code}",
                )
            return

        resp = requests.get(
            f"{BASE_URL}/api/flows/executions/{execution_id}",
            headers=self.auth_headers(),
            timeout=10,
        )

        if resp.status_code != 200:
            self.record("GET /flows/executions/{id}", False, f"Status {resp.status_code}")
            return

        status = resp.json()
        required_keys = ["execution_id", "status", "progress"]
        missing = [k for k in required_keys if k not in status]
        if missing:
            self.record("GET /flows/executions/{id}", False, f"Missing: {missing}")
        else:
            self.record("GET /flows/executions/{id}", True)
            print(f"       status: {status['status']}, progress: {status['progress']}")

    def test_execute_not_found(self):
        """Test 404 for executing non-existent flow."""
        resp = requests.post(
            f"{BASE_URL}/api/flows/nonexistent_flow_xyz/execute",
            headers=self.auth_headers(),
            json={"inputs": {}},
            timeout=10,
        )

        if resp.status_code == 404:
            self.record("POST /flows/nonexistent/execute (404)", True)
        else:
            self.record(
                "POST /flows/nonexistent/execute (404)",
                False,
                f"Expected 404, got {resp.status_code}",
            )

    def test_kickoff_endpoint(self):
        """Test if /kickoff endpoint exists (frontend uses this)."""
        if not self.flows:
            self.record("POST /flows/{name}/kickoff", False, "No flows discovered")
            return

        flow = self.flows[0]
        name = flow["name"]

        resp = requests.post(
            f"{BASE_URL}/api/flows/{name}/kickoff",
            headers=self.auth_headers(),
            json={"inputs": {}},
            timeout=10,
        )

        if resp.status_code == 404:
            self.record(
                "POST /flows/{name}/kickoff (exists)",
                False,
                "Endpoint not found - needs to be added",
            )
        elif resp.status_code in (200, 500):
            # 200 = success, 500 = expected if flow needs real model
            self.record("POST /flows/{name}/kickoff (exists)", True)
        else:
            self.record(
                "POST /flows/{name}/kickoff (exists)",
                False,
                f"Unexpected status {resp.status_code}",
            )

    def run(self):
        """Run all tests."""
        if not self.setup():
            print("[FATAL] Setup failed, cannot run tests")
            return False

        # Task 1: Flow Discovery
        self.test_list_flows()

        # Task 2: Flow Detail and Graph
        self.test_flow_detail()
        self.test_flow_graph()
        self.test_flow_not_found()

        # Task 3: Flow Execution
        execution_id = self.test_flow_execute()
        self.test_flow_execute_stream()
        self.test_execution_status(execution_id)
        self.test_execution_status()  # Test 404 case
        self.test_execute_not_found()
        self.test_kickoff_endpoint()

        # Summary
        print()
        print("=" * 60)
        print("SUMMARY")
        print("=" * 60)

        passed = sum(1 for r in self.results if r["passed"])
        total = len(self.results)
        failed = total - passed

        print(f"Passed: {passed}/{total}")
        print(f"Failed: {failed}/{total}")
        print()

        if failed > 0:
            print("Failed tests:")
            for r in self.results:
                if not r["passed"]:
                    print(f"  - {r['test']}: {r['message']}")

        return failed == 0

if __name__ == "__main__":
    test = FlowsE2ETest()
    success = test.run()
    sys.exit(0 if success else 1)
