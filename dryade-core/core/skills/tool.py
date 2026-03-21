"""SkillBashTool - LLM tool for executing skill scripts.

Implements the OpenClaw pattern: skills are SKILL.md (instructions) + scripts/ (executables).
The LLM reads skill instructions and uses this tool to execute scripts.

Usage in CHAT mode:
    LLM reads skill instructions from system prompt
    LLM calls skill_bash("transcription", "transcribe.sh", ["/path/to/audio.m4a"])
    Tool executes script in sandbox and returns output
"""

import logging
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

class SkillBashInput(BaseModel):
    """Input schema for skill_bash tool.

    This schema is exposed to the LLM for tool calling.
    """

    skill_name: str = Field(description="Name of the skill (matches SKILL.md folder name)")
    script_name: str = Field(
        description="Script to execute from skill's scripts/ folder (e.g., 'transcribe.sh')"
    )
    args: list[str] = Field(default_factory=list, description="Arguments to pass to the script")

class SkillBashOutput(BaseModel):
    """Output schema for skill_bash tool."""

    success: bool
    stdout: str
    stderr: str
    exit_code: int
    skill_name: str
    script_name: str

class SkillBashTool:
    """Tool for LLM to execute skill scripts in sandboxed bash.

    Implements OpenClaw pattern:
    - Skills have SKILL.md (instructions LLM reads) + scripts/ folder (executables)
    - LLM reads instructions and decides which script to call with what args
    - This tool executes the script in sandbox and returns output

    The tool is registered in CHAT mode so LLM can use skills directly.

    Example:
        # LLM sees skill instructions in system prompt:
        # "Use transcribe.sh to convert audio to text. Pass the audio file path."

        # LLM calls:
        result = await skill_bash.execute({
            "skill_name": "transcription",
            "script_name": "transcribe.sh",
            "args": ["/path/to/audio.m4a"]
        })
    """

    name: str = "skill_bash"
    description: str = (
        "Execute a skill script in sandboxed bash. "
        "Read the skill's instructions first to understand available scripts and their usage."
    )

    def __init__(self):
        """Initialize SkillBashTool with SkillScriptExecutor."""
        # Lazy import to avoid circular dependency
        self._executor = None
        self._registry = None

    @property
    def executor(self):
        """Get or create SkillScriptExecutor."""
        if self._executor is None:
            from core.skills.executor import SkillScriptExecutor

            self._executor = SkillScriptExecutor()
        return self._executor

    @property
    def registry(self):
        """Get or create SkillRegistry."""
        if self._registry is None:
            from core.skills.registry import get_skill_registry

            self._registry = get_skill_registry()
        return self._registry

    def get_input_schema(self) -> dict[str, Any]:
        """Return JSON schema for tool input (for LLM tool calling)."""
        return SkillBashInput.model_json_schema()

    async def execute(self, input_data: dict[str, Any]) -> SkillBashOutput:
        """Execute a skill script.

        Args:
            input_data: Dict with skill_name, script_name, args

        Returns:
            SkillBashOutput with execution results
        """
        # Validate input
        try:
            params = SkillBashInput.model_validate(input_data)
        except Exception as e:
            return SkillBashOutput(
                success=False,
                stdout="",
                stderr=f"Invalid input: {e}",
                exit_code=1,
                skill_name=input_data.get("skill_name", "unknown"),
                script_name=input_data.get("script_name", "unknown"),
            )

        # Get skill from registry
        skill = self.registry.get_skill(params.skill_name)
        if not skill:
            return SkillBashOutput(
                success=False,
                stdout="",
                stderr=f"Skill '{params.skill_name}' not found in registry",
                exit_code=1,
                skill_name=params.skill_name,
                script_name=params.script_name,
            )

        # Check skill has scripts
        if not skill.has_scripts:
            return SkillBashOutput(
                success=False,
                stdout="",
                stderr=f"Skill '{params.skill_name}' has no scripts/ folder",
                exit_code=1,
                skill_name=params.skill_name,
                script_name=params.script_name,
            )

        # Execute script via SkillScriptExecutor
        logger.info(
            f"[SKILL_BASH] Executing {params.skill_name}/{params.script_name} "
            f"with args: {params.args}"
        )

        try:
            result = await self.executor.execute(
                skill=skill,
                script=params.script_name,
                args=params.args,
            )

            return SkillBashOutput(
                success=result.success,
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.return_code,
                skill_name=params.skill_name,
                script_name=params.script_name,
            )

        except Exception as e:
            logger.exception(f"[SKILL_BASH] Execution error: {e}")
            return SkillBashOutput(
                success=False,
                stdout="",
                stderr=f"Execution error: {type(e).__name__}: {e}",
                exit_code=1,
                skill_name=params.skill_name,
                script_name=params.script_name,
            )

    def to_tool_definition(self) -> dict[str, Any]:
        """Convert to tool definition for LLM (Claude/GPT-4 tool_use format).

        Returns dict compatible with Anthropic/OpenAI tool calling API.
        """
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.get_input_schema(),
        }

    def to_react_format(self) -> str:
        """Convert to ReAct-style tool description for self-hosted models.

        For models without native tool_use, this provides a text description
        the model can use with JSON output parsing.
        """
        schema = self.get_input_schema()
        properties = schema.get("properties", {})

        params_desc = []
        for name, prop in properties.items():
            desc = prop.get("description", "")
            params_desc.append(f"  - {name}: {desc}")

        return f"""Tool: {self.name}
Description: {self.description}
Parameters:
{chr(10).join(params_desc)}

To use this tool, output JSON:
{{"tool": "{self.name}", "input": {{"skill_name": "...", "script_name": "...", "args": [...]}}}}
"""

# Singleton instance for easy import
_skill_bash_tool: SkillBashTool | None = None

def get_skill_bash_tool() -> SkillBashTool:
    """Get singleton SkillBashTool instance."""
    global _skill_bash_tool
    if _skill_bash_tool is None:
        _skill_bash_tool = SkillBashTool()
    return _skill_bash_tool
