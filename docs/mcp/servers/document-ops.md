# Document Operations MCP Server

| Property | Value |
|----------|-------|
| Package | `@negokaz/excel-mcp-server` |
| Category | Document |
| Default | Enabled |
| Transport | STDIO |
| Credentials | None required |

> **Note:** Despite the package name, this server handles multiple document formats beyond Excel.

## Overview

The Document Operations MCP server provides extraction and conversion capabilities for various office document formats, enabling AI agents to read and process business documents.

### Supported Formats

- **XLSX** - Microsoft Excel spreadsheets
- **DOCX** - Microsoft Word documents
- **PPTX** - Microsoft PowerPoint presentations
- **CSV** - Comma-separated values
- **Markdown** - Markdown text files

### Key Features

- **Auto-Detection** - Automatically detect format and extract
- **Format-Specific Extraction** - Specialized extractors for each format
- **Conversion** - Convert documents to Markdown or plain text
- **Multi-Sheet Support** - Handle multiple Excel sheets

### Use Cases

- Spreadsheet analysis
- Document conversion
- Report generation
- Data import from various formats
- Content migration

## Configuration

Configuration in `config/mcp_servers.yaml`:

```yaml
document-ops:
  enabled: true
  command:
    - npx
    - -y
    - '@negokaz/excel-mcp-server'
  description: Excel file operations (read, write, create sheets)
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

### extract_document

Auto-detect document format and extract content.

| Property | Value |
|----------|-------|
| Parameters | `path: string` |
| Returns | `DocumentContent` |
| Purpose | Universal document extraction |

**Example:**

```python
# Automatically detects format
content = registry.call_tool("document-ops", "extract_document", {
    "path": "/path/to/document.xlsx"  # or .docx, .pptx, .csv, .md
})
```

### extract_docx

Extract content from Microsoft Word documents.

| Property | Value |
|----------|-------|
| Parameters | `path: string` |
| Returns | `DocumentContent` |
| Purpose | Extract Word document content |

**Example:**

```python
content = registry.call_tool("document-ops", "extract_docx", {
    "path": "/path/to/document.docx"
})
# Returns: {
#   text: "Document content...",
#   paragraphs: [...],
#   headings: [...],
#   tables: [...]
# }
```

### extract_xlsx

Extract data from Microsoft Excel spreadsheets.

| Property | Value |
|----------|-------|
| Parameters | `path: string` |
| Returns | `SpreadsheetData[]` (array of sheets) |
| Purpose | Extract Excel spreadsheet data |

**Example:**

```python
sheets = registry.call_tool("document-ops", "extract_xlsx", {
    "path": "/path/to/spreadsheet.xlsx"
})
# Returns: [
#   {name: "Sheet1", rows: [["A1", "B1"], ["A2", "B2"]], columns: ["A", "B"]},
#   {name: "Sheet2", rows: [...], columns: [...]}
# ]
```

### extract_pptx

Extract content from Microsoft PowerPoint presentations.

| Property | Value |
|----------|-------|
| Parameters | `path: string` |
| Returns | `DocumentContent` |
| Purpose | Extract PowerPoint content |

**Example:**

```python
content = registry.call_tool("document-ops", "extract_pptx", {
    "path": "/path/to/presentation.pptx"
})
# Returns: {
#   slides: [
#     {title: "Slide 1", content: "...", notes: "..."},
#     {title: "Slide 2", content: "...", notes: "..."}
#   ]
# }
```

### parse_csv

Parse CSV files with configurable delimiter.

| Property | Value |
|----------|-------|
| Parameters | `path: string`, `delimiter?: string` (default: ",") |
| Returns | `SpreadsheetData` |
| Purpose | Parse CSV files |

**Example:**

```python
# Standard CSV
data = registry.call_tool("document-ops", "parse_csv", {
    "path": "/path/to/data.csv"
})

# Tab-separated
data = registry.call_tool("document-ops", "parse_csv", {
    "path": "/path/to/data.tsv",
    "delimiter": "\t"
})

# Semicolon-separated (European format)
data = registry.call_tool("document-ops", "parse_csv", {
    "path": "/path/to/data.csv",
    "delimiter": ";"
})
```

### parse_markdown

Parse Markdown files into structured content.

| Property | Value |
|----------|-------|
| Parameters | `path: string` |
| Returns | `DocumentContent` |
| Purpose | Parse Markdown structure |

**Example:**

```python
content = registry.call_tool("document-ops", "parse_markdown", {
    "path": "/path/to/document.md"
})
# Returns: {
#   text: "Full text...",
#   headings: [{level: 1, text: "Title"}, ...],
#   code_blocks: [...],
#   links: [...]
# }
```

### to_markdown

Convert any supported document to Markdown format.

| Property | Value |
|----------|-------|
| Parameters | `path: string` |
| Returns | `string` (Markdown content) |
| Purpose | Convert document to Markdown |

**Example:**

```python
# Convert Word to Markdown
markdown = registry.call_tool("document-ops", "to_markdown", {
    "path": "/path/to/document.docx"
})

# Convert Excel to Markdown tables
markdown = registry.call_tool("document-ops", "to_markdown", {
    "path": "/path/to/spreadsheet.xlsx"
})
```

### to_text

Extract plain text from any supported document.

| Property | Value |
|----------|-------|
| Parameters | `path: string` |
| Returns | `string` (plain text) |
| Purpose | Extract plain text |

**Example:**

```python
text = registry.call_tool("document-ops", "to_text", {
    "path": "/path/to/document.docx"
})
```

## Python Wrapper Usage

```python
from core.mcp import get_registry
from core.mcp.servers import DocumentOpsServer

