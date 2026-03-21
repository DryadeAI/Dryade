"""VLLMResponseValidator -- deterministic vLLM response validation and repair.

Validates vLLM LLM responses against 7 known failure modes and attempts
deterministic repair where possible (FM-1, FM-2, FM-3). Non-repairable
failure modes (FM-4 through FM-7) are classified and returned for upstream
handling by the orchestrator retry loop.

Failure modes:
  FM-1: Tool calls buried in reasoning_content instead of tool_calls field
  FM-2: content=None with empty/missing tool_calls
  FM-3: Malformed JSON in tool_calls arguments
  FM-4: KV cache OOM (HTTP 500 with memory error)
  FM-5: Partial streaming interruption (finish_reason=None)
  FM-6: Wrong tool name (not in available_tools)
  FM-7: Truncated response (unclosed brackets/braces)

Validation order (first match wins):
  1. API error check (FM-4 / generic api_error)
  2. Empty response check
  3. FM-1: Tool calls in reasoning_content (repair)
  4. FM-2: content=None recovery from reasoning_content (repair)
  5. FM-6: Wrong tool name
  6. FM-3: Malformed JSON in tool_calls arguments (repair)
  7. FM-5: Stream interruption (finish_reason=None)
  8. FM-7: Truncated response (unclosed brackets/braces)
  9. Pass: valid=True
"""

import json
import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Compiled regex for extracting tool call JSON arrays from reasoning text
# ---------------------------------------------------------------------------

# Matches a JSON array containing objects with "name" and "arguments" keys.
# Uses a non-greedy match to capture the smallest valid array.
_RE_TOOL_CALL_ARRAY = re.compile(
    r'\[(?:\s*\{[^[\]]*?"name"\s*:\s*"[^"]+?"[^[\]]*?"arguments"\s*:.*?\}(?:\s*,\s*\{[^[\]]*?"name"\s*:\s*"[^"]+?"[^[\]]*?"arguments"\s*:.*?\})*\s*)\]',
    re.DOTALL,
)

# OOM / GPU memory patterns (case-insensitive)
_RE_OOM = re.compile(
    r"kv[\s_-]*cache|out[\s_-]*of[\s_-]*memory|gpu[\s_-]*memory",
    re.IGNORECASE,
)

@dataclass
class ValidationResult:
    """Result of validating a vLLM response."""

    valid: bool
    repaired: bool = False
    failure_mode: str | None = None
    repaired_content: str | None = None
    repaired_tool_calls: list | None = None

