"""Configure ``plugins`` namespace package for unit tests.

Looks for plugins/ relative to the monorepo root
or as a sibling of a standalone dryade-core checkout.  If neither exists,
all tests in this directory are skipped automatically.
"""

import sys
import types
from pathlib import Path

import pytest

# Try monorepo layout first (tests/unit/plugins/conftest.py → project root)
_MONOREPO_ROOT = Path(__file__).resolve().parents[4]
_STANDALONE_ROOT = Path(__file__).resolve().parents[3]

if (_MONOREPO_ROOT / "plugins").is_dir():
    _PLUGINS_ROOT = _MONOREPO_ROOT / "plugins"
elif (_STANDALONE_ROOT / "plugins").is_dir():
    _PLUGINS_ROOT = _STANDALONE_ROOT / "plugins"
else:
    _PLUGINS_ROOT = None

def pytest_collection_modifyitems(config, items):
    """Skip all plugin tests when plugins is not available."""
    if _PLUGINS_ROOT is not None:
        return
    skip = pytest.mark.skip(reason="plugins not available (standalone checkout)")
    for item in items:
        if "tests/unit/plugins" in str(item.fspath):
            item.add_marker(skip)

if _PLUGINS_ROOT is not None and "plugins" not in sys.modules:
    _pkg = types.ModuleType("plugins")
    _pkg.__path__ = [
        str(_PLUGINS_ROOT / "starter"),
        str(_PLUGINS_ROOT / "team"),
        str(_PLUGINS_ROOT / "enterprise"),
    ]
    _pkg.__package__ = "plugins"
    sys.modules["plugins"] = _pkg
