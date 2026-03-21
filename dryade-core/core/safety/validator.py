# Migrated from plugins/starter/safety/validator.py into core (Phase 222).

"""Safety: Input Validation, Output Sanitization, and Command Classification.

Three-tier command safety:
- SAFE: Auto-approve (ls, cat, pwd)
- APPROVE: Requires user confirmation (pip install, git push)
- UNSAFE: Block entirely (rm -rf /, fork bombs)

Input/Output protection:
- Pydantic-based input validation with size limits
- Context-aware output sanitization (HTML, SQL, Shell, JSON)
- Transparent validation before agent execution

Inspired by Orchestral AI's safety classification system.

Target: ~350 LOC (net +45 from 305 current)
"""

import html
import json
import logging
import os
import re
import shlex
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

logger = logging.getLogger(__name__)

class SafetyLevel(str, Enum):
    """Safety classification levels."""

    SAFE = "safe"  # Auto-approve, no confirmation needed
    APPROVE = "approve"  # Requires user confirmation
    UNSAFE = "unsafe"  # Block entirely

class SafetyRule(BaseModel):
    """A safety classification rule."""

    pattern: str
    level: SafetyLevel
    reason: str
    category: str = "general"

# Default safety rules
DEFAULT_RULES: list[SafetyRule] = [
    # UNSAFE - Always block
    SafetyRule(
        pattern=r"rm\s+(-rf?|--recursive)\s+/\s*$",
        level=SafetyLevel.UNSAFE,
        reason="Recursive delete from root",
        category="filesystem",
    ),
    SafetyRule(
        pattern=r"rm\s+(-rf?|--recursive)\s+/\*",
        level=SafetyLevel.UNSAFE,
        reason="Delete all files from root",
        category="filesystem",
    ),
    SafetyRule(
        pattern=r"dd\s+if=.*of=/dev/[sh]d",
        level=SafetyLevel.UNSAFE,
        reason="Direct disk write",
        category="filesystem",
    ),
    SafetyRule(
        pattern=r":\(\)\{\s*:\|:\s*&\s*\};:",
        level=SafetyLevel.UNSAFE,
        reason="Fork bomb",
        category="system",
    ),
    SafetyRule(
        pattern=r"mkfs\.",
        level=SafetyLevel.UNSAFE,
        reason="Filesystem format",
        category="filesystem",
    ),
    SafetyRule(
        pattern=r">\s*/dev/[sh]d",
        level=SafetyLevel.UNSAFE,
        reason="Direct device write",
        category="filesystem",
    ),
    # APPROVE - Requires confirmation
    SafetyRule(
        pattern=r"pip\s+install",
        level=SafetyLevel.APPROVE,
        reason="Package installation",
        category="packages",
    ),
    SafetyRule(
        pattern=r"npm\s+(install|i)\s",
        level=SafetyLevel.APPROVE,
        reason="NPM package installation",
        category="packages",
    ),
    SafetyRule(
        pattern=r"git\s+push", level=SafetyLevel.APPROVE, reason="Code publication", category="git"
    ),
    SafetyRule(
        pattern=r"git\s+push\s+.*--force",
        level=SafetyLevel.APPROVE,
        reason="Force push (destructive)",
        category="git",
    ),
    SafetyRule(
        pattern=r"curl.*\|\s*(sh|bash)",
        level=SafetyLevel.APPROVE,
        reason="Remote script execution",
        category="network",
    ),
    SafetyRule(
        pattern=r"wget.*\|\s*(sh|bash)",
        level=SafetyLevel.APPROVE,
        reason="Remote script execution",
        category="network",
    ),
    SafetyRule(
        pattern=r"DROP\s+(TABLE|DATABASE)",
        level=SafetyLevel.APPROVE,
        reason="Database deletion",
        category="database",
    ),
    SafetyRule(
        pattern=r"TRUNCATE\s+TABLE",
        level=SafetyLevel.APPROVE,
        reason="Table truncation",
        category="database",
    ),
    SafetyRule(
        pattern=r"rm\s+-r",
        level=SafetyLevel.APPROVE,
        reason="Recursive delete",
        category="filesystem",
    ),
    SafetyRule(
        pattern=r"chmod\s+777",
        level=SafetyLevel.APPROVE,
        reason="Permissive file permissions",
        category="filesystem",
    ),
    # SAFE - Auto-approve
    SafetyRule(
        pattern=r"^ls(\s|$)", level=SafetyLevel.SAFE, reason="List directory", category="filesystem"
    ),
    SafetyRule(
        pattern=r"^cat\s", level=SafetyLevel.SAFE, reason="Read file", category="filesystem"
    ),
    SafetyRule(
        pattern=r"^pwd$", level=SafetyLevel.SAFE, reason="Print directory", category="filesystem"
    ),
    SafetyRule(
        pattern=r"^cd\s", level=SafetyLevel.SAFE, reason="Change directory", category="filesystem"
    ),
    SafetyRule(pattern=r"^echo\s", level=SafetyLevel.SAFE, reason="Print text", category="general"),
    SafetyRule(
        pattern=r"^git\s+status", level=SafetyLevel.SAFE, reason="Git status", category="git"
    ),
    SafetyRule(pattern=r"^git\s+log", level=SafetyLevel.SAFE, reason="Git log", category="git"),
    SafetyRule(pattern=r"^git\s+diff", level=SafetyLevel.SAFE, reason="Git diff", category="git"),
    SafetyRule(
        pattern=r"^git\s+branch", level=SafetyLevel.SAFE, reason="Git branch", category="git"
    ),
    SafetyRule(
        pattern=r"^head\s", level=SafetyLevel.SAFE, reason="Read file head", category="filesystem"
    ),
    SafetyRule(
        pattern=r"^tail\s", level=SafetyLevel.SAFE, reason="Read file tail", category="filesystem"
    ),
    SafetyRule(
        pattern=r"^grep\s", level=SafetyLevel.SAFE, reason="Search text", category="filesystem"
    ),
    SafetyRule(
        pattern=r"^find\s", level=SafetyLevel.SAFE, reason="Find files", category="filesystem"
    ),
]

