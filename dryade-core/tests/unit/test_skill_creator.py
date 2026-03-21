"""Unit tests for SkillCreator (Phase 67.1).

Tests:
- SkillCreator initialization
- Skill name generation from goal
- SKILL.md formatting
- Signing decision based on leash config
- Singleton pattern (get_skill_creator, reset_skill_creator)
- SkillCreationResult dataclass
"""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.autonomous.leash import LeashConfig
from core.autonomous.skill_creator import (
    SkillCreationResult,
    SkillCreator,
    get_skill_creator,
    reset_skill_creator,
)

class TestSkillCreationResult:
    """Tests for SkillCreationResult dataclass."""

    def test_successful_result(self):
        """Test successful skill creation result."""
        result = SkillCreationResult(
            success=True,
            skill_name="test-skill",
            skill=MagicMock(),
            signed=True,
            staged_path=Path("/tmp/output"),
        )
        assert result.success is True
        assert result.skill_name == "test-skill"
        assert result.skill is not None
        assert result.signed is True
        assert result.error is None
        assert result.validation_issues == []

    def test_failed_result(self):
        """Test failed skill creation result."""
        result = SkillCreationResult(
            success=False,
            skill_name="bad-skill",
            error="Validation failed",
            validation_issues=["Forbidden pattern detected", "Missing required field"],
        )
        assert result.success is False
        assert result.error == "Validation failed"
        assert len(result.validation_issues) == 2

    def test_default_values(self):
        """Test default values are set correctly."""
        result = SkillCreationResult(success=True)
        assert result.skill_name is None
        assert result.skill is None
        assert result.error is None
        assert result.validation_issues == []
        assert result.signed is False
        assert result.staged_path is None

class TestSkillCreatorInit:
    """Tests for SkillCreator initialization."""

    def test_default_init(self):
        """Test SkillCreator with default parameters."""
        with patch("core.autonomous.skill_creator.SelfDevSandbox"):
            with patch("core.autonomous.skill_creator.SkillSigner"):
                creator = SkillCreator()
                assert creator.leash is not None
                assert creator.llm_generator is None
                assert creator.auto_sign is True
                assert creator.auto_register is True

    def test_custom_leash(self):
        """Test SkillCreator with custom leash config."""
        leash = LeashConfig(confidence_threshold=0.9, max_actions=5)
        with patch("core.autonomous.skill_creator.SelfDevSandbox"):
            with patch("core.autonomous.skill_creator.SkillSigner"):
                creator = SkillCreator(leash_config=leash)
                assert creator.leash.confidence_threshold == 0.9
                assert creator.leash.max_actions == 5

    def test_disable_auto_sign(self):
        """Test SkillCreator with auto_sign disabled."""
        with patch("core.autonomous.skill_creator.SelfDevSandbox"):
            with patch("core.autonomous.skill_creator.SkillSigner"):
                creator = SkillCreator(auto_sign=False)
                assert creator.auto_sign is False

    def test_disable_auto_register(self):
        """Test SkillCreator with auto_register disabled."""
        with patch("core.autonomous.skill_creator.SelfDevSandbox"):
            with patch("core.autonomous.skill_creator.SkillSigner"):
                creator = SkillCreator(auto_register=False)
                assert creator.auto_register is False

