"""Unit tests for ScenarioRegistry and ScenarioConfig.

Tests scenario configuration validation, registry discovery, and loading.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from core.workflows.scenarios import (
    InputSchema,
    OutputSchema,
    ScenarioConfig,
    ScenarioRegistry,
    TriggerConfig,
    get_registry,
    load_scenario,
)

class TestTriggerConfig:
    """Tests for TriggerConfig model."""

    def test_empty_trigger_config(self):
        """Should allow all optional fields."""
        config = TriggerConfig()
        assert config.chat_command is None
        assert config.api_endpoint is None
        assert config.ui_button is None

    def test_full_trigger_config(self):
        """Should accept all trigger types."""
        config = TriggerConfig(
            chat_command="/analyze",
            api_endpoint="/api/scenarios/analyze/trigger",
            ui_button={"label": "Analyze", "location": "toolbar"},
        )
        assert config.chat_command == "/analyze"
        assert config.api_endpoint == "/api/scenarios/analyze/trigger"
        assert config.ui_button["label"] == "Analyze"

class TestInputSchema:
    """Tests for InputSchema model."""

    def test_minimal_input_schema(self):
        """Should require name, type, description."""
        schema = InputSchema(
            name="report_file",
            type="file",
            description="Upload report file",
        )
        assert schema.name == "report_file"
        assert schema.type == "file"
        assert schema.required is True
        assert schema.default is None

    def test_full_input_schema(self):
        """Should accept all fields."""
        schema = InputSchema(
            name="count",
            type="number",
            required=False,
            description="Number of items",
            default=10,
        )
        assert schema.required is False
        assert schema.default == 10

    def test_invalid_type_rejected(self):
        """Should reject invalid input types."""
        with pytest.raises(ValueError):
            InputSchema(
                name="test",
                type="invalid_type",
                description="Test",
            )

class TestOutputSchema:
    """Tests for OutputSchema model."""

    def test_output_schema_types(self):
        """Should accept valid output types."""
        for output_type in ["markdown", "json", "file", "table"]:
            schema = OutputSchema(name="result", type=output_type)
            assert schema.type == output_type

    def test_invalid_output_type_rejected(self):
        """Should reject invalid output types."""
        with pytest.raises(ValueError):
            OutputSchema(name="result", type="invalid")

class TestScenarioConfig:
    """Tests for ScenarioConfig model."""

    @pytest.fixture
    def valid_config_dict(self):
        """Provide valid config dictionary."""
        return {
            "name": "test_scenario",
            "display_name": "Test Scenario",
            "description": "A test workflow scenario",
            "domain": "dev",
            "version": "1.0.0",
            "triggers": {"chat_command": "/test"},
            "inputs": [{"name": "input1", "type": "string", "description": "Test input"}],
            "outputs": [{"name": "output1", "type": "markdown"}],
            "required_agents": ["code_reviewer", "devops_engineer"],
        }

    def test_valid_config(self, valid_config_dict):
        """Should validate correct config."""
        config = ScenarioConfig.model_validate(valid_config_dict)
        assert config.name == "test_scenario"
        assert config.domain == "dev"
        assert len(config.required_agents) == 2

    def test_default_values(self):
        """Should provide sensible defaults."""
        config = ScenarioConfig(
            name="minimal",
            display_name="Minimal",
            description="Minimal config",
            domain="finance",
        )
        assert config.version == "1.0.0"
        assert config.inputs == []
        assert config.outputs == []
        assert config.required_agents == []
        assert config.observability["metrics_enabled"] is True

    def test_invalid_domain_rejected(self):
        """Should reject invalid domain."""
        with pytest.raises(ValueError):
            ScenarioConfig(
                name="test",
                display_name="Test",
                description="Test",
                domain="invalid_domain",
            )

    def test_valid_domains(self):
        """Should accept all valid domains."""
        for domain in ["finance", "dev", "operations", "sales", "cross-framework"]:
            config = ScenarioConfig(
                name="test",
                display_name="Test",
                description="Test",
                domain=domain,
            )
            assert config.domain == domain

class TestScenarioRegistry:
    """Tests for ScenarioRegistry class."""

    @pytest.fixture
    def temp_scenarios_dir(self, tmp_path):
        """Create temporary scenarios directory."""
        scenarios_dir = tmp_path / "scenarios"
        scenarios_dir.mkdir()
        return scenarios_dir

    @pytest.fixture
    def sample_scenario(self, temp_scenarios_dir):
        """Create a sample scenario in temp directory."""
        scenario_dir = temp_scenarios_dir / "test_scenario"
        scenario_dir.mkdir()

        # Create config.yaml
        config_yaml = """