class SafetyClassifier:
    """Classify tool calls into SAFE/APPROVE/UNSAFE.

    Usage:
        classifier = SafetyClassifier()
        level, reason = classifier.classify("bash", {"command": "rm -rf /"})

        if level == SafetyLevel.UNSAFE:
            raise SecurityError(f"Blocked: {reason}")
        elif level == SafetyLevel.APPROVE:
            # Ask user for confirmation
            pass
        else:
            # Safe to execute
            pass
    """

    def __init__(self, rules: list[SafetyRule] | None = None):
        """Initialize safety classifier with optional custom rules.

        Args:
            rules: List of safety rules. Uses DEFAULT_RULES if not provided.
        """
        self.rules = rules or DEFAULT_RULES

    def classify(self, tool_name: str, args: dict) -> tuple[SafetyLevel, str]:
        """Classify a tool call.

        Args:
            tool_name: Name of the tool being called
            args: Tool arguments

        Returns:
            Tuple of (SafetyLevel, reason)
        """
        # Build string representation for matching
        if tool_name in ("bash", "shell", "execute", "run_command"):
            call_str = args.get("command", "")
        else:
            call_str = f"{tool_name} {' '.join(str(v) for v in args.values())}"

        # Check rules in priority order: UNSAFE -> APPROVE -> SAFE
        for level in [SafetyLevel.UNSAFE, SafetyLevel.APPROVE, SafetyLevel.SAFE]:
            for rule in self.rules:
                if rule.level == level and re.search(rule.pattern, call_str, re.IGNORECASE):
                    return rule.level, rule.reason

        # Default: APPROVE (unknown operations require confirmation)
        return SafetyLevel.APPROVE, "Unknown operation - requires confirmation"

    def add_rule(self, rule: SafetyRule):
        """Add a custom rule."""
        self.rules.insert(0, rule)  # Higher priority for custom rules

    def get_rules_by_category(self, category: str) -> list[SafetyRule]:
        """Get rules for a specific category."""
        return [r for r in self.rules if r.category == category]

    def is_safe(self, tool_name: str, args: dict) -> bool:
        """Quick check if operation is safe."""
        level, _ = self.classify(tool_name, args)
        return level == SafetyLevel.SAFE

    def is_blocked(self, tool_name: str, args: dict) -> bool:
        """Quick check if operation is blocked."""
        level, _ = self.classify(tool_name, args)
        return level == SafetyLevel.UNSAFE

