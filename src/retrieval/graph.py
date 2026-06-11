from langgraph.graph import StateGraph, END
from src.retrieval.state import GraphState
from src.retrieval.nodes import route_query, retrieve, grade_documents, generate, rewrite, generate_cached

def decide_route(state):
    if state["route"] in ["greeting", "faq"]:
        return "generate_cached"
    return "retrieve"

def decide_grade(state):
    # To prevent infinite loops in our basic setup, we route to generate even if it fails, 
    # letting the LLM safely say "I don't know" based on the context.
    return "generate"

workflow = StateGraph(GraphState)

workflow.add_node("route_query", route_query)
workflow.add_node("retrieve", retrieve)
workflow.add_node("grade_documents", grade_documents)
workflow.add_node("generate", generate)
workflow.add_node("rewrite", rewrite)
workflow.add_node("generate_cached", generate_cached)

workflow.set_entry_point("route_query")
workflow.add_conditional_edges("route_query", decide_route, {"generate_cached": "generate_cached", "retrieve": "retrieve"})
workflow.add_edge("generate_cached", END)

workflow.add_edge("retrieve", "grade_documents")
workflow.add_conditional_edges("grade_documents", decide_grade, {"generate": "generate", "rewrite": "rewrite"})

workflow.add_edge("rewrite", "retrieve")
workflow.add_edge("generate", END)

crag_app = workflow.compile()
