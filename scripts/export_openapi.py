#!/usr/bin/env python3
"""Export the FastAPI OpenAPI spec and generate a Markdown API reference.

Extracts the OpenAPI specification from the Dryade FastAPI application,
writes the raw JSON spec, and generates a human-readable Markdown API
reference document organized by tags.

Usage:
    python scripts/export_openapi.py --output-json docs/openapi.json --output-md docs/API-REFERENCE.md
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

def get_openapi_spec() -> dict | None:
    """Import the FastAPI app and extract the OpenAPI spec.

    Returns:
        OpenAPI spec dict, or None if import/extraction fails.
    """
    try:
        from core.api.main import app

        return app.openapi()
    except Exception as e:
        print(f"WARNING: Could not import FastAPI app: {e}", file=sys.stderr)
        print("Attempting route-based fallback...", file=sys.stderr)
        return None

def generate_markdown_reference(spec: dict) -> str:
    """Generate a Markdown API reference from an OpenAPI spec dict.

    Args:
        spec: OpenAPI specification dictionary.

    Returns:
        Markdown string containing the full API reference.
    """
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    info = spec.get("info", {})
    api_version = info.get("version", "unknown")

    lines = []
    lines.append("# Dryade API Reference")
    lines.append("")
    lines.append(f"> Auto-generated on {timestamp}. API version: **{api_version}**.")
    lines.append("")

    # Build tag -> endpoints mapping
    tags_map: dict[str, list[tuple[str, str, dict]]] = {}
    paths = spec.get("paths", {})
    endpoint_count = 0

    for path, methods in paths.items():
        for method, operation in methods.items():
            if method.lower() in ("get", "post", "put", "patch", "delete", "head", "options"):
                endpoint_count += 1
                op_tags = operation.get("tags", ["Other"])
                for tag in op_tags:
                    tags_map.setdefault(tag, []).append((method.upper(), path, operation))

    # Get tag descriptions from spec
    tag_descriptions = {}
    for tag_info in spec.get("tags", []):
        tag_descriptions[tag_info["name"]] = tag_info.get("description", "")

    # Sort tags, putting "Other" last
    sorted_tags = sorted(tags_map.keys(), key=lambda t: (t == "Other", t.lower()))

    for tag in sorted_tags:
        lines.append(f"## {tag}")
        desc = tag_descriptions.get(tag, "")
        if desc:
            lines.append("")
            lines.append(desc)
        lines.append("")

        endpoints = tags_map[tag]
        # Sort by path then method
        endpoints.sort(key=lambda x: (x[1], x[0]))

        for method, path, operation in endpoints:
            summary = operation.get("summary", "")
            description = operation.get("description", "")
            lines.append(f"### {method} {path}")
            lines.append("")
            if summary:
                lines.append(f"**{summary}**")
                lines.append("")
            if description and description != summary:
                lines.append(description)
                lines.append("")

            # Parameters table
            params = operation.get("parameters", [])
            if params:
                lines.append("**Parameters:**")
                lines.append("")
                lines.append("| Name | In | Type | Required | Description |")
                lines.append("|------|----|------|----------|-------------|")
                for param in params:
                    name = param.get("name", "")
                    location = param.get("in", "")
                    schema = param.get("schema", {})
                    ptype = schema.get("type", "string")
                    required = "Yes" if param.get("required", False) else "No"
                    pdesc = param.get("description", "-")
                    lines.append(f"| {name} | {location} | {ptype} | {required} | {pdesc} |")
                lines.append("")

            # Request body
            request_body = operation.get("requestBody", {})
            if request_body:
                content = request_body.get("content", {})
                for content_type, media in content.items():
                    schema = media.get("schema", {})
                    ref = schema.get("$ref", "")
                    if ref:
                        schema_name = ref.split("/")[-1]
                        lines.append(f"**Request Body:** `{schema_name}` ({content_type})")
                    else:
                        schema_type = schema.get("type", "object")
                        lines.append(f"**Request Body:** {schema_type} ({content_type})")
                    lines.append("")

            # Response codes
            responses = operation.get("responses", {})
            if responses:
                lines.append("**Responses:**")
                lines.append("")
                lines.append("| Code | Description |")
                lines.append("|------|-------------|")
                for code, resp in sorted(responses.items()):
                    rdesc = resp.get("description", "-")
                    lines.append(f"| {code} | {rdesc} |")
                lines.append("")
            lines.append("---")
            lines.append("")

    return "\n".join(lines), endpoint_count

def main():
    """CLI entry point for OpenAPI export."""
    parser = argparse.ArgumentParser(
        description="Export OpenAPI spec and generate Markdown API reference",
    )
    parser.add_argument(
        "--output-json",
        type=str,
        default="docs/openapi.json",
        help="Path to write the raw OpenAPI JSON spec (default: docs/openapi.json)",
    )
    parser.add_argument(
        "--output-md",
        type=str,
        default="docs/API-REFERENCE.md",
        help="Path to write the Markdown API reference (default: docs/API-REFERENCE.md)",
    )

    args = parser.parse_args()

    spec = get_openapi_spec()
    if spec is None:
        print("ERROR: Could not extract OpenAPI spec from FastAPI app", file=sys.stderr)
        sys.exit(1)

    # Write JSON spec
    json_path = Path(args.output_json)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(spec, indent=2) + "\n")
    print(f"OpenAPI JSON written to {json_path}", file=sys.stderr)

    # Generate and write Markdown reference
    markdown, endpoint_count = generate_markdown_reference(spec)
    md_path = Path(args.output_md)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(markdown)
    print(f"API reference written to {md_path}", file=sys.stderr)

    print(f"ENDPOINT_COUNT={endpoint_count}")

if __name__ == "__main__":
    main()
