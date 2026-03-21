# PDF Reader MCP Server

| Property | Value |
|----------|-------|
| Package | `@shtse8/pdf-reader-mcp` |
| Category | Document |
| Default | Enabled |
| Transport | STDIO |
| Credentials | None required |

## Overview

The PDF Reader MCP server provides comprehensive PDF extraction capabilities, enabling AI agents to read, analyze, and extract content from PDF documents.

### Key Features

- **Full Document Extraction** - Extract text, tables, images, and structure
- **Text Extraction** - Get plain text content from PDFs
- **Table Extraction** - Extract tabular data as arrays
- **Page-Level Access** - Extract individual pages
- **Metadata Access** - Read PDF metadata (title, author, dates)
- **Page Counting** - Get document page count

### Use Cases

- Document summarization
- Data extraction from reports
- PDF to text conversion
- Table data extraction for analysis
- Document indexing and search

## Configuration

Configuration in `config/mcp_servers.yaml`:

```yaml
pdf-reader:
  enabled: true
  command:
    - npx
    - -y
    - '@shtse8/pdf-reader-mcp'
  description: PDF extraction (text, tables, images, structure)
  auto_restart: true
  max_restarts: 3
  timeout: 60.0
```

### Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | boolean | true | Enable/disable the server |
| `auto_restart` | boolean | true | Restart on crash |
| `max_restarts` | integer | 3 | Maximum restart attempts |
| `timeout` | float | 60.0 | Operation timeout in seconds |

No environment variables or credentials required.

## Tool Reference

### extract_pdf

Extract complete PDF content including text, tables, and optionally images.

| Property | Value |
|----------|-------|
| Parameters | `path: string`, `include_images?: boolean` |
| Returns | `PDFDocument` object |
| Purpose | Full PDF extraction with all content |

**Example:**

```python
# Full extraction without images
doc = registry.call_tool("pdf-reader", "extract_pdf", {
    "path": "/path/to/document.pdf"
})
# Returns: {pages: [...], metadata: {...}, tables: [...]}

# With images (base64 encoded)
doc = registry.call_tool("pdf-reader", "extract_pdf", {
    "path": "/path/to/document.pdf",
    "include_images": True
})
```

### extract_text

Extract plain text content from a PDF.

| Property | Value |
|----------|-------|
| Parameters | `path: string` |
| Returns | `string` |
| Purpose | Text-only extraction |

**Example:**

```python
text = registry.call_tool("pdf-reader", "extract_text", {
    "path": "/path/to/document.pdf"
})
# Returns: Full text content as string
```

### extract_tables

Extract all tables from a PDF as arrays.

| Property | Value |
|----------|-------|
| Parameters | `path: string` |
| Returns | `table[][]` (array of tables, each table is array of rows) |
| Purpose | Extract tabular data |

**Example:**

```python
tables = registry.call_tool("pdf-reader", "extract_tables", {
    "path": "/path/to/report.pdf"
})
# Returns: [
#   [["Header1", "Header2"], ["Row1Val1", "Row1Val2"], ...],
#   [["Table2Header"], ...]
# ]
```

### extract_page

Extract content from a single page.

| Property | Value |
|----------|-------|
| Parameters | `path: string`, `page_number: int` (1-indexed) |
| Returns | `PDFPage` object |
| Purpose | Single page extraction |

**Example:**

```python
# Extract page 3
page = registry.call_tool("pdf-reader", "extract_page", {
    "path": "/path/to/document.pdf",
    "page_number": 3
})
# Returns: {text: "...", tables: [...], images: [...]}
```

### get_metadata

Retrieve PDF metadata.

| Property | Value |
|----------|-------|
| Parameters | `path: string` |
| Returns | `object` with metadata fields |
| Purpose | Access document metadata |

**Example:**

```python
meta = registry.call_tool("pdf-reader", "get_metadata", {
    "path": "/path/to/document.pdf"
})
# Returns: {
#   title: "Document Title",
#   author: "Author Name",
#   subject: "Subject",
#   keywords: "keyword1, keyword2",
#   creator: "Application Name",
#   producer: "PDF Library",
#   creation_date: "2024-01-15T10:30:00Z",
#   modification_date: "2024-01-20T14:45:00Z"
# }
```

### get_page_count

Get the total number of pages in a PDF.

| Property | Value |
|----------|-------|
| Parameters | `path: string` |
| Returns | `int` |
| Purpose | Get page count |

**Example:**

