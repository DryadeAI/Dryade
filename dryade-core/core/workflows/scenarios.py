"""Scenario Registry - Manages workflow scenario definitions.

Provides infrastructure for discovering, loading, and validating workflow
scenarios from disk-based configuration files.
Target: ~250 LOC
"""

import logging
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator

from core.adapters import list_agents
from core.workflows.schema import WorkflowSchema

logger = logging.getLogger("dryade.workflows.scenarios")

# =============================================================================
# Configuration Models
# =============================================================================

class TriggerConfig(BaseModel):
    """Configuration for how a scenario can be triggered."""

    chat_command: str | None = None  # e.g., "/analyze-report"
    api_endpoint: str | None = None  # e.g., "/workflow-scenarios/financial_reporting/trigger"
    ui_button: dict[str, str] | None = None  # {label, location}

class InputSchema(BaseModel):
    """Schema definition for scenario inputs."""

    name: str
    type: Literal["string", "file", "number", "boolean", "json"]
    required: bool = True
    description: str
    default: Any = None

class OutputSchema(BaseModel):
    """Schema definition for scenario outputs."""

    name: str
    type: Literal["markdown", "json", "file", "table"]

VALID_DOMAINS: frozenset[str] = frozenset(
    {
        "finance",
        "dev",
        "operations",
        "sales",
        "cross-framework",
        "productivity",
        "support",
        "testing",
    }
)

class ScenarioConfig(BaseModel):
    """Complete configuration for a workflow scenario.

    Loaded from YAML config files in scenario directories.
    """

    name: str
    display_name: str
    description: str
    domain: Literal[
        "finance",
        "dev",
        "operations",
        "sales",
        "cross-framework",
        "productivity",
        "support",
        "testing",
    ]
    difficulty: Literal["beginner", "intermediate", "advanced"] = "intermediate"
    version: str = "1.0.0"
    template_ref: str | None = None  # Reference to canonical template in _templates/
    triggers: TriggerConfig = Field(default_factory=TriggerConfig)
    inputs: list[InputSchema] = Field(default_factory=list)
    outputs: list[OutputSchema] = Field(default_factory=list)
    required_agents: list[str] = Field(default_factory=list)
    observability: dict[str, bool] = Field(
        default_factory=lambda: {"metrics_enabled": True, "log_tool_calls": True}
    )

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, v: str) -> str:
        if v not in VALID_DOMAINS:
            raise ValueError(f"Invalid domain '{v}'. Must be one of: {sorted(VALID_DOMAINS)}")
        return v

# =============================================================================
# Scenario Registry
# =============================================================================

