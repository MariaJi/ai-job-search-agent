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
)

def fan_out_jobs_Old(state: JobSearchState):
    return [
        Send(
            "analyze_job",
            {
                "current_job": job,
                "analyses": []
            }
        )
        for job in state["jobs"]
    ]

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
builder.add_node(
    "extract_candidate_profile",
    extract_candidate_profile
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

builder.add_edge("rank_jobs", "select_jobs")
builder.add_edge("select_jobs", "generate_report")
builder.add_edge("generate_report", END)

# Compile the LangGraph
graph = builder.compile()