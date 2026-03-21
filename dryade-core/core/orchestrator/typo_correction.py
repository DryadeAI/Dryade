"""Typo detection for common path segments (F-002).

Uses fuzzy matching against common directory names to catch
user misspellings like 'Dekstop', 'Docuemnts', 'Donwloads' before
they reach MCP tools and cause silent failures.
"""

import difflib
import re

COMMON_PATHS = [
    "Desktop",
    "Documents",
    "Downloads",
    "Pictures",
    "Music",
    "Videos",
    "Templates",
    "Public",
]

# Build lowercase lookup for case-insensitive exact match check
_COMMON_LOWER = {p.lower() for p in COMMON_PATHS}

def suggest_typo_corrections(text: str) -> tuple[str, list[str]]:
    """Detect and correct common path segment typos in user input.

    Uses fuzzy matching against common directory names to catch
    misspellings like 'Dekstop', 'Docuemnts', 'Donwloads'.

    Args:
        text: User input text to check.

    Returns:
        Tuple of (corrected_text, corrections_made).
        corrections_made is empty if no typos found.
    """
    corrections: list[str] = []
    corrected = text

    # Extract candidate words: split on whitespace AND path separators
    # Use word boundaries to find potential path segments (min 4 chars)
    candidates = set(re.findall(r"[A-Za-z]{4,}", text))

    for word in candidates:
        # Skip if already a correct common path (case-insensitive)
        if word.lower() in _COMMON_LOWER:
            continue

        # Check fuzzy match against common paths
        # Compare lowercase to catch case variations
        matches = difflib.get_close_matches(
            word.lower(),
            [p.lower() for p in COMMON_PATHS],
            n=1,
            cutoff=0.7,
        )
        if matches:
            # Find the original-case version of the match
            matched_lower = matches[0]
            correct = next(p for p in COMMON_PATHS if p.lower() == matched_lower)
            corrections.append(f"'{word}' -> '{correct}'")
            # Replace in text preserving surrounding context
            corrected = corrected.replace(word, correct)

    return corrected, corrections
