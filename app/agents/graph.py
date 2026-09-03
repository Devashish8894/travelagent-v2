from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from app.agents.state import AgentState
from app.agents.nodes import retrieve_context_node,execution_node

builder = StateGraph(AgentState)
builder.add_node("retrive_context", retrieve_context_node)
builder.add_node("execution_plan",execution_node)

builder.set_entry_point("retrive_context")
builder.add_edge("retrive_context","execution_plan")
builder.add_edge("execution_plan",END)

memory = MemorySaver()

agent_app = builder.compile(checkpointer=memory)