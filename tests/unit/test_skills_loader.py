"""
Unit tests for MarkdownSkillLoader.

Tests cover:
1. Loading valid SKILL.md files
2. Loading minimal skills (no metadata)
3. Error handling (missing files, invalid frontmatter)
4. Skill requirements parsing
5. Eligibility checking (OS, binaries, env vars)
6. Skill discovery from directories
7. Override semantics (later paths override earlier)

Target: ~80+ LOC
"""

import os
from unittest.mock import patch

import pytest

from core.skills.loader import MarkdownSkillLoader
from core.skills.models import Skill

@pytest.fixture
def temp_skill_dir(tmp_path):
    """Create a temporary skill directory with SKILL.md."""
    skill_dir = tmp_path / "test-skill"
    skill_dir.mkdir()
    return skill_dir

@pytest.fixture
def valid_skill_md():
    """Return valid SKILL.md content."""
    return """---
name: test-skill
description: A test skill for unit testing
metadata:
  dryade:
    emoji: "+"
    os:
      - linux
      - darwin
    requires:
      bins:
        - python
      env:
        - HOME
      config:
        - ~/.bashrc
---

# Test Skill Instructions

Use this skill to test things.

## Steps

1. Do step one
2. Do step two
"""

@pytest.fixture
def minimal_skill_md():
    """Return minimal valid SKILL.md (no metadata)."""
    return """---
name: minimal-skill
description: A minimal skill
---

Just some basic instructions.
"""

@pytest.fixture
def loader():
    """Create a MarkdownSkillLoader instance."""
    return MarkdownSkillLoader()

# =============================================================================
# Test: Loading Valid Skills
# =============================================================================

class TestLoadValidSkills:
    """Tests for loading valid SKILL.md files."""

    def test_load_skill_with_full_metadata(self, loader, temp_skill_dir, valid_skill_md):
        """Test loading a skill with complete metadata."""
        skill_md = temp_skill_dir / "SKILL.md"
        skill_md.write_text(valid_skill_md)

        skill = loader.load_skill(temp_skill_dir)

        assert skill.name == "test-skill"
        assert skill.description == "A test skill for unit testing"
        assert "# Test Skill Instructions" in skill.instructions
        assert skill.metadata.emoji == "+"
        assert "linux" in skill.metadata.os
        assert "darwin" in skill.metadata.os
        assert "python" in skill.metadata.requires.bins
        assert "HOME" in skill.metadata.requires.env
        assert "~/.bashrc" in skill.metadata.requires.config
        assert skill.skill_dir == str(temp_skill_dir)

    def test_load_minimal_skill(self, loader, temp_skill_dir, minimal_skill_md):
        """Test loading a minimal skill without metadata."""
        skill_md = temp_skill_dir / "SKILL.md"
        skill_md.write_text(minimal_skill_md)

        skill = loader.load_skill(temp_skill_dir)

        assert skill.name == "minimal-skill"
        assert skill.description == "A minimal skill"
        assert "basic instructions" in skill.instructions
        assert skill.metadata.emoji is None
        assert skill.metadata.os == []
        assert skill.metadata.requires.bins == []

    def test_load_skill_uses_dir_name_if_no_name(self, loader, temp_skill_dir):
        """Test that skill name falls back to directory name."""
        skill_md = temp_skill_dir / "SKILL.md"
        skill_md.write_text("""---
description: No name field
---

Instructions here.
""")

        skill = loader.load_skill(temp_skill_dir)

        assert skill.name == "test-skill"  # Directory name

# =============================================================================
# Test: Error Handling
# =============================================================================

