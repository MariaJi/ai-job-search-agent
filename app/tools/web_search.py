import os
import requests
from tavily import TavilyClient
from urllib.parse import urlparse

def search_original_job(title: str, company: str) -> list[dict]:
    api_key = os.getenv("TAVILY_API_KEY")

    if not api_key:
        raise ValueError("TAVILY_API_KEY is not configured.")

    client = TavilyClient(api_key=api_key)

    query = (
    f'{title} {company} '
    f'(careers OR jobs OR greenhouse OR lever OR workday OR ashby)'
    )

    response = client.search(
        query=query,
        search_depth="advanced",
        max_results=10,
    )

    results = []

    for item in response.get("results", []):
        results.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "content": item.get("content", ""),
        })

    return results


def search_job_on_source(
    title: str,
    company: str,
    source_url: str
) -> list[dict]:

    api_key = os.getenv("TAVILY_API_KEY")

    if not api_key:
        raise ValueError("TAVILY_API_KEY is not configured.")

    client = TavilyClient(api_key=api_key)

    domain = urlparse(source_url).netloc

    query = f'{title} {company} site:{domain}'

    response = client.search(
        query=query,
        search_depth="advanced",
        max_results=10,
    )

    results = []

    source_prefix = source_url.rstrip("/") + "/"

    for item in response.get("results", []):
        result_url = item.get("url", "")

        # Keep only jobs under this company's job-board path.
        if not result_url.startswith(source_prefix):
            continue

        results.append({
            "title": item.get("title", ""),
            "url": result_url,
            "content": item.get("content", ""),
        })

    return results