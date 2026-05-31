from langgraph.graph import END, START, StateGraph

from graph.nodes.condense_query import condense_query
from graph.nodes.generate_answer import generate_answer
from graph.nodes.load_memory import load_memory
from graph.nodes.retrieve_context import retrieve_context
from graph.nodes.self_ingest import self_ingest
from graph.nodes.store_memory import store_memory
from graph.nodes.summarize import summarize
from graph.nodes.verify_answer import verify_answer
from graph.state import State


def build_graph():
    graph = StateGraph(State)

    graph.add_node("load_memory", load_memory)
    graph.add_node("condense_query", condense_query)
    graph.add_node("retrieve_context", retrieve_context)
    graph.add_node("generate_answer", generate_answer)
    graph.add_node("verify_answer", verify_answer)
    graph.add_node("self_ingest", self_ingest)
    graph.add_node("store_memory", store_memory)
    graph.add_node("summarize", summarize)

    graph.add_edge(START, "load_memory")
    graph.add_edge("load_memory", "condense_query")
    graph.add_edge("condense_query", "retrieve_context")
    graph.add_edge("retrieve_context", "generate_answer")
    graph.add_edge("generate_answer", "verify_answer")
    graph.add_edge("verify_answer", "self_ingest")
    graph.add_edge("self_ingest", "summarize")
    graph.add_edge("summarize", "store_memory")
    graph.add_edge("store_memory", END)

    return graph.compile()
