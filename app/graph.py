from langgraph.graph import StateGraph, START, END
from app.state import JobSearchState
from langgraph.types import Send

from app.nodes import (
    understand_search_request,
    search_jobs,
    analyze_job,
)

def fan_out_jobs(state: JobSearchState):
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

builder = StateGraph(JobSearchState)

# Nodes

builder.add_node("understand_search_request", understand_search_request)
builder.add_node("search_jobs", search_jobs)
builder.add_node("analyze_job", analyze_job)
# Edges
builder.add_edge(START, "understand_search_request")
builder.add_edge("understand_search_request", "search_jobs")

builder.add_conditional_edges(
    "search_jobs",        # FROM this node
    fan_out_jobs,         # function decides where/how to go
    ["analyze_job"]       # possible destination node(s)
)
builder.add_edge("analyze_job", END)

# Compile the LangGraph
graph = builder.compile()