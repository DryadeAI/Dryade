"""Chunking Service for Knowledge/RAG Pipeline.

Splits text using configurable recursive character splitting
with a separator hierarchy: paragraph > line > sentence > word.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.knowledge.config import KnowledgeConfig

@dataclass
class Chunk:
    """A text chunk with metadata and position index."""

    text: str
    metadata: dict = field(default_factory=dict)
    index: int = 0

class ChunkingService:
    """Recursive character text splitter with configurable overlap.

    Splits text by trying separators in order of granularity:
    paragraph breaks > line breaks > sentence ends > word boundaries.
    """

    SEPARATORS = ["\n\n", "\n", ". ", " "]

    def __init__(self, config: KnowledgeConfig):
        self.chunk_size = config.chunk_size
        self.chunk_overlap = config.chunk_overlap

    def chunk(self, text: str, metadata: dict | None = None) -> list[Chunk]:
        """Chunk text using recursive character splitting.

        Args:
            text: Input text to split into chunks.
            metadata: Optional metadata dict to attach to each chunk.

        Returns:
            List of Chunk objects with text, metadata, and index.
        """
        metadata = metadata or {}
        raw_chunks = self._recursive_split(text, self.SEPARATORS)
        return [
            Chunk(text=c, metadata={**metadata, "chunk_index": i}, index=i)
            for i, c in enumerate(raw_chunks)
            if c.strip()
        ]

    def _recursive_split(self, text: str, separators: list[str]) -> list[str]:
        """Split text by separator hierarchy with overlap.

        Algorithm:
        1. Try first separator (e.g., "\\n\\n")
        2. Split text on that separator
        3. Merge splits into chunks up to chunk_size chars
        4. If any chunk exceeds chunk_size, recurse with next separator
        5. Apply chunk_overlap by prepending overlap chars from previous chunk
        6. Base case: if no separators left, hard-split at chunk_size
        """
        if not text:
            return []

        if len(text) <= self.chunk_size:
            return [text]

        # Base case: no separators left, hard-split
        if not separators:
            return self._hard_split(text)

        separator = separators[0]
        remaining_separators = separators[1:]

        # Split on current separator
        parts = text.split(separator)

        # Merge small parts into chunks up to chunk_size
        merged = self._merge_parts(parts, separator)

        # Recurse on chunks that are still too large
        result = []
        for chunk_text in merged:
            if len(chunk_text) > self.chunk_size and remaining_separators:
                sub_chunks = self._recursive_split(chunk_text, remaining_separators)
                result.extend(sub_chunks)
            else:
                result.append(chunk_text)

        # Apply overlap between consecutive chunks
        if self.chunk_overlap > 0 and len(result) > 1:
            result = self._apply_overlap(result)

        return result

    def _merge_parts(self, parts: list[str], separator: str) -> list[str]:
        """Merge split parts into chunks up to chunk_size."""
        merged: list[str] = []
        current = ""

        for part in parts:
            candidate = (current + separator + part) if current else part

            if len(candidate) <= self.chunk_size:
                current = candidate
            else:
                if current:
                    merged.append(current)
                current = part

        if current:
            merged.append(current)

        return merged

    def _hard_split(self, text: str) -> list[str]:
        """Split text at exact chunk_size boundaries (last resort)."""
        chunks = []
        for i in range(0, len(text), self.chunk_size):
            chunks.append(text[i : i + self.chunk_size])
        return chunks

    def _apply_overlap(self, chunks: list[str]) -> list[str]:
        """Prepend overlap characters from previous chunk to each subsequent chunk."""
        if not chunks:
            return chunks

        result = [chunks[0]]
        for i in range(1, len(chunks)):
            prev = chunks[i - 1]
            overlap_text = prev[-self.chunk_overlap :] if len(prev) >= self.chunk_overlap else prev
            # Only prepend if it doesn't duplicate the start of the current chunk
            current = chunks[i]
            if not current.startswith(overlap_text):
                result.append(overlap_text + current)
            else:
                result.append(current)
        return result
