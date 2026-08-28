

from dotenv import load_dotenv

load_dotenv()
from app.nodes import send_verified_jobs_for_analysis
def test_send_verified_jobs_for_analysis():

    state = {
        "verified_jobs": [
            {
                "title": "Job A",
                "verification_status": "verified",
            },
            {
                "title": "Job B",
                "verification_status": "failed",
            },
            {
                "title": "Job C",
                "verification_status": "verified",
            },
        ]
    }

    sends = send_verified_jobs_for_analysis(state)

    assert len(sends) == 2
if __name__ == "__main__":
    test_send_verified_jobs_for_analysis()
    print("Test passed!")