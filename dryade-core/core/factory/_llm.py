"""Thin LLM call helper for factory modules.

Wraps get_configured_llm() without importing OrchestrationThinkingProvider.
"""

import asyncio
import json
import logging
import re

logger = logging.getLogger(__name__)

__all__ = ["call_llm", "call_llm_json"]

# Pattern to strip <think>...</think> blocks (DeepSeek/Qwen reasoning models)
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)

# Pattern to strip markdown code fences (```json ... ``` or plain ```)
_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)

async def call_llm(prompt: str, *, system: str | None = None) -> str:
    """Call the configured LLM with a prompt and return the response text.

    Uses lazy import of get_configured_llm to avoid circular imports
    (factory is a leaf module).

    Args:
        prompt: User message content.
        system: Optional system message.

    Returns:
        LLM response as a string.
    """
    logger.debug("Factory LLM call: %d chars prompt", len(prompt))

    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    # Lazy import to avoid circular dependencies
    from core.config import get_settings
    from core.providers.llm_adapter import get_configured_llm

    # Factory LLM calls (config enrichment) can generate long responses —
    # use the planner timeout (300s) instead of the default chat timeout (120s).
    settings = get_settings()
    llm = get_configured_llm(timeout=settings.llm_planner_timeout)

    # Support both .call() (VLLMBaseLLM) and .invoke() (CrewAI LLM) patterns
    def _sync_call() -> str:
        if hasattr(llm, "call") and callable(llm.call):
            result = llm.call(messages=messages)
        elif hasattr(llm, "invoke") and callable(llm.invoke):
            result = llm.invoke(messages)
        else:
            raise TypeError(f"LLM instance {type(llm).__name__} has neither .call() nor .invoke()")
        return str(result)

    return await asyncio.to_thread(_sync_call)

async def call_llm_json(prompt: str, *, system: str | None = None) -> dict:
    """Call the configured LLM and parse the response as JSON.

    Args:
        prompt: User message content (should ask for JSON output).
        system: Optional system message.

    Returns:
        Parsed JSON as a dict.

    Raises:
        json.JSONDecodeError: If the response cannot be parsed as JSON.
    """
    raw = await call_llm(prompt, system=system)
    try:
        return _extract_json(raw)
    except json.JSONDecodeError:
        logger.warning("Factory LLM JSON parse failed. Raw response: %.500s", raw)
        raise

# Regex to strip trailing commas before ] or } (handles whitespace between them)
_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")

def _strip_trailing_commas(text: str) -> str:
    """Remove trailing commas before closing braces/brackets.

    Handles patterns like ``{"a": 1,}`` and ``[1, 2,]``.
    Applies the substitution repeatedly until no more changes occur.
    """
    result = text
    while True:
        new = _TRAILING_COMMA_RE.sub(r"\1", result)
        if new == result:
            break
        result = new
    return result

