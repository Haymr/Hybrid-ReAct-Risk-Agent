from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import trim_messages
from langchain_openai import ChatOpenAI
import os
from .state import AgentState
from tools.inventory import tools_list
import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver

# Initialize the LLM (Ensure OPENAI_API_KEY is in .env)
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# Bind our tools to the LLM
llm_with_tools = llm.bind_tools(tools_list)

# System Prompt with strict guardrails
SYSTEM_PROMPT = """
You are a supply chain and inventory risk analysis assistant.
Your ONLY purpose is to analyze inventory risks, stock levels, and supply chain metrics.
You MUST use the 'calculate_inventory_risk' tool when asked about specific products.

Strict Rules:
1. DO NOT answer general knowledge questions (e.g., weather, history, coding).
2. If the user asks something unrelated to inventory or supply chain, politely decline.
3. DO NOT invent product data. If you don't know the exact product name to use the tool, ask the user.
4. Keep your answers concise and professional.
"""

# Create prompt template
prompt_template = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    MessagesPlaceholder(variable_name="messages"),
])

# Chain the prompt template with our tools-bound LLM
agent_runnable = prompt_template | llm_with_tools

# Initialize the message trimmer to prevent token/context bloat
trimmer = trim_messages(
    max_tokens=4000,
    strategy="last",
    token_counter=llm,
    allow_partial=False
)

async def agent_node(state: AgentState):
    """
    LLM decision-making node.
    It trims the conversation history to max 4000 tokens, 
    formats them through the prompt template, calls the LLM, 
    and appends the LLM's response.
    """
    trimmed_history = trimmer.invoke(state["messages"])
    response = await agent_runnable.ainvoke({"messages": trimmed_history})
    return {"messages": [response]}


def should_continue(state: AgentState) -> str:
    """
    Conditional edge function to determine if we should call a tool or end the cycle.
    """
    last_message = state["messages"][-1]
    # If the LLM made a tool call, route to the 'tools' node
    if last_message.tool_calls:
        return "tools"
    # Otherwise, stop
    return END

# Build the Graph
workflow = StateGraph(AgentState)

# Add nodes
workflow.add_node("agent", agent_node)
workflow.add_node("tools", ToolNode(tools_list))

# Add Edges
workflow.add_edge(START, "agent")
workflow.add_conditional_edges("agent", should_continue, ["tools", END])
workflow.add_edge("tools", "agent")

# Initialize Sqlite Checkpointer for true persistence
conn = sqlite3.connect("database/agent_state.db", check_same_thread=False)
conn.execute("PRAGMA journal_mode=WAL;")
conn.execute("PRAGMA synchronous=NORMAL;")
memory = SqliteSaver(conn)

# Compile the graph
app = workflow.compile(checkpointer=memory)
