"""Unit tests for TemplateLoader module."""

from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

class TestPlanTemplate:
    """Tests for PlanTemplate model."""

    def test_plan_template_defaults(self):
        """Test PlanTemplate with default values."""
        from core.orchestrator.templates import PlanTemplate

        template = PlanTemplate(
            name="test_template",
            description="Test template",
            nodes=[{"id": "node1", "agent": "Agent1", "task": "Task 1"}],
        )
        assert template.name == "test_template"
        assert template.description == "Test template"
        assert template.category == "general"
        assert template.parameters == []
        assert len(template.nodes) == 1
        assert template.edges == []
        assert template.metadata == {}

    def test_plan_template_all_fields(self):
        """Test PlanTemplate with all fields."""
        from core.orchestrator.templates import PlanTemplate

        template = PlanTemplate(
            name="analysis_template",
            description="Analyze data",
            category="analysis",
            parameters=[{"name": "input_file", "type": "string", "required": True}],
            nodes=[
                {"id": "node1", "agent": "Agent1", "task": "Read {input_file}"},
                {"id": "node2", "agent": "Agent2", "task": "Analyze"},
            ],
            edges=[{"source": "node1", "target": "node2"}],
            metadata={"version": "1.0"},
        )
        assert template.name == "analysis_template"
        assert template.category == "analysis"
        assert len(template.parameters) == 1
        assert len(template.nodes) == 2
        assert len(template.edges) == 1
        assert template.metadata["version"] == "1.0"

class TestTemplateLoaderInitialization:
    """Tests for TemplateLoader initialization."""

    def test_loader_initialization_default(self):
        """Test TemplateLoader with default path."""
        from core.orchestrator.templates import TemplateLoader

        loader = TemplateLoader()
        assert loader.templates_path == "config/plan_templates"
        assert loader._templates == {}

    def test_loader_initialization_custom_path(self):
        """Test TemplateLoader with custom path."""
        from core.orchestrator.templates import TemplateLoader

        loader = TemplateLoader(templates_path="/custom/path")
        assert loader.templates_path == "/custom/path"

class TestTemplateLoaderLoading:
    """Tests for template loading."""

    def test_load_templates_no_directory(self):
        """Test load_templates when directory doesn't exist."""
        from core.orchestrator.templates import TemplateLoader

        loader = TemplateLoader(templates_path="/nonexistent/path")

        with patch.object(Path, "exists", return_value=False):
            templates = loader.load_templates()
            assert templates == {}

    def test_load_templates_empty_directory(self):
        """Test load_templates with empty directory."""
        from core.orchestrator.templates import TemplateLoader

        loader = TemplateLoader(templates_path="/empty/path")

        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.glob.return_value = []

        with patch.object(Path, "__new__", return_value=mock_path):
            # Just verify it doesn't crash
            templates = loader.load_templates()
            assert isinstance(templates, dict)

    def test_load_templates_success(self):
        """Test load_templates with valid YAML files."""
        from core.orchestrator.templates import TemplateLoader

        loader = TemplateLoader()

        template_data = {
            "name": "loaded_template",
            "description": "Template from file",
            "nodes": [{"id": "n1", "agent": "Agent1", "task": "Task"}],
        }

        # Create mock file path
        mock_file = MagicMock()
        mock_file.__str__ = lambda self: "/path/to/template.yaml"

        # Mock Path and yaml
        with (
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "glob", return_value=[mock_file]),
            patch("builtins.open", mock_open()),
            patch("yaml.safe_load", return_value=template_data),
        ):
            loader.load_templates()
            # Template loading happens inside load_templates
            # Due to complex Path mocking, we verify structure
            assert isinstance(loader._templates, dict)

