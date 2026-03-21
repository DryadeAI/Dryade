"""Unit tests for PDF Reader MCP server wrapper.

Comprehensive tests for PDF extraction: text, tables, images, and metadata.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from core.mcp.protocol import MCPToolCallContent, MCPToolCallResult
from core.mcp.servers.pdf_reader import (
    MAX_FILE_SIZE_BYTES,
    MAX_FILE_SIZE_MB,
    PDFDocument,
    PDFPage,
    PDFReaderServer,
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
# Constants Tests
# ============================================================================

class TestConstants:
    """Tests for module constants."""

    def test_max_file_size_mb(self):
        """Test MAX_FILE_SIZE_MB is 100."""
        assert MAX_FILE_SIZE_MB == 100

    def test_max_file_size_bytes(self):
        """Test MAX_FILE_SIZE_BYTES is correctly calculated."""
        assert MAX_FILE_SIZE_BYTES == 100 * 1024 * 1024

# ============================================================================
# PDFPage Tests
# ============================================================================

class TestPDFPage:
    """Tests for PDFPage dataclass."""

    def test_pdf_page_init_basic(self):
        """Test PDFPage initialization with basic fields."""
        page = PDFPage(
            page_number=1,
            text="Hello, World!",
        )

        assert page.page_number == 1
        assert page.text == "Hello, World!"
        assert page.tables == []
        assert page.images == []

    def test_pdf_page_init_with_tables(self):
        """Test PDFPage initialization with tables."""
        table = [["Header 1", "Header 2"], ["Cell 1", "Cell 2"]]
        page = PDFPage(
            page_number=1,
            text="Table page",
            tables=[table],
        )

        assert len(page.tables) == 1
        assert page.tables[0] == table

    def test_pdf_page_init_with_images(self):
        """Test PDFPage initialization with images."""
        images = [
            {"width": 100, "height": 100, "format": "png"},
            {"width": 200, "height": 150, "format": "jpeg"},
        ]
        page = PDFPage(
            page_number=1,
            text="Image page",
            images=images,
        )

        assert len(page.images) == 2
        assert page.images[0]["format"] == "png"

    def test_pdf_page_to_dict(self):
        """Test PDFPage.to_dict() returns correct structure."""
        page = PDFPage(
            page_number=1,
            text="Test content",
            tables=[[["A", "B"]]],
            images=[{"width": 100}],
        )

        data = page.to_dict()

        assert data == {
            "page_number": 1,
            "text": "Test content",
            "tables": [[["A", "B"]]],
            "images": [{"width": 100}],
        }

# ============================================================================
# PDFDocument Tests
# ============================================================================

class TestPDFDocument:
    """Tests for PDFDocument dataclass."""

    def test_pdf_document_init(self):
        """Test PDFDocument initialization."""
        pages = [
            PDFPage(page_number=1, text="Page 1"),
            PDFPage(page_number=2, text="Page 2"),
        ]
        doc = PDFDocument(
            path="/path/to/doc.pdf",
            page_count=2,
            metadata={"title": "Test Doc", "author": "Test Author"},
            pages=pages,
        )

        assert doc.path == "/path/to/doc.pdf"
        assert doc.page_count == 2
        assert doc.metadata["title"] == "Test Doc"
        assert len(doc.pages) == 2

    def test_pdf_document_to_dict(self):
        """Test PDFDocument.to_dict() returns correct structure."""
        pages = [PDFPage(page_number=1, text="Page 1")]
        doc = PDFDocument(
            path="/path/to/doc.pdf",
            page_count=1,
            metadata={"title": "Test"},
            pages=pages,
        )

        data = doc.to_dict()

        assert data["path"] == "/path/to/doc.pdf"
        assert data["page_count"] == 1
        assert data["metadata"] == {"title": "Test"}
        assert len(data["pages"]) == 1

    def test_pdf_document_full_text(self):
        """Test PDFDocument.full_text property."""
        pages = [
            PDFPage(page_number=1, text="First page content"),
            PDFPage(page_number=2, text="Second page content"),
            PDFPage(page_number=3, text="Third page content"),
        ]
        doc = PDFDocument(
            path="/path/to/doc.pdf",
            page_count=3,
            metadata={},
            pages=pages,
        )

        full_text = doc.full_text

        assert full_text == "First page content\n\nSecond page content\n\nThird page content"

    def test_pdf_document_full_text_empty(self):
        """Test PDFDocument.full_text with no pages."""
        doc = PDFDocument(
            path="/path/to/empty.pdf",
            page_count=0,
            metadata={},
            pages=[],
        )

        assert doc.full_text == ""

# ============================================================================
# PDFReaderServer Initialization Tests
# ============================================================================

class TestPDFReaderServerInit:
    """Tests for PDFReaderServer initialization."""

    def test_init_default_server_name(self, mock_registry):
        """Test default server name is 'pdf-reader'."""
        server = PDFReaderServer(mock_registry)

        assert server._server_name == "pdf-reader"
        assert server._registry is mock_registry

    def test_init_custom_server_name(self, mock_registry):
        """Test custom server name."""
        server = PDFReaderServer(mock_registry, server_name="custom-pdf")

        assert server._server_name == "custom-pdf"

# ============================================================================
# PDFReaderServer Extract Tests
# ============================================================================

class TestPDFReaderServerExtract:
    """Tests for PDF extraction operations."""

    @pytest.fixture
    def server(self, mock_registry):
        """Create server with mock registry."""
        return PDFReaderServer(mock_registry)

    def test_extract_basic(self, server, mock_registry, mock_result_text):
        """Test basic PDF extraction."""
        mock_registry.call_tool.return_value = mock_result_text(
            json.dumps(
                {
                    "path": "/path/to/doc.pdf",
                    "page_count": 2,
                    "metadata": {"title": "Test Document"},
                    "pages": [
                        {"page_number": 1, "text": "Page 1 content", "tables": [], "images": []},
                        {"page_number": 2, "text": "Page 2 content", "tables": [], "images": []},
                    ],
                }
            )
        )

        with patch.object(server, "_validate_file_size"):
            doc = server.extract("/path/to/doc.pdf")

        assert isinstance(doc, PDFDocument)
        assert doc.page_count == 2
        assert len(doc.pages) == 2
        mock_registry.call_tool.assert_called_once()

    def test_extract_with_images(self, server, mock_registry, mock_result_text):
        """Test PDF extraction with images enabled."""
        mock_registry.call_tool.return_value = mock_result_text(
            json.dumps(
                {
                    "path": "/path/to/doc.pdf",
                    "page_count": 1,
                    "metadata": {},
                    "pages": [
                        {
                            "page_number": 1,
                            "text": "Content",
                            "tables": [],
                            "images": [{"width": 100, "height": 100}],
                        }
                    ],
                }
            )
        )

        with patch.object(server, "_validate_file_size"):
            doc = server.extract("/path/to/doc.pdf", include_images=True)

        args = mock_registry.call_tool.call_args
        assert args[0][2].get("include_images") is True
        assert len(doc.pages[0].images) == 1

    def test_extract_with_tables(self, server, mock_registry, mock_result_text):
        """Test PDF extraction with tables."""
        table_data = [["Header 1", "Header 2"], ["Cell 1", "Cell 2"]]
        mock_registry.call_tool.return_value = mock_result_text(
            json.dumps(
                {
                    "path": "/path/to/doc.pdf",
                    "page_count": 1,
                    "metadata": {},
                    "pages": [
                        {
                            "page_number": 1,
                            "text": "Table content",
                            "tables": [table_data],
                            "images": [],
                        }
                    ],
                }
            )
        )

        with patch.object(server, "_validate_file_size"):
            doc = server.extract("/path/to/doc.pdf")

        assert len(doc.pages[0].tables) == 1
        assert doc.pages[0].tables[0] == table_data

# ============================================================================
# PDFReaderServer Page Range Tests
# ============================================================================

class TestPDFReaderServerPageRange:
    """Tests for single page extraction (extract_page, not extract_pages)."""

    @pytest.fixture
    def server(self, mock_registry):
        """Create server with mock registry."""
        return PDFReaderServer(mock_registry)

    def test_extract_page(self, server, mock_registry, mock_result_text):
        """Test extracting a specific page by number."""
        mock_registry.call_tool.return_value = mock_result_text(
            json.dumps(
                {
                    "page_number": 2,
                    "text": "Page 2 content",
                    "tables": [],
                    "images": [],
                }
            )
        )

        with patch.object(server, "_validate_file_size"):
            page = server.extract_page("/path/to/doc.pdf", page_number=2)

        assert isinstance(page, PDFPage)
        assert page.page_number == 2
        assert page.text == "Page 2 content"
        args = mock_registry.call_tool.call_args
        assert args[0][2].get("page_number") == 2

    def test_extract_single_page(self, server, mock_registry, mock_result_text):
        """Test extracting page 5 returns correct content."""
        mock_registry.call_tool.return_value = mock_result_text(
            json.dumps(
                {
                    "page_number": 5,
                    "text": "Page 5 content",
                    "tables": [],
                    "images": [],
                }
            )
        )

        with patch.object(server, "_validate_file_size"):
            page = server.extract_page("/path/to/doc.pdf", page_number=5)

        assert page.page_number == 5
        assert page.text == "Page 5 content"

# ============================================================================
# PDFReaderServer Metadata Tests
# ============================================================================

class TestPDFReaderServerMetadata:
    """Tests for metadata operations."""

    @pytest.fixture
    def server(self, mock_registry):
        """Create server with mock registry."""
        return PDFReaderServer(mock_registry)

    def test_get_metadata(self, server, mock_registry, mock_result_text):
        """Test getting PDF metadata only."""
        mock_registry.call_tool.return_value = mock_result_text(
            json.dumps(
                {
                    "title": "Annual Report 2024",
                    "author": "Finance Team",
                    "creation_date": "2024-01-15",
                    "modification_date": "2024-01-20",
                }
            )
        )

        with patch.object(server, "_validate_file_size"):
            metadata = server.get_metadata("/path/to/doc.pdf")

        assert metadata["title"] == "Annual Report 2024"
        assert metadata["author"] == "Finance Team"
        mock_registry.call_tool.assert_called_once_with(
            "pdf-reader", "get_metadata", {"path": "/path/to/doc.pdf"}
        )

# ============================================================================
# PDFReaderServer Config Tests
# ============================================================================

class TestPDFReaderServerConfig:
    """Tests for configuration -- PDFReaderServer has no get_config class method."""

    def test_no_get_config_method(self):
        """Verify get_config does not exist (config is external)."""
        assert not hasattr(PDFReaderServer, "get_config")

    def test_server_name_default(self, mock_registry):
        """Test default server name."""
        server = PDFReaderServer(mock_registry)
        assert server._server_name == "pdf-reader"

# ============================================================================
# PDFReaderServer Validation Tests
# ============================================================================

class TestPDFReaderServerValidation:
    """Tests for file validation."""

    @pytest.fixture
    def server(self, mock_registry):
        """Create server with mock registry."""
        return PDFReaderServer(mock_registry)

    def test_validate_file_size_within_limit(self, server):
        """Test validation passes for files within limit."""
        with (
            patch("os.path.exists", return_value=True),
            patch("os.path.getsize", return_value=50 * 1024 * 1024),
        ):  # 50 MB
            # Should not raise
            server._validate_file_size("/path/to/small.pdf")

    def test_validate_file_size_exceeds_limit(self, server):
        """Test validation fails for files exceeding limit."""
        with (
            patch("os.path.exists", return_value=True),
            patch("os.path.getsize", return_value=150 * 1024 * 1024),
        ):  # 150 MB
            with pytest.raises(ValueError, match="exceeds"):
                server._validate_file_size("/path/to/large.pdf")

    def test_validate_file_size_at_limit(self, server):
        """Test validation passes for files at exactly the limit."""
        with (
            patch("os.path.exists", return_value=True),
            patch("os.path.getsize", return_value=MAX_FILE_SIZE_BYTES),
        ):
            # Should not raise
            server._validate_file_size("/path/to/exact.pdf")

# ============================================================================
# PDFReaderServer Error Handling Tests
# ============================================================================

class TestPDFReaderServerErrors:
    """Tests for error handling."""

    @pytest.fixture
    def server(self, mock_registry):
        """Create server with mock registry."""
        return PDFReaderServer(mock_registry)

    def test_extract_error_response_parsed(self, server, mock_registry):
        """Test error response text is still parsed (source does not check isError)."""
        mock_registry.call_tool.return_value = MCPToolCallResult(
            content=[MCPToolCallContent(type="text", text="File not found")],
            isError=True,
        )

        with patch.object(server, "_validate_file_size"):
            # Source tries json.loads on "File not found" -> JSONDecodeError
            with pytest.raises(json.JSONDecodeError):
                server.extract("/path/to/missing.pdf")

    def test_extract_invalid_json_response(self, server, mock_registry, mock_result_text):
        """Test handling of invalid JSON response."""
        mock_registry.call_tool.return_value = mock_result_text("not valid json")

        with patch.object(server, "_validate_file_size"):
            with pytest.raises(json.JSONDecodeError):
                server.extract("/path/to/doc.pdf")

    def test_no_extract_pages_method(self, server):
        """Test extract_pages does not exist (use extract_page for single page)."""
        assert not hasattr(server, "extract_pages")
        assert hasattr(server, "extract_page")

    def test_extract_page_returns_empty_for_missing(self, server, mock_registry, mock_result_empty):
        """Test extract_page returns empty page for empty MCP response."""
        mock_registry.call_tool.return_value = mock_result_empty

        with patch.object(server, "_validate_file_size"):
            page = server.extract_page("/path/to/doc.pdf", page_number=1)

        assert page.text == ""
        assert page.page_number == 1
