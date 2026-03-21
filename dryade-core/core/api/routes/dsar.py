"""GDPR Data Subject Access Request (DSAR) API.

Implements Article 17 (Right to Erasure) and Article 20 (Data Portability).
DSAR requests are tracked with a status lifecycle and rate-limited to 1/24h per user.

Target: ~250 LOC
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import tempfile
import zipfile
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import update
from sqlalchemy.orm import Session

from core.auth.audit import log_audit_sync
from core.auth.dependencies import get_current_user, get_db
from core.database.models import (
    AuditLog,
    Conversation,
    CostRecord,
    DSARRequest,
    Message,
    User,
    Workflow,
    WorkflowApprovalRequest,
)
from core.database.session import get_session_factory

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class DSARCreateRequest(BaseModel):
    """Request body for initiating a DSAR."""

    request_type: str  # "export" or "erasure"

class DSARStatusResponse(BaseModel):
    """Response schema for DSAR status."""

    id: int
    user_id: str
    request_type: str
    status: str
    download_url: str | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_TYPES = {"export", "erasure"}
_RATE_LIMIT_HOURS = 24
_DOWNLOAD_TTL_HOURS = 24

def _check_access(user_id: str, current_user: dict) -> None:
    """Verify the caller can access this user's DSAR data."""
    caller_id = current_user.get("sub", "")
    caller_role = current_user.get("role", "member")
    if caller_id != user_id and caller_role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")