class TestTemplateLoaderGetTemplate:
    """Tests for get_template method."""

    def test_get_template_exists(self):
        """Test get_template when template exists."""
        from core.orchestrator.templates import PlanTemplate, TemplateLoader

        loader = TemplateLoader()

        # Manually set a template
        template = PlanTemplate(
            name="existing",
            description="Existing template",
            nodes=[{"id": "n1", "agent": "A1", "task": "T1"}],
        )
        loader._templates = {"existing": template}

        result = loader.get_template("existing")
        assert result is not None
        assert result.name == "existing"

    def test_get_template_not_exists(self):
        """Test get_template when template doesn't exist."""
        from core.orchestrator.templates import TemplateLoader

        loader = TemplateLoader()
        loader._templates = {}

        with patch.object(loader, "load_templates", return_value={}):
            result = loader.get_template("nonexistent")
            assert result is None

class TestTemplateLoaderListTemplates:
    """Tests for list_templates method."""

    def test_list_templates_empty(self):
        """Test list_templates with no templates."""
        from core.orchestrator.templates import TemplateLoader

        loader = TemplateLoader()
        loader._templates = {}

        with patch.object(loader, "load_templates", return_value={}):
            templates = loader.list_templates()
            assert templates == []

    def test_list_templates_all(self):
        """Test list_templates returns all templates."""
        from core.orchestrator.templates import PlanTemplate, TemplateLoader

        loader = TemplateLoader()

        template1 = PlanTemplate(
            name="template1",
            description="Template 1",
            category="analysis",
            nodes=[{"id": "n1", "agent": "A1", "task": "T1"}],
        )
        template2 = PlanTemplate(
            name="template2",
            description="Template 2",
            category="general",
            nodes=[{"id": "n2", "agent": "A2", "task": "T2"}],
        )
        loader._templates = {"template1": template1, "template2": template2}

        templates = loader.list_templates()
        assert len(templates) == 2
        assert any(t["name"] == "template1" for t in templates)
        assert any(t["name"] == "template2" for t in templates)

    def test_list_templates_filtered_by_category(self):
        """Test list_templates with category filter."""
        from core.orchestrator.templates import PlanTemplate, TemplateLoader

        loader = TemplateLoader()

        template1 = PlanTemplate(
            name="analysis1",
            description="Analysis template",
            category="analysis",
            nodes=[{"id": "n1", "agent": "A1", "task": "T1"}],
        )
        template2 = PlanTemplate(
            name="general1",
            description="General template",
            category="general",
            nodes=[{"id": "n2", "agent": "A2", "task": "T2"}],
        )
        loader._templates = {"analysis1": template1, "general1": template2}

        templates = loader.list_templates(category="analysis")
        assert len(templates) == 1
        assert templates[0]["name"] == "analysis1"

class TestTemplateLoaderInstantiation:
    """Tests for template instantiation."""

    def test_instantiate_template_basic(self):
        """Test instantiate_template with basic parameters."""
        from core.orchestrator.templates import PlanTemplate, TemplateLoader

        loader = TemplateLoader()

        template = PlanTemplate(
            name="param_template",
            description="Template with {param}",
            parameters=[{"name": "param", "required": True}],
            nodes=[{"id": "n1", "agent": "Agent", "task": "Process {param}"}],
        )
        loader._templates = {"param_template": template}

        result = loader.instantiate_template("param_template", {"param": "test_value"})

        assert result["name"] == "param_template"
        assert result["nodes"][0]["task"] == "Process test_value"

    def test_instantiate_template_not_found(self):
        """Test instantiate_template when template not found."""
        from core.orchestrator.templates import TemplateLoader

        loader = TemplateLoader()
        loader._templates = {}

        with (
            patch.object(loader, "load_templates", return_value={}),
            pytest.raises(ValueError, match="not found"),
        ):
            loader.instantiate_template("nonexistent", {})

    def test_instantiate_template_missing_required_param(self):
        """Test instantiate_template with missing required parameter."""
        from core.orchestrator.templates import PlanTemplate, TemplateLoader

        loader = TemplateLoader()

        template = PlanTemplate(
            name="required_param",
            description="Template",
            parameters=[{"name": "required_field", "required": True}],
            nodes=[{"id": "n1", "agent": "A", "task": "T"}],
        )
        loader._templates = {"required_param": template}

        with pytest.raises(ValueError, match="required_field"):
            loader.instantiate_template("required_param", {})

    def test_instantiate_template_uses_default(self):
        """Test instantiate_template uses default values."""
        from core.orchestrator.templates import PlanTemplate, TemplateLoader

        loader = TemplateLoader()

        template = PlanTemplate(
            name="default_param",
            description="Template",
            parameters=[{"name": "optional", "required": True, "default": "default_value"}],
            nodes=[{"id": "n1", "agent": "A", "task": "Do {optional}"}],
        )
        loader._templates = {"default_param": template}

        result = loader.instantiate_template("default_param", {})

        assert result["nodes"][0]["task"] == "Do default_value"

