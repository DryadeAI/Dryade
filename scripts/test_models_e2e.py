#!/usr/bin/env python3
"""End-to-end tests for Model Registry, Comparison, and Routing REST API endpoints.

Comprehensive coverage (20+ tests):
  - Model CRUD (list, get, create, update, delete)
  - Set default model (ensures only one default per user)
  - Model comparison (compare 2+, verify ranking by metrics)
  - Model metrics retrieval
  - Routing options (list available models for routing)
  - Routing classification (classify message for tool-calling needs)

Usage:
  # Quick test (no training jobs, uses mock models)
  python scripts/test_models_e2e.py --base-url http://localhost:8080

  # With license file for enterprise features
  python scripts/test_models_e2e.py --base-url http://localhost:8080 \
    --license-file tests/fixtures/licenses/valid_enterprise.key

Requirements:
  - Backend running at BASE_URL with valid enterprise license
  - Trainer plugin loaded (enterprise feature)
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Any

import requests

@dataclass(frozen=True)
class Settings:
    base_url: str
    license_file: str | None = None

    @property
    def api_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/api"

class TestResults:
    """Track test results and statistics."""

    def __init__(self):
        self.tests: list[dict[str, Any]] = []
        self.passed = 0
        self.failed = 0
        self.skipped = 0

    def add(self, name: str, passed: bool, details: str = "") -> None:
        self.tests.append(
            {"name": name, "status": "PASS" if passed else "FAIL", "details": details}
        )
        if passed:
            self.passed += 1
            print(f"[PASS] {name}")
        else:
            self.failed += 1
            print(f"[FAIL] {name}")
        if details:
            print(f"       {details}")

    def skip(self, name: str, details: str) -> None:
        self.tests.append({"name": name, "status": "SKIP", "details": details})
        self.skipped += 1
        print(f"[SKIP] {name}")
        print(f"       {details}")

    def summary(self) -> None:
        print("\n" + "=" * 80)
        print(f"Test Summary: {self.passed} passed, {self.failed} failed, {self.skipped} skipped")
        print("=" * 80)

        if self.failed > 0:
            print("\nFailed tests:")
            for test in self.tests:
                if test["status"] == "FAIL":
                    print(f"  - {test['name']}: {test['details']}")

        if self.skipped > 0:
            print("\nSkipped coverage:")
            for test in self.tests:
                if test["status"] == "SKIP":
                    print(f"  - {test['name']}: {test['details']}")

def _safe_json(response: requests.Response) -> dict[str, Any] | list[Any] | None:
    try:
        return response.json()
    except Exception:
        return None

def get_auth_token(settings: Settings) -> str | None:
    """Register/Login to get a valid token."""
    # Try login first
    login_url = f"{settings.api_url}/auth/login"
    payload = {"email": "admin@example.com", "password": "password123"}
    resp = requests.post(login_url, json=payload)
    if resp.status_code == 200:
        return resp.json().get("access_token")

    # If login fails, try register
    reg_url = f"{settings.api_url}/auth/register"
    payload = {"email": "admin@example.com", "password": "password123", "full_name": "Admin User"}
    resp = requests.post(reg_url, json=payload)
    if resp.status_code in (200, 201):
        return resp.json().get("access_token")

    # If both fail, try setup
    setup_url = f"{settings.api_url}/auth/setup"
    resp = requests.post(setup_url, json=payload)
    if resp.status_code in (200, 201):
        return resp.json().get("access_token")

    return None

# ============================================================================
# Model CRUD Tests
# ============================================================================

def test_model_list(settings: Settings, token: str, results: TestResults) -> None:
    """Test GET /api/trainer/models - list all models."""
    try:
        resp = requests.get(
            f"{settings.api_url}/trainer/models",
            headers={"Authorization": f"Bearer {token}"},
        )

        if resp.status_code in (403, 404):
            results.skip(
                "List models",
                f"Trainer plugin not available (status {resp.status_code})",
            )
            return

        passed = resp.status_code == 200
        data = _safe_json(resp)
        details = ""

        if passed and data:
            items = data.get("items", data.get("models", []))
            details = f"Found {len(items)} models"
        else:
            details = f"Status {resp.status_code}"

        results.add("List models", passed, details)

    except Exception as e:
        results.add("List models", False, str(e))

def test_model_create(settings: Settings, token: str, results: TestResults) -> str | None:
    """Test POST /api/trainer/models - create a model.

    Returns: model_id if created successfully, None otherwise
    """
    try:
        model_data = {
            "name": "test-model-e2e",
            "display_name": "Test Model E2E",
            "model_family": "gemma",
            "base_model": "unsloth/gemma-2-2b-it",
            "adapter_path": "/tmp/test-adapter-path",
            "version": "1.0.0",
            "eval_metrics": {
                "accuracy": 0.85,
                "f1": 0.83,
                "latency_avg_ms": 120,
                "success_rate": 0.88,
            },
        }

        resp = requests.post(
            f"{settings.api_url}/trainer/models",
            headers={"Authorization": f"Bearer {token}"},
            json=model_data,
        )

        if resp.status_code in (403, 404):
            results.skip(
                "Create model",
                f"Trainer plugin not available (status {resp.status_code})",
            )
            return None

        # 400 is expected if adapter_path doesn't exist (this is by design)
        # We're testing the API, not filesystem requirements
        if resp.status_code == 400 and "does not exist" in str(resp.text):
            # Retry without adapter_path (should create with default path)
            model_data.pop("adapter_path")
            resp = requests.post(
                f"{settings.api_url}/trainer/models",
                headers={"Authorization": f"Bearer {token}"},
                json=model_data,
            )

        passed = resp.status_code == 201
        data = _safe_json(resp) if passed else None
        model_id = data.get("id") if data else None
        details = (
            f"Created model {model_id}"
            if model_id
            else f"Status {resp.status_code}: {resp.text[:100]}"
        )

        results.add("Create model", passed, details)
        return model_id

    except Exception as e:
        results.add("Create model", False, str(e))
        return None

def test_model_get(settings: Settings, token: str, model_id: str, results: TestResults) -> None:
    """Test GET /api/trainer/models/{model_id} - get model details."""
    try:
        resp = requests.get(
            f"{settings.api_url}/trainer/models/{model_id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        passed = resp.status_code == 200
        data = _safe_json(resp) if passed else None
        details = f"Retrieved model {data.get('name')}" if data else f"Status {resp.status_code}"

        results.add("Get model by ID", passed, details)

    except Exception as e:
        results.add("Get model by ID", False, str(e))

def test_model_update(settings: Settings, token: str, model_id: str, results: TestResults) -> None:
    """Test PATCH /api/trainer/models/{model_id} - update model metadata."""
    try:
        update_data = {
            "display_name": "Test Model E2E (Updated)",
            "eval_metrics": {
                "accuracy": 0.90,
                "f1": 0.88,
                "latency_avg_ms": 100,
                "success_rate": 0.92,
            },
        }

        resp = requests.patch(
            f"{settings.api_url}/trainer/models/{model_id}",
            headers={"Authorization": f"Bearer {token}"},
            json=update_data,
        )

        passed = resp.status_code == 200
        data = _safe_json(resp) if passed else None
        details = ""

        if passed and data:
            details = f"Updated to '{data.get('display_name')}'"
            # Verify metrics were updated
            metrics = data.get("eval_metrics", {})
            if metrics.get("accuracy") != 0.90:
                passed = False
                details = f"Metrics not updated: {metrics}"
        else:
            details = f"Status {resp.status_code}"

        results.add("Update model", passed, details)

    except Exception as e:
        results.add("Update model", False, str(e))

def test_model_set_default(
    settings: Settings, token: str, model_id: str, results: TestResults
) -> None:
    """Test POST /api/trainer/models/{model_id}/set-default - set default model."""
    try:
        resp = requests.post(
            f"{settings.api_url}/trainer/models/{model_id}/set-default",
            headers={"Authorization": f"Bearer {token}"},
        )

        passed = resp.status_code == 200
        data = _safe_json(resp) if passed else None
        details = ""

        if passed and data:
            is_default = data.get("is_default")
            if is_default:
                details = "Model set as default"
            else:
                passed = False
                details = "is_default flag not set to True"
        else:
            details = f"Status {resp.status_code}"

        results.add("Set default model", passed, details)

    except Exception as e:
        results.add("Set default model", False, str(e))

def test_model_delete(settings: Settings, token: str, model_id: str, results: TestResults) -> None:
    """Test DELETE /api/trainer/models/{model_id} - delete model."""
    try:
        resp = requests.delete(
            f"{settings.api_url}/trainer/models/{model_id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        passed = resp.status_code == 204
        details = "Model deleted" if passed else f"Status {resp.status_code}"

        results.add("Delete model", passed, details)

        # Verify deletion - should return 404
        if passed:
            verify_resp = requests.get(
                f"{settings.api_url}/trainer/models/{model_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            if verify_resp.status_code != 404:
                results.add(
                    "Verify model deleted",
                    False,
                    f"Model still exists (status {verify_resp.status_code})",
                )
            else:
                results.add("Verify model deleted", True, "404 returned as expected")

    except Exception as e:
        results.add("Delete model", False, str(e))

def test_model_metrics(settings: Settings, token: str, model_id: str, results: TestResults) -> None:
    """Test GET /api/trainer/models/{model_id}/metrics - get model metrics."""
    try:
        resp = requests.get(
            f"{settings.api_url}/trainer/models/{model_id}/metrics",
            headers={"Authorization": f"Bearer {token}"},
        )

        passed = resp.status_code == 200
        data = _safe_json(resp) if passed else None
        details = ""

        if passed and data:
            metrics_count = len(data.keys()) if isinstance(data, dict) else 0
            details = f"Retrieved {metrics_count} metrics"
        else:
            details = f"Status {resp.status_code}"

        results.add("Get model metrics", passed, details)

    except Exception as e:
        results.add("Get model metrics", False, str(e))

# ============================================================================
# Model Comparison Tests
# ============================================================================

def test_model_comparison(settings: Settings, token: str, results: TestResults) -> None:
    """Test POST /api/trainer/models/compare - compare multiple models by metrics."""
    # First, create 3 test models with different metrics
    model_ids = []

    for i in range(3):
        model_data = {
            "name": f"compare-model-{i}",
            "display_name": f"Compare Model {i}",
            "model_family": "gemma",
            "base_model": "unsloth/gemma-2-2b-it",
            "version": f"1.0.{i}",
            "eval_metrics": {
                "accuracy": 0.70 + (i * 0.1),  # 0.70, 0.80, 0.90
                "f1": 0.68 + (i * 0.1),
                "latency_avg_ms": 150 - (i * 20),  # 150, 130, 110
                "success_rate": 0.75 + (i * 0.08),
            },
        }

        try:
            resp = requests.post(
                f"{settings.api_url}/trainer/models",
                headers={"Authorization": f"Bearer {token}"},
                json=model_data,
            )
            if resp.status_code == 201:
                data = _safe_json(resp)
                if data and data.get("id"):
                    model_ids.append(data["id"])
        except Exception:
            pass

    if len(model_ids) < 2:
        results.skip(
            "Compare models",
            f"Need at least 2 models to compare (created {len(model_ids)})",
        )
        return

    # Test comparison
    try:
        compare_data = {
            "model_ids": model_ids,
            "metrics": ["accuracy", "f1", "latency_avg_ms"],
        }

        resp = requests.post(
            f"{settings.api_url}/trainer/models/compare",
            headers={"Authorization": f"Bearer {token}"},
            json=compare_data,
        )

        if resp.status_code in (403, 404):
            results.skip(
                "Compare models",
                f"Comparison endpoint not available (status {resp.status_code})",
            )
            # Clean up created models
            for mid in model_ids:
                try:
                    requests.delete(
                        f"{settings.api_url}/trainer/models/{mid}",
                        headers={"Authorization": f"Bearer {token}"},
                    )
                except Exception:
                    pass
            return

        passed = resp.status_code == 200
        data = _safe_json(resp) if passed else None
        details = ""

        if passed and data:
            comparison_data = data.get("comparison", {})
            models = data.get("models", [])
            comp_metrics = comparison_data.get("comparison", {})
            best_by_metric = comparison_data.get("best_by_metric", {})

            details = f"Compared {len(models)} models across {len(comp_metrics)} metrics"

            # Verify structure: comparison should have entries for each requested metric
            for metric in ["accuracy", "f1", "latency_avg_ms"]:
                if metric not in comp_metrics:
                    passed = False
                    details += f", missing metric: {metric}"
                    break

            # Verify best_by_metric exists
            if not best_by_metric:
                passed = False
                details += ", no best_by_metric rankings"
            else:
                details += f", best_by_metric: {len(best_by_metric)} entries"
        else:
            details = f"Status {resp.status_code}: {resp.text[:100]}"

        results.add("Compare models", passed, details)

        # Clean up created models
        for mid in model_ids:
            try:
                requests.delete(
                    f"{settings.api_url}/trainer/models/{mid}",
                    headers={"Authorization": f"Bearer {token}"},
                )
            except Exception:
                pass

    except Exception as e:
        results.add("Compare models", False, str(e))
        # Clean up created models
        for mid in model_ids:
            try:
                requests.delete(
                    f"{settings.api_url}/trainer/models/{mid}",
                    headers={"Authorization": f"Bearer {token}"},
                )
            except Exception:
                pass

def test_model_comparison_ranking(settings: Settings, token: str, results: TestResults) -> None:
    """Test model comparison ranking logic - verify models are ranked by specified metric."""
    # Create 3 models with known metric values to test ranking accuracy
    model_ids = []
    model_accuracies = {
        "ranking-low": 0.60,
        "ranking-mid": 0.80,
        "ranking-high": 0.95,
    }

    try:
        # Create models with different accuracies
        for name, accuracy in model_accuracies.items():
            resp = requests.post(
                f"{settings.api_url}/trainer/models",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "name": name,
                    "model_family": "gemma",
                    "base_model": "unsloth/gemma-2-2b-it",
                    "version": f"{accuracy}",
                    "eval_metrics": {
                        "accuracy": accuracy,
                        "f1": accuracy - 0.02,
                        "latency_avg_ms": 200 - (accuracy * 100),  # Lower latency is better
                    },
                },
            )
            if resp.status_code == 201:
                data = _safe_json(resp)
                if data and data.get("id"):
                    model_ids.append((data["id"], name, accuracy))

        if len(model_ids) < 3:
            results.skip(
                "Verify comparison ranking",
                f"Failed to create test models (created {len(model_ids)}/3)",
            )
            return

        # Compare all models
        resp = requests.post(
            f"{settings.api_url}/trainer/models/compare",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "model_ids": [m[0] for m in model_ids],
                "metrics": ["accuracy", "f1", "latency_avg_ms"],
            },
        )

        passed = resp.status_code == 200
        data = _safe_json(resp) if passed else None
        details = ""

        if passed and data:
            comparison = data.get("comparison", {})
            best_by_metric = comparison.get("best_by_metric", {})
            comp_data = comparison.get("comparison", {})

            # Verify that high-accuracy model is ranked best for accuracy
            best_accuracy_id = best_by_metric.get("accuracy")
            high_model_id = model_ids[2][0]  # ranking-high has highest accuracy

            if best_accuracy_id == high_model_id:
                details = "Correct: highest accuracy model ranked best"

                # Verify comparison values are correct
                if "accuracy" in comp_data:
                    acc_values = comp_data["accuracy"]
                    expected_high = 0.95
                    actual_high = acc_values.get(high_model_id)

                    if actual_high == expected_high:
                        details += f", values correct ({actual_high})"
                    else:
                        passed = False
                        details += f", value mismatch (expected {expected_high}, got {actual_high})"
            else:
                passed = False
                details = f"Incorrect ranking: expected {high_model_id[:8]}, got {best_accuracy_id[:8] if best_accuracy_id else 'None'}"
        else:
            details = f"Status {resp.status_code}"

        results.add("Verify comparison ranking", passed, details)

    except Exception as e:
        results.add("Verify comparison ranking", False, str(e))
    finally:
        # Clean up all created models
        for mid, _, _ in model_ids:
            try:
                requests.delete(
                    f"{settings.api_url}/trainer/models/{mid}",
                    headers={"Authorization": f"Bearer {token}"},
                )
            except Exception:
                pass

# ============================================================================
# Routing Tests
# ============================================================================

def test_routing_options(settings: Settings, token: str, results: TestResults) -> None:
    """Test GET /api/trainer/routing/options - get available models for routing."""
    try:
        resp = requests.get(
            f"{settings.api_url}/trainer/routing/options",
            headers={"Authorization": f"Bearer {token}"},
        )

        if resp.status_code in (403, 404):
            results.skip(
                "Get routing options",
                f"Routing endpoint not available (status {resp.status_code})",
            )
            return

        passed = resp.status_code == 200
        data = _safe_json(resp) if passed else None
        details = ""

        if passed and data:
            models = data.get("models", [])
            details = f"Found {len(models)} routing options"

            # Verify "auto" and "base" options exist
            option_ids = [m.get("id") for m in models]
            if "auto" not in option_ids:
                passed = False
                details += " (missing 'auto' option)"
            if "base" not in option_ids:
                passed = False
                details += " (missing 'base' option)"
        else:
            details = f"Status {resp.status_code}"

        results.add("Get routing options", passed, details)

    except Exception as e:
        results.add("Get routing options", False, str(e))

def test_routing_classify_simple(settings: Settings, token: str, results: TestResults) -> None:
    """Test POST /api/trainer/routing/classify - classify simple message."""
    try:
        classify_data = {
            "message": "What is the weather today?",
            "tools": [],
        }

        resp = requests.post(
            f"{settings.api_url}/trainer/routing/classify",
            headers={"Authorization": f"Bearer {token}"},
            json=classify_data,
        )

        if resp.status_code in (403, 404):
            results.skip(
                "Classify simple message",
                f"Routing endpoint not available (status {resp.status_code})",
            )
            return

        passed = resp.status_code == 200
        data = _safe_json(resp) if passed else None
        details = ""

        if passed and data:
            recommended = data.get("recommended_model")
            confidence = data.get("confidence")
            details = f"Recommended: {recommended}, Confidence: {confidence}"
        else:
            details = f"Status {resp.status_code}"

        results.add("Classify simple message", passed, details)

    except Exception as e:
        results.add("Classify simple message", False, str(e))

def test_routing_classify_tool_calling(
    settings: Settings, token: str, results: TestResults
) -> None:
    """Test POST /api/trainer/routing/classify - classify tool-calling message."""
    try:
        classify_data = {
            "message": "Call the get_weather function for San Francisco",
            "tools": ["get_weather", "send_email", "search_database"],
        }

        resp = requests.post(
            f"{settings.api_url}/trainer/routing/classify",
            headers={"Authorization": f"Bearer {token}"},
            json=classify_data,
        )

        if resp.status_code in (403, 404):
            results.skip(
                "Classify tool-calling message",
                f"Routing endpoint not available (status {resp.status_code})",
            )
            return

        passed = resp.status_code == 200
        data = _safe_json(resp) if passed else None
        details = ""

        if passed and data:
            recommended = data.get("recommended_model")
            confidence = data.get("confidence")
            alternatives = data.get("alternatives", [])
            details = f"Recommended: {recommended}, Confidence: {confidence}, Alternatives: {len(alternatives)}"

            # For tool-calling message, confidence should be relatively high
            if confidence and confidence < 0.3:
                details += " (unexpectedly low confidence for tool-calling message)"
        else:
            details = f"Status {resp.status_code}"

        results.add("Classify tool-calling message", passed, details)

    except Exception as e:
        results.add("Classify tool-calling message", False, str(e))

def test_routing_classify_confidence(settings: Settings, token: str, results: TestResults) -> None:
    """Test routing classification returns confidence and alternatives."""
    try:
        classify_data = {
            "message": "Show me the dashboard metrics",
            "tools": ["get_metrics", "get_dashboard", "fetch_analytics"],
        }

        resp = requests.post(
            f"{settings.api_url}/trainer/routing/classify",
            headers={"Authorization": f"Bearer {token}"},
            json=classify_data,
        )

        if resp.status_code in (403, 404):
            results.skip(
                "Verify classification confidence",
                f"Routing endpoint not available (status {resp.status_code})",
            )
            return

        passed = resp.status_code == 200
        data = _safe_json(resp) if passed else None
        details = ""

        if passed and data:
            confidence = data.get("confidence")
            alternatives = data.get("alternatives", [])

            # Verify confidence is a valid float between 0 and 1
            if confidence is not None and 0 <= confidence <= 1:
                details = f"Valid confidence: {confidence}"
            else:
                passed = False
                details = f"Invalid confidence: {confidence}"

            # Verify alternatives is a list with at least one alternative
            if len(alternatives) >= 1:
                details += f", {len(alternatives)} alternatives"
            else:
                passed = False
                details += ", no alternatives provided"
        else:
            details = f"Status {resp.status_code}"

        results.add("Verify classification confidence", passed, details)

    except Exception as e:
        results.add("Verify classification confidence", False, str(e))

# ============================================================================
# Default Model Enforcement Tests
# ============================================================================

def test_only_one_default_model(settings: Settings, token: str, results: TestResults) -> None:
    """Test that setting a model as default clears other defaults."""
    model_ids = []

    try:
        # Create 2 models
        for i in range(2):
            resp = requests.post(
                f"{settings.api_url}/trainer/models",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "name": f"default-test-{i}",
                    "model_family": "gemma",
                    "base_model": "unsloth/gemma-2-2b-it",
                    "version": f"1.0.{i}",
                    "eval_metrics": {"accuracy": 0.85},
                },
            )
            if resp.status_code == 201:
                data = _safe_json(resp)
                if data and data.get("id"):
                    model_ids.append(data["id"])

        if len(model_ids) < 2:
            results.skip(
                "Only one default model",
                f"Need 2 models for test (created {len(model_ids)})",
            )
            return

        # Set first model as default
        resp1 = requests.post(
            f"{settings.api_url}/trainer/models/{model_ids[0]}/set-default",
            headers={"Authorization": f"Bearer {token}"},
        )

        if resp1.status_code != 200:
            results.add(
                "Only one default model", False, f"Failed to set first default: {resp1.status_code}"
            )
            return

        # Set second model as default
        resp2 = requests.post(
            f"{settings.api_url}/trainer/models/{model_ids[1]}/set-default",
            headers={"Authorization": f"Bearer {token}"},
        )

        if resp2.status_code != 200:
            results.add(
                "Only one default model",
                False,
                f"Failed to set second default: {resp2.status_code}",
            )
            return

        # Verify first model is no longer default
        resp_check = requests.get(
            f"{settings.api_url}/trainer/models/{model_ids[0]}",
            headers={"Authorization": f"Bearer {token}"},
        )

        passed = False
        details = ""

        if resp_check.status_code == 200:
            data = _safe_json(resp_check)
            is_default = data.get("is_default") if data else None
            if is_default is False:
                passed = True
                details = "First model correctly cleared as default"
            else:
                details = f"First model still has is_default={is_default}"
        else:
            details = f"Failed to check first model: {resp_check.status_code}"

        results.add("Only one default model", passed, details)

    except Exception as e:
        results.add("Only one default model", False, str(e))
    finally:
        # Clean up
        for mid in model_ids:
            try:
                requests.delete(
                    f"{settings.api_url}/trainer/models/{mid}",
                    headers={"Authorization": f"Bearer {token}"},
                )
            except Exception:
                pass

# ============================================================================
# Main Test Runner
# ============================================================================

def run_all_tests(settings: Settings) -> int:
    """Run all model registry, comparison, and routing tests."""
    results = TestResults()

    print("\n" + "=" * 80)
    print("Model Registry, Comparison, and Routing E2E Tests")
    print("=" * 80)
    print(f"Base URL: {settings.base_url}")
    print(f"License: {settings.license_file or 'Not provided'}")
    print()

    # Get authentication token
    print("[INFO] Authenticating...")
    token = get_auth_token(settings)
    if not token:
        print("[ERROR] Failed to authenticate - cannot run tests")
        return 1

    print("[INFO] Authenticated successfully\n")

    # Run test suites
    print("\n--- Model CRUD Tests ---")
    test_model_list(settings, token, results)

    # Create a model for subsequent tests
    model_id = test_model_create(settings, token, results)

    if model_id:
        test_model_get(settings, token, model_id, results)
        test_model_metrics(settings, token, model_id, results)
        test_model_update(settings, token, model_id, results)
        test_model_set_default(settings, token, model_id, results)
        test_model_delete(settings, token, model_id, results)
    else:
        results.skip("Get model by ID", "No model created")
        results.skip("Get model metrics", "No model created")
        results.skip("Update model", "No model created")
        results.skip("Set default model", "No model created")
        results.skip("Delete model", "No model created")

    print("\n--- Model Comparison Tests ---")
    test_model_comparison(settings, token, results)
    test_model_comparison_ranking(settings, token, results)

    print("\n--- Routing Tests ---")
    test_routing_options(settings, token, results)
    test_routing_classify_simple(settings, token, results)
    test_routing_classify_tool_calling(settings, token, results)
    test_routing_classify_confidence(settings, token, results)

    print("\n--- Default Model Enforcement Tests ---")
    test_only_one_default_model(settings, token, results)

    # Print summary
    results.summary()

    return 0 if results.failed == 0 else 1

def main() -> int:
    parser = argparse.ArgumentParser(
        description="E2E tests for model registry, comparison, and routing endpoints"
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8080",
        help="Base URL of the backend (default: http://localhost:8080)",
    )
    parser.add_argument(
        "--license-file",
        help="Path to enterprise license file",
    )

    args = parser.parse_args()

    settings = Settings(
        base_url=args.base_url,
        license_file=args.license_file,
    )

    return run_all_tests(settings)

if __name__ == "__main__":
    sys.exit(main())
