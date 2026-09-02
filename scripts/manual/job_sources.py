"""Live Tavily/OpenAI source, extraction, and verification diagnostics."""


def main():
    import argparse
    import json
    from dotenv import load_dotenv
    from app.nodes import rank_job_sources, select_exact_job_posting, verify_job
    from app.tools.web_search import (
        extract_job_description,
        search_job_on_source,
        search_original_job,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--title", required=True)
    parser.add_argument("--company", required=True)
    parser.add_argument("--location", default="Remote")
    parser.add_argument("--snippet", default="")
    parser.add_argument("--url", default="", help="Original job URL, if known")
    parser.add_argument(
        "--source-url",
        help="Optional company job-board root for source-specific searching",
    )
    parser.add_argument(
        "--verify", action="store_true",
        help="Run verify_job instead of the individual source diagnostic steps",
    )
    args = parser.parse_args()
    load_dotenv()
    job = {
        "title": args.title,
        "company": args.company,
        "location": args.location,
        "description": args.snippet,
        "description_source": "manual_snippet",
        "description_complete": False,
        "source": "manual",
        "url": args.url,
        "source_url": args.url,
        "updated_date": "",
    }

    if args.verify:
        print(json.dumps(verify_job({"current_job": job}), indent=2))
        return

    results = search_original_job(title=args.title, company=args.company)
    print("SEARCH RESULTS:", json.dumps(results, indent=2))
    ranked = rank_job_sources(job=job, search_results=results)
    print("RANKED SOURCES:", json.dumps(ranked, indent=2))
    source = ranked[0] if ranked else None

    if args.source_url:
        source_results = search_job_on_source(
            title=args.title, company=args.company, source_url=args.source_url,
        )
        print("SOURCE-SPECIFIC RESULTS:", json.dumps(source_results, indent=2))
        source = select_exact_job_posting(job=job, search_results=source_results)
        print("EXACT POSTING:", json.dumps(source, indent=2))

    if source:
        print("EXTRACTION:", json.dumps(extract_job_description(source["url"]), indent=2))
    else:
        print("No matching source found; extraction skipped.")


if __name__ == "__main__":
    main()