class TestSkillCreatorNameGeneration:
    """Tests for skill name generation."""

    def test_generate_skill_name_simple(self):
        """Test name generation from simple goal."""
        with patch("core.autonomous.skill_creator.SelfDevSandbox"):
            with patch("core.autonomous.skill_creator.SkillSigner"):
                creator = SkillCreator()
                name = creator._generate_skill_name("Parse JSON files")
                assert name == "parse-json-files"

    def test_generate_skill_name_long_goal(self):
        """Test name generation truncates long goals."""
        with patch("core.autonomous.skill_creator.SelfDevSandbox"):
            with patch("core.autonomous.skill_creator.SkillSigner"):
                creator = SkillCreator()
                name = creator._generate_skill_name(
                    "Analyze and process Excel spreadsheets to extract data and generate reports"
                )
                # Only first 4 words, max 30 chars
                assert len(name) <= 30
                assert name.startswith("analyze")

    def test_generate_skill_name_special_chars(self):
        """Test name generation handles special characters."""
        with patch("core.autonomous.skill_creator.SelfDevSandbox"):
            with patch("core.autonomous.skill_creator.SkillSigner"):
                creator = SkillCreator()
                name = creator._generate_skill_name("Parse JSON/XML & CSV files!")
                # Non-alphanumeric words should be filtered
                assert "/" not in name
                assert "&" not in name
                assert "!" not in name

    def test_generate_skill_name_empty_goal(self):
        """Test name generation with empty goal falls back to default."""
        with patch("core.autonomous.skill_creator.SelfDevSandbox"):
            with patch("core.autonomous.skill_creator.SkillSigner"):
                creator = SkillCreator()
                name = creator._generate_skill_name("")
                assert name == "custom-skill"

    def test_generate_skill_name_all_special_chars(self):
        """Test name generation with goal of only special chars."""
        with patch("core.autonomous.skill_creator.SelfDevSandbox"):
            with patch("core.autonomous.skill_creator.SkillSigner"):
                creator = SkillCreator()
                name = creator._generate_skill_name("!@#$%^&*()")
                assert name == "custom-skill"

class TestSkillCreatorFormatting:
    """Tests for SKILL.md formatting."""

    def test_format_skill_md_basic(self):
        """Test basic SKILL.md formatting."""
        with patch("core.autonomous.skill_creator.SelfDevSandbox"):
            with patch("core.autonomous.skill_creator.SkillSigner"):
                creator = SkillCreator()
                content = creator._format_skill_md(
                    name="test-skill",
                    description="A test skill",
                    instructions="Do the test",
                )

                assert "name: test-skill" in content
                assert "description: A test skill" in content
                assert 'version: "1.0.0"' in content
                assert "generated: true" in content
                assert "# test-skill" in content
                assert "A test skill" in content
                assert "## Instructions" in content
                assert "Do the test" in content

    def test_format_skill_md_multiline_instructions(self):
        """Test SKILL.md with multiline instructions."""
        with patch("core.autonomous.skill_creator.SelfDevSandbox"):
            with patch("core.autonomous.skill_creator.SkillSigner"):
                creator = SkillCreator()
                content = creator._format_skill_md(
                    name="complex-skill",
                    description="A complex skill",
                    instructions="Step 1: Do X\nStep 2: Do Y\nStep 3: Do Z",
                )

                assert "Step 1: Do X" in content
                assert "Step 2: Do Y" in content
                assert "Step 3: Do Z" in content

class TestSkillCreatorSigning:
    """Tests for skill signing decisions."""

    def test_should_sign_permissive_leash(self):
        """Test signing enabled with permissive leash."""
        leash = LeashConfig(confidence_threshold=0.5)  # Low threshold = permissive
        with patch("core.autonomous.skill_creator.SelfDevSandbox"):
            with patch("core.autonomous.skill_creator.SkillSigner"):
                creator = SkillCreator(leash_config=leash)
                assert creator._should_sign() is True

    def test_should_sign_strict_leash(self):
        """Test signing disabled with strict leash."""
        leash = LeashConfig(confidence_threshold=0.95)  # High threshold = strict
        with patch("core.autonomous.skill_creator.SelfDevSandbox"):
            with patch("core.autonomous.skill_creator.SkillSigner"):
                creator = SkillCreator(leash_config=leash)
                # 0.95 > 0.85, so should NOT sign
                assert creator._should_sign() is False

    def test_should_sign_boundary(self):
        """Test signing at boundary threshold."""
        leash = LeashConfig(confidence_threshold=0.85)
        with patch("core.autonomous.skill_creator.SelfDevSandbox"):
            with patch("core.autonomous.skill_creator.SkillSigner"):
                creator = SkillCreator(leash_config=leash)
                # 0.85 <= 0.85, so should sign
                assert creator._should_sign() is True

