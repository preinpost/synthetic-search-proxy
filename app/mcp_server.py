"""
MCP server exposing Synthetic web search as a `web_search` tool.

This brings web search back to LLM clients (e.g. Claude Code on a Synthetic /
third-party backend) where the built-in WebSearch tool is unavailable, since
that tool is hardcoded to Anthropic's server-side web_search_* and can't point
at a different backend. MCP tools are client-side, so they work regardless of
which model backend is in use.

Run modes (set MCP_TRANSPORT):
  - stdio (default): each user runs it locally with their own SYNTHETIC_API_KEY
  - http:            streamable-HTTP server (MCP_HOST / MCP_PORT)
"""

import os

import httpx
from mcp.server.fastmcp import FastMCP

SYNTHETIC_API_KEY = os.environ.get("SYNTHETIC_API_KEY", "")
SYNTHETIC_URL = os.environ.get("SYNTHETIC_URL", "https://api.synthetic.new/v2/search")
SNIPPET_MAX_CHARS = int(os.environ.get("SNIPPET_MAX_CHARS", "2000"))
REQUEST_TIMEOUT = float(os.environ.get("REQUEST_TIMEOUT", "20"))

mcp = FastMCP(
    "synthetic-search",
    host=os.environ.get("MCP_HOST", "0.0.0.0"),
    port=int(os.environ.get("MCP_PORT", "9000")),
)


@mcp.tool()
async def web_search(query: str, max_results: int = 5) -> str:
    """Search the web for current information and return ranked results.

    Use this when you need up-to-date facts, documentation, news, versions, or
    anything beyond your training data. Returns each result's title, URL, and a
    text snippet. Follow up with a fetch of a URL if you need the full page.

    Args:
        query: The search query.
        max_results: Max results to return (Synthetic caps at ~5).
    """
    if not SYNTHETIC_API_KEY:
        return "Error: SYNTHETIC_API_KEY is not set on the MCP server."

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.post(
                SYNTHETIC_URL,
                headers={"Authorization": f"Bearer {SYNTHETIC_API_KEY}"},
                json={"query": query},
            )
            resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        return f"Search failed: upstream {e.response.status_code}"
    except httpx.HTTPError as e:
        return f"Search failed: {e}"

    results = resp.json().get("results", [])[:max_results]
    if not results:
        return f"No results for: {query}"

    blocks = []
    for i, item in enumerate(results, 1):
        url = item.get("url") or ""
        title = item.get("title") or url
        text = item.get("text") or ""
        if SNIPPET_MAX_CHARS > 0:
            text = text[:SNIPPET_MAX_CHARS]
        blocks.append(f"## {i}. {title}\n{url}\n\n{text}")

    return "\n\n---\n\n".join(blocks)


def main() -> None:
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    mcp.run(transport="streamable-http" if transport == "http" else "stdio")


if __name__ == "__main__":
    main()
