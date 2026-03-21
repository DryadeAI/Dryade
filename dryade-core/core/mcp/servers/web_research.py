"""MCP server: WebSearch + WebFetch — free, zero external dependencies.

Uses DuckDuckGo HTML search + httpx for fetching. No API key needed.
"""

import html as html_mod
import json
import re
import urllib.parse

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

server = Server("web-research")

@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="web_search",
            description="Search the web via DuckDuckGo. Returns titles, URLs, snippets.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "max_results": {"type": "integer", "description": "Max results (default 5)", "default": 5},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="web_fetch",
            description="Fetch a web page and extract text content.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to fetch"},
                    "max_length": {"type": "integer", "description": "Max chars (default 10000)", "default": 10000},
                },
                "required": ["url"],
            },
        ),
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "web_search":
        results = _search(arguments.get("query", ""), arguments.get("max_results", 5))
        return [TextContent(type="text", text=json.dumps(results, ensure_ascii=False, indent=2))]
    elif name == "web_fetch":
        text = _fetch(arguments.get("url", ""), arguments.get("max_length", 10000))
        return [TextContent(type="text", text=text)]
    raise ValueError(f"Unknown tool: {name}")

def _search(query: str, max_results: int = 5) -> list[dict[str, str]]:
    try:
        r = httpx.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": "Mozilla/5.0 (compatible; Dryade/1.0)"},
            timeout=15,
            follow_redirects=True,
        )
        r.raise_for_status()
        results = []
        blocks = re.findall(
            r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?'
            r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
            r.text, re.DOTALL,
        )
        for url, title, snippet in blocks[:max_results]:
            title = re.sub(r"<[^>]+>", "", html_mod.unescape(title)).strip()
            snippet = re.sub(r"<[^>]+>", "", html_mod.unescape(snippet)).strip()
            if "uddg=" in url:
                parsed = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
                url = parsed.get("uddg", [url])[0]
            results.append({"title": title, "url": url, "snippet": snippet})
        return results or [{"title": "No results", "url": "", "snippet": f"No results for: {query}"}]
    except Exception as e:
        return [{"error": f"Search failed: {e}"}]

def _fetch(url: str, max_length: int = 10000) -> str:
    try:
        r = httpx.get(url, timeout=30, follow_redirects=True,
                       headers={"User-Agent": "Dryade/1.0 (web-research-mcp)"})
        r.raise_for_status()
        if "json" in r.headers.get("content-type", ""):
            return r.text[:max_length]
        text = r.text
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        text = html_mod.unescape(text)
        return text[:max_length]
    except Exception as e:
        return f"Fetch failed: {e}"

async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
