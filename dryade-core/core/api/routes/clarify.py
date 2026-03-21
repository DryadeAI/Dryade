"""Clarify API routes — structured clarification forms with preference memory.

Migrated from plugin to core in Phase 191. These routes are unconditionally
available to all users.

Endpoints:
- POST /api/clarify/form/generate - Generate form from clarification questions
- POST /api/clarify/form/submit - Submit form answers
- GET /api/clarify/preferences - List user preferences
- POST /api/clarify/preferences - Save preference
- DELETE /api/clarify/preferences/{id} - Delete preference
- PUT /api/clarify/preferences/{id} - Update preference
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.auth.dependencies import get_current_user, get_db
from core.clarify.forms import create_fallback_form, generate_form_schema
from core.clarify.preferences import compute_cosine_similarity, generate_embedding
from core.database.models import SavedPreference

logger = logging.getLogger(__name__)

router = APIRouter()

# ============================================================================
# Sync Preference Operations
# ============================================================================

def sync_save_preference(
    db: Session,
    user_id: str,
    question: str,
    question_embedding: list[float],
    answer: Any,
    answer_type: str,
    project_id: str | None = None,
    match_threshold: float = 0.85,
) -> SavedPreference:
    """Save a new user preference (sync version)."""
    preference = SavedPreference(
        user_id=user_id,
        project_id=project_id,
        question=question,
        question_embedding=question_embedding,
        answer=answer,
        answer_type=answer_type,
        match_threshold=match_threshold,
    )
    db.add(preference)
    db.flush()
    db.refresh(preference)
    return preference

def sync_get_user_preferences(
    db: Session,
    user_id: str,
    project_id: str | None = None,
    include_global: bool = True,
) -> list[SavedPreference]:
    """Get all preferences for a user (sync version)."""
    conditions = [SavedPreference.user_id == user_id]

    if project_id is not None:
        if include_global:
            conditions.append(
                (SavedPreference.project_id == project_id) | (SavedPreference.project_id.is_(None))
            )
        else:
            conditions.append(SavedPreference.project_id == project_id)
    else:
        conditions.append(SavedPreference.project_id.is_(None))

    stmt = (
        select(SavedPreference)
        .where(*conditions)
        .order_by(
            SavedPreference.project_id.is_(None).asc(),
            SavedPreference.last_used.desc(),
        )
    )

    result = db.execute(stmt)
    return list(result.scalars().all())

def sync_get_preference_by_id(
    db: Session,
    preference_id: int,
    user_id: str | None = None,
) -> SavedPreference | None:
    """Get a single preference by ID (sync version)."""
    conditions = [SavedPreference.id == preference_id]
    if user_id is not None:
        conditions.append(SavedPreference.user_id == user_id)

    stmt = select(SavedPreference).where(*conditions)
    result = db.execute(stmt)
    return result.scalar_one_or_none()

def sync_update_preference(
    db: Session,
    preference_id: int,
    user_id: str,
    answer: Any | None = None,
    match_threshold: float | None = None,
) -> SavedPreference | None:
    """Update an existing preference (sync version)."""
    preference = sync_get_preference_by_id(db, preference_id, user_id)
    if preference is None:
        return None

    if answer is not None:
        preference.answer = answer

    if match_threshold is not None:
        preference.match_threshold = match_threshold

    db.flush()
    db.refresh(preference)
    return preference

def sync_delete_preference(
    db: Session,
    preference_id: int,
    user_id: str,
) -> bool:
    """Delete a preference (sync version)."""
    preference = sync_get_preference_by_id(db, preference_id, user_id)
    if preference is None:
        return False

    db.delete(preference)
    db.flush()
    return True

def sync_match_preference(
    db: Session,
    question: str,
    user_id: str,
    project_id: str | None = None,
    threshold: float = 0.85,
) -> dict | None:
    """Find best matching preference for a question (sync version)."""
    preferences = sync_get_user_preferences(
        db,
        user_id,
        project_id=project_id,
        include_global=True,
    )

    if not preferences:
        return None

    query_embedding = generate_embedding(question)

    best_match: SavedPreference | None = None
    best_similarity = 0.0

    for pref in preferences:
        if pref.question_embedding is None:
            continue

        pref_threshold = pref.match_threshold or threshold

        similarity = compute_cosine_similarity(
            query_embedding,
            pref.question_embedding,
        )

        if similarity >= pref_threshold and similarity > best_similarity:
            best_match = pref
            best_similarity = similarity

    if best_match:
        logger.info(
            f"[CLARIFY] Found match for '{question[:50]}...' "
            f"(sim={best_similarity:.3f}, pref_id={best_match.id})"
        )
        return {
            "preference": best_match,
            "similarity": best_similarity,
            "prefill_value": best_match.answer,
        }

    return None

# ============================================================================
# Request/Response Models
# ============================================================================

class FormGenerateRequest(BaseModel):
    """Request to generate clarification form."""

    user_request: str = Field(..., description="Original user request")
    clarification_questions: list[str] = Field(..., description="Questions to ask")
    capabilities: list[dict[str, Any]] = Field(
        default_factory=list, description="Available agent capabilities"
    )
    project_id: str | None = Field(default=None, description="Optional project ID")

class FormGenerateResponse(BaseModel):
    """Response with generated form."""

    form: dict = Field(..., description="FormSchema as dict")
    prefills: dict[str, Any] = Field(
        default_factory=dict, description="Prefill values from matched preferences"
    )

class FormSubmitRequest(BaseModel):
    """Request to submit form answers."""

    form_id: str = Field(..., description="Form ID")
    answers: dict[str, Any] = Field(..., description="Question ID -> answer mapping")
    question_texts: dict[str, str] = Field(
        ...,
        description="Question ID -> actual question text mapping (required for preference matching)",
    )
    save_preferences: bool = Field(
        default=True, description="Whether to save answers as preferences"
    )
    project_id: str | None = Field(default=None, description="Optional project ID")

class FormSubmitResponse(BaseModel):
    """Response after form submission."""

    success: bool
    saved_count: int = Field(default=0, description="Number of preferences saved")

class PreferenceResponse(BaseModel):
    """Preference data for API response."""

    id: int
    question: str
    answer: Any
    answer_type: str
    project_id: str | None
    used_count: int
    match_threshold: float

class SavePreferenceRequest(BaseModel):
    """Request to save a preference."""

    question: str
    answer: Any
    answer_type: str
    project_id: str | None = None
    match_threshold: float = 0.85

class UpdatePreferenceRequest(BaseModel):
    """Request to update a preference."""

    answer: Any | None = None
    match_threshold: float | None = None

# ============================================================================
# Form Endpoints (Team/Enterprise)
# ============================================================================

@router.post("/form/generate", response_model=FormGenerateResponse)
async def generate_form(
    request: FormGenerateRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate structured clarification form.

    Team/Enterprise only. Generates form schema from clarification questions
    and prefills with matched preferences.
    """
    user_id = user["sub"]
    form = await generate_form_schema(
        user_request=request.user_request,
        capabilities=request.capabilities,
        clarification_questions=request.clarification_questions,
    )

    if form is None:
        form = create_fallback_form(
            request.clarification_questions,
            request.user_request,
        )

    prefills = {}
    for question in form.questions:
        match = sync_match_preference(
            db=db,
            question=question.question,
            user_id=user_id,
            project_id=request.project_id,
        )
        if match:
            prefills[question.id] = match["prefill_value"]
            logger.debug(
                f"[CLARIFY] Prefill {question.id} with preference {match['preference'].id}"
            )

    return FormGenerateResponse(
        form=form.model_dump(),
        prefills=prefills,
    )

