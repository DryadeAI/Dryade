"""Test Domain Plugin.

A simple test domain for E2E validation of the agents system.
This domain provides test agents that don't require any external services.
"""

from pathlib import Path


def get_domain_path() -> Path:
    """Get the path to this domain's directory."""
    return Path(__file__).parent

def get_yaml_path() -> Path:
    """Get the path to this domain's YAML configuration."""
    return get_domain_path() / "domain.yaml"

# Domain metadata
DOMAIN_NAME = "test"
DOMAIN_VERSION = "1.0.0"
DOMAIN_DESCRIPTION = "Test domain for E2E validation"

__all__ = [
    "DOMAIN_NAME",
    "DOMAIN_VERSION",
    "DOMAIN_DESCRIPTION",
    "get_domain_path",
    "get_yaml_path",
]
