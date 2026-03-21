"""Unit tests for core.factory.tester.

Covers: generate_test_task(), _FRAMEWORK_PACKAGES mapping,
_check_framework_available(), _find_main_py().
"""

from core.factory.models import ArtifactType
from core.factory.tester import (
    _FRAMEWORK_PACKAGES,
    _check_framework_available,
    _find_main_py,
    generate_test_task,
)

# ---------------------------------------------------------------------------
# generate_test_task
# ---------------------------------------------------------------------------

class TestGenerateTestTask:
    """Test task generation per artifact type."""

    def test_agent_default_task(self):
        task = generate_test_task(ArtifactType.AGENT, {})
        assert task
        assert "capabilities" in task.lower() or "operational" in task.lower()

    def test_tool_default_task(self):
        task = generate_test_task(ArtifactType.TOOL, {})
        assert task
        assert "tool" in task.lower()

    def test_skill_default_task(self):
        task = generate_test_task(ArtifactType.SKILL, {})
        assert task
        assert "skill" in task.lower() or "validate" in task.lower()

    def test_custom_test_task_from_config(self):
        """User-provided test_task in config takes priority."""
        task = generate_test_task(ArtifactType.AGENT, {"test_task": "My custom task"})
        assert task == "My custom task"

    def test_empty_test_task_ignored(self):
        """Empty or whitespace test_task falls back to default."""
        task = generate_test_task(ArtifactType.AGENT, {"test_task": "   "})
        assert task  # Should get a real default
        assert task.strip() != ""

    def test_returns_string(self):
        """Always returns a non-empty string."""
        for art_type in ArtifactType:
            task = generate_test_task(art_type, {})
            assert isinstance(task, str)
            assert len(task) > 0

# ---------------------------------------------------------------------------
# _FRAMEWORK_PACKAGES mapping
# ---------------------------------------------------------------------------

class TestFrameworkPackages:
    """Framework-to-package mapping for import checks."""

    def test_known_frameworks_present(self):
        expected = {"crewai", "langchain", "adk", "custom", "mcp_function", "mcp_server", "skill"}
        assert expected.issubset(set(_FRAMEWORK_PACKAGES.keys()))

    def test_custom_is_none(self):
        """custom framework has no package dependency."""
        assert _FRAMEWORK_PACKAGES["custom"] is None

    def test_skill_is_none(self):
        """skill framework has no package dependency."""
        assert _FRAMEWORK_PACKAGES["skill"] is None

    def test_crewai_maps_correctly(self):
        assert _FRAMEWORK_PACKAGES["crewai"] == "crewai"

    def test_mcp_function_maps_to_fastmcp(self):
        assert _FRAMEWORK_PACKAGES["mcp_function"] == "fastmcp"

# ---------------------------------------------------------------------------
# _check_framework_available
# ---------------------------------------------------------------------------

class TestCheckFrameworkAvailable:
    """Framework availability check."""

    def test_custom_always_available(self):
        """custom framework (package=None) is always available."""
        assert _check_framework_available("custom") is True

    def test_skill_always_available(self):
        """skill framework (package=None) is always available."""
        assert _check_framework_available("skill") is True

    def test_unknown_framework_available(self):
        """Unknown framework (not in dict) has package=None, so returns True."""
        assert _check_framework_available("totally_unknown") is True

# ---------------------------------------------------------------------------
# _find_main_py
# ---------------------------------------------------------------------------

class TestFindMainPy:
    """Main Python file discovery in artifact directories."""

    def test_finds_init_py(self, tmp_path):
        """Prioritizes __init__.py."""
        (tmp_path / "__init__.py").write_text("# init")
        (tmp_path / "other.py").write_text("# other")
        result = _find_main_py(str(tmp_path))
        assert result is not None
        assert result.name == "__init__.py"

    def test_finds_named_py(self, tmp_path):
        """Falls back to {dirname}.py."""
        dirname = tmp_path.name
        (tmp_path / f"{dirname}.py").write_text("# main")
        result = _find_main_py(str(tmp_path))
        assert result is not None
        assert result.name == f"{dirname}.py"

    def test_finds_first_py(self, tmp_path):
        """Falls back to first .py file alphabetically."""
        (tmp_path / "alpha.py").write_text("# alpha")
        (tmp_path / "beta.py").write_text("# beta")
        result = _find_main_py(str(tmp_path))
        assert result is not None
        assert result.name == "alpha.py"

    def test_returns_none_when_no_py(self, tmp_path):
        """Returns None when no Python files exist."""
        (tmp_path / "readme.txt").write_text("hello")
        result = _find_main_py(str(tmp_path))
        assert result is None
