from langgraph.graph import StateGraph, START, END
from app.state import JobSearchState
from langgraph.types import Send


from app.nodes import (
    understand_search_request,
    extract_candidate_profile,
    search_jobs,
    analyze_job,
    rank_jobs,
    select_jobs,
    generate_report,
    select_verification_candidates,
    verify_job,
    send_verification_jobs,
    analyze_verified_job,
    send_verified_jobs_for_analysis,
    collect_verified_jobs,
    final_rank_jobs,
    collect_verified_analyses,
)



def fan_out_jobs(state: JobSearchState):
    return [
        Send(
            "analyze_job",
            {
                "current_job": job,
                "candidate_profile": state["candidate_profile"],
                "analyses": []
            }
        )
        for job in state["jobs"]
    ]

builder = StateGraph(JobSearchState)

# Nodes

builder.add_node("understand_search_request", understand_search_request)
builder.add_node("search_jobs", search_jobs)
builder.add_node("analyze_job", analyze_job)
builder.add_node("rank_jobs", rank_jobs)
builder.add_node("select_jobs", select_jobs)
builder.add_node("generate_report", generate_report)
builder.add_node("verify_job", verify_job)
builder.add_node(
    "select_verification_candidates",
    select_verification_candidates
)

builder.add_node(
    "collect_verified_analyses",
    collect_verified_analyses
)

builder.add_node(
    "extract_candidate_profile",
    extract_candidate_profile
)

builder.add_node(
    "collect_verified_jobs",
    collect_verified_jobs
)

builder.add_node(
    "analyze_verified_job",
    analyze_verified_job
)

builder.add_node(
    "final_rank_jobs",
    final_rank_jobs
)

# Edges
builder.add_edge(START, "understand_search_request")


builder.add_edge(
    "understand_search_request",
    "extract_candidate_profile"
)

builder.add_edge(
    "extract_candidate_profile",
    "search_jobs"
)

builder.add_conditional_edges(
    "search_jobs",        # FROM this node
    fan_out_jobs,         # function decides where/how to go
    ["analyze_job"]       # possible destination node(s)
)

builder.add_edge("analyze_job", "rank_jobs")


builder.add_edge(
    "rank_jobs",
    "select_verification_candidates"
)


builder.add_conditional_edges(
    "select_verification_candidates",
    send_verification_jobs,
    ["verify_job"],
)
builder.add_edge(
    "verify_job",
    "collect_verified_jobs"
)

builder.add_conditional_edges(
    "collect_verified_jobs",
    send_verified_jobs_for_analysis,
    ["analyze_verified_job"],
)
builder.add_edge(
    "analyze_verified_job",
    "collect_verified_analyses"
)

builder.add_edge(
    "collect_verified_analyses",
    "final_rank_jobs"
)
builder.add_edge(
    "final_rank_jobs",
    "select_jobs"
)

builder.add_edge("select_jobs", "generate_report")
builder.add_edge("generate_report", END)

# Compile the LangGraph
graph = builder.compile()