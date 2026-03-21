"""Memory block subsystem for Letta-inspired agent self-modification.

Phase 115.3: MemoryBlockStore with database persistence, compile-to-prompt,
and 4 memory tool execution functions (insert, replace, rethink, search).

Memory blocks are agent-scoped labeled text regions that compile into XML
for system prompt injection. Agents modify their own context through these
tools without requiring escalation (all memory tools are read-only from the
system's perspective).
"""

import logging
import re
import threading
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field

from core.orchestrator.config import get_orchestration_config

logger = logging.getLogger(__name__)

__all__ = [
    "MemoryBlock",
    "MemoryBlockStore",
    "get_memory_block_store",
    "execute_memory_insert",
    "execute_memory_replace",
    "execute_memory_rethink",
    "execute_memory_search",
    "execute_memory_delete",
]

# ---------------------------------------------------------------------------
# Pydantic model (in-memory representation)
# ---------------------------------------------------------------------------

class MemoryBlock(BaseModel):
    """In-memory representation of a memory block.

    Not to be confused with MemoryBlockRecord (SQLAlchemy model for persistence).
    """

    block_id: str = Field(default_factory=lambda: str(uuid4()))
    agent_id: str
    label: str
    value: str = ""
    description: str = ""
    char_limit: int = 5000
    read_only: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

# ---------------------------------------------------------------------------
# MemoryBlockStore
# ---------------------------------------------------------------------------

