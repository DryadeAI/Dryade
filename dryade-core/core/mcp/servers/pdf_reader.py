"""PDF Reader MCP Server wrapper.

Provides typed Python interface for pdf-reader-mcp server
with full extraction capabilities: text, tables, images, and structure.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.mcp.protocol import MCPToolCallResult
    from core.mcp.registry import MCPRegistry

# From CONTEXT.md: File size limit 100 MB
MAX_FILE_SIZE_MB = 100
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

@dataclass
class PDFPage:
    """Extracted content from a single PDF page.

    Attributes:
        page_number: 1-indexed page number.
        text: Extracted text content from the page.
        tables: List of tables, each as a 2D list of cell strings.
        images: List of image metadata dictionaries.
    """

    page_number: int
    text: str
    tables: list[list[list[str]]] = field(default_factory=list)
    images: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation.

        Returns:
            Dictionary with page data.
        """
        return {
            "page_number": self.page_number,
            "text": self.text,
            "tables": self.tables,
            "images": self.images,
        }

@dataclass
class PDFDocument:
    """Extracted PDF document with metadata and pages.

    Attributes:
        path: Path to the source PDF file.
        page_count: Total number of pages in the document.
        metadata: Document metadata (title, author, creation date, etc.).
        pages: List of extracted pages.
    """

    path: str
    page_count: int
    metadata: dict[str, str]
    pages: list[PDFPage]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation.

        Returns:
            Dictionary with document data including all pages.
        """
        return {
            "path": self.path,
            "page_count": self.page_count,
            "metadata": self.metadata,
            "pages": [p.to_dict() for p in self.pages],
        }

    @property
    def full_text(self) -> str:
        """Concatenated text from all pages.

        Returns:
            Full document text with pages separated by double newlines.
        """
        return "\n\n".join(p.text for p in self.pages)

class PDFReaderServer:
    """Typed wrapper for pdf-reader-mcp MCP server.

    Provides typed Python methods for PDF extraction:
    - Full text extraction with page structure
    - Table detection and extraction
    - Image extraction (optional)
    - Document metadata

    Example:
        >>> from core.mcp import get_registry, MCPServerConfig
        >>> registry = get_registry()
        >>> config = MCPServerConfig(
        ...     name="pdf-reader",
        ...     command=["npx", "-y", "@shtse8/pdf-reader-mcp"]
        ... )
        >>> registry.register(config)
        >>> pdf = PDFReaderServer(registry)
        >>> doc = pdf.extract("/path/to/document.pdf")
        >>> print(doc.full_text)
    """

    def __init__(
        self,
        registry: MCPRegistry,
        server_name: str = "pdf-reader",
    ) -> None:
        """Initialize PDFReaderServer wrapper.

        Args:
            registry: MCP registry for server communication.
            server_name: Name of the pdf-reader server in registry.
        """
        self._registry = registry
        self._server_name = server_name

    def extract(self, path: str, include_images: bool = False) -> PDFDocument:
        """Extract full content from a PDF document.

        Extracts text, tables, metadata, and optionally images from
        all pages of the PDF.

        Args:
            path: Absolute path to the PDF file.
            include_images: Whether to extract image metadata (default: False).

        Returns:
            PDFDocument with all extracted content.

        Raises:
            ValueError: If file exceeds size limit.
            MCPTransportError: If extraction fails.
        """
        self._validate_file_size(path)
        result = self._registry.call_tool(
            self._server_name,
            "extract_pdf",
            {"path": path, "include_images": include_images},
        )
        text = self._extract_text(result)
        if text:
            data = json.loads(text)
            pages = [
                PDFPage(
                    page_number=p.get("page_number", i + 1),
                    text=p.get("text", ""),
                    tables=p.get("tables", []),
                    images=p.get("images", []),
                )
                for i, p in enumerate(data.get("pages", []))
            ]
            return PDFDocument(
                path=path,
                page_count=data.get("page_count", len(pages)),
                metadata=data.get("metadata", {}),
                pages=pages,
            )
        return PDFDocument(path=path, page_count=0, metadata={}, pages=[])

    def extract_text(self, path: str) -> str:
        """Extract text content only from a PDF (faster than full extraction).

        Args:
            path: Absolute path to the PDF file.

        Returns:
            Concatenated text from all pages.

        Raises:
            ValueError: If file exceeds size limit.
            MCPTransportError: If extraction fails.
        """
        self._validate_file_size(path)
        result = self._registry.call_tool(
            self._server_name,
            "extract_text",
            {"path": path},
        )
        return self._extract_text(result)

    def extract_tables(self, path: str) -> list[list[list[str]]]:
        """Extract tables only from a PDF.

        Args:
            path: Absolute path to the PDF file.

        Returns:
            List of tables, each as a 2D list of cell strings.

        Raises:
            ValueError: If file exceeds size limit.
            MCPTransportError: If extraction fails.
        """
        self._validate_file_size(path)
        result = self._registry.call_tool(
            self._server_name,
            "extract_tables",
            {"path": path},
        )
        text = self._extract_text(result)
        if text:
            return json.loads(text)
        return []

    def extract_page(self, path: str, page_number: int) -> PDFPage:
        """Extract content from a single page.

        Args:
            path: Absolute path to the PDF file.
            page_number: 1-indexed page number to extract.

        Returns:
            PDFPage with extracted content.

        Raises:
            ValueError: If file exceeds size limit or page number invalid.
            MCPTransportError: If extraction fails.
        """
        self._validate_file_size(path)
        result = self._registry.call_tool(
            self._server_name,
            "extract_page",
            {"path": path, "page_number": page_number},
        )
        text = self._extract_text(result)
        if text:
            data = json.loads(text)
            return PDFPage(
                page_number=data.get("page_number", page_number),
                text=data.get("text", ""),
                tables=data.get("tables", []),
                images=data.get("images", []),
            )
        return PDFPage(page_number=page_number, text="")

    def get_metadata(self, path: str) -> dict[str, str]:
        """Get document metadata only.

        Retrieves PDF metadata such as title, author, creation date,
        modification date, and producer.

        Args:
            path: Absolute path to the PDF file.

        Returns:
            Dictionary of metadata key-value pairs.

        Raises:
            ValueError: If file exceeds size limit.
            MCPTransportError: If metadata retrieval fails.
        """
        self._validate_file_size(path)
        result = self._registry.call_tool(
            self._server_name,
            "get_metadata",
            {"path": path},
        )
        text = self._extract_text(result)
        if text:
            return json.loads(text)
        return {}

    def get_page_count(self, path: str) -> int:
        """Get the number of pages in a PDF.

        Args:
            path: Absolute path to the PDF file.

        Returns:
            Number of pages in the document.

        Raises:
            ValueError: If file exceeds size limit.
            MCPTransportError: If page count retrieval fails.
        """
        self._validate_file_size(path)
        result = self._registry.call_tool(
            self._server_name,
            "get_page_count",
            {"path": path},
        )
        text = self._extract_text(result)
        if text:
            return int(text)
        return 0

    def _validate_file_size(self, path: str) -> None:
        """Validate file size against limit.

        Args:
            path: Path to the file.

        Raises:
            ValueError: If file exceeds size limit.
        """
        import os

        if os.path.exists(path):
            size = os.path.getsize(path)
            if size > MAX_FILE_SIZE_BYTES:
                raise ValueError(
                    f"File size {size / (1024 * 1024):.1f}MB exceeds limit of {MAX_FILE_SIZE_MB}MB"
                )

    def _extract_text(self, result: MCPToolCallResult) -> str:
        """Extract text content from MCP tool result.

        Args:
            result: MCP tool call result.

        Returns:
            Text content from the first text item, or empty string.
        """
        if result.content:
            for item in result.content:
                if item.type == "text" and item.text:
                    return item.text
        return ""
