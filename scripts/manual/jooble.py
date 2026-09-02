"""Live Jooble diagnostic, executed only when explicitly invoked."""


def main():
    import argparse
    import json
    from dotenv import load_dotenv
    from app.tools.job_search import search_jooble_jobs

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keywords", required=True)
    parser.add_argument("--location", default="Remote")
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()
    load_dotenv()
    result = search_jooble_jobs(
        keywords=args.keywords,
        location=args.location,
        results_per_page=args.limit,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
