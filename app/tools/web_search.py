import os
import requests
from tavily import TavilyClient
from urllib.parse import urlparse
import json
from bs4 import BeautifulSoup
from app.live_config import tavily_max_results

def search_original_job(title: str, company: str) -> list[dict]:
    api_key = os.getenv("TAVILY_API_KEY")
    max_results = tavily_max_results()
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
        include_raw_content=True,
    )

    print(f"Verification search: completed returned={len(response.get('results', []))} "
          f"considered={len(response.get('results', [])[:max_results])}")
    results = []

    for item in response.get("results", [])[:max_results]:
        results.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "content": item.get("content", ""),
            "raw_content": item.get("raw_content") or "",
        })

    return results


def search_job_on_source(
    title: str,
    company: str,
    source_url: str
) -> list[dict]:

    max_results = tavily_max_results()
    api_key = os.getenv("TAVILY_API_KEY")

    if not api_key:
        raise ValueError("TAVILY_API_KEY is not configured.")

    client = TavilyClient(api_key=api_key)

    domain = urlparse(source_url).netloc

    query = f'{title} {company} site:{domain}'

    response = client.search(
        query=query,
        search_depth="advanced",
        max_results=max_results,
    )

    results = []

    source_prefix = source_url.rstrip("/") + "/"

    for item in response.get("results", [])[:max_results]:
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

def extract_job_description(url: str) -> dict:
    api_key = os.getenv("TAVILY_API_KEY")

    # 1. Try Tavily extraction first
    tavily_error = None
    try:
        if not api_key:
            raise ValueError("TAVILY_API_KEY is not configured.")
        client = TavilyClient(api_key=api_key)
        response = client.extract(urls=[url])
        results = response.get("results", [])
    except Exception as exc:
        tavily_error = str(exc)
        print(f"Verification extraction: stage=tavily_extract outcome=error class={type(exc).__name__}")
        results = []

    if results:
        content = results[0].get("raw_content", "")

        if content.strip():
            print(f"Verification extraction: stage=tavily_extract outcome=success usable=True characters={len(content.strip())}")
            print("Verification extraction: stage=direct_http fallback_attempted=False")
            return {
                "status": "success",
                "content": content.strip(),
                "source": "tavily_extract",
            }

    # 2. Tavily failed: try direct HTTP
    if tavily_error is None:
        print("Verification extraction: stage=tavily_extract outcome=empty usable=False characters=0")
    return extract_job_description_http(url, tavily_error=tavily_error)


def extract_job_description_http(url: str, tavily_error: str | None = None) -> dict:
    """Retrieve the existing JSON-LD fallback without repeating Tavily extraction."""
    print("Verification extraction: stage=direct_http fallback_attempted=True")
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

        status = getattr(response, "status_code", None)
        print(f"Verification extraction: stage=direct_http http_status={status if type(status) is int else 'unknown'}")
        response.raise_for_status()

        html = response.text

        if html.strip():
            evidence = parse_job_posting(html)
            clean_description = evidence.get("content", "")

            if clean_description:
                print(f"Verification extraction: stage=direct_http outcome=success usable=True characters={len(clean_description)}")
                return {
                    "status": "success",
                    "content": clean_description,
                    "source": "direct_http",
                    "structured_metadata": evidence["structured_metadata"],
                }

    except requests.RequestException as exc:
        print(f"Verification extraction: stage=direct_http outcome=error class={type(exc).__name__} usable=False characters=0")
        return {
            "status": "failed",
            "content": "",
            "source": "direct_http",
            "error": str(exc),
            "tavily_error": tavily_error,
        }

    print("Verification extraction: stage=direct_http outcome=empty usable=False characters=0")
    return {
        "status": "failed",
        "content": "",
        "source": "direct_http",
        "error": "No usable job description found",
        "tavily_error": tavily_error,
    }




def parse_job_description(html: str) -> str:
    return parse_job_posting(html).get("content", "")


def parse_job_posting(html: str) -> dict:
    """Keep metadata bound to the exact posting whose description was selected."""
    soup = BeautifulSoup(html, "html.parser")

    def find_description(data) -> dict:
        if isinstance(data, dict):
            types = data.get("@type")
            if types == "JobPosting" or (
                isinstance(types, list) and "JobPosting" in types
            ):
                description = data.get("description")
                if isinstance(description, str) and description.strip():
                    text = BeautifulSoup(description, "html.parser").get_text(
                        separator="\n", strip=True
                    )
                    if text:
                        return {
                            "content": text,
                            "structured_metadata": {
                                key: data[key] for key in (
                                    "datePosted", "jobLocation", "jobLocationType",
                                    "applicantLocationRequirements", "employmentType",
                                ) if key in data
                            },
                        }
            children = data.values()
        elif isinstance(data, list):
            children = data
        else:
            return {}

        for child in children:
            description = find_description(child)
            if description:
                return description
        return {}

    for script in soup.find_all(
        "script",
        type="application/ld+json",
    ):
        try:
            data = json.loads(script.string)

        except (json.JSONDecodeError, TypeError):
            continue

        description = find_description(data)
        if description:
            return description

    return {}