```python
count = registry.call_tool("pdf-reader", "get_page_count", {
    "path": "/path/to/document.pdf"
})
# Returns: 42
```

## Python Wrapper Usage

```python
from core.mcp import get_registry
from core.mcp.servers import PDFReaderServer

registry = get_registry()
pdf = PDFReaderServer(registry)

# Get page count first
pages = pdf.get_page_count("/path/to/report.pdf")
print(f"Document has {pages} pages")

# Get metadata
meta = pdf.get_metadata("/path/to/report.pdf")
print(f"Title: {meta.get('title', 'Unknown')}")
print(f"Author: {meta.get('author', 'Unknown')}")

# Extract all text
text = pdf.extract_text("/path/to/report.pdf")
print(f"Content length: {len(text)} characters")

# Extract tables for analysis
tables = pdf.extract_tables("/path/to/report.pdf")
for i, table in enumerate(tables):
    print(f"Table {i+1}: {len(table)} rows")
    if table:
        print(f"  Headers: {table[0]}")

# Extract specific page
page_content = pdf.extract_page("/path/to/report.pdf", page_number=1)
print(f"First page text: {page_content['text'][:200]}...")

# Full extraction
doc = pdf.extract_pdf("/path/to/report.pdf", include_images=True)
```

## Use Cases

### Document Summarization

```python
# Extract text and summarize
text = pdf.extract_text("/path/to/document.pdf")
meta = pdf.get_metadata("/path/to/document.pdf")

summary_prompt = f"""
Document: {meta.get('title', 'Unknown')}
Author: {meta.get('author', 'Unknown')}

Content:
{text[:10000]}

Please provide a 3-5 sentence summary.
"""
```

### Data Extraction from Reports

```python
# Extract financial tables from annual report
tables = pdf.extract_tables("/path/to/annual_report.pdf")

# Find revenue table (heuristic: contains "Revenue" header)
for table in tables:
    if table and any("revenue" in str(cell).lower() for cell in table[0]):
        print("Revenue Table Found:")
        for row in table:
            print(row)
```

### Document Indexing

```python
# Index PDF for search
doc = pdf.extract_pdf("/path/to/document.pdf")
meta = pdf.get_metadata("/path/to/document.pdf")

index_entry = {
    "path": "/path/to/document.pdf",
    "title": meta.get("title"),
    "author": meta.get("author"),
    "pages": len(doc.get("pages", [])),
    "text": pdf.extract_text("/path/to/document.pdf"),
    "indexed_at": datetime.utcnow().isoformat()
}
```

### Batch Processing

```python
import os

def process_pdfs(directory):
    results = []
    for filename in os.listdir(directory):
        if filename.endswith(".pdf"):
            path = os.path.join(directory, filename)
            try:
                meta = pdf.get_metadata(path)
                pages = pdf.get_page_count(path)
                results.append({
                    "file": filename,
                    "title": meta.get("title"),
                    "pages": pages,
                    "status": "success"
                })
            except Exception as e:
                results.append({
                    "file": filename,
                    "status": "error",
                    "error": str(e)
                })
    return results
```

## Troubleshooting

### File Not Found

```
Error: File not found: /path/to/document.pdf
```

**Solutions:**
1. Verify file path is correct and absolute
2. Check file permissions
3. Ensure file exists

### Encrypted PDF

```
Error: PDF is encrypted
```

**Solutions:**
1. Use a PDF tool to decrypt the file first
2. Provide password-protected PDF handling (not supported)

### Extraction Timeout

```
Error: Operation timeout after 60s
```

**Causes:**
- Very large PDF file
- Complex document structure

**Solutions:**
1. Increase timeout in configuration
2. Extract pages individually
3. Use `extract_text` for faster text-only extraction

### Empty Extraction

```
Extraction returned empty content
```

**Causes:**
- PDF contains only images (scanned document)
- PDF uses non-standard encoding

**Solutions:**
1. Use OCR preprocessing for scanned documents
2. Try different extraction tools

## Limitations

- **Scanned PDFs** - Requires OCR preprocessing; native extraction returns empty text
- **Password Protected** - Cannot process encrypted/password-protected PDFs
- **Complex Layouts** - Multi-column layouts may have extraction order issues
- **Forms** - Form field data extraction not supported

## Related Documentation

- [MCP Overview](../README.md)
- [Document Ops Server](./document-ops.md)
- [Tool Inventory](../INVENTORY.md)
