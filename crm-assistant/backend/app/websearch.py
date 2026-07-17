"""Optional external web search.

If WEB_SEARCH_PROVIDER + credentials are configured, performs a real web search.
Otherwise returns None so the caller can fall back to the LLM's general knowledge
(clearly labeled as external / unverified).
"""
import json
import urllib.request
from . import config


def search(query, max_results=5):
    provider = config.WEB_SEARCH_PROVIDER
    try:
        if provider == "tavily" and config.TAVILY_API_KEY:
            return _tavily(query, max_results)
    except Exception as e:
        return {"text": f"(web search error: {e})", "results": [], "provider": provider}
    return None  # no provider configured -> caller uses LLM general knowledge


def _tavily(query, max_results):
    body = json.dumps({
        "api_key": config.TAVILY_API_KEY,
        "query": query,
        "max_results": max_results,
        "search_depth": "basic",
        "include_answer": True,
    }).encode()
    req = urllib.request.Request(
        "https://api.tavily.com/search", data=body,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.load(r)
    results = [{"title": x.get("title", ""), "url": x.get("url", ""),
                "content": x.get("content", "")} for x in data.get("results", [])]
    lines = []
    if data.get("answer"):
        lines.append("Summary: " + data["answer"])
    for x in results:
        lines.append(f"- {x['title']} ({x['url']}): {x['content'][:300]}")
    return {
        "text": "\n".join(lines),
        "results": [{"title": x["title"], "url": x["url"]} for x in results],
        "provider": "tavily",
    }
