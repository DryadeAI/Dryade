"""Adapter that wraps MD skills as UniversalAgent instances.

Makes skills visible to DryadeOrchestrator alongside coded agents.
Two execution strategies based on skill type:
  - Script-bearing skills: execute scripts via SkillScriptExecutor
  - Instruction-only skills: return instructions as context enrichment
"""

import logging
import time
from typing import Any

from core.adapters.protocol import (
    AgentCapabilities,
    AgentCapability,
    AgentCard,
    AgentFramework,
    AgentResult,
    UniversalAgent,
)
from core.skills.executor import ScriptExecutionResult, get_skill_executor
from core.skills.models import Skill

logger = logging.getLogger(__name__)

# Namespace prefix for skill-as-agent names
SKILL_AGENT_PREFIX = "skill-"

class SkillAgentAdapter(UniversalAgent):
    """Wrap a markdown Skill as a UniversalAgent.

    This adapter makes MD skills discoverable and executable by the
    DryadeOrchestrator through the standard AgentRegistry. The orchestrator
    does not need to know whether it is calling a coded agent or a skill --
    the interface is identical.

    Two execution strategies:
      Strategy A (script-bearing): Skill has a scripts/ directory.
          The adapter runs the first matching script via SkillScriptExecutor
          and returns stdout as the result.
      Strategy B (instruction-only): Skill has only SKILL.md instructions.
          The adapter returns the instructions as structured context for
          the ThinkingProvider to incorporate into the next LLM call.
          This is NOT a no-op -- it enriches the orchestrator's context
          so the LLM can follow the skill's domain-specific guidance.
    """

    def __init__(self, skill: Skill):
        """Initialize adapter with a Skill instance.

        Args:
            skill: Parsed Skill from SkillRegistry
        """
        self._skill = skill
        self._executor = get_skill_executor()

    @property
    def skill(self) -> Skill:
        """Access the underlying Skill."""
        return self._skill

    @property
    def adapter_name(self) -> str:
        """Canonical name used in AgentRegistry."""
        return f"{SKILL_AGENT_PREFIX}{self._skill.name}"

    def get_card(self) -> AgentCard:
        """Return agent card for orchestrator discovery.

        Maps Skill fields to AgentCard fields:
          - name: "skill-{skill.name}" (namespaced to avoid collisions)
          - description: skill.description
          - framework: AgentFramework.CUSTOM with skill metadata
          - capabilities: one AgentCapability per script, or a single
            "instruction-guidance" capability for instruction-only skills
        """
        capabilities = []

        if self._skill.has_scripts:
            # One capability per script
            for script_name in self._skill.get_scripts():
                capabilities.append(
                    AgentCapability(
                        name=script_name,
                        description=f"Execute {script_name} from skill '{self._skill.name}'",
                        input_schema={
                            "type": "object",
                            "properties": {
                                "args": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Command-line arguments for the script",
                                },
                                "stdin_data": {
                                    "type": "string",
                                    "description": "Data to pass to script's stdin",
                                },
                            },
                        },
                        output_schema={
                            "type": "object",
                            "properties": {
                                "stdout": {"type": "string"},
                                "stderr": {"type": "string"},
                                "return_code": {"type": "integer"},
                            },
                        },
                    )
                )
        else:
            # Instruction-only: single capability
            capabilities.append(
                AgentCapability(
                    name="instruction-guidance",
                    description=f"Domain-specific guidance for: {self._skill.description}",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "task": {"type": "string", "description": "Task to apply skill to"},
                        },
                    },
                    output_schema={
                        "type": "object",
                        "properties": {
                            "instructions": {"type": "string"},
                            "skill_type": {"type": "string", "enum": ["instruction"]},
                        },
                    },
                )
            )

        return AgentCard(
            name=self.adapter_name,
            description=self._skill.description,
            version="1.0",
            framework=AgentFramework.CUSTOM,
            capabilities=capabilities,
            metadata={
                "is_skill": True,
                "skill_type": "script" if self._skill.has_scripts else "instruction",
                "skill_name": self._skill.name,
                "skill_dir": self._skill.skill_dir,
                "plugin_id": self._skill.plugin_id,
                "emoji": self._skill.metadata.emoji,
                "chat_eligible": self._skill.chat_eligible,
            },
        )

    async def execute(self, task: str, context: dict[str, Any] | None = None) -> AgentResult:
        """Execute the skill.

        Routes to Strategy A (script) or Strategy B (instruction) based on
        the skill's has_scripts flag.

        Args:
            task: Natural language task description from orchestrator
            context: Execution context dict

        Returns:
            AgentResult with execution output
        """
        context = context or {}
        start_time = time.perf_counter()

        try:
            if self._skill.has_scripts:
                return await self._execute_script(task, context)
            else:
                return self._execute_instruction(task, context)
        except Exception as e:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            logger.exception(
                f"[SKILL-ADAPTER] Execution failed for skill '{self._skill.name}': {e}"
            )
            return AgentResult(
                result=None,
                status="error",
                error=f"{type(e).__name__}: {str(e)}",
                metadata={
                    "type": "skill",
                    "skill_name": self._skill.name,
                    "skill_type": "script" if self._skill.has_scripts else "instruction",
                    "duration_ms": duration_ms,
                },
            )

    async def _execute_script(self, task: str, context: dict[str, Any]) -> AgentResult:
        """Strategy A: Execute a script-bearing skill.

        Script selection:
        1. If context contains "script" key, use that script name
        2. If task string matches a script name, use it
        3. Otherwise, use the first available script (entry point convention)

        Args:
            task: Task description (may contain script name)
            context: Execution context

        Returns:
            AgentResult with script stdout
        """
        scripts = self._skill.get_scripts()
        if not scripts:
            return AgentResult(
                result=None,
                status="error",
                error=f"Skill '{self._skill.name}' has scripts_dir but no scripts found",
                metadata={"type": "skill", "skill_name": self._skill.name},
            )

        # Script selection
        script_name = context.get("script")
        if not script_name:
            # Try to find script mentioned in the task
            for s in scripts:
                if s.lower() in task.lower():
                    script_name = s
                    break
        if not script_name:
            # Default: first script (entry point convention)
            script_name = scripts[0]

        # Extract arguments
        args = context.get("args", [])
        if isinstance(args, str):
            args = args.split()

        extra_env = context.get("env", {})
        stdin_data = context.get("stdin_data")

        logger.info(
            f"[SKILL-ADAPTER] Executing script: skill={self._skill.name}, "
            f"script={script_name}, args={args}"
        )

        result: ScriptExecutionResult = await self._executor.execute(
            skill=self._skill,
            script=script_name,
            args=args,
            extra_env=extra_env,
            stdin_data=stdin_data,
        )

        status = "ok" if result.success else "error"
        output = result.stdout if result.success else result.stderr or result.error

        return AgentResult(
            result=output,
            status=status,
            error=result.error if not result.success else None,
            metadata={
                "type": "skill",
                "skill_name": self._skill.name,
                "skill_type": "script",
                "script": script_name,
                "return_code": result.return_code,
                "duration_ms": result.duration_ms,
                "timed_out": result.timed_out,
            },
        )

    def _execute_instruction(self, task: str, context: dict[str, Any]) -> AgentResult:
        """Strategy B: Return instructions as context enrichment.

        Instruction-only skills have no runnable code. Instead, the adapter
        returns the skill's markdown instructions in a structured format that
        the ThinkingProvider can inject into the next orchestration LLM call.

        The orchestrator loop receives this as a successful observation:
        the "result" is the skill's instructions. The ThinkingProvider then
        sees these instructions in the observation history and can follow
        them when reasoning about subsequent steps.

        This is equivalent to what MarkdownSkillAdapter.format_skills_for_prompt()
        does for chat mode, but triggered on-demand by the orchestrator.

        Args:
            task: Task to apply instructions to
            context: Execution context

        Returns:
            AgentResult with structured instruction context
        """
        from core.skills.adapter import MarkdownSkillAdapter

        adapter = MarkdownSkillAdapter()
        adapter.format_skills_for_prompt([self._skill])
        guidance = adapter.build_skill_guidance()

        instruction_context = (
            f"## Skill: {self._skill.name}\n\n"
            f"**Task:** {task}\n\n"
            f"**Instructions:**\n{self._skill.instructions}\n\n"
            f"**Guidance:**\n{guidance}"
        )

        return AgentResult(
            result=instruction_context,
            status="ok",
            metadata={
                "type": "skill",
                "skill_name": self._skill.name,
                "skill_type": "instruction",
                "instruction_length": len(self._skill.instructions),
                "is_context_enrichment": True,
            },
        )

    def get_tools(self) -> list[dict[str, Any]]:
        """Return tools in OpenAI function format.

        Script-bearing skills expose each script as a tool.
        Instruction-only skills expose a single "apply_instructions" tool.
        """
        tools = []

        if self._skill.has_scripts:
            for script_name in self._skill.get_scripts():
                tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": f"{self._skill.name}__{script_name.replace('.', '_')}",
                            "description": f"Run {script_name} from skill '{self._skill.name}'",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "args": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "CLI arguments",
                                    },
                                },
                            },
                        },
                    }
                )
        else:
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": f"{self._skill.name}__apply_instructions",
                        "description": self._skill.description,
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "task": {
                                    "type": "string",
                                    "description": "Task to apply skill instructions to",
                                },
                            },
                            "required": ["task"],
                        },
                    },
                }
            )

        return tools

    def capabilities(self) -> AgentCapabilities:
        """Return skill-specific capabilities.

        Skills never support streaming (scripts are batch, instructions
        are synchronous). Timeout defaults to 60s for scripts (matching
        SkillScriptExecutor.DEFAULT_TIMEOUT_SECONDS).
        """
        return AgentCapabilities(
            supports_streaming=False,
            supports_memory=False,
            supports_knowledge=False,
            supports_delegation=False,
            supports_callbacks=False,
            max_retries=2,  # Scripts are deterministic; fewer retries
            timeout_seconds=60 if self._skill.has_scripts else 5,
            is_critical=False,  # Skills are generally non-critical
            framework_specific={
                "is_skill": True,
                "skill_type": "script" if self._skill.has_scripts else "instruction",
                "has_scripts": self._skill.has_scripts,
            },
        )

    def supports_streaming(self) -> bool:
        """Skills do not support streaming."""
        return False
