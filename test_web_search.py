from dotenv import load_dotenv

from app.tools.web_search import search_original_job


load_dotenv()


results = search_original_job(
    title="AI-focused Senior Software Engineer",
    company="Tight",
)

for result in results:
    print("\nTITLE:", result["title"])
    print("URL:", result["url"])
    print("CONTENT:", result["content"])