class MemoryBlockStore:
    """Thread-safe in-memory + database-backed store for memory blocks.

    Blocks are cached in memory (keyed by agent_id -> label) and persisted
    to the database via MemoryBlockRecord. Cache misses trigger DB loads.
    """

    def __init__(self) -> None:
        self._blocks: dict[str, dict[str, MemoryBlock]] = {}
        self._lock = threading.Lock()

    # --- Public API ---

    def get_blocks(self, agent_id: str) -> list[MemoryBlock]:
        """Return all blocks for an agent. Loads from DB on cache miss."""
        with self._lock:
            if agent_id not in self._blocks:
                loaded = self._load_from_db(agent_id)
                self._blocks[agent_id] = {b.label: b for b in loaded}
            return list(self._blocks[agent_id].values())

    def get_block(self, agent_id: str, label: str) -> MemoryBlock | None:
        """Get a single block by agent_id and label."""
        with self._lock:
            if agent_id not in self._blocks:
                loaded = self._load_from_db(agent_id)
                self._blocks[agent_id] = {b.label: b for b in loaded}
            return self._blocks.get(agent_id, {}).get(label)

    def create_block(self, block: MemoryBlock) -> MemoryBlock:
        """Create a new block. Validates total budget and persists to DB.

        Raises:
            ValueError: If total char budget would be exceeded.
        """
        with self._lock:
            if block.agent_id not in self._blocks:
                loaded = self._load_from_db(block.agent_id)
                self._blocks[block.agent_id] = {b.label: b for b in loaded}

            if not self._check_total_budget(block.agent_id, len(block.value)):
                config = get_orchestration_config()
                raise ValueError(
                    f"Total memory budget ({config.memory_blocks_max_total_chars} chars) "
                    f"would be exceeded. Cannot create block '{block.label}'."
                )

            self._blocks.setdefault(block.agent_id, {})[block.label] = block
            self._persist_block(block)

            logger.info(
                "[MEMORY-BLOCK] Created block agent=%s label=%s chars=%d value=%.100s",
                block.agent_id,
                block.label,
                len(block.value),
                block.value,
            )
            return block

    def update_block(self, agent_id: str, label: str, value: str) -> MemoryBlock:
        """Update a block's value. Validates read-only, char_limit, and budget.

        Raises:
            ValueError: If block not found, is read-only, exceeds char_limit,
                        or exceeds total budget.
        """
        with self._lock:
            if agent_id not in self._blocks:
                loaded = self._load_from_db(agent_id)
                self._blocks[agent_id] = {b.label: b for b in loaded}

            block = self._blocks.get(agent_id, {}).get(label)
            if block is None:
                raise ValueError(f"Block '{label}' not found for agent '{agent_id}'.")

            if block.read_only:
                raise ValueError(f"Block '{label}' is read-only and cannot be modified.")

            if len(value) > block.char_limit:
                raise ValueError(
                    f"Value length ({len(value)}) exceeds char_limit ({block.char_limit}) "
                    f"for block '{label}'."
                )

            # Check total budget (subtract old value, add new value)
            delta = len(value) - len(block.value)
            if delta > 0 and not self._check_total_budget(agent_id, delta):
                config = get_orchestration_config()
                raise ValueError(
                    f"Total memory budget ({config.memory_blocks_max_total_chars} chars) "
                    f"would be exceeded. Cannot update block '{label}'."
                )

            old_value = block.value
            block.value = value
            block.updated_at = datetime.now(UTC)
            self._persist_block(block)

            logger.info(
                "[MEMORY-BLOCK] Updated block agent=%s label=%s before=%.100s after=%.100s",
                agent_id,
                label,
                old_value,
                value,
            )
            return block

    def delete_block(self, agent_id: str, label: str) -> bool:
        """Delete a block from cache and DB. Returns True if block existed."""
        with self._lock:
            if agent_id not in self._blocks:
                loaded = self._load_from_db(agent_id)
                self._blocks[agent_id] = {b.label: b for b in loaded}

            if label not in self._blocks.get(agent_id, {}):
                return False

            del self._blocks[agent_id][label]
            self._delete_from_db(agent_id, label)

            logger.info(
                "[MEMORY-BLOCK] Deleted block agent=%s label=%s",
                agent_id,
                label,
            )
            return True

    def compile_to_prompt(self, agent_id: str) -> str:
        """Compile all blocks for an agent into XML format for system prompt.

        Returns empty string if no blocks or memory_blocks_enabled=False.
        """
        config = get_orchestration_config()
        if not config.memory_blocks_enabled:
            return ""

        blocks = self.get_blocks(agent_id)
        if not blocks:
            return ""

        parts = ["<memory_blocks>"]
        for block in blocks:
            parts.append(f"  <{block.label}>")
            parts.append(f"    <description>{block.description}</description>")
            parts.append(
                f"    <metadata>chars_current={len(block.value)} chars_limit={block.char_limit}</metadata>"
            )
            parts.append(f"    <value>{block.value}</value>")
            parts.append(f"  </{block.label}>")
        parts.append("</memory_blocks>")
        return "\n".join(parts)

    # --- Private helpers ---

    def _check_total_budget(self, agent_id: str, new_chars: int) -> bool:
        """Check if adding new_chars would exceed total budget.

        Returns True if within budget, False if would exceed.
        """
        config = get_orchestration_config()
        current_total = sum(len(b.value) for b in self._blocks.get(agent_id, {}).values())
        return (current_total + new_chars) <= config.memory_blocks_max_total_chars

    def _persist_block(self, block: MemoryBlock) -> None:
        """Save block to DB using MemoryBlockRecord. Upserts by block_id."""
        try:
            from core.database.models import MemoryBlockRecord
            from core.database.session import get_session

            with get_session() as session:
                existing = session.query(MemoryBlockRecord).filter_by(id=block.block_id).first()
                if existing:
                    existing.value = block.value
                    existing.description = block.description
                    existing.char_limit = block.char_limit
                    existing.read_only = block.read_only
                    existing.updated_at = block.updated_at
                else:
                    record = MemoryBlockRecord(
                        id=block.block_id,
                        agent_id=block.agent_id,
                        label=block.label,
                        value=block.value,
                        description=block.description,
                        char_limit=block.char_limit,
                        read_only=block.read_only,
                        created_at=block.created_at,
                        updated_at=block.updated_at,
                    )
                    session.add(record)
        except Exception:
            logger.exception(
                "[MEMORY-BLOCK] Failed to persist block %s/%s", block.agent_id, block.label
            )

    def _load_from_db(self, agent_id: str) -> list[MemoryBlock]:
        """Load blocks from DB for a given agent_id."""
        try:
            from core.database.models import MemoryBlockRecord
            from core.database.session import get_session

            with get_session() as session:
                records = session.query(MemoryBlockRecord).filter_by(agent_id=agent_id).all()
                return [
                    MemoryBlock(
                        block_id=r.id,
                        agent_id=r.agent_id,
                        label=r.label,
                        value=r.value or "",
                        description=r.description or "",
                        char_limit=r.char_limit or 5000,
                        read_only=r.read_only or False,
                        created_at=r.created_at or datetime.now(UTC),
                        updated_at=r.updated_at or datetime.now(UTC),
                    )
                    for r in records
                ]
        except Exception:
            logger.exception("[MEMORY-BLOCK] Failed to load blocks for agent %s", agent_id)
            return []

    def _delete_from_db(self, agent_id: str, label: str) -> None:
        """Delete a block from DB by agent_id + label."""
        try:
            from core.database.models import MemoryBlockRecord
            from core.database.session import get_session

            with get_session() as session:
                session.query(MemoryBlockRecord).filter_by(agent_id=agent_id, label=label).delete()
        except Exception:
            logger.exception("[MEMORY-BLOCK] Failed to delete block %s/%s", agent_id, label)

# ---------------------------------------------------------------------------
# 4 memory tool execution functions
# ---------------------------------------------------------------------------

