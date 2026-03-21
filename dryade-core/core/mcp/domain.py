"""Domain models for MCP file operations.

This module provides shared data models used across MCP file-related tools.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

class FileLocator(BaseModel):
    """Locates a file within a logical root directory.

    This provides a portable way to reference files without exposing
    absolute server paths to clients.

    Attributes:
        root: Logical root name (e.g., "spec-exports", "model-exports")
        relative_path: Path relative to the root directory
    """

    root: str
    relative_path: str

    def to_os_path(self, mapping: dict[str, str]) -> Path:
        """Convert to an OS-specific absolute path.

        Args:
            mapping: Dict mapping logical root names to absolute paths

        Returns:
            Absolute Path object

        Raises:
            ValueError: If root is not in the mapping
        """
        if self.root not in mapping:
            raise ValueError(f"Unknown file root: {self.root!r}")
        return Path(mapping[self.root]) / self.relative_path

    def to_posix_path(self) -> str:
        """Return the relative path in POSIX format."""
        return Path(self.relative_path).as_posix()

class ExportResult(BaseModel):
    """Result of a document export operation.

    Contains both the file locator and download-ready fields
    for browser consumption.
    """

    status: str
    locator: FileLocator
    download_filename: str
    download_content: str  # Base64-encoded file content
    download_mime_type: str
    download_size: int

    # Optional metadata
    format: str | None = None
    generation_id: str | None = None
