"""Workflow Scenarios Package.

This package contains production-ready workflow scenario definitions that
orchestrate showcase agents across multiple frameworks (CrewAI, LangChain, ADK).

Scenarios are organized by domain:
- finance/: Financial reporting, invoice processing
- dev/: Code review, sprint planning
- operations/: Compliance audit, DevOps deployment
- sales/: Prospect research, customer onboarding
- cross-framework/: Multi-framework orchestration demo

Each scenario directory contains:
- workflow.json: WorkflowSchema definition
- config.yaml: ScenarioConfig with triggers, inputs, outputs

Usage:
    from workflows.scenarios import SCENARIOS_DIR
    from core.workflows.scenarios import ScenarioRegistry

    registry = ScenarioRegistry(str(SCENARIOS_DIR))
    scenarios = registry.list_scenarios()
"""

from pathlib import Path

from core.workflows.scenarios import ScenarioRegistry, get_registry

SCENARIOS_DIR = Path(__file__).parent

SCENARIO_NAMES = [
    "financial_reporting",
    "invoice_processing",
    "code_review_pipeline",
    "sprint_planning",
    "compliance_audit",
    "devops_deployment",
    "prospect_research",
    "customer_onboarding",
    "multi_framework_demo",
]

SCENARIOS_BY_DOMAIN = {
    "finance": ["financial_reporting", "invoice_processing"],
    "dev": ["code_review_pipeline", "sprint_planning"],
    "operations": ["compliance_audit", "devops_deployment"],
    "sales": ["prospect_research", "customer_onboarding"],
    "cross-framework": ["multi_framework_demo"],
}

# Default registry singleton
registry = get_registry()

def list_scenarios():
    """List all available workflow scenarios.

    Returns:
        List of ScenarioConfig objects for all discovered scenarios.
    """
    return registry.list_scenarios()

def get_scenario(name: str):
    """Get a workflow scenario by name.

    Args:
        name: Name of the scenario (directory name).

    Returns:
        Tuple of (ScenarioConfig, WorkflowSchema).

    Raises:
        FileNotFoundError: If scenario not found.
    """
    return registry.get_scenario(name)

def validate_scenario(name: str) -> list[str]:
    """Validate a scenario's requirements.

    Args:
        name: Name of the scenario to validate.

    Returns:
        List of validation errors (empty if valid).
    """
    return registry.validate_scenario(name)

__all__ = [
    "SCENARIOS_DIR",
    "SCENARIO_NAMES",
    "SCENARIOS_BY_DOMAIN",
    "registry",
    "list_scenarios",
    "get_scenario",
    "validate_scenario",
    "ScenarioRegistry",
]
