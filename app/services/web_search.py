from __future__ import annotations

import asyncio
from typing import List, Dict, Any
from ddgs import DDGS # Changed from duckduckgo_search import DDGS

async def search_google(query: str, num_results: int = 5) -> List[Dict[str, Any]]:
    """Performs a Google search and returns the results.
    This is a placeholder. In a real scenario, this would integrate with a Google Search API.
    """
    print(f"Simulating Google search for: {query}")
    # For now, return an empty list or mock data
    return []

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
        if res.get('href') not in seen_urls: # Changed from res.get('url')
            unique_results.append({
                "title": res.get("title", "No Title"),
                "url": res.get("href", "No URL"), # Changed from res.get('url')
                "snippet": res.get("body", "No Snippet"), # Changed from res.get('snippet')
            })
            seen_urls.add(res.get('href')) # Changed from res.get('url')

    return unique_results