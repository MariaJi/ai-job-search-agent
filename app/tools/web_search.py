import os
import requests
from tavily import TavilyClient
from urllib.parse import urlparse
import json
from bs4 import BeautifulSoup

def search_original_job(title: str, company: str) -> list[dict]:
    api_key = os.getenv("TAVILY_API_KEY")
    max_results = int(
    os.getenv("TAVILY_MAX_RESULTS", "5")
    )
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
        max_results=max_results,
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

def extract_job_description_Old(url: str) -> str:
    api_key = os.getenv("TAVILY_API_KEY")

    if not api_key:
        raise ValueError("TAVILY_API_KEY is not configured.")

    client = TavilyClient(api_key=api_key)

    response = client.extract(
        urls=[url]
    )

    results = response.get("results", [])

    if not results:
        return ""

    return results[0].get("raw_content", "")



def extract_job_description(url: str) -> dict:
    api_key = os.getenv("TAVILY_API_KEY")

    if not api_key:
        raise ValueError("TAVILY_API_KEY is not configured.")

    client = TavilyClient(api_key=api_key)

    # 1. Try Tavily extraction first
    response = client.extract(
        urls=[url]
    )

    results = response.get("results", [])

    if results:
        content = results[0].get("raw_content", "")

        if content.strip():
            return {
                "status": "success",
                "content": content.strip(),
                "source": "tavily_extract",
            }

    # 2. Tavily failed: try direct HTTP
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/120.0 Safari/537.36"
            )
        }

        response = requests.get(
            url,
            headers=headers,
            timeout=15,
        )

        response.raise_for_status()

        html = response.text

        if html.strip():
            clean_description = parse_job_description(html)

            if clean_description:
                return {
                    "status": "success",
                    "content": clean_description,
                    "source": "direct_http",
                }

    except requests.RequestException as exc:
        return {
            "status": "failed",
            "content": "",
            "source": "direct_http",
            "error": str(exc),
        }

    return {
        "status": "failed",
        "content": "",
        "source": "direct_http",
        "error": "No usable job description found",
    }




def parse_job_description(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    for script in soup.find_all(
        "script",
        type="application/ld+json",
    ):
        try:
            data = json.loads(script.string)

            if data.get("@type") == "JobPosting":
                description_html = data.get(
                    "description",
                    ""
                )

                description_soup = BeautifulSoup(
                    description_html,
                    "html.parser",
                )

                return description_soup.get_text(
                    separator="\n",
                    strip=True,
                )

        except (json.JSONDecodeError, AttributeError):
            continue

    return ""