"""Document Operations MCP Server wrapper.

Provides typed Python interface for Document Operations MCP server
supporting Office formats (DOCX, XLSX, PPTX) plus CSV and Markdown.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.mcp.protocol import MCPToolCallResult
    from core.mcp.registry import MCPRegistry

# From CONTEXT.md: File size limit 100 MB
MAX_FILE_SIZE_MB = 100
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

class DocumentType(Enum):
    """Supported document types.

    Attributes:
        DOCX: Microsoft Word documents.
        XLSX: Microsoft Excel spreadsheets.
        PPTX: Microsoft PowerPoint presentations.
        CSV: Comma-separated values files.
        MARKDOWN: Markdown text files.
    """

    DOCX = "docx"
    XLSX = "xlsx"
    PPTX = "pptx"
    CSV = "csv"
    MARKDOWN = "markdown"

@dataclass
class DocumentContent:
    """Extracted document content.

    Attributes:
        path: Path to the source document.
        document_type: Type of the document.
        text: Extracted text content.
        metadata: Document metadata (author, title, etc.).
        sheets: List of sheet data for XLSX files.
        slides: List of slide data for PPTX files.
    """

    path: str
    document_type: DocumentType
    text: str
    metadata: dict[str, str] = field(default_factory=dict)
    sheets: list[dict[str, Any]] | None = None  # For XLSX
    slides: list[dict[str, Any]] | None = None  # For PPTX

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation.

        Returns:
            Dictionary with document data.
        """
        result: dict[str, Any] = {
            "path": self.path,
            "document_type": self.document_type.value,
            "text": self.text,
            "metadata": self.metadata,
        }
        if self.sheets:
            result["sheets"] = self.sheets
        if self.slides:
            result["slides"] = self.slides
        return result