@router.post("/form/submit", response_model=FormSubmitResponse)
async def submit_form(
    request: FormSubmitRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Submit form answers and save as preferences."""
    user_id = user["sub"]
    saved_count = 0

    if request.save_preferences:
        for question_id, answer in request.answers.items():
            question_text = request.question_texts.get(question_id)

            if not question_text:
                logger.warning(
                    f"[CLARIFY] Missing question text for {question_id}, skipping preference save"
                )
                continue

            try:
                embedding = generate_embedding(question_text)

                if isinstance(answer, bool):
                    answer_type = "toggle"
                elif isinstance(answer, list):
                    answer_type = "checkbox"
                elif isinstance(answer, (int, float)):
                    answer_type = "number"
                else:
                    answer_type = "text"

                sync_save_preference(
                    db=db,
                    user_id=user_id,
                    question=question_text,
                    question_embedding=embedding,
                    answer=answer,
                    answer_type=answer_type,
                    project_id=request.project_id,
                )
                saved_count += 1
            except Exception as e:
                logger.warning(
                    f"[CLARIFY] Failed to save preference for '{question_text[:50]}': {e}"
                )

    return FormSubmitResponse(success=True, saved_count=saved_count)

# ============================================================================
# Preference Management Endpoints (Team/Enterprise)
# ============================================================================

@router.get("/preferences", response_model=list[PreferenceResponse])
async def list_preferences(
    project_id: str | None = None,
    include_global: bool = True,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List user's saved preferences."""
    user_id = user["sub"]

    preferences = sync_get_user_preferences(
        db=db,
        user_id=user_id,
        project_id=project_id,
        include_global=include_global,
    )

    return [
        PreferenceResponse(
            id=p.id,
            question=p.question,
            answer=p.answer,
            answer_type=p.answer_type,
            project_id=p.project_id,
            used_count=p.used_count,
            match_threshold=p.match_threshold,
        )
        for p in preferences
    ]

@router.post("/preferences", response_model=PreferenceResponse)
async def create_preference(
    request: SavePreferenceRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Save a new preference."""
    user_id = user["sub"]

    embedding = generate_embedding(request.question)

    preference = sync_save_preference(
        db=db,
        user_id=user_id,
        question=request.question,
        question_embedding=embedding,
        answer=request.answer,
        answer_type=request.answer_type,
        project_id=request.project_id,
        match_threshold=request.match_threshold,
    )

    return PreferenceResponse(
        id=preference.id,
        question=preference.question,
        answer=preference.answer,
        answer_type=preference.answer_type,
        project_id=preference.project_id,
        used_count=preference.used_count,
        match_threshold=preference.match_threshold,
    )

@router.put("/preferences/{preference_id}", response_model=PreferenceResponse)
async def update_pref(
    preference_id: int,
    request: UpdatePreferenceRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update an existing preference."""
    user_id = user["sub"]

    preference = sync_update_preference(
        db=db,
        preference_id=preference_id,
        user_id=user_id,
        answer=request.answer,
        match_threshold=request.match_threshold,
    )

    if preference is None:
        raise HTTPException(status_code=404, detail="Preference not found")

    return PreferenceResponse(
        id=preference.id,
        question=preference.question,
        answer=preference.answer,
        answer_type=preference.answer_type,
        project_id=preference.project_id,
        used_count=preference.used_count,
        match_threshold=preference.match_threshold,
    )

@router.delete("/preferences/{preference_id}")
async def delete_pref(
    preference_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a preference."""
    user_id = user["sub"]

    success = sync_delete_preference(db=db, preference_id=preference_id, user_id=user_id)

    if not success:
        raise HTTPException(status_code=404, detail="Preference not found")

    return {"success": True}
