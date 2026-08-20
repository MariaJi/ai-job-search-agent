import os
import requests


def search_jooble_jobs(
    keywords: str,
    location: str,
    results_per_page: int = 5
) -> dict:
    api_key = os.getenv("JOOBLE_API_KEY")

    if not api_key:
        raise ValueError("JOOBLE_API_KEY is not configured.")

    url = f"https://jooble.org/api/{api_key}"

    payload = {
        "keywords": keywords,
        "location": location,
        "ResultOnPage": results_per_page
    }

    response = requests.post(
        url,
        json=payload,
        timeout=15
    )

    response.raise_for_status()

    return response.json()