@dataclass
class SpreadsheetData:
    """Extracted spreadsheet data.

    Attributes:
        sheet_name: Name of the sheet or file.
        headers: Column header names.
        rows: List of data rows.
        row_count: Total number of data rows.
    """

    sheet_name: str
    headers: list[str]
    rows: list[list[Any]]
    row_count: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation.

        Returns:
            Dictionary with spreadsheet data.
        """
        return {
            "sheet_name": self.sheet_name,
            "headers": self.headers,
            "rows": self.rows,
            "row_count": self.row_count,
        }

class DocumentOpsServer:
    """Typed wrapper for Document Operations MCP server.

    Provides typed Python methods for Office document operations:
    - Word documents (DOCX): text, paragraphs, tables
    - Excel spreadsheets (XLSX): sheets, cells, formulas
    - PowerPoint presentations (PPTX): slides, text, images
    - CSV files: parse, convert
    - Markdown: parse, render

    Example:
        >>> from core.mcp import get_registry, MCPServerConfig
        >>> registry = get_registry()
        >>> config = MCPServerConfig(
        ...     name="document-ops",
        ...     command=["npx", "-y", "@negokaz/excel-mcp-server"]
        ... )
        >>> registry.register(config)
        >>> docs = DocumentOpsServer(registry)
        >>> content = docs.extract("/path/to/file.xlsx")

    Note:
        Currently uses @negokaz/excel-mcp-server which focuses on Excel files.
        For other document types (DOCX, PPTX), additional servers may be needed.
    """

    def __init__(
        self,
        registry: MCPRegistry,
        server_name: str = "document-ops",
    ) -> None:
        """Initialize DocumentOpsServer wrapper.

        Args:
            registry: MCP registry for server communication.
            server_name: Name of the document-ops server in registry.
        """
        self._registry = registry
        self._server_name = server_name

    def extract(self, path: str) -> DocumentContent:
        """Extract content from any supported document type.

        Auto-detects document type based on file extension and
        extracts content accordingly.

        Args:
            path: Absolute path to the document.

        Returns:
            DocumentContent with extracted text and metadata.

        Raises:
            ValueError: If file exceeds size limit or type unsupported.
            MCPTransportError: If extraction fails.
        """
        doc_type = self._validate_file(path)
        result = self._registry.call_tool(
            self._server_name,
            "extract_document",
            {"path": path},
        )
        text = self._extract_text(result)
        if text:
            data = json.loads(text)
            return DocumentContent(
                path=path,
                document_type=doc_type,
                text=data.get("text", ""),
                metadata=data.get("metadata", {}),
                sheets=data.get("sheets"),
                slides=data.get("slides"),
            )
        return DocumentContent(path=path, document_type=doc_type, text="")

    def extract_docx(self, path: str) -> DocumentContent:
        """Extract content from a Word document.

        Args:
            path: Absolute path to the DOCX file.

        Returns:
            DocumentContent with extracted text, paragraphs, and metadata.

        Raises:
            ValueError: If file exceeds size limit or is not a DOCX.
            MCPTransportError: If extraction fails.
        """
        self._validate_file_type(path, DocumentType.DOCX)
        self._validate_file_size(path)
        result = self._registry.call_tool(
            self._server_name,
            "extract_docx",
            {"path": path},
        )
        text = self._extract_text(result)
        if text:
            data = json.loads(text)
            return DocumentContent(
                path=path,
                document_type=DocumentType.DOCX,
                text=data.get("text", ""),
                metadata=data.get("metadata", {}),
            )
        return DocumentContent(path=path, document_type=DocumentType.DOCX, text="")

    def extract_xlsx(self, path: str) -> list[SpreadsheetData]:
        """Extract content from an Excel spreadsheet.

        Extracts all sheets with headers and data rows.

        Args:
            path: Absolute path to the XLSX file.

        Returns:
            List of SpreadsheetData, one per sheet.

        Raises:
            ValueError: If file exceeds size limit or is not an XLSX.
            MCPTransportError: If extraction fails.
        """
        self._validate_file_type(path, DocumentType.XLSX)
        self._validate_file_size(path)
        result = self._registry.call_tool(
            self._server_name,
            "extract_xlsx",
            {"path": path},
        )
        text = self._extract_text(result)
        if text:
            data = json.loads(text)
            sheets = []
            for sheet in data.get("sheets", []):
                sheets.append(
                    SpreadsheetData(
                        sheet_name=sheet.get("name", "Sheet1"),
                        headers=sheet.get("headers", []),
                        rows=sheet.get("rows", []),
                        row_count=sheet.get("row_count", len(sheet.get("rows", []))),
                    )
                )
            return sheets
        return []

    def extract_pptx(self, path: str) -> DocumentContent:
        """Extract content from a PowerPoint presentation.

        Extracts slide text, notes, and metadata.

        Args:
            path: Absolute path to the PPTX file.

        Returns:
            DocumentContent with extracted slides and metadata.

        Raises:
            ValueError: If file exceeds size limit or is not a PPTX.
            MCPTransportError: If extraction fails.
        """
        self._validate_file_type(path, DocumentType.PPTX)
        self._validate_file_size(path)
        result = self._registry.call_tool(
            self._server_name,
            "extract_pptx",
            {"path": path},
        )
        text = self._extract_text(result)
        if text:
            data = json.loads(text)
            return DocumentContent(
                path=path,
                document_type=DocumentType.PPTX,
                text=data.get("text", ""),
                metadata=data.get("metadata", {}),
                slides=data.get("slides"),
            )
        return DocumentContent(path=path, document_type=DocumentType.PPTX, text="")

    def parse_csv(self, path: str, delimiter: str = ",") -> SpreadsheetData:
        """Parse a CSV file.

        Args:
            path: Absolute path to the CSV file.
            delimiter: Field delimiter (default: comma).

        Returns:
            SpreadsheetData with headers and rows.

        Raises:
            ValueError: If file exceeds size limit or is not a CSV.
            MCPTransportError: If parsing fails.
        """
        self._validate_file_type(path, DocumentType.CSV)
        self._validate_file_size(path)
        result = self._registry.call_tool(
            self._server_name,
            "parse_csv",
            {"path": path, "delimiter": delimiter},
        )
        text = self._extract_text(result)
        if text:
            data = json.loads(text)
            return SpreadsheetData(
                sheet_name=data.get("name", "CSV"),
                headers=data.get("headers", []),
                rows=data.get("rows", []),
                row_count=data.get("row_count", len(data.get("rows", []))),
            )
        return SpreadsheetData(sheet_name="CSV", headers=[], rows=[], row_count=0)

    def parse_markdown(self, path: str) -> DocumentContent:
        """Parse a Markdown file.

        Args:
            path: Absolute path to the Markdown file.

        Returns:
            DocumentContent with extracted text and structure.

        Raises:
            ValueError: If file exceeds size limit or is not Markdown.
            MCPTransportError: If parsing fails.
        """
        self._validate_file_type(path, DocumentType.MARKDOWN)
        self._validate_file_size(path)
        result = self._registry.call_tool(
            self._server_name,
            "parse_markdown",
            {"path": path},
        )
        text = self._extract_text(result)
        if text:
            data = json.loads(text)
            return DocumentContent(
                path=path,
                document_type=DocumentType.MARKDOWN,
                text=data.get("text", ""),
                metadata=data.get("metadata", {}),
            )
        return DocumentContent(path=path, document_type=DocumentType.MARKDOWN, text="")

    def to_markdown(self, path: str) -> str:
        """Convert any supported document to Markdown.

        Args:
            path: Absolute path to the document.

        Returns:
            Markdown representation of the document.

        Raises:
            ValueError: If file exceeds size limit or type unsupported.
            MCPTransportError: If conversion fails.
        """
        self._validate_file(path)
        result = self._registry.call_tool(
            self._server_name,
            "to_markdown",
            {"path": path},
        )
        return self._extract_text(result)

    def to_text(self, path: str) -> str:
        """Extract plain text from any supported document.

        Args:
            path: Absolute path to the document.

        Returns:
            Plain text content of the document.

        Raises:
            ValueError: If file exceeds size limit or type unsupported.
            MCPTransportError: If extraction fails.
        """
        self._validate_file(path)
        result = self._registry.call_tool(
            self._server_name,
            "to_text",
            {"path": path},
        )
        return self._extract_text(result)

    def _validate_file(self, path: str) -> DocumentType:
        """Validate file and determine document type.

        Args:
            path: Path to the file.

        Returns:
            DocumentType for the file.

        Raises:
            ValueError: If file exceeds size limit or type unsupported.
        """
        import os

        # Size check
        if os.path.exists(path):
            size = os.path.getsize(path)
            if size > MAX_FILE_SIZE_BYTES:
                raise ValueError(
                    f"File size {size / (1024 * 1024):.1f}MB exceeds limit of {MAX_FILE_SIZE_MB}MB"
                )

        # Type detection
        ext = os.path.splitext(path)[1].lower()
        type_map = {
            ".docx": DocumentType.DOCX,
            ".xlsx": DocumentType.XLSX,
            ".pptx": DocumentType.PPTX,
            ".csv": DocumentType.CSV,
            ".md": DocumentType.MARKDOWN,
            ".markdown": DocumentType.MARKDOWN,
        }
        if ext not in type_map:
            raise ValueError(f"Unsupported document type: {ext}")
        return type_map[ext]

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

    def _validate_file_type(self, path: str, expected: DocumentType) -> None:
        """Validate file has expected type.

        Args:
            path: Path to the file.
            expected: Expected document type.

        Raises:
            ValueError: If file type doesn't match expected.
        """
        import os

        ext = os.path.splitext(path)[1].lower()
        type_map = {
            ".docx": DocumentType.DOCX,
            ".xlsx": DocumentType.XLSX,
            ".pptx": DocumentType.PPTX,
            ".csv": DocumentType.CSV,
            ".md": DocumentType.MARKDOWN,
            ".markdown": DocumentType.MARKDOWN,
        }
        actual = type_map.get(ext)
        if actual != expected:
            raise ValueError(
                f"Expected {expected.value} file, got {ext if actual is None else actual.value}"
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