# Global classifier instance
safety_classifier = SafetyClassifier()

# -----------------------------------------------------------------------------
# Input Validation
# -----------------------------------------------------------------------------

# Size limits (configurable via environment)
MAX_MESSAGE_SIZE = int(os.getenv("DRYADE_MAX_MESSAGE_SIZE", str(10 * 1024)))  # 10KB default
MAX_FILE_SIZE = int(os.getenv("DRYADE_MAX_FILE_SIZE", str(100 * 1024 * 1024)))  # 100MB default
MAX_ARRAY_ITEMS = int(os.getenv("DRYADE_MAX_ARRAY_ITEMS", "1000"))

class ChatMessage(BaseModel):
    """Validated chat message input."""

    role: str = Field(..., pattern="^(system|user|assistant|tool)$")
    content: str = Field(..., max_length=MAX_MESSAGE_SIZE)
    name: str | None = Field(None, max_length=64)
    tool_call_id: str | None = Field(None, max_length=64)

class ToolArgs(BaseModel):
    """Validated tool arguments."""

    tool_name: str = Field(..., max_length=64, pattern="^[a-zA-Z0-9_-]+$")
    args: dict[str, Any] = Field(default_factory=dict)

    @field_validator("args")
    @classmethod
    def validate_args_size(cls, v):
        """Ensure args don't exceed size limits."""
        # Check total serialized size
        args_str = json.dumps(v)
        if len(args_str) > MAX_MESSAGE_SIZE:
            raise ValueError(f"Arguments too large ({len(args_str)} bytes, max {MAX_MESSAGE_SIZE})")

        # Check array sizes
        for key, value in v.items():
            if isinstance(value, list) and len(value) > MAX_ARRAY_ITEMS:
                raise ValueError(
                    f"Array '{key}' exceeds max items ({len(value)} > {MAX_ARRAY_ITEMS})"
                )

        return v

class QueryParams(BaseModel):
    """Validated query parameters."""

    limit: int | None = Field(None, ge=1, le=1000)
    offset: int | None = Field(None, ge=0)
    filter: str | None = Field(None, max_length=512)
    sort: str | None = Field(None, max_length=64, pattern="^[a-zA-Z0-9_,-]+$")

class FileUpload(BaseModel):
    """Validated file upload metadata."""

    filename: str = Field(..., max_length=255, pattern="^[a-zA-Z0-9._-]+$")
    content_type: str = Field(..., max_length=128)
    size: int = Field(..., ge=0, le=MAX_FILE_SIZE)

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, v):
        """Prevent path traversal in filenames."""
        if ".." in v or "/" in v or "\\" in v:
            raise ValueError("Filename contains invalid path characters")
        return v

@dataclass
class ValidationResult:
    """Result of input validation."""

    valid: bool
    errors: list[str] = dataclass_field(default_factory=list)
    sanitized_input: Any = None

