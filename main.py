
from dotenv import load_dotenv


def build_initial_state(search_request: str, resume_text: str) -> dict:
    return {
        "search_request": search_request,
        "role": "",
        "location": "",
        "employment_type": "",
        "days_old": 7,
        "jobs": [],
        "current_job": None,
        "resume_text": resume_text,
        "candidate_profile": {},
        "analyses": [],
        "ranked_jobs": [],
        "verification_candidates": [],
        "verified_jobs": [],
        "verified_analyses": [],
        "final_ranked_jobs": [],
        "selected_jobs": [],
        "final_report": "",
    }


def main() -> None:
    load_dotenv()

    from app.graph import graph
    from app.tools.resume_reader import read_docx_resume

    resume_text = read_docx_resume("data/resume.docx")
    initial_state = build_initial_state(
        "Find remote Senior AI Engineer jobs from the last 7 days",
        resume_text,
    )
    result = graph.invoke(initial_state)
    print(result["final_report"])


if __name__ == "__main__":
    main()