class TestErrorHandling:
    """Tests for error handling in skill loading."""

    def test_missing_skill_file(self, loader, temp_skill_dir):
        """Test error when SKILL.md doesn't exist."""
        with pytest.raises(FileNotFoundError) as exc:
            loader.load_skill(temp_skill_dir)

        assert "SKILL.md" in str(exc.value)

    def test_invalid_frontmatter_no_start(self, loader, temp_skill_dir):
        """Test error when frontmatter doesn't start with ---."""
        skill_md = temp_skill_dir / "SKILL.md"
        skill_md.write_text("name: test\n---\nInstructions")

        with pytest.raises(ValueError) as exc:
            loader.load_skill(temp_skill_dir)

        assert "must start with ---" in str(exc.value)

    def test_invalid_frontmatter_no_end(self, loader, temp_skill_dir):
        """Test error when frontmatter isn't closed."""
        skill_md = temp_skill_dir / "SKILL.md"
        skill_md.write_text("---\nname: test\nInstructions without closing")

        with pytest.raises(ValueError) as exc:
            loader.load_skill(temp_skill_dir)

        assert "closed with ---" in str(exc.value)

# =============================================================================
# Test: Eligibility Checking
# =============================================================================

class TestEligibilityChecking:
    """Tests for skill eligibility gating."""

    def test_eligible_skill_no_requirements(self, loader):
        """Test skill with no requirements is always eligible."""
        skill = Skill(
            name="simple",
            description="Simple skill",
            instructions="Do things",
            skill_dir="/tmp/simple",
        )

        result = loader.check_skill_eligibility(skill)

        assert result.eligible is True
        assert result.reason is None

    def test_ineligible_os_mismatch(self, loader):
        """Test skill is ineligible when OS doesn't match."""
        from core.skills.models import SkillMetadata

        skill = Skill(
            name="mac-only",
            description="Mac only skill",
            instructions="Do things",
            skill_dir="/tmp/mac",
            metadata=SkillMetadata(os=["darwin"]),
        )

        # Mock platform to be Linux
        with patch.object(loader, "_current_os", "linux"):
            result = loader.check_skill_eligibility(skill)

        assert result.eligible is False
        assert "OS mismatch" in result.reason

    def test_ineligible_missing_binary(self, loader):
        """Test skill is ineligible when binary is missing."""
        from core.skills.models import SkillMetadata, SkillRequirements

        skill = Skill(
            name="needs-tool",
            description="Needs a specific tool",
            instructions="Use the tool",
            skill_dir="/tmp/tool",
            metadata=SkillMetadata(requires=SkillRequirements(bins=["nonexistent_binary_xyz"])),
        )

        result = loader.check_skill_eligibility(skill)

        assert result.eligible is False
        assert "nonexistent_binary_xyz" in result.missing_bins

    def test_ineligible_missing_env_var(self, loader):
        """Test skill is ineligible when env var is missing."""
        from core.skills.models import SkillMetadata, SkillRequirements

        skill = Skill(
            name="needs-env",
            description="Needs env var",
            instructions="Use the env",
            skill_dir="/tmp/env",
            metadata=SkillMetadata(requires=SkillRequirements(env=["NONEXISTENT_VAR_XYZ"])),
        )

        # Ensure the var is not set
        if "NONEXISTENT_VAR_XYZ" in os.environ:
            del os.environ["NONEXISTENT_VAR_XYZ"]

        result = loader.check_skill_eligibility(skill)

        assert result.eligible is False
        assert "NONEXISTENT_VAR_XYZ" in result.missing_env

    def test_ineligible_missing_config(self, loader):
        """Test skill is ineligible when config path is missing."""
        from core.skills.models import SkillMetadata, SkillRequirements

        skill = Skill(
            name="needs-config",
            description="Needs config",
            instructions="Use config",
            skill_dir="/tmp/config",
            metadata=SkillMetadata(requires=SkillRequirements(config=["/nonexistent/path/xyz"])),
        )

        result = loader.check_skill_eligibility(skill)

        assert result.eligible is False
        assert "/nonexistent/path/xyz" in result.missing_config

    def test_eligible_with_all_requirements_met(self, loader):
        """Test skill is eligible when all requirements are met."""
        from core.skills.models import SkillMetadata, SkillRequirements

        current_os = loader._current_os

        skill = Skill(
            name="full-requirements",
            description="Has requirements",
            instructions="Use all",
            skill_dir="/tmp/full",
            metadata=SkillMetadata(
                os=[current_os],
                requires=SkillRequirements(
                    bins=["python"],  # Should exist
                    env=["HOME"],  # Should exist
                ),
            ),
        )

        result = loader.check_skill_eligibility(skill)

        assert result.eligible is True

