"""
Open WebUI <-> Synthetic web search adapter.

Open WebUI's "External" web search engine POSTs {"query", "count"} and expects
a top-level JSON array of {"link", "title", "snippet"}.

Synthetic's /v2/search returns {"results": [{"url", "title", "text", "published"}]}.

This proxy translates between the two.
"""

import logging
import os
from typing import List, Optional

import httpx
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
log = logging.getLogger("search-proxy")

# --- config (env) -----------------------------------------------------------
SYNTHETIC_API_KEY = os.environ.get("SYNTHETIC_API_KEY", "")
SYNTHETIC_URL = os.environ.get(
    "SYNTHETIC_URL", "https://api.synthetic.new/v2/search"
)
# Bearer token Open WebUI must send (set as "External Web Search API Key").
# Leave empty to disable inbound auth.
PROXY_KEY = os.environ.get("PROXY_KEY", "")
REQUEST_TIMEOUT = float(os.environ.get("REQUEST_TIMEOUT", "20"))
# Synthetic returns full page text in `text`; forwarding it whole bloats the
# search response (~1MB), which overflows the model request in agentic mode.
# Truncate each snippet; the model can fetch_url for full content. 0 = no limit.
SNIPPET_MAX_CHARS = int(os.environ.get("SNIPPET_MAX_CHARS", "2000"))

if not SYNTHETIC_API_KEY:
    log.warning("SYNTHETIC_API_KEY is not set; upstream calls will fail (401).")

app = FastAPI(title="open-webui-search-proxy", version="1.0.0")
client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT)


class SearchRequest(BaseModel):
    query: str
    count: int = 5


class SearchResult(BaseModel):
    link: str
    title: str
    snippet: str


@app.get("/health")
async def health():
    return {"status": "ok", "upstream": SYNTHETIC_URL}


@app.post("/search", response_model=List[SearchResult])
async def search(
    body: SearchRequest,
    authorization: Optional[str] = Header(default=None),
) -> List[SearchResult]:
    # Validate the inbound key Open WebUI sends, if configured.
    if PROXY_KEY and authorization != f"Bearer {PROXY_KEY}":
        raise HTTPException(status_code=401, detail="unauthorized")

    try:
        resp = await client.post(
            SYNTHETIC_URL,
            headers={"Authorization": f"Bearer {SYNTHETIC_API_KEY}"},
            json={"query": body.query},
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        log.error("upstream error %s: %s", e.response.status_code, e.response.text)
        raise HTTPException(status_code=502, detail="upstream search failed")
    except httpx.HTTPError as e:
        log.error("upstream request failed: %s", e)
        raise HTTPException(status_code=502, detail="upstream search failed")

    results = resp.json().get("results", [])

    out: List[SearchResult] = []
    for item in results[: body.count]:
        url = item.get("url")
        if not url:
            continue
        snippet = item.get("text") or ""
        if SNIPPET_MAX_CHARS > 0:
            snippet = snippet[:SNIPPET_MAX_CHARS]
        out.append(
            SearchResult(
                link=url,
                title=item.get("title") or url,
                snippet=snippet,
            )
        )

    log.info("query=%r -> %d results", body.query, len(out))
    return out


@app.on_event("shutdown")
async def _shutdown():
    await client.aclose()
