"""Skill creator for autonomous mid-execution skill generation.

Orchestrates:
1. SelfDevSandbox for isolated development
2. Validation via forbidden pattern checks
3. Ed25519 signing (if allowed by leash)
4. Registration with SkillRegistry

Usage:
    creator = SkillCreator(leash_config=my_leash)
    result = await creator.create_skill(
        goal="Analyze Excel files and extract data",
        skill_name="excel-analyzer",
    )
    if result.success:
        # Skill is now available in registry
        print(f"Created: {result.skill_name}")
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from core.autonomous.leash import LeashConfig
from core.self_dev.sandbox import SelfDevSandbox
from core.self_dev.signer import SkillSigner, ensure_user_keypair

if TYPE_CHECKING:
    from core.skills.models import Skill

logger = logging.getLogger(__name__)

@dataclass
class SkillCreationResult:
    """Result of skill creation attempt."""

    success: bool
    skill_name: str | None = None
    skill: "Skill | None" = None
    error: str | None = None
    validation_issues: list[str] = field(default_factory=list)
    signed: bool = False
    staged_path: Path | None = None

class LLMSkillGenerator(Protocol):
    """Protocol for LLM-based skill generation.

    Implementations generate SKILL.md content from a goal description.
    """

    async def generate_skill(
        self,
        goal: str,
        skill_name: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> tuple[str, str, str]:
        """Generate skill from goal.

        Args:
            goal: What the skill should accomplish
            skill_name: Suggested name (can be modified)
            context: Additional context

        Returns:
            (skill_name, description, instructions) tuple
        """
        ...

class SkillCreator:
    """Create skills mid-execution via SelfDevSandbox.

    Orchestrates the full skill creation pipeline:
    1. Enter sandbox for isolated development
    2. Generate skill content (via LLM or template)
    3. Validate against forbidden patterns
    4. Sign if leash config allows
    5. Register with SkillRegistry for immediate use

    Example:
        creator = SkillCreator()
        result = await creator.create_skill(
            goal="Parse and analyze Excel files",
        )
    """

    def __init__(
        self,
        leash_config: LeashConfig | None = None,
        llm_generator: LLMSkillGenerator | None = None,
        auto_sign: bool = True,
        auto_register: bool = True,
    ):
        """Initialize skill creator.

        Args:
            leash_config: Autonomy constraints (affects signing)
            llm_generator: LLM for generating skill content
            auto_sign: Whether to automatically sign created skills
            auto_register: Whether to automatically register with registry
        """
        self.leash = leash_config or LeashConfig()
        self.llm_generator = llm_generator
        self.auto_sign = auto_sign
        self.auto_register = auto_register

        self._sandbox = SelfDevSandbox()
        self._signer = SkillSigner()

    async def create_skill(
        self,
        goal: str,
        skill_name: str | None = None,
        description: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> SkillCreationResult:
        """Create a new skill to fulfill a goal.

        Args:
            goal: What the skill should accomplish
            skill_name: Suggested skill name (auto-generated if None)
            description: Skill description (auto-generated if None)
            context: Additional context for generation

        Returns:
            SkillCreationResult with outcome
        """
        context = context or {}

        # 1. Enter sandbox
        try:
            session = await self._sandbox.enter_self_dev_mode(goal)
            logger.info(f"[SkillCreator] Started session {session.session_id} for: {goal[:50]}...")
        except Exception as e:
            return SkillCreationResult(
                success=False,
                error=f"Failed to enter sandbox: {e}",
            )

        try:
            # 2. Generate skill content
            if self.llm_generator:
                skill_name, description, instructions = await self.llm_generator.generate_skill(
                    goal, skill_name, context
                )
            else:
                # Fallback: create minimal skill from goal
                skill_name = skill_name or self._generate_skill_name(goal)
                description = description or goal
                instructions = f"Accomplish the following goal:\n\n{goal}"

            # 3. Write skill to sandbox
            skill_dir = session.sandbox_path / "skills" / skill_name
            skill_dir.mkdir(parents=True, exist_ok=True)

            skill_md_content = self._format_skill_md(skill_name, description, instructions)
            skill_md_path = skill_dir / "SKILL.md"
            skill_md_path.write_text(skill_md_content)

            # 4. Validate
            validation = await self._sandbox.validate_and_stage(
                session,
                [skill_dir],
            )

            if not validation.passed:
                return SkillCreationResult(
                    success=False,
                    skill_name=skill_name,
                    error="Validation failed",
                    validation_issues=validation.issues,
                )

            # 5. Sign if allowed and auto_sign enabled
            signed = False
            if self.auto_sign and self._should_sign():
                try:
                    signed = await self._sign_skill(skill_dir, skill_name)
                except Exception as e:
                    logger.warning(f"[SkillCreator] Signing failed: {e}")

            # 6. Register if auto_register enabled
            skill = None
            if self.auto_register:
                skill = await self._register_skill(skill_name, description, instructions)

            # 7. Cleanup sandbox
            await self._sandbox.end_session(session)

            return SkillCreationResult(
                success=True,
                skill_name=skill_name,
                skill=skill,
                signed=signed,
                staged_path=session.output_path,
            )

        except Exception as e:
            logger.error(f"[SkillCreator] Skill creation failed: {e}")
            await self._sandbox.end_session(session)
            return SkillCreationResult(
                success=False,
                skill_name=skill_name,
                error=str(e),
            )

    def _generate_skill_name(self, goal: str) -> str:
        """Generate skill name from goal."""
        # Simple slug generation
        words = goal.lower().split()[:4]
        return "-".join(w for w in words if w.isalnum())[:30] or "custom-skill"

    def _format_skill_md(self, name: str, description: str, instructions: str) -> str:
        """Format skill content as SKILL.md."""
        return f"""---
name: {name}
description: {description}
version: "1.0.0"
generated: true
---

# {name}

{description}

## Instructions

{instructions}
"""

    def _should_sign(self) -> bool:
        """Check if skill should be signed based on leash config."""
        # Sign if leash is permissive (higher confidence threshold = more trust)
        return self.leash.confidence_threshold <= 0.85

    async def _sign_skill(self, skill_dir: Path, skill_name: str) -> bool:
        """Sign skill with user's key."""
        try:
            private_path, _ = ensure_user_keypair()
            private_key = self._signer.load_private_key(private_path)
            self._signer.sign_skill(skill_dir, private_key, signer_id="autonomous-executor")
            logger.info(f"[SkillCreator] Signed skill: {skill_name}")
            return True
        except Exception as e:
            logger.warning(f"[SkillCreator] Could not sign skill: {e}")
            return False

    async def _register_skill(self, name: str, description: str, instructions: str) -> "Skill":
        """Register skill with global registry."""
        from core.skills import create_and_register_skill

        skill = create_and_register_skill(
            name=name,
            description=description,
            instructions=instructions,
            persist=True,
        )
        logger.info(f"[SkillCreator] Registered skill: {name}")
        return skill

# Default creator instance
_skill_creator: SkillCreator | None = None

def get_skill_creator(leash_config: LeashConfig | None = None) -> SkillCreator:
    """Get or create default skill creator.

    Args:
        leash_config: Optional leash config (uses default if None)

    Returns:
        SkillCreator instance
    """
    global _skill_creator
    if _skill_creator is None:
        _skill_creator = SkillCreator(leash_config=leash_config)
    return _skill_creator

def reset_skill_creator() -> None:
    """Reset default skill creator (for testing)."""
    global _skill_creator
    _skill_creator = None
