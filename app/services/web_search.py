
from __future__ import annotations

import asyncio
from typing import List, Dict, Any
from duckduckgo_search import DDGS
from ..config import get_settings

async def search_google(query: str, num_results: int = 5) -> List[Dict[str, Any]]:
    """Performs a Google search and returns the results."""
    # This is a placeholder for the actual google_web_search tool call
    # In a real scenario, you would call the tool here.
    # For now, we'll simulate it with DuckDuckGo search.
    return await search_duckduckgo(query, num_results)

async def search_duckduckgo(query: str, num_results: int = 5) -> List[Dict[str, Any]]:
    """Performs a DuckDuckGo search and returns the results."""
    results = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=num_results):
            results.append(r)
    return results

async def search_web(query: str, num_results: int = 5) -> List[Dict[str, Any]]:
    """Performs a web search using multiple search engines and returns the combined results."""
    google_results_task = search_google(query, num_results)
    duckduckgo_results_task = search_duckduckgo(query, num_results)

    results = await asyncio.gather(
        google_results_task,
        duckduckgo_results_task
    )

    # Flatten and combine results
    combined_results = []
    for res_list in results:
        combined_results.extend(res_list)

    # Deduplicate results based on URL
    unique_results = []
    seen_urls = set()
    for res in combined_results:
        if res.get('href') not in seen_urls:
            unique_results.append({
                "title": res.get("title"),
                "url": res.get("href"),
                "snippet": res.get("body"),
            })
            seen_urls.add(res.get('href'))

    return unique_results