class TestSkillCreatorSingleton:
    """Tests for singleton pattern."""

    def test_get_skill_creator_singleton(self):
        """Test get_skill_creator returns same instance."""
        reset_skill_creator()

        with patch("core.autonomous.skill_creator.SelfDevSandbox"):
            with patch("core.autonomous.skill_creator.SkillSigner"):
                creator1 = get_skill_creator()
                creator2 = get_skill_creator()
                assert creator1 is creator2

        reset_skill_creator()

    def test_reset_skill_creator(self):
        """Test reset_skill_creator clears singleton."""
        reset_skill_creator()

        with patch("core.autonomous.skill_creator.SelfDevSandbox"):
            with patch("core.autonomous.skill_creator.SkillSigner"):
                creator1 = get_skill_creator()
                reset_skill_creator()
                creator2 = get_skill_creator()
                assert creator1 is not creator2

        reset_skill_creator()

    def test_get_skill_creator_with_leash(self):
        """Test get_skill_creator respects leash config on first call."""
        reset_skill_creator()

        leash = LeashConfig(max_actions=99)
        with patch("core.autonomous.skill_creator.SelfDevSandbox"):
            with patch("core.autonomous.skill_creator.SkillSigner"):
                creator = get_skill_creator(leash_config=leash)
                assert creator.leash.max_actions == 99

        reset_skill_creator()

