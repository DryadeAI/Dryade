"""Skip all scenario tests when workflow scenarios directory is not available.

The scenario JSON/YAML files live in workflows/scenarios/,
not in dryade-core. In standalone dryade-core CI, skip these tests.
"""

from pathlib import Path

import pytest

SCENARIOS_DIR = Path(__file__).resolve().parents[5] / "workflows" / "scenarios"

def pytest_collection_modifyitems(config, items):
    if SCENARIOS_DIR.is_dir():
        return
    skip = pytest.mark.skip(
        reason=f"Workflow scenarios not available at {SCENARIOS_DIR} (standalone checkout)"
    )
    for item in items:
        if "tests/unit/workflows/scenarios" in str(item.fspath):
            item.add_marker(skip)
