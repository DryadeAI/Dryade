"""LLM-driven form generation for structured clarification.

Generates FormSchema from planner context and user request.
Uses simple prompt format for LLM reliability (not JSON Schema).
"""

import json
import logging
import uuid
from typing import Any

from .schema import ControlType, FormQuestion, FormSchema

logger = logging.getLogger(__name__)

def _build_form_generation_prompt(
    user_request: str,
    capabilities: list[dict[str, Any]],
    clarification_questions: list[str],
) -> str:
    """Build prompt for form schema generation."""
    caps_summary = json.dumps(
        [{"agent": c["agent"], "description": c["description"]} for c in capabilities[:10]],
        indent=2,
    )

    questions_list = "\n".join(f"- {q}" for q in clarification_questions)

    return f"""Generate a structured form for clarification.

## User Request
{user_request}

## Available Agents (for reference)
{caps_summary}

## Questions to Ask
{questions_list}

## Instructions
Convert each question into a structured form field. Choose appropriate control types:

**Basic Controls (Team tier):**
- radio: Single choice from 2-5 options
- checkbox: Multiple choices
- text: Free-form text input

**Advanced Controls (Enterprise tier):**
- dropdown: Single choice from many options (6+)
- number: Numeric input with optional min/max
- date: Date picker
- slider: Numeric range selection
- toggle: Yes/No, On/Off
- file: File upload (specify file_types)
- code: Code editor (specify code_language)

## Rules
1. Keep questions concise and actionable
2. Provide 2-5 options for radio/checkbox/dropdown
3. Use text for file paths, descriptions, open-ended input
4. Add depends_on for conditional questions
5. Mark required: false for optional questions

## Output Format (JSON only, no markdown)
{{
  "title": "Brief form title",
  "description": "Optional context",
  "context": "What you understand so far",
  "questions": [
    {{
      "id": "q1",
      "question": "Question text?",
      "type": "radio",
      "options": ["Option 1", "Option 2"],
      "required": true
    }},
    {{
      "id": "q2",
      "question": "Follow-up question?",
      "type": "text",
      "placeholder": "e.g., /path/to/file.py",
      "depends_on": "q1",
      "depends_value": "Option 1"
    }}
  ]
}}

Generate the form schema:"""

async def generate_form_schema(
    user_request: str,
    capabilities: list[dict[str, Any]],
    clarification_questions: list[str],
    llm=None,
) -> FormSchema | None:
    """Generate a form schema from clarification questions.

    Args:
        user_request: Original user request
        capabilities: Available agent/tool capabilities
        clarification_questions: Questions to convert to form
        llm: Optional LLM instance (defaults to configured LLM)

    Returns:
        FormSchema if generation successful, None on error
    """
    if not clarification_questions:
        logger.warning("[FORM_GEN] No clarification questions provided")
        return None

    # Get LLM if not provided
    if llm is None:
        from core.providers.llm_adapter import get_configured_llm

        llm = get_configured_llm()

    prompt = _build_form_generation_prompt(user_request, capabilities, clarification_questions)
    messages = [{"role": "user", "content": prompt}]

    logger.info(f"[FORM_GEN] Generating form for {len(clarification_questions)} questions")

    try:
        response = llm.call(messages)

        # Handle dict response from reasoning models
        if isinstance(response, dict):
            response_text = response.get("content", "")
        else:
            response_text = str(response)

        # Strip thinking tags
        if "<think>" in response_text and "</think>" in response_text:
            response_text = response_text.split("</think>")[-1].strip()

        # Extract JSON from markdown blocks
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0]

        # Find JSON object
        response_text = response_text.strip()
        if not response_text.startswith("{"):
            start_idx = response_text.find("{")
            end_idx = response_text.rfind("}")
            if start_idx != -1 and end_idx > start_idx:
                response_text = response_text[start_idx : end_idx + 1]

        form_data = json.loads(response_text)

        # Parse questions with validation
        questions = []
        for i, q_data in enumerate(form_data.get("questions", [])):
            try:
                if "id" not in q_data:
                    q_data["id"] = f"q{i + 1}"

                control_type = q_data.get("type", "text")
                if isinstance(control_type, str):
                    try:
                        q_data["type"] = ControlType(control_type.lower())
                    except ValueError:
                        logger.warning(
                            f"[FORM_GEN] Unknown control type '{control_type}', using text"
                        )
                        q_data["type"] = ControlType.TEXT

                questions.append(FormQuestion(**q_data))
            except Exception as e:
                logger.warning(f"[FORM_GEN] Skipping invalid question {i}: {e}")
                continue

        if not questions:
            logger.error("[FORM_GEN] No valid questions parsed from LLM response")
            return None

        form_schema = FormSchema(
            id=str(uuid.uuid4())[:8],
            title=form_data.get("title", "Clarification Needed"),
            description=form_data.get("description"),
            questions=questions,
            context=form_data.get("context"),
            generated_for=user_request[:200],
        )

        logger.info(
            f"[FORM_GEN] Generated form '{form_schema.title}' with {len(questions)} questions"
        )
        return form_schema

    except json.JSONDecodeError as e:
        logger.error(f"[FORM_GEN] Failed to parse LLM response as JSON: {e}")
        return None
    except Exception as e:
        logger.error(f"[FORM_GEN] Form generation failed: {e}", exc_info=True)
        return None

def create_fallback_form(clarification_questions: list[str], user_request: str) -> FormSchema:
    """Create a simple fallback form when LLM generation fails.

    All questions become text inputs.
    """
    questions = [
        FormQuestion(
            id=f"q{i + 1}",
            question=q,
            type=ControlType.TEXT,
            required=True,
        )
        for i, q in enumerate(clarification_questions)
    ]

    return FormSchema(
        id=str(uuid.uuid4())[:8],
        title="Please provide more details",
        description="We need some additional information to proceed.",
        questions=questions,
        generated_for=user_request[:200],
    )