class InputValidator:
    """Pydantic-based input validator with size limits and schema enforcement.

    Usage:
        validator = InputValidator()
        result = validator.validate_input(
            {"role": "user", "content": "Hello"},
            ChatMessage
        )
        if not result.valid:
            raise ValueError(result.errors)
    """

    def __init__(self):
        """Initialize input validator with strict mode from environment."""
        self._strict_mode = os.getenv("DRYADE_INPUT_VALIDATION_STRICT", "true").lower() == "true"

    def validate_input(self, data: Any, model: type[BaseModel]) -> ValidationResult:
        """Validate input against Pydantic model.

        Args:
            data: Input data to validate
            model: Pydantic model class

        Returns:
            ValidationResult with validity status and errors
        """
        try:
            # Validate with Pydantic
            validated = model.model_validate(data)
            return ValidationResult(valid=True, sanitized_input=validated.model_dump())
        except ValidationError as e:
            errors = [f"{err['loc'][0]}: {err['msg']}" for err in e.errors()]
            logger.warning(f"Input validation failed: {errors}")

            if self._strict_mode:
                # Strict mode: reject invalid input
                return ValidationResult(valid=False, errors=errors)
            else:
                # Permissive mode: sanitize and warn
                sanitized = self._sanitize_invalid_input(data, model)
                return ValidationResult(valid=True, errors=errors, sanitized_input=sanitized)

    def _sanitize_invalid_input(self, data: Any, model: type[BaseModel]) -> dict:
        """Best-effort sanitization of invalid input.

        Removes invalid fields, truncates oversized fields.
        """
        if not isinstance(data, dict):
            return {}

        sanitized = {}
        model_fields = model.model_fields

        for field_name, field_info in model_fields.items():
            if field_name in data:
                value = data[field_name]

                # Truncate strings that are too long
                if isinstance(value, str) and hasattr(field_info, "max_length"):
                    max_len = field_info.max_length
                    if max_len and len(value) > max_len:
                        sanitized[field_name] = value[:max_len]
                    else:
                        sanitized[field_name] = value
                else:
                    sanitized[field_name] = value

        return sanitized

    def validate_json_schema(self, data: Any, schema: dict) -> ValidationResult:
        """Validate data against JSON schema.

        Args:
            data: Data to validate
            schema: JSON schema definition

        Returns:
            ValidationResult
        """
        try:
            import jsonschema

            jsonschema.validate(instance=data, schema=schema)
            return ValidationResult(valid=True, sanitized_input=data)
        except ImportError:
            logger.warning("jsonschema not installed, skipping JSON schema validation")
            return ValidationResult(valid=True, sanitized_input=data)
        except Exception as e:
            return ValidationResult(valid=False, errors=[str(e)])

# Global validator instance
input_validator = InputValidator()

# -----------------------------------------------------------------------------
# Output Sanitization
# -----------------------------------------------------------------------------

class SanitizationContext(str, Enum):
    """Output context types for sanitization."""

    HTML = "html"
    SQL = "sql"
    SHELL = "shell"
    JSON = "json"
    PLAIN = "plain"

