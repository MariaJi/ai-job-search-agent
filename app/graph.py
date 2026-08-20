from langgraph.graph import StateGraph, START, END

from app.state import JobSearchState

from app.nodes import (
    understand_search_request,
    search_jobs,
    analyze_job,
)

builder = StateGraph(JobSearchState)

# Nodes

builder.add_node("understand_search_request", understand_search_request)
builder.add_node("search_jobs", search_jobs)
builder.add_node("analyze_job", analyze_job)
# Edges
builder.add_edge(START, "understand_search_request")
builder.add_edge("understand_search_request", "search_jobs")
builder.add_edge("search_jobs", "analyze_job")
builder.add_edge("analyze_job", END)

# Compile the LangGraph
graph = builder.compile()