class TestSkillCreatorCreateSkill:
    """Tests for create_skill method."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.mark.asyncio
    async def test_create_skill_success(self, temp_dir):
        """Test successful skill creation."""
        # Mock sandbox
        mock_session = MagicMock()
        mock_session.session_id = "test-session"
        mock_session.sandbox_path = temp_dir
        mock_session.output_path = temp_dir / "output"

        mock_sandbox = MagicMock()
        mock_sandbox.enter_self_dev_mode = AsyncMock(return_value=mock_session)
        mock_sandbox.validate_and_stage = AsyncMock(
            return_value=MagicMock(passed=True, issues=[], warnings=[])
        )
        mock_sandbox.end_session = AsyncMock()

        with patch("core.autonomous.skill_creator.SelfDevSandbox", return_value=mock_sandbox):
            with patch("core.autonomous.skill_creator.SkillSigner"):
                with patch("core.skills.create_and_register_skill") as mock_register:
                    mock_skill = MagicMock(name="test-skill")
                    mock_register.return_value = mock_skill

                    creator = SkillCreator(auto_sign=False, auto_register=True)
                    result = await creator.create_skill(
                        goal="Parse CSV files",
                        skill_name="csv-parser",
                    )

                    assert result.success is True
                    assert result.skill_name == "csv-parser"
                    mock_sandbox.enter_self_dev_mode.assert_called_once()
                    mock_sandbox.validate_and_stage.assert_called_once()
                    mock_sandbox.end_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_skill_sandbox_failure(self, temp_dir):
        """Test skill creation when sandbox fails to start."""
        mock_sandbox = MagicMock()
        mock_sandbox.enter_self_dev_mode = AsyncMock(
            side_effect=Exception("Sandbox initialization failed")
        )

        with patch("core.autonomous.skill_creator.SelfDevSandbox", return_value=mock_sandbox):
            with patch("core.autonomous.skill_creator.SkillSigner"):
                creator = SkillCreator()
                result = await creator.create_skill(goal="Test")

                assert result.success is False
                assert "Failed to enter sandbox" in result.error

    @pytest.mark.asyncio
    async def test_create_skill_validation_failure(self, temp_dir):
        """Test skill creation with validation failure."""
        mock_session = MagicMock()
        mock_session.session_id = "test-session"
        mock_session.sandbox_path = temp_dir
        mock_session.output_path = temp_dir / "output"

        mock_sandbox = MagicMock()
        mock_sandbox.enter_self_dev_mode = AsyncMock(return_value=mock_session)
        mock_sandbox.validate_and_stage = AsyncMock(
            return_value=MagicMock(
                passed=False,
                issues=["Forbidden pattern: rm -rf", "Unsafe import"],
                warnings=[],
            )
        )
        mock_sandbox.end_session = AsyncMock()

        with patch("core.autonomous.skill_creator.SelfDevSandbox", return_value=mock_sandbox):
            with patch("core.autonomous.skill_creator.SkillSigner"):
                creator = SkillCreator()
                result = await creator.create_skill(goal="Do bad things")

                assert result.success is False
                assert result.error == "Validation failed"
                assert len(result.validation_issues) == 2
                assert "rm -rf" in result.validation_issues[0]

    @pytest.mark.asyncio
    async def test_create_skill_with_llm_generator(self, temp_dir):
        """Test skill creation with LLM generator."""
        mock_session = MagicMock()
        mock_session.session_id = "test-session"
        mock_session.sandbox_path = temp_dir
        mock_session.output_path = temp_dir / "output"

        mock_sandbox = MagicMock()
        mock_sandbox.enter_self_dev_mode = AsyncMock(return_value=mock_session)
        mock_sandbox.validate_and_stage = AsyncMock(
            return_value=MagicMock(passed=True, issues=[], warnings=[])
        )
        mock_sandbox.end_session = AsyncMock()

        # Mock LLM generator
        mock_llm = MagicMock()
        mock_llm.generate_skill = AsyncMock(
            return_value=("llm-skill", "LLM generated description", "LLM instructions")
        )

        with patch("core.autonomous.skill_creator.SelfDevSandbox", return_value=mock_sandbox):
            with patch("core.autonomous.skill_creator.SkillSigner"):
                with patch("core.skills.create_and_register_skill") as mock_register:
                    mock_skill = MagicMock(name="llm-skill")
                    mock_register.return_value = mock_skill

                    creator = SkillCreator(
                        llm_generator=mock_llm,
                        auto_sign=False,
                        auto_register=True,
                    )
                    result = await creator.create_skill(goal="Generate something")

                    assert result.success is True
                    assert result.skill_name == "llm-skill"
                    mock_llm.generate_skill.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_skill_without_registration(self, temp_dir):
        """Test skill creation without auto-registration."""
        mock_session = MagicMock()
        mock_session.session_id = "test-session"
        mock_session.sandbox_path = temp_dir
        mock_session.output_path = temp_dir / "output"

        mock_sandbox = MagicMock()
        mock_sandbox.enter_self_dev_mode = AsyncMock(return_value=mock_session)
        mock_sandbox.validate_and_stage = AsyncMock(
            return_value=MagicMock(passed=True, issues=[], warnings=[])
        )
        mock_sandbox.end_session = AsyncMock()

        with patch("core.autonomous.skill_creator.SelfDevSandbox", return_value=mock_sandbox):
            with patch("core.autonomous.skill_creator.SkillSigner"):
                with patch("core.skills.create_and_register_skill") as mock_register:
                    creator = SkillCreator(auto_sign=False, auto_register=False)
                    result = await creator.create_skill(goal="Test skill")

                    assert result.success is True
                    assert result.skill is None  # Not registered
                    mock_register.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_skill_auto_generated_name(self, temp_dir):
        """Test skill creation with auto-generated name."""
        mock_session = MagicMock()
        mock_session.session_id = "test-session"
        mock_session.sandbox_path = temp_dir
        mock_session.output_path = temp_dir / "output"

        mock_sandbox = MagicMock()
        mock_sandbox.enter_self_dev_mode = AsyncMock(return_value=mock_session)
        mock_sandbox.validate_and_stage = AsyncMock(
            return_value=MagicMock(passed=True, issues=[], warnings=[])
        )
        mock_sandbox.end_session = AsyncMock()

        with patch("core.autonomous.skill_creator.SelfDevSandbox", return_value=mock_sandbox):
            with patch("core.autonomous.skill_creator.SkillSigner"):
                with patch("core.skills.create_and_register_skill") as mock_register:
                    mock_skill = MagicMock()
                    mock_register.return_value = mock_skill

                    creator = SkillCreator(auto_sign=False)
                    result = await creator.create_skill(
                        goal="Analyze Excel files quickly",
                        # No skill_name provided
                    )

                    assert result.success is True
                    assert result.skill_name is not None
                    # Name should be generated from goal
                    assert "analyze" in result.skill_name.lower()
