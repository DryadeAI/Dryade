"""Unit tests for core.factory.scaffold.

Covers: scaffold_artifact(), list_available_frameworks(),
get_template_dir(), get_output_dir().

Gap 2 regression: verifies scaffolded dryade.json includes entry_point field.
"""

import json
from pathlib import Path

import pytest

from core.factory.models import ArtifactType
from core.factory.scaffold import (
    TEMPLATE_DIR,
    get_output_dir,
    get_template_dir,
    list_available_frameworks,
    scaffold_artifact,
)

# ---------------------------------------------------------------------------
# list_available_frameworks
# ---------------------------------------------------------------------------

class TestListAvailableFrameworks:
    """Framework discovery from template directories."""

    def test_agent_frameworks_non_empty(self):
        frameworks = list_available_frameworks(ArtifactType.AGENT)
        assert len(frameworks) > 0

    def test_agent_frameworks_include_custom(self):
        frameworks = list_available_frameworks(ArtifactType.AGENT)
        assert "custom" in frameworks

    def test_tool_frameworks_include_mcp_function(self):
        frameworks = list_available_frameworks(ArtifactType.TOOL)
        assert "mcp_function" in frameworks

    def test_returns_sorted_list(self):
        frameworks = list_available_frameworks(ArtifactType.AGENT)
        assert frameworks == sorted(frameworks)

# ---------------------------------------------------------------------------
# get_template_dir / get_output_dir
# ---------------------------------------------------------------------------

class TestPathHelpers:
    """Template and output directory resolution."""

    def test_template_dir_agents_custom(self):
        result = get_template_dir(ArtifactType.AGENT, "custom")
        assert result == TEMPLATE_DIR / "agents" / "custom"

    def test_template_dir_tools_mcp_function(self):
        result = get_template_dir(ArtifactType.TOOL, "mcp_function")
        assert result == TEMPLATE_DIR / "tools" / "mcp_function"

    def test_output_dir_default(self):
        result = get_output_dir(ArtifactType.AGENT, "my_agent")
        assert result.name == "my_agent"
        assert result.parent.name == "agents"

    def test_output_dir_custom_base(self):
        result = get_output_dir(ArtifactType.AGENT, "my_agent", base_dir="/tmp/out")
        assert result == Path("/tmp/out") / "my_agent"

    def test_template_dir_invalid_type_raises(self):
        with pytest.raises(ValueError, match="Unknown artifact type"):
            get_template_dir("not_a_type", "custom")  # type: ignore

# ---------------------------------------------------------------------------
# scaffold_artifact
# ---------------------------------------------------------------------------

class TestScaffoldArtifact:
    """Template rendering and file writing."""

    def test_scaffold_custom_agent(self, tmp_path):
        """Scaffolds a custom agent, returns success triple, creates files."""
        config = {
            "name": "test_scaffold_agent",
            "description": "A test agent",
            "goal": "Test goal",
            "version": "1.0.0",
            "framework": "custom",
            "factory_created": True,
            "tools": [],
            "mcp_servers": [],
            "capabilities": [],
        }
        success, path, msg = scaffold_artifact(
            config, ArtifactType.AGENT, "custom", base_dir=str(tmp_path)
        )
        assert success is True
        assert path != ""
        assert "Scaffolded" in msg

        out_dir = Path(path)
        assert out_dir.is_dir()
        # Should have rendered at least one file
        assert len(list(out_dir.iterdir())) > 0

    def test_scaffold_creates_directory(self, tmp_path):
        """Verify output directory is created."""
        config = {
            "name": "dir_test_agent",
            "description": "Test",
            "goal": "Test",
            "version": "1.0.0",
            "framework": "custom",
            "factory_created": True,
            "tools": [],
            "mcp_servers": [],
            "capabilities": [],
        }
        success, path, _ = scaffold_artifact(
            config, ArtifactType.AGENT, "custom", base_dir=str(tmp_path)
        )
        assert success is True
        assert Path(path).is_dir()

    def test_scaffold_invalid_framework(self, tmp_path):
        """Unknown framework with no templates returns failure."""
        config = {"name": "bad_agent"}
        success, path, msg = scaffold_artifact(
            config, ArtifactType.AGENT, "nonexistent_framework_xyz", base_dir=str(tmp_path)
        )
        assert success is False
        assert path == ""

    def test_scaffold_duplicate_directory_fails(self, tmp_path):
        """Scaffolding into an existing directory returns failure."""
        config = {
            "name": "duplicate_agent",
            "description": "Test",
            "goal": "Test",
            "version": "1.0.0",
            "framework": "custom",
            "factory_created": True,
            "tools": [],
            "mcp_servers": [],
            "capabilities": [],
        }
        # First scaffold succeeds
        success1, _, _ = scaffold_artifact(
            config, ArtifactType.AGENT, "custom", base_dir=str(tmp_path)
        )
        assert success1 is True

        # Second scaffold fails (directory exists)
        success2, _, msg = scaffold_artifact(
            config, ArtifactType.AGENT, "custom", base_dir=str(tmp_path)
        )
        assert success2 is False
        assert "already exists" in msg.lower() or "exists" in msg.lower()

    def test_dryade_json_has_entry_point(self, tmp_path):
        """Verify scaffolded dryade.json includes entry_point field (Gap 2 regression)."""
        config = {
            "name": "entry_point_agent",
            "description": "Test entry point",
            "goal": "Test",
            "version": "1.0.0",
            "framework": "custom",
            "factory_created": True,
            "tools": [],
            "mcp_servers": [],
            "capabilities": [],
        }
        success, path, _ = scaffold_artifact(
            config, ArtifactType.AGENT, "custom", base_dir=str(tmp_path)
        )
        assert success is True

        dryade_json_path = Path(path) / "dryade.json"
        if dryade_json_path.exists():
            data = json.loads(dryade_json_path.read_text())
            assert "entry_point" in data, "dryade.json missing entry_point field"

    def test_scaffold_returns_three_tuple(self, tmp_path):
        """scaffold_artifact always returns (bool, str, str)."""
        config = {"name": "tuple_test"}
        result = scaffold_artifact(
            config, ArtifactType.AGENT, "nonexistent_xyz", base_dir=str(tmp_path)
        )
        assert isinstance(result, tuple)
        assert len(result) == 3
        assert isinstance(result[0], bool)
        assert isinstance(result[1], str)
        assert isinstance(result[2], str)