def execute_memory_insert(
    agent_id: str,
    label: str,
    new_str: str,
    insert_line: int = -1,
) -> dict:
    """Insert text into a memory block at a specific line.

    If the block doesn't exist, creates it with new_str as value.
    If insert_line == -1, appends to end.

    Returns:
        dict with status, label, and char count.
    """
    store = get_memory_block_store()
    block = store.get_block(agent_id, label)

    if block is None:
        # Create new block
        block = MemoryBlock(agent_id=agent_id, label=label, value=new_str)
        store.create_block(block)
        logger.info(
            "[MEMORY-BLOCK] memory_insert created new block agent=%s label=%s chars=%d",
            agent_id,
            label,
            len(new_str),
        )
        return {"status": "ok", "label": label, "chars": len(new_str)}

    # Insert into existing block
    lines = block.value.split("\n") if block.value else []
    if insert_line == -1 or insert_line >= len(lines):
        if block.value:
            new_value = block.value + "\n" + new_str
        else:
            new_value = new_str
    else:
        lines.insert(insert_line, new_str)
        new_value = "\n".join(lines)

    store.update_block(agent_id, label, new_value)
    logger.info(
        "[MEMORY-BLOCK] memory_insert appended agent=%s label=%s chars=%d",
        agent_id,
        label,
        len(new_value),
    )
    return {"status": "ok", "label": label, "chars": len(new_value)}

def execute_memory_replace(
    agent_id: str,
    label: str,
    old_str: str,
    new_str: str,
) -> dict:
    """Find-and-replace within a memory block.

    Raises:
        ValueError: If block not found or old_str not found in block value.

    Returns:
        dict with status, label, and char count.
    """
    store = get_memory_block_store()
    block = store.get_block(agent_id, label)

    if block is None:
        raise ValueError(f"Block '{label}' not found for agent '{agent_id}'.")

    if old_str not in block.value:
        raise ValueError(
            f"String '{old_str[:50]}...' not found in block '{label}'."
            if len(old_str) > 50
            else f"String '{old_str}' not found in block '{label}'."
        )

    new_value = block.value.replace(old_str, new_str, 1)
    store.update_block(agent_id, label, new_value)

    logger.info(
        "[MEMORY-BLOCK] memory_replace agent=%s label=%s old=%.100s new=%.100s",
        agent_id,
        label,
        old_str,
        new_str,
    )
    return {"status": "ok", "label": label, "chars": len(new_value)}

def execute_memory_rethink(
    agent_id: str,
    label: str,
    new_memory: str,
) -> dict:
    """Full rewrite of a memory block's value.

    Creates the block if it doesn't exist.

    Returns:
        dict with status, label, and char count.
    """
    store = get_memory_block_store()
    block = store.get_block(agent_id, label)

    if block is None:
        block = MemoryBlock(agent_id=agent_id, label=label, value=new_memory)
        store.create_block(block)
        logger.info(
            "[MEMORY-BLOCK] memory_rethink created new block agent=%s label=%s chars=%d",
            agent_id,
            label,
            len(new_memory),
        )
    else:
        store.update_block(agent_id, label, new_memory)
        logger.info(
            "[MEMORY-BLOCK] memory_rethink rewrote block agent=%s label=%s chars=%d",
            agent_id,
            label,
            len(new_memory),
        )

    return {"status": "ok", "label": label, "chars": len(new_memory)}

def execute_memory_search(
    agent_id: str,
    query: str,
) -> dict:
    """Search across all memory blocks for matching content.

    Uses regex search (case-insensitive) against block values.

    Returns:
        dict with results list containing label, match, and context.
    """
    store = get_memory_block_store()
    blocks = store.get_blocks(agent_id)
    results = []

    for block in blocks:
        try:
            match = re.search(query, block.value, re.IGNORECASE)
        except re.error:
            # Fall back to literal match if regex is invalid
            idx = block.value.lower().find(query.lower())
            if idx >= 0:
                match_str = block.value[idx : idx + len(query)]
                start = max(0, idx - 50)
                end = min(len(block.value), idx + len(query) + 50)
                context = block.value[start:end]
                results.append({"label": block.label, "match": match_str, "context": context})
            continue

        if match:
            start = max(0, match.start() - 50)
            end = min(len(block.value), match.end() + 50)
            context = block.value[start:end]
            results.append({"label": block.label, "match": match.group(), "context": context})

    logger.info(
        "[MEMORY-BLOCK] memory_search agent=%s query=%s results=%d",
        agent_id,
        query,
        len(results),
    )
    return {"results": results}

def execute_memory_delete(agent_id: str, label: str) -> dict:
    """Delete a memory block entirely.

    Phase 167: Added to support the unified `memory_delete` self-mod tool.

    Returns:
        {"status": "ok", "label": ...} if block existed and was deleted,
        or {"status": "not_found", "label": ...} if the block did not exist.
    """
    store = get_memory_block_store()
    existed = store.delete_block(agent_id, label)
    return {"status": "ok" if existed else "not_found", "label": label}

# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_memory_block_store: MemoryBlockStore | None = None
_memory_block_store_lock = threading.Lock()

def get_memory_block_store() -> MemoryBlockStore:
    """Get the singleton MemoryBlockStore instance."""
    global _memory_block_store
    if _memory_block_store is None:
        with _memory_block_store_lock:
            if _memory_block_store is None:
                _memory_block_store = MemoryBlockStore()
    return _memory_block_store