name: test_scenario
display_name: Test Scenario
description: A test workflow
domain: dev
required_agents:
  - code_reviewer
"""
        (scenario_dir / "config.yaml").write_text(config_yaml)

        # Create workflow.json
        workflow_json = {
            "version": "1.0.0",
            "nodes": [
                {"id": "start", "type": "start", "position": {"x": 0, "y": 0}},
                {
                    "id": "review",
                    "type": "task",
                    "data": {"agent": "code_reviewer", "task": "Review code"},
                    "position": {"x": 200, "y": 0},
                },
                {"id": "end", "type": "end", "position": {"x": 400, "y": 0}},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "review"},
                {"id": "e2", "source": "review", "target": "end"},
            ],
        }
        (scenario_dir / "workflow.json").write_text(json.dumps(workflow_json))

        return scenario_dir

    def test_init_with_custom_dir(self, temp_scenarios_dir):
        """Should accept custom scenarios directory."""
        registry = ScenarioRegistry(str(temp_scenarios_dir))
        assert registry.scenarios_dir == temp_scenarios_dir

    def test_list_scenarios_empty_dir(self, temp_scenarios_dir):
        """Should return empty list for empty directory."""
        registry = ScenarioRegistry(str(temp_scenarios_dir))
        scenarios = registry.list_scenarios()
        assert scenarios == []

    def test_list_scenarios_nonexistent_dir(self, tmp_path):
        """Should return empty list for nonexistent directory."""
        registry = ScenarioRegistry(str(tmp_path / "nonexistent"))
        scenarios = registry.list_scenarios()
        assert scenarios == []

    def test_list_scenarios_discovers_scenarios(self, temp_scenarios_dir, sample_scenario):
        """Should discover scenarios from directory."""
        registry = ScenarioRegistry(str(temp_scenarios_dir))
        scenarios = registry.list_scenarios()

        assert len(scenarios) == 1
        assert scenarios[0].name == "test_scenario"

    def test_get_scenario_success(self, temp_scenarios_dir, sample_scenario):
        """Should load scenario config and workflow."""
        registry = ScenarioRegistry(str(temp_scenarios_dir))
        config, workflow = registry.get_scenario("test_scenario")

        assert config.name == "test_scenario"
        assert config.domain == "dev"
        assert len(workflow.nodes) == 3

    def test_get_scenario_not_found(self, temp_scenarios_dir):
        """Should raise FileNotFoundError for missing scenario."""
        registry = ScenarioRegistry(str(temp_scenarios_dir))

        with pytest.raises(FileNotFoundError, match="Scenario not found"):
            registry.get_scenario("nonexistent")

    def test_get_scenario_caches_result(self, temp_scenarios_dir, sample_scenario):
        """Should cache loaded scenarios."""
        registry = ScenarioRegistry(str(temp_scenarios_dir))

        # First load
        config1, workflow1 = registry.get_scenario("test_scenario")
        # Second load (from cache)
        config2, workflow2 = registry.get_scenario("test_scenario")

        assert config1 is config2
        assert workflow1 is workflow2

    def test_clear_cache(self, temp_scenarios_dir, sample_scenario):
        """Should clear cached scenarios."""
        registry = ScenarioRegistry(str(temp_scenarios_dir))

        registry.get_scenario("test_scenario")
        assert len(registry._cache) == 1

        registry.clear_cache()
        assert len(registry._cache) == 0

    def test_register_scenario(self, temp_scenarios_dir):
        """Should register scenario at runtime."""
        registry = ScenarioRegistry(str(temp_scenarios_dir))

        config = ScenarioConfig(
            name="runtime_scenario",
            display_name="Runtime",
            description="Registered at runtime",
            domain="dev",
        )
        # Create minimal workflow schema
        from core.workflows.schema import WorkflowSchema

        workflow = WorkflowSchema(
            nodes=[
                {"id": "start", "type": "start", "position": {"x": 0, "y": 0}},
                {"id": "end", "type": "end", "position": {"x": 100, "y": 0}},
            ],
            edges=[{"id": "e1", "source": "start", "target": "end"}],
        )

        registry.register_scenario(config, workflow)

        # Should be retrievable
        loaded_config, loaded_workflow = registry.get_scenario("runtime_scenario")
        assert loaded_config.name == "runtime_scenario"

class TestValidateScenario:
    """Tests for validate_scenario method."""

    @pytest.fixture
    def registry_with_scenario(self, tmp_path):
        """Create registry with a scenario."""
        scenarios_dir = tmp_path / "scenarios"
        scenarios_dir.mkdir()
        scenario_dir = scenarios_dir / "test"
        scenario_dir.mkdir()

        config_yaml = """