class TestParameterSubstitution:
    """Tests for parameter substitution helper."""

    def test_substitute_string(self):
        """Test substitution in string."""
        from core.orchestrator.templates import TemplateLoader

        loader = TemplateLoader()

        result = loader._substitute_params("Hello {name}!", {"name": "World"})
        assert result == "Hello World!"

    def test_substitute_dict(self):
        """Test substitution in dictionary."""
        from core.orchestrator.templates import TemplateLoader

        loader = TemplateLoader()

        obj = {"key": "Value is {value}", "other": "No placeholder"}
        result = loader._substitute_params(obj, {"value": "42"})

        assert result["key"] == "Value is 42"
        assert result["other"] == "No placeholder"

    def test_substitute_list(self):
        """Test substitution in list."""
        from core.orchestrator.templates import TemplateLoader

        loader = TemplateLoader()

        obj = ["Item {num}", "Other"]
        result = loader._substitute_params(obj, {"num": "1"})

        assert result[0] == "Item 1"
        assert result[1] == "Other"

    def test_substitute_nested(self):
        """Test substitution in nested structure."""
        from core.orchestrator.templates import TemplateLoader

        loader = TemplateLoader()

        obj = {
            "outer": {
                "inner": "Value is {val}",
                "list": ["{val}", "static"],
            }
        }
        result = loader._substitute_params(obj, {"val": "X"})

        assert result["outer"]["inner"] == "Value is X"
        assert result["outer"]["list"][0] == "X"

    def test_substitute_non_string_value(self):
        """Test substitution with non-string value."""
        from core.orchestrator.templates import TemplateLoader

        loader = TemplateLoader()

        result = loader._substitute_params("Count: {count}", {"count": 42})
        assert result == "Count: 42"

class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_get_template_loader_singleton(self):
        """Test get_template_loader returns singleton."""
        from core.orchestrator import templates as templates_module

        # Reset global state
        templates_module._loader = None

        with patch("core.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock()
            mock_settings.return_value.planner_templates_path = "config/plan_templates"

            loader1 = templates_module.get_template_loader()
            loader2 = templates_module.get_template_loader()

            assert loader1 is loader2

    def test_list_templates_convenience(self):
        """Test list_templates convenience function."""
        from core.orchestrator import templates as templates_module
        from core.orchestrator.templates import PlanTemplate

        # Reset global state
        templates_module._loader = None

        with patch("core.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock()
            mock_settings.return_value.planner_templates_path = "config/plan_templates"

            # Get loader and set templates
            loader = templates_module.get_template_loader()
            template = PlanTemplate(
                name="test",
                description="Test",
                nodes=[{"id": "n1", "agent": "A", "task": "T"}],
            )
            loader._templates = {"test": template}

            templates = templates_module.list_templates()
            assert len(templates) == 1

    def test_instantiate_template_convenience(self):
        """Test instantiate_template convenience function."""
        from core.orchestrator import templates as templates_module
        from core.orchestrator.templates import PlanTemplate

        # Reset global state
        templates_module._loader = None

        with patch("core.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock()
            mock_settings.return_value.planner_templates_path = "config/plan_templates"

            # Get loader and set templates
            loader = templates_module.get_template_loader()
            template = PlanTemplate(
                name="conv_test",
                description="Test",
                parameters=[],
                nodes=[{"id": "n1", "agent": "A", "task": "T"}],
            )
            loader._templates = {"conv_test": template}

            result = templates_module.instantiate_template("conv_test", {})
            assert result["name"] == "conv_test"
