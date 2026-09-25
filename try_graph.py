"""Learning entry point for the graph without report persistence."""

from qa_agent.graph import graph

if __name__ == "__main__":
    final_state = graph.invoke({})
    print(final_state["report"])