registry = get_registry()
docs = DocumentOpsServer(registry)

# Extract Excel spreadsheet
sheets = docs.extract_xlsx("/path/to/data.xlsx")
for sheet in sheets:
    print(f"Sheet: {sheet['name']}")
    print(f"  Rows: {len(sheet['rows'])}")
    print(f"  Columns: {sheet['columns']}")

# Extract Word document
word_doc = docs.extract_docx("/path/to/report.docx")
print(f"Headings: {word_doc['headings']}")
print(f"Tables: {len(word_doc.get('tables', []))}")

# Convert PowerPoint to Markdown
pptx_md = docs.to_markdown("/path/to/slides.pptx")
print(pptx_md)

# Parse CSV with custom delimiter
csv_data = docs.parse_csv("/path/to/european.csv", delimiter=";")

# Universal extraction
content = docs.extract_document("/path/to/any-file.docx")
```

## Use Cases

### Spreadsheet Analysis

```python
# Analyze financial data from Excel
sheets = docs.extract_xlsx("/path/to/financial_report.xlsx")

# Find summary sheet
summary = next((s for s in sheets if "summary" in s["name"].lower()), None)
if summary:
    headers = summary["rows"][0] if summary["rows"] else []
    data_rows = summary["rows"][1:]

    # Find revenue column
    if "Revenue" in headers:
        revenue_idx = headers.index("Revenue")
        revenues = [row[revenue_idx] for row in data_rows if len(row) > revenue_idx]
        print(f"Revenue values: {revenues}")
```

### Document Conversion Pipeline

```python
def convert_to_markdown(input_path, output_path):
    """Convert any supported document to Markdown."""
    markdown = docs.to_markdown(input_path)

    # Write output
    with open(output_path, 'w') as f:
        f.write(markdown)

    return output_path

# Batch convert
import os
for file in os.listdir("/path/to/docs"):
    if file.endswith(('.docx', '.xlsx', '.pptx')):
        input_path = os.path.join("/path/to/docs", file)
        output_path = os.path.join("/path/to/output", file.rsplit('.', 1)[0] + '.md')
        convert_to_markdown(input_path, output_path)
```

### Report Generation from Templates

```python
def generate_report_context(excel_path, word_template_path):
    """Extract data for report generation."""
    # Get data from Excel
    sheets = docs.extract_xlsx(excel_path)
    data_sheet = sheets[0]

    # Get template structure
    template = docs.extract_docx(word_template_path)

    return {
        "data": data_sheet["rows"],
        "headers": data_sheet["rows"][0] if data_sheet["rows"] else [],
        "template_headings": template.get("headings", []),
        "template_structure": template
    }
```

### Data Import from Multiple Sources

```python
def import_data(file_path):
    """Import data from any supported format."""
    ext = file_path.rsplit('.', 1)[-1].lower()

    if ext == 'xlsx':
        sheets = docs.extract_xlsx(file_path)
        # Return first sheet data
        return sheets[0]["rows"] if sheets else []

    elif ext == 'csv':
        data = docs.parse_csv(file_path)
        return data["rows"]

    elif ext == 'docx':
        content = docs.extract_docx(file_path)
        # Return tables from document
        return content.get("tables", [])

    else:
        # Use auto-detection
        content = docs.extract_document(file_path)
        return content
```

### Presentation Content Extraction

```python
def extract_presentation_outline(pptx_path):
    """Extract presentation outline from PowerPoint."""
    content = docs.extract_pptx(pptx_path)

    outline = []
    for i, slide in enumerate(content.get("slides", []), 1):
        outline.append({
            "slide": i,
            "title": slide.get("title", f"Slide {i}"),
            "summary": slide.get("content", "")[:200] + "..."
        })

    return outline
```

## Troubleshooting

### File Not Found

```
Error: File not found: /path/to/document.xlsx
```

**Solutions:**
1. Verify file path is correct and absolute
2. Check file permissions
3. Ensure file exists

### Unsupported Format

```
Error: Unsupported file format
```

**Causes:**
- File extension not recognized
- File is corrupted

**Solutions:**
1. Verify file has correct extension
2. Try opening file in native application
3. Use format-specific extraction tool

### Encoding Issues

```
Error: Unable to decode file content
```

**Causes:**
- Non-UTF8 encoding in CSV
- Special characters in file

**Solutions:**
1. Convert file to UTF-8 encoding
2. Specify correct delimiter for CSV

### Large File Timeout

```
Error: Operation timeout after 60s
```

**Causes:**
- Very large Excel file
- Many sheets/rows

**Solutions:**
1. Increase timeout in configuration
2. Split large files
3. Use streaming extraction if available

### Corrupted Document

```
Error: Invalid document structure
```

**Causes:**
- File is corrupted
- Incomplete download
- Wrong file extension

**Solutions:**
1. Re-download or re-create file
2. Try opening in native application
3. Verify file integrity

## Limitations

- **Large Files** - Memory constraints for very large spreadsheets
- **Formulas** - Extracts values, not formulas from Excel
- **Formatting** - Style/formatting information not preserved in text extraction
- **Embedded Objects** - OLE objects and embedded files not extracted
- **Password Protection** - Cannot process password-protected documents
- **Macros** - Excel macros are not extracted or executed

## Related Documentation

- [MCP Overview](../README.md)
- [PDF Reader Server](./pdf-reader.md)
- [Tool Inventory](../INVENTORY.md)