def _serialize_datetime(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None

def _row_to_json(obj, columns: list[str]) -> dict:
    """Convert a SQLAlchemy model row to a JSON-serializable dict."""
    result = {}
    for col in columns:
        val = getattr(obj, col, None)
        if isinstance(val, datetime):
            result[col] = val.isoformat()
        else:
            result[col] = val
    return result

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/users/{user_id}/dsar", response_model=DSARStatusResponse)
async def initiate_dsar(
    user_id: str,
    body: DSARCreateRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Initiate a DSAR (data export or erasure) request.

    Rate-limited to 1 request per user per 24 hours.
    """
    _check_access(user_id, current_user)

    if body.request_type not in _VALID_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid request_type. Must be one of: {', '.join(sorted(_VALID_TYPES))}",
        )

    # Rate limit: 1 per 24h
    cutoff = datetime.now(UTC) - timedelta(hours=_RATE_LIMIT_HOURS)
    recent = (
        db.query(DSARRequest)
        .filter(
            DSARRequest.user_id == user_id,
            DSARRequest.created_at >= cutoff,
        )
        .first()
    )
    if recent:
        raise HTTPException(status_code=429, detail="One DSAR per 24 hours")

    dsar = DSARRequest(
        user_id=user_id,
        request_type=body.request_type,
        status="pending",
    )
    db.add(dsar)
    db.flush()  # Assign ID

    dsar_id = dsar.id
    session_factory = get_session_factory()

    if body.request_type == "export":
        background_tasks.add_task(_process_export, session_factory, dsar_id, user_id)
    else:
        background_tasks.add_task(_process_erasure, session_factory, dsar_id, user_id)

    return DSARStatusResponse(
        id=dsar.id,
        user_id=dsar.user_id,
        request_type=dsar.request_type,
        status=dsar.status,
        download_url=dsar.download_url,
        created_at=dsar.created_at,
        completed_at=dsar.completed_at,
    )

@router.get("/users/{user_id}/dsar/{request_id}", response_model=DSARStatusResponse)
async def get_dsar_status(
    user_id: str,
    request_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get status of a DSAR request. Checks download TTL expiry."""
    _check_access(user_id, current_user)

    dsar = (
        db.query(DSARRequest)
        .filter(DSARRequest.id == request_id, DSARRequest.user_id == user_id)
        .first()
    )
    if not dsar:
        raise HTTPException(status_code=404, detail="DSAR request not found")

    # Check download TTL expiry
    if dsar.status == "ready" and dsar.download_expires_at:
        if datetime.now(UTC) > dsar.download_expires_at:
            dsar.status = "expired"
            db.flush()

    return DSARStatusResponse(
        id=dsar.id,
        user_id=dsar.user_id,
        request_type=dsar.request_type,
        status=dsar.status,
        download_url=dsar.download_url if dsar.status == "ready" else None,
        created_at=dsar.created_at,
        completed_at=dsar.completed_at,
    )

# ---------------------------------------------------------------------------
# Background tasks
# ---------------------------------------------------------------------------

def _process_export(session_factory, dsar_id: int, user_id: str) -> None:
    """Collect user data from all stores and produce a downloadable ZIP."""
    session = session_factory()
    try:
        dsar = session.query(DSARRequest).filter(DSARRequest.id == dsar_id).first()
        if not dsar:
            return
        dsar.status = "processing"
        session.commit()

        categories = {}
        stores_included = ["postgresql"]
        stores_skipped = []

        # --- PostgreSQL data ---
        user_obj = session.query(User).filter(User.id == user_id).first()
        if user_obj:
            categories["profile"] = _row_to_json(
                user_obj,
                ["id", "email", "display_name", "role", "is_active", "created_at", "updated_at"],
            )

        conversations = session.query(Conversation).filter(Conversation.user_id == user_id).all()
        categories["conversations"] = [
            _row_to_json(c, ["id", "title", "mode", "status", "created_at", "updated_at"])
            for c in conversations
        ]

        conv_ids = [c.id for c in conversations]
        if conv_ids:
            messages = session.query(Message).filter(Message.conversation_id.in_(conv_ids)).all()
        else:
            messages = []
        categories["messages"] = [
            _row_to_json(m, ["id", "conversation_id", "role", "content", "created_at"])
            for m in messages
        ]

        cost_records = session.query(CostRecord).filter(CostRecord.user_id == user_id).all()
        categories["cost_records"] = [
            _row_to_json(
                cr,
                [
                    "id",
                    "user_id",
                    "model",
                    "input_tokens",
                    "output_tokens",
                    "total_cost",
                    "timestamp",
                ],
            )
            for cr in cost_records
        ]

        workflows = session.query(Workflow).filter(Workflow.user_id == user_id).all()
        categories["workflows"] = [
            _row_to_json(w, ["id", "name", "description", "version", "status", "created_at"])
            for w in workflows
        ]

        # --- Qdrant (optional) ---
        try:
            from qdrant_client import QdrantClient  # noqa: F811

            client = QdrantClient(
                host=os.getenv("QDRANT_HOST", "localhost"),
                port=int(os.getenv("QDRANT_PORT", "6333")),
            )
            # Attempt to retrieve points with user_id metadata filter
            # Collection name is configurable; use default "dryade"
            collection = os.getenv("QDRANT_COLLECTION", "dryade")
            from qdrant_client.models import FieldCondition, Filter, MatchValue

            results = client.scroll(
                collection_name=collection,
                scroll_filter=Filter(
                    must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))]
                ),
                limit=10000,
                with_payload=True,
                with_vectors=False,
            )
            points = results[0] if results else []
            categories["qdrant_embeddings"] = [
                {"id": str(p.id), "metadata": p.payload} for p in points
            ]
            stores_included.append("qdrant")
        except (ImportError, Exception) as exc:
            logger.info("Qdrant export skipped: %s", exc)
            stores_skipped.append("qdrant (not available)")

        # --- Neo4j (optional) ---
        try:
            from neo4j import GraphDatabase

            neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
            neo4j_user = os.getenv("NEO4J_USER", "neo4j")
            neo4j_password = os.getenv("NEO4J_PASSWORD", "")
            driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
            with driver.session() as neo_session:
                result = neo_session.run("MATCH (n {user_id: $uid}) RETURN n", uid=user_id)
                nodes = [dict(record["n"]) for record in result]
            driver.close()
            categories["neo4j_nodes"] = nodes
            stores_included.append("neo4j")
        except (ImportError, Exception) as exc:
            logger.info("Neo4j export skipped: %s", exc)
            stores_skipped.append("neo4j (not available)")

        # Redis explicitly skipped (ephemeral)
        stores_skipped.append("redis (ephemeral)")

        # --- Build ZIP ---
        manifest = {
            "export_date": datetime.now(UTC).isoformat(),
            "user_id": user_id,
            "categories": list(categories.keys()),
            "stores_included": stores_included,
            "stores_skipped": stores_skipped,
        }

        export_dir = os.path.join(tempfile.gettempdir(), "dryade_dsar_exports")
        os.makedirs(export_dir, exist_ok=True)
        zip_path = os.path.join(export_dir, f"dsar_export_{dsar_id}_{user_id}.zip")

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(manifest, indent=2, default=str))
            for name, data in categories.items():
                zf.writestr(f"{name}.json", json.dumps(data, indent=2, default=str))

        with open(zip_path, "wb") as f:
            f.write(buf.getvalue())

        # Update DSAR record
        dsar.download_url = zip_path
        dsar.download_expires_at = datetime.now(UTC) + timedelta(hours=_DOWNLOAD_TTL_HOURS)
        dsar.status = "ready"
        session.commit()

        logger.info("DSAR export %d ready for user %s", dsar_id, user_id)

    except Exception as exc:
        logger.error("DSAR export %d failed: %s", dsar_id, exc)
        session.rollback()
        try:
            dsar_row = session.query(DSARRequest).filter(DSARRequest.id == dsar_id).first()
            if dsar_row:
                dsar_row.status = "failed"
                session.commit()
        except Exception:
            session.rollback()
    finally:
        session.close()