def _repair_truncated_json(text: str) -> str | None:
    """Repair truncated JSON by scanning for open structures and closing them.

    Handles these truncation edge cases:
    - Truncation mid-string value (unclosed quotes) — closes the string
    - Truncation mid-array (missing ]) — closes open brackets
    - Truncation mid-nested object (multiple unclosed }) — closes all open braces
    - Truncation after key but before value (trailing :) — removes dangling key
    - Trailing comma before closing brace/bracket — removes trailing comma
    - Complete top-level object followed by trailing content — returns the object

    Algorithm:
    1. Scan character-by-character tracking string boundaries, brace depth,
       and bracket depth.
    2. Record the last position where all structures are balanced (last_close).
    3. If balanced position found, return that substring (original behavior).
    4. If not, attempt active repair: close open string, remove trailing comma
       or colon, then close open brackets and braces in LIFO order.

    Returns:
        The repaired JSON string, or None if no valid repair is possible.
    """
    depth = 0
    bracket_depth = 0  # Track array nesting depth separately
    last_close = -1
    in_string = False
    escape_next = False
    # Stack tracks open structure types: '{' or '[' for LIFO close ordering
    open_stack: list[str] = []

    for i, ch in enumerate(text):
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
            depth += 1
            open_stack.append("{")
        elif ch == "}":
            depth -= 1
            if open_stack and open_stack[-1] == "{":
                open_stack.pop()
            if depth == 0 and bracket_depth == 0:
                last_close = i
        elif ch == "[":
            bracket_depth += 1
            open_stack.append("[")
        elif ch == "]":
            bracket_depth -= 1
            if open_stack and open_stack[-1] == "[":
                open_stack.pop()

    # Fast path: complete balanced top-level object already present
    if last_close >= 0:
        candidate = text[: last_close + 1]
        # The candidate may still contain trailing commas (e.g. {"a":1,})
        # Try parsing directly first, then fall through to comma cleanup
        try:
            json.loads(candidate)
            return candidate
        except (json.JSONDecodeError, ValueError):
            return _strip_trailing_commas(candidate)

    # No complete balanced object found — attempt active repair
    # Must have at least started a top-level object
    if depth <= 0 and bracket_depth <= 0:
        return None

    # Build the repair suffix
    # Start from a clean working copy of the text
    working = text

    # Step 1: Close unclosed string (if scan ended mid-string)
    if in_string:
        working = working + '"'

    # Step 2: Remove trailing comma or dangling key-colon patterns.
    # These appear when truncation happens right after a comma or a key.
    # We do this iteratively because stripping one may reveal another.
    for _ in range(5):
        stripped = working.rstrip()
        # Remove trailing comma (with optional whitespace before close)
        if stripped.endswith(","):
            working = stripped[:-1]
            continue
        # Remove trailing colon (key present but no value yet)
        if stripped.endswith(":"):
            # Walk back to remove the key token too
            # Find matching '"' pair before the colon
            colon_pos = len(stripped) - 1
            # Skip whitespace before colon
            pos = colon_pos - 1
            while pos >= 0 and stripped[pos] in " \t\n\r":
                pos -= 1
            # Now pos should be at closing '"' of the key
            if pos >= 0 and stripped[pos] == '"':
                pos -= 1
                # Scan back for opening '"' of the key, handling escapes naively
                while pos >= 0:
                    if stripped[pos] == '"' and (pos == 0 or stripped[pos - 1] != "\\"):
                        break
                    pos -= 1
                if pos >= 0:
                    # Remove ",  <whitespace>  "key" :" or just '"key":'
                    start_key = pos
                    # Check for preceding comma
                    pre = stripped[:start_key].rstrip()
                    if pre.endswith(","):
                        working = pre[:-1]
                    else:
                        working = pre
                    continue
            # Fallback: just remove the colon
            working = stripped[:-1]
            continue
        break

    # Step 3: Close open arrays and objects in LIFO order using open_stack
    # Rebuild the open_stack since working may have changed — use simple
    # depth counting from open_stack state at scan end (still valid for suffix)
    closing = ""
    # Close remaining open structures from innermost to outermost
    for opener in reversed(open_stack):
        if opener == "[":
            closing += "]"
        elif opener == "{":
            closing += "}"

    candidate = working + closing

    # Step 4: Validate the repaired result is parseable
    try:
        json.loads(candidate)
        return candidate
    except (json.JSONDecodeError, ValueError):
        pass

    # Step 5: Strip trailing commas that may have been introduced by the
    # active repair (e.g. truncation right after "key": value, then closing
    # the structure leaves a trailing comma inside).
    cleaned_candidate = _strip_trailing_commas(candidate)
    try:
        json.loads(cleaned_candidate)
        return cleaned_candidate
    except (json.JSONDecodeError, ValueError):
        pass

    return None

def _extract_json(text: str) -> dict:
    """Extract JSON from LLM output, stripping think tags and code fences.

    Handles three common LLM output patterns:
    1. Raw JSON: ``{"key": "value"}``
    2. Think-tagged: ``<think>reasoning</think>{"key": "value"}``
    3. Markdown-fenced: ``\\`\\`\\`json\\n{"key": "value"}\\n\\`\\`\\````

    Args:
        text: Raw LLM output text.

    Returns:
        Parsed dict from the JSON content.

    Raises:
        json.JSONDecodeError: If no valid JSON can be extracted.
    """
    # Step 1: Strip <think>...</think> blocks
    cleaned = _THINK_RE.sub("", text)

    # Step 2: Extract content from markdown code fences if present
    fence_match = _CODE_FENCE_RE.search(cleaned)
    if fence_match:
        cleaned = fence_match.group(1)
    elif cleaned.lstrip().startswith("```"):
        # Unclosed fence — output was truncated before closing ```.
        # Strip the opening fence line (e.g. "```json\n") and keep the rest.
        first_newline = cleaned.find("\n")
        if first_newline >= 0:
            cleaned = cleaned[first_newline + 1 :]

    # Step 3: Strip whitespace and parse
    cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Attempt to recover truncated JSON by finding last balanced closing brace
        repaired = _repair_truncated_json(cleaned)
        if repaired:
            logger.warning(
                "Factory JSON truncated, recovered %d/%d chars",
                len(repaired),
                len(cleaned),
            )
            return json.loads(repaired)
        raise
