"""Plan Template System - YAML-based templates for common workflows.

Templates provide shortcuts for frequently used patterns.
Target: ~200 LOC
"""

import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

logger = logging.getLogger("dryade.templates")

class PlanTemplate(BaseModel):
    """Plan template definition."""

    name: str
    description: str
    category: str = "general"
    parameters: list[dict[str, Any]] = []
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]] = []
    metadata: dict[str, Any] = {}

class TemplateLoader:
    """Loads and manages plan templates from YAML files.

    Templates are shortcuts for common workflows that can be instantiated
    with user-provided parameters.
    """

    def __init__(self, templates_path: str = "config/plan_templates"):
        """Initialize the template loader.

        Args:
            templates_path: Directory path containing YAML template files.
        """
        self.templates_path = templates_path
        self._templates = {}
        logger.info(f"[TEMPLATES] Template loader initialized with path: {templates_path}")

    def load_templates(self) -> dict[str, PlanTemplate]:
        """Load all templates from the templates directory."""
        templates = {}
        template_dir = Path(self.templates_path)

        if not template_dir.exists():
            logger.warning(f"[TEMPLATES] Template directory not found: {template_dir}")
            return templates

        for template_file in template_dir.glob("*.yaml"):
            try:
                with open(template_file) as f:
                    template_data = yaml.safe_load(f)

                template = PlanTemplate(**template_data)
                templates[template.name] = template
                logger.info(f"[TEMPLATES] Loaded template: {template.name}")
            except Exception as e:
                logger.error(f"[TEMPLATES] Failed to load template {template_file}: {e}")

        self._templates = templates
        logger.info(f"[TEMPLATES] ✓ Loaded {len(templates)} templates")
        return templates

    def get_template(self, name: str) -> PlanTemplate | None:
        """Get a template by name."""
        if not self._templates:
            self.load_templates()

        return self._templates.get(name)

    def list_templates(self, category: str | None = None) -> list[dict[str, Any]]:
        """List all available templates, optionally filtered by category."""
        if not self._templates:
            self.load_templates()

        templates = []
        for template in self._templates.values():
            if category and template.category != category:
                continue

            templates.append(
                {
                    "name": template.name,
                    "description": template.description,
                    "category": template.category,
                    "parameters": template.parameters,
                }
            )

        return templates

    def instantiate_template(
        self, template_name: str, parameters: dict[str, Any]
    ) -> dict[str, Any]:
        """Instantiate a template with provided parameters.

        Args:
            template_name: Name of the template to instantiate
            parameters: Parameter values to substitute

        Returns:
            Instantiated plan data ready for ExecutionPlan creation
        """
        template = self.get_template(template_name)
        if not template:
            raise ValueError(f"Template '{template_name}' not found")

        logger.info(f"[TEMPLATES] Instantiating template: {template_name}")
        logger.debug(f"[TEMPLATES] Parameters: {parameters}")

        # Validate required parameters
        for param in template.parameters:
            param_name = param.get("name")
            required = param.get("required", True)

            if required and param_name not in parameters:
                # Check for default value
                if "default" in param:
                    parameters[param_name] = param["default"]
                    logger.debug(
                        f"[TEMPLATES] Using default for '{param_name}': {param['default']}"
                    )
                else:
                    raise ValueError(f"Required parameter '{param_name}' not provided")

        # Substitute parameters in nodes
        instantiated_nodes = []
        for node in template.nodes:
            instantiated_node = self._substitute_params(node, parameters)
            instantiated_nodes.append(instantiated_node)

        # Substitute parameters in edges if needed
        instantiated_edges = []
        for edge in template.edges:
            instantiated_edge = self._substitute_params(edge, parameters)
            instantiated_edges.append(instantiated_edge)

        logger.info(f"[TEMPLATES] ✓ Template instantiated with {len(instantiated_nodes)} nodes")

        return {
            "name": template.name,
            "description": template.description,
            "nodes": instantiated_nodes,
            "edges": instantiated_edges,
            "reasoning": f"Instantiated from template '{template_name}'",
            "confidence": 0.9,  # Templates are pre-validated
        }

    def _substitute_params(self, obj: Any, parameters: dict[str, Any]) -> Any:
        """Recursively substitute parameter placeholders in an object.

        Placeholders use the format: {param_name}
        """
        if isinstance(obj, str):
            # Simple string substitution
            result = obj
            for key, value in parameters.items():
                placeholder = f"{{{key}}}"
                if placeholder in result:
                    # Convert value to string for substitution
                    str_value = str(value) if not isinstance(value, (list, dict)) else str(value)
                    result = result.replace(placeholder, str_value)
            return result

        elif isinstance(obj, dict):
            # Recursively substitute in dictionary
            return {k: self._substitute_params(v, parameters) for k, v in obj.items()}

        elif isinstance(obj, list):
            # Recursively substitute in list
            return [self._substitute_params(item, parameters) for item in obj]

        else:
            # Return as-is for other types
            return obj

# Global template loader instance
_loader: TemplateLoader | None = None

def get_template_loader() -> TemplateLoader:
    """Get or create global template loader instance."""
    global _loader
    if _loader is None:
        from core.config import get_settings

        settings = get_settings()
        templates_path = getattr(settings, "planner_templates_path", "config/plan_templates")
        _loader = TemplateLoader(templates_path)
    return _loader

def list_templates(category: str | None = None) -> list[dict[str, Any]]:
    """Convenience function to list templates."""
    loader = get_template_loader()
    return loader.list_templates(category)

def instantiate_template(template_name: str, parameters: dict[str, Any]) -> dict[str, Any]:
    """Convenience function to instantiate a template."""
    loader = get_template_loader()
    return loader.instantiate_template(template_name, parameters)