def _process_erasure(session_factory, dsar_id: int, user_id: str) -> None:
    """Purge user data across all stores. Order: Qdrant -> Neo4j -> Redis -> PostgreSQL -> anonymize audit."""
    session = session_factory()
    store_results: dict[str, str] = {}
    try:
        dsar = session.query(DSARRequest).filter(DSARRequest.id == dsar_id).first()
        if not dsar:
            return
        dsar.status = "processing"
        session.commit()

        # 1. Qdrant
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import FieldCondition, Filter, MatchValue

            client = QdrantClient(
                host=os.getenv("QDRANT_HOST", "localhost"),
                port=int(os.getenv("QDRANT_PORT", "6333")),
            )
            collection = os.getenv("QDRANT_COLLECTION", "dryade")
            client.delete(
                collection_name=collection,
                points_selector=Filter(
                    must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))]
                ),
            )
            store_results["qdrant"] = "purged"
        except (ImportError, Exception) as exc:
            logger.warning("Qdrant erasure skipped: %s", exc)
            store_results["qdrant"] = f"skipped: {exc}"

        # 2. Neo4j
        try:
            from neo4j import GraphDatabase

            neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
            neo4j_user = os.getenv("NEO4J_USER", "neo4j")
            neo4j_password = os.getenv("NEO4J_PASSWORD", "")
            driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
            with driver.session() as neo_session:
                neo_session.run("MATCH (n {user_id: $uid}) DETACH DELETE n", uid=user_id)
            driver.close()
            store_results["neo4j"] = "purged"
        except (ImportError, Exception) as exc:
            logger.warning("Neo4j erasure skipped: %s", exc)
            store_results["neo4j"] = f"skipped: {exc}"

        # 3. Redis
        try:
            import redis as redis_lib

            redis_host = os.getenv("REDIS_HOST", "localhost")
            redis_port = int(os.getenv("REDIS_PORT", "6379"))
            r = redis_lib.Redis(host=redis_host, port=redis_port, decode_responses=True)
            cursor = 0
            pattern = f"user:{user_id}:*"
            deleted = 0
            while True:
                cursor, keys = r.scan(cursor=cursor, match=pattern, count=100)
                if keys:
                    r.delete(*keys)
                    deleted += len(keys)
                if cursor == 0:
                    break
            store_results["redis"] = f"purged ({deleted} keys)"
        except (ImportError, Exception) as exc:
            logger.warning("Redis erasure skipped: %s", exc)
            store_results["redis"] = f"skipped: {exc}"

        # 4. PostgreSQL -- delete in FK order
        # Messages (via conversations)
        conv_ids = [
            c.id
            for c in session.query(Conversation.id).filter(Conversation.user_id == user_id).all()
        ]
        if conv_ids:
            session.query(Message).filter(Message.conversation_id.in_(conv_ids)).delete(
                synchronize_session=False
            )
        session.query(Conversation).filter(Conversation.user_id == user_id).delete(
            synchronize_session=False
        )
        session.query(CostRecord).filter(CostRecord.user_id == user_id).delete(
            synchronize_session=False
        )

        # Workflow approval requests (FK to workflows)
        wf_ids = [
            w.id for w in session.query(Workflow.id).filter(Workflow.user_id == user_id).all()
        ]
        if wf_ids:
            session.query(WorkflowApprovalRequest).filter(
                WorkflowApprovalRequest.workflow_id.in_(wf_ids)
            ).delete(synchronize_session=False)
        session.query(Workflow).filter(Workflow.user_id == user_id).delete(
            synchronize_session=False
        )
        store_results["postgresql"] = "purged"

        # 5. Anonymize audit logs (not deleted -- per locked decision)
        anon_id = f"DELETED_USER_{hashlib.sha256(user_id.encode()).hexdigest()[:12]}"
        session.execute(update(AuditLog).where(AuditLog.user_id == user_id).values(user_id=anon_id))
        store_results["audit_anonymized"] = anon_id

        session.commit()

        # Log the erasure event
        log_audit_sync(
            db=session,
            user_id=anon_id,
            action="user_data_erased",
            resource_type="dsar",
            resource_id=str(dsar_id),
            metadata={
                "original_user_id_hash": hashlib.sha256(user_id.encode()).hexdigest()[:12],
                "store_results": store_results,
            },
            event_severity="critical",
        )

        # Mark DSAR as completed
        dsar_row = session.query(DSARRequest).filter(DSARRequest.id == dsar_id).first()
        if dsar_row:
            dsar_row.status = "completed"
            dsar_row.completed_at = datetime.now(UTC)
        session.commit()

        logger.info("DSAR erasure %d completed for user %s", dsar_id, user_id)

    except Exception as exc:
        logger.error("DSAR erasure %d failed: %s", dsar_id, exc)
        session.rollback()
        try:
            dsar_row = session.query(DSARRequest).filter(DSARRequest.id == dsar_id).first()
            if dsar_row:
                dsar_row.status = "failed"
                session.commit()
        except Exception:
            session.rollback()
    finally:
        session.close()
