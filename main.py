
from dotenv import load_dotenv
from app.state import build_initial_state


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

