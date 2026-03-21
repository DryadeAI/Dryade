"""Form schema models for structured clarification.

Simple custom format designed for LLM reliability (not JSON Schema).
Control types are tiered: Team gets basic controls, Enterprise gets all.
"""

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

class ControlType(str, Enum):
    """Form control types with tier requirements.

    Team tier: radio, checkbox, text
    Enterprise tier: all controls
    """

    # Team tier controls
    RADIO = "radio"
    CHECKBOX = "checkbox"
    TEXT = "text"

    # Enterprise tier controls
    DROPDOWN = "dropdown"
    NUMBER = "number"
    DATE = "date"
    SLIDER = "slider"
    TOGGLE = "toggle"
    FILE = "file"
    CODE = "code"

# Controls available at each tier
TEAM_CONTROLS = {ControlType.RADIO, ControlType.CHECKBOX, ControlType.TEXT}
ENTERPRISE_CONTROLS = set(ControlType)  # All controls

class FormQuestion(BaseModel):
    """Single question in a clarification form.

    Designed for LLM generation reliability - simple flat structure.
    """

    id: str = Field(..., description="Unique question ID (e.g., 'q1', 'file_path')")
    question: str = Field(..., description="Question text to display to user")
    type: ControlType = Field(..., description="Control type for answer input")

    # Optional fields
    options: list[str] | None = Field(
        default=None, description="Options for radio/checkbox/dropdown controls"
    )
    placeholder: str | None = Field(
        default=None, description="Placeholder text for text/number/code inputs"
    )
    default: Any | None = Field(default=None, description="Default value to prefill")
    required: bool = Field(default=True, description="Whether answer is required")

    # Conditional display
    depends_on: str | None = Field(
        default=None, description="Question ID this depends on (conditional display)"
    )
    depends_value: Any | None = Field(
        default=None, description="Value of depends_on question that triggers display"
    )

    # Validation
    min_value: float | None = Field(default=None, description="Min for number/slider")
    max_value: float | None = Field(default=None, description="Max for number/slider")
    pattern: str | None = Field(default=None, description="Regex pattern for text validation")
    file_types: list[str] | None = Field(
        default=None, description="Accepted file extensions for file control"
    )
    code_language: str | None = Field(
        default=None, description="Language hint for code editor (python, javascript, etc.)"
    )

    @field_validator("options")
    @classmethod
    def validate_options(cls, v, info):
        """Ensure options provided for option-based controls."""
        control_type = info.data.get("type")
        if control_type in [ControlType.RADIO, ControlType.CHECKBOX, ControlType.DROPDOWN]:
            if not v or len(v) < 2:
                raise ValueError(f"{control_type} requires at least 2 options")
        return v

    def get_tier_requirement(self) -> Literal["team", "enterprise"]:
        """Get minimum tier required for this control."""
        if self.type in TEAM_CONTROLS:
            return "team"
        return "enterprise"

class FormSchema(BaseModel):
    """Complete form schema for clarification.

    Questions are ordered - first question shown first in conversational flow.
    """

    id: str = Field(..., description="Unique form ID")
    title: str = Field(..., description="Form title/header")
    description: str | None = Field(default=None, description="Optional form description")
    questions: list[FormQuestion] = Field(
        ..., min_length=1, description="Ordered list of questions"
    )

    # Metadata for tracking
    context: str | None = Field(
        default=None, description="What the planner understands so far (from LLM)"
    )
    generated_for: str | None = Field(
        default=None, description="Original user request that triggered clarification"
    )

    def get_visible_questions(self, answers: dict[str, Any]) -> list[FormQuestion]:
        """Get questions visible based on current answers.

        Respects depends_on/depends_value for conditional display.
        """
        visible = []
        for q in self.questions:
            if q.depends_on is None:
                visible.append(q)
            elif q.depends_on in answers:
                if answers[q.depends_on] == q.depends_value:
                    visible.append(q)
        return visible

    def get_next_question(self, answers: dict[str, Any]) -> FormQuestion | None:
        """Get next unanswered question in conversational flow."""
        for q in self.get_visible_questions(answers):
            if q.id not in answers:
                return q
        return None

    def is_complete(self, answers: dict[str, Any]) -> bool:
        """Check if all required visible questions are answered."""
        for q in self.get_visible_questions(answers):
            if q.required and q.id not in answers:
                return False
        return True

    def get_minimum_tier(self) -> Literal["team", "enterprise"]:
        """Get minimum tier required for this form based on controls used."""
        for q in self.questions:
            if q.get_tier_requirement() == "enterprise":
                return "enterprise"
        return "team"

    def downgrade_for_tier(self, tier: Literal["community", "team", "enterprise"]) -> "FormSchema":
        """Create a copy with controls downgraded for user's tier.

        Enterprise controls become text inputs for Team users.
        Community users get no form (handled elsewhere).
        """
        if tier == "enterprise":
            return self  # No downgrade needed

        # For Team: downgrade enterprise controls to text
        downgraded_questions = []
        for q in self.questions:
            if q.type not in TEAM_CONTROLS:
                downgraded = q.model_copy(
                    update={
                        "type": ControlType.TEXT,
                        "placeholder": f"Enter value (was: {q.type.value})",
                        "options": None,
                    }
                )
                downgraded_questions.append(downgraded)
            else:
                downgraded_questions.append(q)

        return FormSchema(
            id=self.id,
            title=self.title,
            description=self.description,
            questions=downgraded_questions,
            context=self.context,
            generated_for=self.generated_for,
        )