# =============================================================================
# Test: Skill Discovery
# =============================================================================

class TestSkillDiscovery:
    """Tests for discovering skills from directories."""

    def test_discover_skills_from_path(self, loader, tmp_path, valid_skill_md):
        """Test discovering skills from a search path."""
        # Create skill directory
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(valid_skill_md)

        skills = loader.discover_skills([tmp_path], filter_eligible=False)

        assert len(skills) == 1
        assert skills[0].name == "test-skill"

    def test_discover_skills_ignores_non_skill_dirs(self, loader, tmp_path):
        """Test that non-skill directories are ignored."""
        # Create dir without SKILL.md
        (tmp_path / "not-a-skill").mkdir()

        skills = loader.discover_skills([tmp_path], filter_eligible=False)

        assert len(skills) == 0

    def test_discover_skills_override_semantics(self, loader, tmp_path, valid_skill_md):
        """Test that later paths override earlier ones for same-named skills."""
        # First path
        path1 = tmp_path / "bundled"
        path1.mkdir()
        skill_dir1 = path1 / "test-skill"
        skill_dir1.mkdir()
        (skill_dir1 / "SKILL.md").write_text(valid_skill_md)

        # Second path with same skill name but different content
        path2 = tmp_path / "managed"
        path2.mkdir()
        skill_dir2 = path2 / "test-skill"
        skill_dir2.mkdir()
        (skill_dir2 / "SKILL.md").write_text("""---
name: test-skill
description: Override version
---

Override instructions.
""")

        skills = loader.discover_skills([path1, path2], filter_eligible=False)

        assert len(skills) == 1
        assert skills[0].description == "Override version"
        assert str(skill_dir2) == skills[0].skill_dir

    def test_discover_skills_filter_ineligible(self, loader, tmp_path):
        """Test that ineligible skills are filtered when requested."""
        skill_dir = tmp_path / "linux-only"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("""---
name: linux-only
description: Linux only
metadata:
  dryade:
    os:
      - nonexistent_os
---

Linux instructions.
""")

        # With filtering (default)
        skills = loader.discover_skills([tmp_path], filter_eligible=True)
        assert len(skills) == 0

        # Without filtering
        skills = loader.discover_skills([tmp_path], filter_eligible=False)
        assert len(skills) == 1

    def test_discover_skills_nonexistent_path(self, loader, tmp_path):
        """Test that nonexistent paths are handled gracefully."""
        nonexistent = tmp_path / "does-not-exist"

        skills = loader.discover_skills([nonexistent], filter_eligible=False)

        assert len(skills) == 0

# =============================================================================
# Test: Platform Detection
# =============================================================================

class TestPlatformDetection:
    """Tests for platform detection in loader."""

    def test_platform_mapping_darwin(self):
        """Test Darwin (macOS) platform mapping."""
        with patch("platform.system", return_value="Darwin"):
            loader = MarkdownSkillLoader()
            assert loader._current_os == "darwin"

    def test_platform_mapping_linux(self):
        """Test Linux platform mapping."""
        with patch("platform.system", return_value="Linux"):
            loader = MarkdownSkillLoader()
            assert loader._current_os == "linux"

    def test_platform_mapping_windows(self):
        """Test Windows platform mapping."""
        with patch("platform.system", return_value="Windows"):
            loader = MarkdownSkillLoader()
            assert loader._current_os == "win32"