class VLLMResponseValidator:
    """Validates and repairs vLLM responses against 7 known failure modes.

    Usage::

        validator = VLLMResponseValidator(available_tools=["search", "write"])
        result = validator.validate(response_dict)
        if result.valid:
            if result.repaired:
                # use result.repaired_content or result.repaired_tool_calls
                ...
            else:
                # original response is fine
                ...
        else:
            # handle failure: result.failure_mode tells you what went wrong
            ...
    """

    def __init__(self, available_tools: list[str] | None = None) -> None:
        self.available_tools = available_tools

    # -------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------

    def validate(self, response: dict) -> ValidationResult:
        """Validate a vLLM response dict and attempt repair if possible.

        The *response* dict may contain any of these keys:
        ``content``, ``reasoning_content``, ``reasoning``, ``tool_calls``,
        ``finish_reason``, ``error``, ``http_status``.

        Returns a :class:`ValidationResult` describing whether the response
        is valid, was repaired, or failed (with a failure_mode string).
        """
        # -- Step 1: API error check (FM-4 first, then generic) -----------
        error = response.get("error")
        if error is not None:
            error_str = str(error)
            http_status = response.get("http_status")
            if http_status == 500 and _RE_OOM.search(error_str):
                return ValidationResult(valid=False, failure_mode="kv_cache_oom")
            return ValidationResult(valid=False, failure_mode="api_error")

        # -- Extract common fields ----------------------------------------
        content = response.get("content")
        reasoning_content = response.get("reasoning_content") or response.get("reasoning")
        tool_calls = response.get("tool_calls")
        finish_reason = response.get("finish_reason")

        # Normalize empty tool_calls to None for easier checks
        has_tool_calls = bool(tool_calls)

        # -- Step 2: Empty response check ---------------------------------
        if content is None and not has_tool_calls and not reasoning_content:
            return ValidationResult(valid=False, failure_mode="empty_response")

        # -- Step 3 & 4: FM-1 (tool calls in reasoning) / FM-2 (content recovery)
        if (content is None or content == "") and reasoning_content:
            # Check if reasoning_content contains tool call patterns (FM-1)
            extracted = self._extract_tool_calls_from_reasoning(reasoning_content)
            if extracted is not None:
                return ValidationResult(
                    valid=True,
                    repaired=True,
                    repaired_tool_calls=extracted,
                )
            # No tool call pattern -- fall through to FM-2 content recovery
            if content is None:
                return ValidationResult(
                    valid=True,
                    repaired=True,
                    repaired_content=reasoning_content,
                )

        # -- Step 5: FM-6 (wrong tool name) -------------------------------
        if has_tool_calls and self.available_tools is not None:
            for tc in tool_calls:
                # Handle both OpenAI format (nested under "function") and
                # flat format (from FM-1 repair extraction)
                name = tc.get("function", {}).get("name", "") or tc.get("name", "")
                if name and name not in self.available_tools:
                    return ValidationResult(valid=False, failure_mode="wrong_tool")

        # -- Step 6: FM-3 (malformed JSON in tool_calls arguments) --------
        if has_tool_calls:
            repaired_calls, any_repaired, any_failed = self._check_tool_call_json(tool_calls)
            if any_failed:
                return ValidationResult(valid=False, failure_mode="malformed_json")
            if any_repaired:
                return ValidationResult(
                    valid=True,
                    repaired=True,
                    repaired_tool_calls=repaired_calls,
                )

        # -- Step 7: FM-5 (stream interruption) ---------------------------
        if content and "finish_reason" in response and finish_reason is None:
            return ValidationResult(valid=False, failure_mode="stream_interrupted")

        # -- Step 8: FM-7 (truncation) ------------------------------------
        if content and self._is_truncated(content, finish_reason):
            return ValidationResult(valid=False, failure_mode="truncated")

        # -- Step 9: Pass -------------------------------------------------
        return ValidationResult(valid=True)

    # -------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------

    @staticmethod
    def _extract_tool_calls_from_reasoning(text: str) -> list | None:
        """Extract tool call JSON array from reasoning text.

        Returns a list of tool-call dicts if a valid JSON array containing
        objects with ``name`` and ``arguments`` keys is found, else None.
        """
        match = _RE_TOOL_CALL_ARRAY.search(text)
        if match is None:
            return None
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, list) and all(
                isinstance(item, dict) and "name" in item and "arguments" in item for item in parsed
            ):
                # Ensure arguments are JSON strings
                for item in parsed:
                    if not isinstance(item["arguments"], str):
                        item["arguments"] = json.dumps(item["arguments"])
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
        return None

    @staticmethod
    def _check_tool_call_json(
        tool_calls: list[dict],
    ) -> tuple[list[dict], bool, bool]:
        """Validate and attempt repair of JSON arguments in tool calls.

        Returns ``(repaired_calls, any_repaired, any_failed)``.
        """
        repaired_calls: list[dict] = []
        any_repaired = False
        any_failed = False

        for tc in tool_calls:
            args = tc.get("arguments", "{}")
            if not isinstance(args, str):
                # Already parsed (dict/list) -- fine
                repaired_calls.append(tc)
                continue

            # Try parsing as-is
            try:
                json.loads(args)
                repaired_calls.append(tc)
                continue
            except json.JSONDecodeError:
                pass

            # Attempt repair
            repaired = VLLMResponseValidator._repair_json(args)
            if repaired is not None:
                new_tc = dict(tc)
                new_tc["arguments"] = repaired
                repaired_calls.append(new_tc)
                any_repaired = True
            else:
                any_failed = True
                break  # One unrepairable call fails the whole response

        return repaired_calls, any_repaired, any_failed

    @staticmethod
    def _repair_json(text: str) -> str | None:
        """Attempt to repair malformed JSON.

        Strategies:
        1. Strip trailing garbage after the last valid JSON boundary.
        2. Close unclosed brackets/braces.
        3. Combine both (strip then close).

        Returns the repaired JSON string, or None if unrepairable.
        """
        # Strategy 1: strip trailing garbage
        stripped = VLLMResponseValidator._strip_trailing_garbage(text)
        if stripped:
            try:
                json.loads(stripped)
                return stripped
            except json.JSONDecodeError:
                pass

        # Strategy 2: close unclosed brackets
        closed = VLLMResponseValidator._close_unclosed_brackets(text)
        try:
            json.loads(closed)
            return closed
        except json.JSONDecodeError:
            pass

        # Strategy 3: strip then close
        if stripped:
            closed2 = VLLMResponseValidator._close_unclosed_brackets(stripped)
            try:
                json.loads(closed2)
                return closed2
            except json.JSONDecodeError:
                pass

        return None

    @staticmethod
    def _strip_trailing_garbage(text: str) -> str | None:
        """Find the last valid JSON boundary and strip everything after it.

        Looks for the last ``}`` or ``]`` that could end a JSON value.
        Returns the stripped string, or None if no boundary found.
        """
        # Walk backwards to find the last } or ]
        for i in range(len(text) - 1, -1, -1):
            if text[i] in ("}", "]"):
                candidate = text[: i + 1]
                return candidate
        return None

    @staticmethod
    def _close_unclosed_brackets(text: str) -> str:
        """Append missing closing brackets/braces to make JSON valid.

        Counts open vs close ``{}``, ``[]`` pairs and appends the
        appropriate closers in reverse order.
        """
        stack: list[str] = []
        in_string = False
        escape_next = False

        for ch in text:
            if escape_next:
                escape_next = False
                continue
            if ch == "\\" and in_string:
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                stack.append("}")
            elif ch == "[":
                stack.append("]")
            elif ch in ("}", "]"):
                if stack and stack[-1] == ch:
                    stack.pop()

        # Append closers in reverse order
        stack.reverse()
        return text + "".join(stack)

    @staticmethod
    def _is_truncated(content: str, finish_reason: str | None = None) -> bool:
        """Detect if content appears to be truncated.

        A response is considered truncated if:
        - ``finish_reason`` is ``"length"`` (explicit token limit) AND the
          content has unclosed JSON brackets/braces.
        """
        if finish_reason != "length":
            return False

        # Check for unclosed brackets/braces in JSON-like content
        opens = 0
        in_string = False
        escape_next = False

        for ch in content:
            if escape_next:
                escape_next = False
                continue
            if ch == "\\" and in_string:
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch in ("{", "["):
                opens += 1
            elif ch in ("}", "]"):
                opens -= 1

        return opens > 0
