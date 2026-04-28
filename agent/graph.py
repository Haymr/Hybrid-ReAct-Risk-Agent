from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import trim_messages
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
import os
from .state import AgentState
from tools.inventory import tools_list
import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver
import tiktoken

def get_llm():
    """
    Selects the LLM based on the LLM_PROVIDER environment variable.
    Defaults to 'openai' if not specified.
    """
    provider = os.getenv("LLM_PROVIDER", "openai").lower()
    print(f"LLM PROVIDER: {provider}")
    
    if provider == "gemini":
        if not os.getenv("GEMINI_API_KEY"):
            raise ValueError("GEMINI_API_KEY is not set in .env")
        return ChatGoogleGenerativeAI(model="gemini-3.1-flash-lite-preview", temperature=0, max_retries=3)
    else:
        if not os.getenv("OPENAI_API_KEY"):
            raise ValueError("OPENAI_API_KEY is not set in .env")
        return ChatOpenAI(model="gpt-4o-mini", temperature=0, max_retries=3)

# Initialize the selected LLM
llm = get_llm()

# Bind our tools to the LLM
llm_with_tools = llm.bind_tools(tools_list)

# System Prompt with strict guardrails
SYSTEM_PROMPT = """
You are a highly capable AI Supply Chain and Inventory Risk Consultant powered by a Machine Learning Demand Forecasting Model.
Your main purpose is to analyze inventory risks and supply chain metrics using dynamic ML predictions, and then offer actionable advice.

You MUST use the 'calculate_inventory_risk' tool to fetch predicted 30-day demand and stock data when the user asks about specific products.

Core Guidelines:
1. Always maintain a conversational, helpful, and professional consultant tone. Remember previous context and references.
2. Provide strategic advice based on the ML Model's predicted 30-day demand compared against the current stock.
3. If the user asks about general knowledge, politely decline.
4. DO NOT invent product data. If the user provides an incomplete name or asks for options (e.g. 'kurta' or 'JNE'), DO NOT say you can't browse. Instead, use the 'search_products' tool to find available options.
5. Emphasize any "High" or "Critical" risk items and suggest immediate actions like reordering.
"""

# Create prompt template
prompt_template = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    MessagesPlaceholder(variable_name="messages"),
])

# Chain the prompt template with our tools-bound LLM
agent_runnable = prompt_template | llm_with_tools

def count_tokens_local(messages) -> int:
    """
    Local tiktoken proxy counter. 
    Eger token_counter=llm yaparsak, Gemini/OpenAI'a HTTP istegi atip sunucuyu (503) rate limit sokar.
    Tiktoken ile sifir api cagrisiyla %97+ dogrulukla sayim yapar.
    """
    try:
        encoding = tiktoken.get_encoding("cl100k_base")
    except:
        encoding = tiktoken.encoding_for_model("gpt-4")
        
    total = 0
    for m in messages:
        content = str(m.content) if hasattr(m, "content") else str(m)
        total += len(encoding.encode(content))
    return total

# Initialize the message trimmer to prevent token/context bloat
trimmer = trim_messages(
    max_tokens=4000,
    strategy="last",
    token_counter=count_tokens_local,
    allow_partial=False
)

def agent_node(state: AgentState):
    """
    LLM decision-making node.
    It trims the conversation history to max 4000 tokens, 
    formats them through the prompt template, calls the LLM, 
    and appends the LLM's response.
    """
    trimmed_history = trimmer.invoke(state["messages"])
    response = agent_runnable.invoke({"messages": trimmed_history})
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
import os
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "database", "agent_state.db")

# Veritabanina baglan
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
conn.execute("PRAGMA journal_mode=WAL;")
conn.execute("PRAGMA synchronous=NORMAL;")
memory = SqliteSaver(conn)

# Compile the graph
app = workflow.compile(checkpointer=memory)