class OutputSanitizer:
    """Context-aware output sanitizer.

    Prevents injection attacks by sanitizing outputs based on context:
    - HTML: Escape script tags, HTML entities
    - SQL: Reject raw SQL, recommend parameterized queries
    - Shell: Quote arguments, reject pipe/redirect operators
    - JSON: Validate structure, escape control characters

    Usage:
        sanitizer = OutputSanitizer()
        safe_html = sanitizer.sanitize_output("<script>alert('xss')</script>", SanitizationContext.HTML)
        # Result: "&lt;script&gt;alert('xss')&lt;/script&gt;"
    """

    def __init__(self):
        """Initialize output sanitizer with enabled state from environment."""
        self._enabled = os.getenv("DRYADE_OUTPUT_SANITIZATION_ENABLED", "true").lower() == "true"

    def sanitize_output(self, output: str, context: SanitizationContext) -> str:
        """Sanitize output based on context.

        Args:
            output: Output string to sanitize
            context: Sanitization context

        Returns:
            Sanitized output string
        """
        if not self._enabled:
            return output

        if context == SanitizationContext.HTML:
            return self.sanitize_html(output)
        elif context == SanitizationContext.SQL:
            return self.sanitize_sql(output)
        elif context == SanitizationContext.SHELL:
            return self.sanitize_shell(output)
        elif context == SanitizationContext.JSON:
            return self.sanitize_json(output)
        else:
            return output

    def sanitize_html(self, output: str) -> str:
        """Escape HTML entities to prevent XSS.

        Escapes: <, >, &, ", '
        """
        return html.escape(output, quote=True)

    def sanitize_sql(self, output: str) -> str:
        """Sanitize SQL output (reject raw SQL in user-facing output).

        Note: This is for outputs, not queries. For queries, use parameterized statements.
        """
        # Detect SQL keywords in output (potential SQL injection)
        sql_keywords = [
            "SELECT ",
            "INSERT ",
            "UPDATE ",
            "DELETE ",
            "DROP ",
            "CREATE ",
            "ALTER ",
            "TRUNCATE ",
            "EXEC ",
            "UNION ",
            "--",
            ";",
        ]

        output_upper = output.upper()
        for keyword in sql_keywords:
            if keyword in output_upper:
                logger.warning(f"SQL keyword detected in output: {keyword}")
                # Replace with placeholder to prevent execution
                output = output.replace(keyword.strip(), "[SQL_FILTERED]")
                output = output.replace(keyword.strip().lower(), "[SQL_FILTERED]")

        return output

    def sanitize_shell(self, output: str) -> str:
        """Quote shell output to prevent command injection.

        Rejects: pipe operators (|), redirects (>, <), command substitution ($(), ``)
        """
        # Detect shell operators
        dangerous_patterns = [
            r"\|",  # Pipe
            r">\s*[/\w]",  # Redirect
            r"<\s*[/\w]",  # Redirect
            r"\$\(",  # Command substitution
            r"`",  # Command substitution
            r"&&",  # Chain commands
            r"\|\|",  # Chain commands
            r";",  # Command separator
        ]

        for pattern in dangerous_patterns:
            if re.search(pattern, output):
                logger.warning(f"Dangerous shell pattern detected: {pattern}")
                # Quote the output to make it safe
                return shlex.quote(output)

        return output

    def sanitize_json(self, output: str) -> str:
        """Validate and sanitize JSON output.

        Ensures valid JSON structure and escapes control characters.
        """
        try:
            # Parse to validate structure
            parsed = json.loads(output)
            # Re-serialize to escape control characters
            return json.dumps(parsed, ensure_ascii=True)
        except (json.JSONDecodeError, TypeError):
            # Not valid JSON, escape as string
            return json.dumps(output, ensure_ascii=True)

    def detect_context(self, route: str) -> SanitizationContext:
        """Auto-detect sanitization context from route.

        Args:
            route: API route path

        Returns:
            Appropriate sanitization context
        """
        if "/chat" in route or "/websocket" in route:
            return SanitizationContext.HTML
        elif "/api" in route:
            return SanitizationContext.JSON
        elif "/query" in route or "/database" in route:
            return SanitizationContext.SQL
        elif "/execute" in route or "/command" in route:
            return SanitizationContext.SHELL
        else:
            return SanitizationContext.PLAIN

# Global sanitizer instance
output_sanitizer = OutputSanitizer()

# -----------------------------------------------------------------------------
# Convenience functions
# -----------------------------------------------------------------------------

def classify_safety(tool_name: str, args: dict) -> tuple[SafetyLevel, str]:
    """Classify a tool call's safety level."""
    return safety_classifier.classify(tool_name, args)

def is_safe_operation(tool_name: str, args: dict) -> bool:
    """Check if operation is safe to auto-approve."""
    return safety_classifier.is_safe(tool_name, args)

def is_blocked_operation(tool_name: str, args: dict) -> bool:
    """Check if operation should be blocked."""
    return safety_classifier.is_blocked(tool_name, args)

def validate_input(data: Any, model: type[BaseModel]) -> ValidationResult:
    """Validate input against Pydantic model."""
    return input_validator.validate_input(data, model)

def sanitize_output(output: str, context: SanitizationContext) -> str:
    """Sanitize output for specific context."""
    return output_sanitizer.sanitize_output(output, context)
