"""Dryade Flows.

Native CrewAI flows for complex workflows.

Flow stubs (AnalysisFlow, CoverageFlow) removed in Phase 181 audit cleanup.
Both contained NotImplementedError stubs that would crash at runtime.
The FLOW_REGISTRY is kept as an empty dict so API routes continue to work
(they return an empty list of flows rather than import-erroring).
"""

# Flow registry for API discovery — empty after stale flow removal
FLOW_REGISTRY: dict = {}

def get_flow_class(name: str):
    """Get a flow class by name."""
    if name not in FLOW_REGISTRY:
        return None
    return FLOW_REGISTRY[name]["class"]

def list_flows():
    """List all registered flows."""
    return list(FLOW_REGISTRY.keys())

__all__ = [
    "FLOW_REGISTRY",
    "get_flow_class",
    "list_flows",
]
