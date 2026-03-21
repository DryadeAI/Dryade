"""Unit tests for Document Operations MCP server wrapper.

Comprehensive tests for Office format operations: DOCX, XLSX, PPTX, CSV, Markdown.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from core.mcp.protocol import MCPToolCallContent, MCPToolCallResult
from core.mcp.servers.document_ops import (
    DocumentContent,
    DocumentOpsServer,
    DocumentType,
    SpreadsheetData,
)

# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def mock_registry():
    """Create a mock MCPRegistry for testing."""
    registry = MagicMock()
    registry.is_registered.return_value = True
    return registry

@pytest.fixture
def mock_result_text():
    """Create a factory for MCPToolCallResult with text content."""

    def _make_result(text: str, is_error: bool = False) -> MCPToolCallResult:
        return MCPToolCallResult(
            content=[MCPToolCallContent(type="text", text=text)],
            isError=is_error,
        )

    return _make_result

@pytest.fixture
def mock_result_empty():
    """Create an empty MCPToolCallResult."""
    return MCPToolCallResult(content=[], isError=False)

# ============================================================================
# DocumentType Tests
# ============================================================================

class TestDocumentType:
    """Tests for DocumentType enum."""

    def test_docx_value(self):
        """Test DOCX enum value."""
        assert DocumentType.DOCX.value == "docx"

    def test_xlsx_value(self):
        """Test XLSX enum value."""
        assert DocumentType.XLSX.value == "xlsx"

    def test_pptx_value(self):
        """Test PPTX enum value."""
        assert DocumentType.PPTX.value == "pptx"

    def test_csv_value(self):
        """Test CSV enum value."""
        assert DocumentType.CSV.value == "csv"

    def test_markdown_value(self):
        """Test MARKDOWN enum value."""
        assert DocumentType.MARKDOWN.value == "markdown"

    def test_all_document_types_exist(self):
        """Test all expected document types are defined."""
        expected = {"docx", "xlsx", "pptx", "csv", "markdown"}
        actual = {dt.value for dt in DocumentType}
        assert actual == expected

# ============================================================================
# DocumentContent Tests
# ============================================================================

class TestDocumentContent:
    """Tests for DocumentContent dataclass."""

    def test_document_content_init_basic(self):
        """Test DocumentContent initialization with basic fields."""
        content = DocumentContent(
            path="/path/to/doc.docx",
            document_type=DocumentType.DOCX,
            text="Hello, World!",
        )

        assert content.path == "/path/to/doc.docx"
        assert content.document_type == DocumentType.DOCX
        assert content.text == "Hello, World!"
        assert content.metadata == {}
        assert content.sheets is None
        assert content.slides is None

    def test_document_content_init_docx(self):
        """Test DocumentContent for DOCX with metadata."""
        content = DocumentContent(
            path="/path/to/doc.docx",
            document_type=DocumentType.DOCX,
            text="Document content",
            metadata={"author": "John Doe", "title": "Test Document"},
        )

        assert content.metadata["author"] == "John Doe"

    def test_document_content_init_xlsx(self):
        """Test DocumentContent for XLSX with sheets."""
        sheets = [
            {"name": "Sheet1", "data": [["A1", "B1"], ["A2", "B2"]]},
            {"name": "Sheet2", "data": [["X1", "Y1"]]},
        ]
        content = DocumentContent(
            path="/path/to/file.xlsx",
            document_type=DocumentType.XLSX,
            text="",
            sheets=sheets,
        )

        assert len(content.sheets) == 2
        assert content.sheets[0]["name"] == "Sheet1"

    def test_document_content_init_pptx(self):
        """Test DocumentContent for PPTX with slides."""
        slides = [
            {"slide_number": 1, "title": "Intro", "content": "Welcome"},
            {"slide_number": 2, "title": "Main", "content": "Details"},
        ]
        content = DocumentContent(
            path="/path/to/presentation.pptx",
            document_type=DocumentType.PPTX,
            text="",
            slides=slides,
        )

        assert len(content.slides) == 2
        assert content.slides[0]["title"] == "Intro"

    def test_document_content_to_dict(self):
        """Test DocumentContent.to_dict() returns correct structure."""
        content = DocumentContent(
            path="/path/to/doc.docx",
            document_type=DocumentType.DOCX,
            text="Test content",
            metadata={"author": "Test"},
        )

        data = content.to_dict()

        assert data == {
            "path": "/path/to/doc.docx",
            "document_type": "docx",
            "text": "Test content",
            "metadata": {"author": "Test"},
        }

    def test_document_content_to_dict_with_sheets(self):
        """Test DocumentContent.to_dict() includes sheets."""
        sheets = [{"name": "Sheet1", "data": []}]
        content = DocumentContent(
            path="/path/to/file.xlsx",
            document_type=DocumentType.XLSX,
            text="",
            sheets=sheets,
        )

        data = content.to_dict()

        assert "sheets" in data
        assert data["sheets"] == sheets

    def test_document_content_to_dict_with_slides(self):
        """Test DocumentContent.to_dict() includes slides."""
        slides = [{"slide_number": 1, "title": "Title"}]
        content = DocumentContent(
            path="/path/to/file.pptx",
            document_type=DocumentType.PPTX,
            text="",
            slides=slides,
        )

        data = content.to_dict()

        assert "slides" in data
        assert data["slides"] == slides

# ============================================================================
# SpreadsheetData Tests
# ============================================================================

class TestSpreadsheetData:
    """Tests for SpreadsheetData dataclass."""

    def test_spreadsheet_data_init(self):
        """Test SpreadsheetData initialization."""
        data = SpreadsheetData(
            sheet_name="Sales",
            headers=["Product", "Quantity", "Price"],
            rows=[
                ["Widget", 100, 9.99],
                ["Gadget", 50, 19.99],
            ],
            row_count=2,
        )

        assert data.sheet_name == "Sales"
        assert len(data.headers) == 3
        assert len(data.rows) == 2
        assert data.row_count == 2

    def test_spreadsheet_data_to_dict(self):
        """Test SpreadsheetData.to_dict() returns correct structure."""
        data = SpreadsheetData(
            sheet_name="Data",
            headers=["A", "B"],
            rows=[[1, 2]],
            row_count=1,
        )

        result = data.to_dict()

        assert result == {
            "sheet_name": "Data",
            "headers": ["A", "B"],
            "rows": [[1, 2]],
            "row_count": 1,
        }

# ============================================================================
# DocumentOpsServer Initialization Tests
# ============================================================================

class TestDocumentOpsServerInit:
    """Tests for DocumentOpsServer initialization."""

    def test_init_default_server_name(self, mock_registry):
        """Test default server name is 'document-ops'."""
        server = DocumentOpsServer(mock_registry)

        assert server._server_name == "document-ops"
        assert server._registry is mock_registry

    def test_init_custom_server_name(self, mock_registry):
        """Test custom server name."""
        server = DocumentOpsServer(mock_registry, server_name="custom-docs")

        assert server._server_name == "custom-docs"

# ============================================================================
# DocumentOpsServer Extract Tests
# ============================================================================

class TestDocumentOpsServerExtract:
    """Tests for document extraction operations."""

    @pytest.fixture
    def server(self, mock_registry):
        """Create server with mock registry."""
        return DocumentOpsServer(mock_registry)

    def test_extract_docx(self, server, mock_registry, mock_result_text):
        """Test DOCX extraction."""
        mock_registry.call_tool.return_value = mock_result_text(
            json.dumps(
                {
                    "path": "/path/to/doc.docx",
                    "document_type": "docx",
                    "text": "Document content here",
                    "metadata": {"author": "Test Author"},
                }
            )
        )

        with patch.object(server, "_validate_file_size"):
            content = server.extract("/path/to/doc.docx")

        assert isinstance(content, DocumentContent)
        assert content.document_type == DocumentType.DOCX
        assert content.text == "Document content here"

    def test_extract_xlsx(self, server, mock_registry, mock_result_text):
        """Test XLSX extraction."""
        mock_registry.call_tool.return_value = mock_result_text(
            json.dumps(
                {
                    "path": "/path/to/file.xlsx",
                    "document_type": "xlsx",
                    "text": "",
                    "metadata": {},
                    "sheets": [
                        {"name": "Sheet1", "data": [["A", "B"], [1, 2]]},
                    ],
                }
            )
        )

        with patch.object(server, "_validate_file_size"):
            content = server.extract("/path/to/file.xlsx")

        assert content.document_type == DocumentType.XLSX
        assert content.sheets is not None
        assert len(content.sheets) == 1

    def test_extract_pptx(self, server, mock_registry, mock_result_text):
        """Test PPTX extraction."""
        mock_registry.call_tool.return_value = mock_result_text(
            json.dumps(
                {
                    "path": "/path/to/presentation.pptx",
                    "document_type": "pptx",
                    "text": "Slide content",
                    "metadata": {},
                    "slides": [
                        {"slide_number": 1, "title": "Title Slide"},
                    ],
                }
            )
        )

        with patch.object(server, "_validate_file_size"):
            content = server.extract("/path/to/presentation.pptx")

        assert content.document_type == DocumentType.PPTX
        assert content.slides is not None
        assert len(content.slides) == 1

    def test_extract_csv(self, server, mock_registry, mock_result_text):
        """Test CSV extraction."""
        mock_registry.call_tool.return_value = mock_result_text(
            json.dumps(
                {
                    "path": "/path/to/data.csv",
                    "document_type": "csv",
                    "text": "col1,col2\nval1,val2",
                    "metadata": {},
                }
            )
        )

        with patch.object(server, "_validate_file_size"):
            content = server.extract("/path/to/data.csv")

        assert content.document_type == DocumentType.CSV

    def test_extract_markdown(self, server, mock_registry, mock_result_text):
        """Test Markdown extraction."""
        mock_registry.call_tool.return_value = mock_result_text(
            json.dumps(
                {
                    "path": "/path/to/readme.md",
                    "document_type": "markdown",
                    "text": "# Heading\n\nContent here",
                    "metadata": {},
                }
            )
        )

        with patch.object(server, "_validate_file_size"):
            content = server.extract("/path/to/readme.md")

        assert content.document_type == DocumentType.MARKDOWN
        assert "# Heading" in content.text

# ============================================================================
# DocumentOpsServer Specific Extraction Tests
# ============================================================================

class TestDocumentOpsServerSpecificExtraction:
    """Tests for type-specific extraction methods."""

    @pytest.fixture
    def server(self, mock_registry):
        """Create server with mock registry."""
        return DocumentOpsServer(mock_registry)

    def test_extract_docx_specific(self, server, mock_registry, mock_result_text):
        """Test extract_docx method."""
        mock_registry.call_tool.return_value = mock_result_text(
            json.dumps(
                {
                    "path": "/path/to/doc.docx",
                    "document_type": "docx",
                    "text": "Word document content",
                    "metadata": {"author": "Test"},
                }
            )
        )

        with patch.object(server, "_validate_file_size"):
            content = server.extract_docx("/path/to/doc.docx")

        assert content.document_type == DocumentType.DOCX

    def test_extract_xlsx_specific(self, server, mock_registry, mock_result_text):
        """Test extract_xlsx method returns SpreadsheetData."""
        mock_registry.call_tool.return_value = mock_result_text(
            json.dumps(
                {
                    "path": "/path/to/file.xlsx",
                    "sheets": [
                        {
                            "name": "Data",
                            "headers": ["A", "B", "C"],
                            "rows": [[1, 2, 3], [4, 5, 6]],
                            "row_count": 2,
                        }
                    ],
                }
            )
        )

        with patch.object(server, "_validate_file_size"):
            sheets = server.extract_xlsx("/path/to/file.xlsx")

        assert len(sheets) == 1
        assert isinstance(sheets[0], SpreadsheetData)
        assert sheets[0].sheet_name == "Data"
        assert sheets[0].row_count == 2

    def test_extract_xlsx_no_sheet_name_param(self, server):
        """Test extract_xlsx does not accept a sheet_name keyword argument."""
        import inspect

        sig = inspect.signature(server.extract_xlsx)
        assert "sheet_name" not in sig.parameters

    def test_parse_csv(self, server, mock_registry, mock_result_text):
        """Test parse_csv method returns SpreadsheetData."""
        mock_registry.call_tool.return_value = mock_result_text(
            json.dumps(
                {
                    "name": "CSV",
                    "headers": ["name", "value"],
                    "rows": [["item1", "100"], ["item2", "200"]],
                    "row_count": 2,
                }
            )
        )

        with patch.object(server, "_validate_file_size"):
            data = server.parse_csv("/path/to/data.csv")

        assert isinstance(data, SpreadsheetData)
        assert data.row_count == 2

    def test_parse_csv_with_delimiter(self, server, mock_registry, mock_result_text):
        """Test parse_csv with custom delimiter (tab-separated but .csv extension)."""
        mock_registry.call_tool.return_value = mock_result_text(
            json.dumps(
                {
                    "name": "CSV",
                    "headers": ["col1", "col2"],
                    "rows": [],
                    "row_count": 0,
                }
            )
        )

        with patch.object(server, "_validate_file_size"):
            server.parse_csv("/path/to/data.csv", delimiter="\t")

        args = mock_registry.call_tool.call_args
        assert args[0][2].get("delimiter") == "\t"

# ============================================================================
# DocumentOpsServer Config Tests
# ============================================================================

class TestDocumentOpsServerConfig:
    """Tests for configuration -- DocumentOpsServer has no get_config class method."""

    def test_no_get_config_method(self):
        """Verify get_config does not exist (config is external)."""
        assert not hasattr(DocumentOpsServer, "get_config")

    def test_server_name_default(self, mock_registry):
        """Test default server name."""
        server = DocumentOpsServer(mock_registry)
        assert server._server_name == "document-ops"

# ============================================================================
# DocumentOpsServer Validation Tests
# ============================================================================

class TestDocumentOpsServerValidation:
    """Tests for file validation."""

    @pytest.fixture
    def server(self, mock_registry):
        """Create server with mock registry."""
        return DocumentOpsServer(mock_registry)

    def test_validate_file_size_within_limit(self, server):
        """Test validation passes for files within limit."""
        with (
            patch("os.path.exists", return_value=True),
            patch("os.path.getsize", return_value=50 * 1024 * 1024),
        ):  # 50 MB
            server._validate_file_size("/path/to/small.docx")

    def test_validate_file_size_exceeds_limit(self, server):
        """Test validation fails for files exceeding limit."""
        with (
            patch("os.path.exists", return_value=True),
            patch("os.path.getsize", return_value=150 * 1024 * 1024),
        ):  # 150 MB
            with pytest.raises(ValueError, match="exceeds"):
                server._validate_file_size("/path/to/large.docx")

# ============================================================================
# DocumentOpsServer Error Handling Tests
# ============================================================================

class TestDocumentOpsServerErrors:
    """Tests for error handling."""

    @pytest.fixture
    def server(self, mock_registry):
        """Create server with mock registry."""
        return DocumentOpsServer(mock_registry)

    def test_extract_error_response_unsupported_ext(self, server, mock_registry):
        """Test extract with unsupported extension raises ValueError from _validate_file."""
        # .xyz is not a supported extension, so _validate_file raises ValueError
        # before even reaching MCP call
        with pytest.raises(ValueError, match="Unsupported document type"):
            server.extract("/path/to/file.xyz")

        mock_registry.call_tool.assert_not_called()

    def test_extract_invalid_json_response(self, server, mock_registry, mock_result_text):
        """Test handling of invalid JSON response."""
        mock_registry.call_tool.return_value = mock_result_text("not valid json")

        with patch.object(server, "_validate_file_size"):
            with pytest.raises(json.JSONDecodeError):
                server.extract("/path/to/doc.docx")

    def test_unsupported_file_extension(self, server, mock_registry):
        """Test unsupported file extension is rejected."""
        with pytest.raises(ValueError, match="Unsupported"):
            server.extract("/path/to/file.unknown")

        mock_registry.call_tool.assert_not_called()

# ============================================================================
# DocumentOpsServer Conversion Tests
# ============================================================================

class TestDocumentOpsServerConversion:
    """Tests for document conversion operations."""

    @pytest.fixture
    def server(self, mock_registry):
        """Create server with mock registry."""
        return DocumentOpsServer(mock_registry)

    def test_to_markdown(self, server, mock_registry, mock_result_text):
        """Test converting document to Markdown via to_markdown method."""
        mock_registry.call_tool.return_value = mock_result_text(
            "# Converted Document\n\nContent here"
        )

        with patch.object(server, "_validate_file"):
            result = server.to_markdown("/path/to/doc.docx")

        assert "# Converted Document" in result
        mock_registry.call_tool.assert_called_once()

    def test_to_text(self, server, mock_registry, mock_result_text):
        """Test extracting plain text via to_text method."""
        mock_registry.call_tool.return_value = mock_result_text("Plain text content from document")

        with patch.object(server, "_validate_file"):
            result = server.to_text("/path/to/doc.docx")

        assert "Plain text content" in result
        mock_registry.call_tool.assert_called_once()