class ScenarioRegistry:
    """Registry for discovering, loading, and validating workflow scenarios.

    Scenarios are stored in a directory structure:
        workflows/scenarios/
            financial_reporting/
                config.yaml      # ScenarioConfig
                workflow.json    # WorkflowSchema
            sprint_planning/
                config.yaml
                workflow.json

    Usage:
        registry = ScenarioRegistry("workflows/scenarios")
        scenarios = registry.list_scenarios()
        config, workflow = registry.get_scenario("financial_reporting")
    """

    def __init__(self, scenarios_dir: str = "workflows/scenarios"):
        """Initialize registry with scenarios directory.

        Args:
            scenarios_dir: Path to directory containing scenario subdirectories.
        """
        self._scenarios_dir = Path(scenarios_dir)
        self._cache: dict[str, tuple[ScenarioConfig, WorkflowSchema]] = {}
        logger.debug(f"[SCENARIO_REGISTRY] Initialized with dir: {scenarios_dir}")

    @property
    def scenarios_dir(self) -> Path:
        """Get the scenarios directory path."""
        return self._scenarios_dir

    def list_scenarios(self) -> list[ScenarioConfig]:
        """Discover and list all available scenarios.

        Internal scenarios (names starting with '_') are excluded from the
        user-facing list. These include templates (_templates/*), mock demos
        (_mock_demo), and synthetic test scenarios (_tool_node_test).

        Returns:
            List of ScenarioConfig objects for all discovered scenarios.
        """
        scenarios = []
        filtered_count = 0

        if not self._scenarios_dir.exists():
            logger.warning(
                f"[SCENARIO_REGISTRY] Scenarios directory not found: {self._scenarios_dir}"
            )
            return scenarios

        for scenario_path in self._scenarios_dir.iterdir():
            if not scenario_path.is_dir():
                continue

            # Skip internal/template directories (underscore prefix)
            if scenario_path.name.startswith("_"):
                filtered_count += 1
                logger.debug(
                    f"[SCENARIO_REGISTRY] Skipping internal scenario: {scenario_path.name}"
                )
                continue

            config_path = scenario_path / "config.yaml"
            if not config_path.exists():
                logger.debug(f"[SCENARIO_REGISTRY] Skipping {scenario_path.name}: no config.yaml")
                continue

            try:
                config = self._load_config(config_path)
                scenarios.append(config)
            except Exception as e:
                logger.warning(f"[SCENARIO_REGISTRY] Failed to load {scenario_path.name}: {e}")

        logger.debug(f"[SCENARIO_REGISTRY] Filtered {filtered_count} internal scenarios")
        logger.info(f"[SCENARIO_REGISTRY] Discovered {len(scenarios)} scenarios")
        return scenarios

    def get_scenario(self, name: str) -> tuple[ScenarioConfig, WorkflowSchema]:
        """Load a scenario by name.

        Args:
            name: Name of the scenario (directory name).

        Returns:
            Tuple of (ScenarioConfig, WorkflowSchema).

        Raises:
            FileNotFoundError: If scenario directory or files not found.
            ValueError: If config or workflow is invalid.
        """
        # Check cache first
        if name in self._cache:
            return self._cache[name]

        scenario_path = self._scenarios_dir / name

        if not scenario_path.exists():
            raise FileNotFoundError(f"Scenario not found: {name}")

        # Load config
        config_path = scenario_path / "config.yaml"
        if not config_path.exists():
            raise FileNotFoundError(f"Scenario config not found: {config_path}")

        config = self._load_config(config_path)

        # Resolve workflow path — use template if template_ref is set
        if config.template_ref is not None:
            template_workflow_path = self._scenarios_dir / config.template_ref / "workflow.json"
            if template_workflow_path.exists():
                logger.debug(
                    f"[SCENARIO_REGISTRY] Resolving template_ref for {name}: {config.template_ref}"
                )
                workflow_path = template_workflow_path
            else:
                logger.warning(
                    f"[SCENARIO_REGISTRY] template_ref '{config.template_ref}' workflow not found "
                    f"for scenario '{name}' — falling back to own workflow.json"
                )
                workflow_path = scenario_path / "workflow.json"
        else:
            workflow_path = scenario_path / "workflow.json"

        if not workflow_path.exists():
            raise FileNotFoundError(f"Scenario workflow not found: {workflow_path}")

        workflow = self._load_workflow(workflow_path)

        # Cache and return
        self._cache[name] = (config, workflow)
        logger.info(f"[SCENARIO_REGISTRY] Loaded scenario: {name}")

        return config, workflow

    def validate_scenario(self, name: str) -> list[str]:
        """Validate a scenario's agent and resource availability.

        Args:
            name: Name of the scenario to validate.

        Returns:
            List of validation error messages (empty if valid).
        """
        errors = []

        try:
            config, workflow = self.get_scenario(name)
        except FileNotFoundError as e:
            return [str(e)]
        except ValueError as e:
            return [f"Invalid scenario: {e}"]

        # Check required agents exist
        available_agents = {card.name for card in list_agents()}

        for agent_name in config.required_agents:
            if agent_name not in available_agents:
                errors.append(f"Required agent not found: {agent_name}")

        # Validate workflow schema agents
        workflow_errors = workflow.validate_agents()
        errors.extend([f"Workflow agent not found: {a}" for a in workflow_errors])

        if errors:
            logger.warning(f"[SCENARIO_REGISTRY] Validation errors for {name}: {errors}")
        else:
            logger.debug(f"[SCENARIO_REGISTRY] Validation passed for {name}")

        return errors

    def register_scenario(self, config: ScenarioConfig, workflow: WorkflowSchema) -> None:
        """Register a scenario at runtime (not persisted to disk).

        Args:
            config: ScenarioConfig for the scenario.
            workflow: WorkflowSchema for the scenario.
        """
        self._cache[config.name] = (config, workflow)
        logger.info(f"[SCENARIO_REGISTRY] Registered scenario: {config.name}")

    def clear_cache(self) -> None:
        """Clear the scenario cache."""
        self._cache.clear()
        logger.debug("[SCENARIO_REGISTRY] Cache cleared")

    def _load_config(self, path: Path) -> ScenarioConfig:
        """Load and validate scenario config from YAML.

        Args:
            path: Path to config.yaml file.

        Returns:
            Validated ScenarioConfig.

        Raises:
            ValueError: If config is invalid.
        """
        with open(path) as f:
            data = yaml.safe_load(f)

        return ScenarioConfig.model_validate(data)

    def _load_workflow(self, path: Path) -> WorkflowSchema:
        """Load and validate workflow from JSON.

        Args:
            path: Path to workflow.json file.

        Returns:
            Validated WorkflowSchema.

        Raises:
            ValueError: If workflow is invalid.
        """
        import json

        with open(path) as f:
            data = json.load(f)

        return WorkflowSchema.model_validate(data)

# =============================================================================
# Helper Functions
# =============================================================================

def load_scenario(name: str, scenarios_dir: str = "workflows/scenarios") -> ScenarioConfig:
    """Convenience function to load a scenario config.

    Args:
        name: Name of the scenario to load.
        scenarios_dir: Path to scenarios directory.

    Returns:
        ScenarioConfig for the scenario.
    """
    registry = ScenarioRegistry(scenarios_dir)
    config, _ = registry.get_scenario(name)
    return config

# Default registry singleton (lazy initialization)
_default_registry: ScenarioRegistry | None = None

def get_registry(scenarios_dir: str = "workflows/scenarios") -> ScenarioRegistry:
    """Get or create the default scenario registry.

    Args:
        scenarios_dir: Path to scenarios directory.

    Returns:
        ScenarioRegistry singleton.
    """
    global _default_registry
    if _default_registry is None:
        _default_registry = ScenarioRegistry(scenarios_dir)
    return _default_registry