name: test
display_name: Test
description: Test
domain: dev
required_agents:
  - nonexistent_agent
  - another_missing
"""
        (scenario_dir / "config.yaml").write_text(config_yaml)

        workflow_json = {
            "version": "1.0.0",
            "nodes": [
                {"id": "start", "type": "start", "position": {"x": 0, "y": 0}},
                {"id": "end", "type": "end", "position": {"x": 100, "y": 0}},
            ],
            "edges": [{"id": "e1", "source": "start", "target": "end"}],
        }
        (scenario_dir / "workflow.json").write_text(json.dumps(workflow_json))

        return ScenarioRegistry(str(scenarios_dir))

    def test_validate_returns_errors_for_missing_agents(self, registry_with_scenario):
        """Should return errors for missing required agents."""
        with patch("core.workflows.scenarios.list_agents") as mock_list:
            mock_list.return_value = []  # No agents available
            errors = registry_with_scenario.validate_scenario("test")

        assert len(errors) >= 2
        assert any("nonexistent_agent" in e for e in errors)
        assert any("another_missing" in e for e in errors)

    def test_validate_returns_empty_for_valid(self, registry_with_scenario):
        """Should return empty list when all agents available."""
        mock_card = MagicMock()
        mock_card.name = "nonexistent_agent"
        mock_card2 = MagicMock()
        mock_card2.name = "another_missing"

        with patch("core.workflows.scenarios.list_agents") as mock_list:
            mock_list.return_value = [mock_card, mock_card2]
            errors = registry_with_scenario.validate_scenario("test")

        assert errors == []

class TestHelperFunctions:
    """Tests for module-level helper functions."""

    def test_load_scenario_function(self, tmp_path):
        """Should load scenario using convenience function."""
        scenarios_dir = tmp_path / "scenarios"
        scenarios_dir.mkdir()
        scenario_dir = scenarios_dir / "helper_test"
        scenario_dir.mkdir()

        config_yaml = """
name: helper_test
display_name: Helper Test
description: Test helper function
domain: finance
"""
        (scenario_dir / "config.yaml").write_text(config_yaml)
        workflow_json = {
            "version": "1.0.0",
            "nodes": [
                {"id": "start", "type": "start", "position": {"x": 0, "y": 0}},
                {"id": "end", "type": "end", "position": {"x": 100, "y": 0}},
            ],
            "edges": [{"id": "e1", "source": "start", "target": "end"}],
        }
        (scenario_dir / "workflow.json").write_text(json.dumps(workflow_json))

        config = load_scenario("helper_test", str(scenarios_dir))
        assert config.name == "helper_test"

    def test_get_registry_singleton(self):
        """Should return singleton registry."""
        # Reset singleton for test
        import core.workflows.scenarios as scenarios_module

        scenarios_module._default_registry = None

        registry1 = get_registry()
        registry2 = get_registry()

        assert registry1 is registry2
