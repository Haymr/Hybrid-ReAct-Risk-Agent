from fastapi import APIRouter, HTTPException
import json
from pydantic import BaseModel
from langchain_core.messages import HumanMessage
from agent.graph import app as agent_app

router = APIRouter()

class ChatRequest(BaseModel):
    user_id: str
    message: str

class ChatResponse(BaseModel):
    response: str
    thought_process: list[dict] = []
    tool_used: str | None = None
    risk_level: str | None = None

@router.post("/chat", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest):
    print(request.user_id)
    """
    Receives user message and passes it to the LangGraph agent.
    Returns the agent's final decision and thought steps, optimized for n8n Webhooks.
    """
    config = {"configurable": {"thread_id": request.user_id}, "recursion_limit": 5}
    
    def invoke_agent():
        steps = []
        # LLM max_retries will automatically handle temporary API timeouts.
        for event in agent_app.stream(
            {"messages": [HumanMessage(content=request.message)]},
            config,
            stream_mode="values"
        ):
            steps.append(event)
        return steps
        
    try:
        # Get the agent steps (now running in FastAPI's background threadpool)
        events = invoke_agent()
        
        thought_process = []
        final_message = ""
        tool_used = None
        risk_level = None
        
        for event in events:
            # Safely get the last message
            last_msg = event["messages"][-1]
            
            # Extract meaningful text safely
            if hasattr(last_msg, "content") and last_msg.content:
                final_message = last_msg.content
                
            # Record thought process metadata (simplistic extract)
            step_info = {
                "type": last_msg.__class__.__name__,
                "content": last_msg.content
            }
            
            # Detect tool call requested by agent
            if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                step_info["tool_calls"] = last_msg.tool_calls
                tool_used = last_msg.tool_calls[0]["name"]
                
            # Parse tool output to expose critical variables directly to n8n
            if last_msg.__class__.__name__ == "ToolMessage":
                try:
                    tool_data = json.loads(last_msg.content)
                    if isinstance(tool_data, dict) and "risk_level" in tool_data:
                        risk_level = tool_data["risk_level"]
                except:
                    pass
                
            thought_process.append(step_info)
            
        return ChatResponse(
            response=final_message,
            thought_process=thought_process,
            tool_used=tool_used,
            risk_level=risk_level
        )
        
    except Exception as e:
        # Handle recursion limit or other errors gracefully
        raise HTTPException(status_code=500, detail=str(e))
