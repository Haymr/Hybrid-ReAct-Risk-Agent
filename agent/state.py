from typing import Annotated, TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage

class AgentState(TypedDict):
    """
    This file holds the entire state of the agent. It is the backbone of LangGraph.
    """
    # Custom operator that appends messages to the list rather than overwriting them
    messages: Annotated[list[AnyMessage], add_messages]
