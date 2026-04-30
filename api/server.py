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
    requires_alert: bool = False

@router.post("/chat", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest):
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
        requires_alert = False
        
        for event in events:
            # Safely get the last message
            last_msg = event["messages"][-1]
            
            # Extract meaningful text safely
            if hasattr(last_msg, "content") and last_msg.content:
                if isinstance(last_msg.content, list):
                    # Combine text chunks if content is a list of blocks
                    final_message = "".join(
                        chunk.get("text", "") if isinstance(chunk, dict) else str(chunk) 
                        for chunk in last_msg.content
                    )
                else:
                    final_message = str(last_msg.content)
                
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
                        requires_alert = risk_level in ["High", "Critical"]
                except:
                    pass
                
            thought_process.append(step_info)
            
        return ChatResponse(
            response=final_message,
            thought_process=thought_process,
            tool_used=tool_used,
            risk_level=risk_level,
            requires_alert=requires_alert
        )
        
    except Exception as e:
        # Graceful Degradation: Recursion/Timeout vb cokmelerde LLM i darlamak yerine JSON Safety Net
        return ChatResponse(
            response="I encountered a technical difficulty while resolving the supply chain data or fell into a reasoning loop. Please verify the product details and try again.",
            thought_process=[{"type": "Error", "content": str(e)}],
            tool_used=None,
            risk_level="Error",
            requires_alert=False
        )

class StockUpdateRequest(BaseModel):
    sku: str
    qty_sold: int

@router.post("/update-stock")
def update_stock(request: StockUpdateRequest):
    """
    Simulates real-world sales by decrementing the current_stock in the inventory table.
    """
    import sqlite3
    import os
    db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../database/amazon_sales.db"))
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=rw", uri=True)
        cursor = conn.cursor()
        
        cursor.execute("SELECT current_stock FROM inventory WHERE sku = ?", (request.sku,))
        row = cursor.fetchone()
        
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail=f"SKU {request.sku} not found")
            
        new_stock = max(0, row[0] - request.qty_sold)
        cursor.execute("UPDATE inventory SET current_stock = ? WHERE sku = ?", (new_stock, request.sku))
        conn.commit()
        conn.close()
        return {"status": "success", "sku": request.sku, "new_stock": new_stock}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/retrain")
def retrain_model():
    """
    Runs the offline training script via subprocess and reloads the model artifact into memory.
    """
    import subprocess
    import os
    import sys
    from tools.inventory import reload_model
    
    script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../scripts/train_model.py"))
    
    try:
        result = subprocess.run([sys.executable, script_path], capture_output=True, text=True, check=True, timeout=120)
        reload_model()
        return {"status": "success", "message": "Model retrained and loaded into memory successfully.", "logs": result.stdout}
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Training failed: {e.stderr}")
    except subprocess.TimeoutExpired as e:
        raise HTTPException(status_code=500, detail="Training timed out after 120 seconds.")

@router.get("/scan-inventory")
def scan_inventory():
    """
    Nightly Batch Scanner to calculate risk for all items and return SKUs that have escalated in risk.
    """
    import sqlite3
    import os
    import pandas as pd
    from tools.inventory import get_ml_model
    
    db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../database/amazon_sales.db"))
    
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=rw", uri=True)
        
        query = '''
        WITH max_date AS (SELECT MAX(date) as max_d FROM sales_history),
        lags AS (
            SELECT 
                s.sku,
                SUM(CASE WHEN s.date > date(m.max_d, '-7 days') THEN s.qty ELSE 0 END) as lag_7,
                SUM(CASE WHEN s.date > date(m.max_d, '-14 days') THEN s.qty ELSE 0 END) as lag_14,
                SUM(CASE WHEN s.date > date(m.max_d, '-30 days') THEN s.qty ELSE 0 END) as lag_30
            FROM sales_history s
            CROSS JOIN max_date m
            GROUP BY s.sku
        )
        SELECT i.sku, i.current_stock, i.critical_threshold, 
               COALESCE(l.lag_7, 0) as lag_7, 
               COALESCE(l.lag_14, 0) as lag_14, 
               COALESCE(l.lag_30, 0) as lag_30
        FROM inventory i
        LEFT JOIN lags l ON i.sku = l.sku
        '''
        
        df = pd.read_sql_query(query, conn)
        if df.empty:
            return {"escalated_items": []}
            
        # Add new features for quantile model
        df['velocity_ratio'] = df['lag_7'] / (df['lag_30'] + 1)
        df['is_no_history'] = (df['lag_30'] == 0).astype(int)
            
        model = get_ml_model()
        X_infer = df[['lag_7', 'lag_14', 'lag_30', 'velocity_ratio', 'is_no_history']]
        
        preds = model.predict(X_infer).clip(min=0).astype(int)
        df['predicted_demand_p50'] = preds[:, 1]
        df['predicted_demand_p90'] = preds[:, 2]
        
        demand_per_day = df['predicted_demand_p50'] / 30.0
        df['days_of_stock'] = df.apply(lambda row: row['current_stock'] / demand_per_day[row.name] if demand_per_day[row.name] > 0 else float('inf'), axis=1)
        
        def get_risk(row):
            if row['current_stock'] <= row['critical_threshold']: return "Critical"
            elif row['days_of_stock'] < 7: return "High"
            elif row['days_of_stock'] < 14: return "Medium"
            else: return "Low"
            
        df['risk_level'] = df.apply(get_risk, axis=1)
        
        # Switch to agent_state.db for snapshots
        state_db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../database/agent_state.db"))
        state_conn = sqlite3.connect(f"file:{state_db_path}?mode=rwc", uri=True)
        
        # Create table if not exists just to be safe
        state_conn.execute('''CREATE TABLE IF NOT EXISTS risk_snapshots (sku TEXT PRIMARY KEY, last_risk_level TEXT)''')
        
        snapshots = pd.read_sql_query("SELECT sku, last_risk_level FROM risk_snapshots", state_conn)
        merged = df.merge(snapshots, on='sku', how='left')
        
        risk_rank = {"Low": 0, "Medium": 1, "High": 2, "Critical": 3}
        escalated_items = []
        
        for _, row in merged.iterrows():
            old_risk = row['last_risk_level'] if pd.notna(row['last_risk_level']) else "Low"
            new_risk = row['risk_level']
            
            if risk_rank[new_risk] > risk_rank[old_risk]:
                escalated_items.append({
                    "sku": row['sku'],
                    "old_risk": old_risk,
                    "new_risk": new_risk,
                    "current_stock": row['current_stock'],
                    "predicted_demand_p50": row['predicted_demand_p50'],
                    "tail_risk_demand_p90": row['predicted_demand_p90']
                })
                
        snapshot_updates = df[['sku', 'risk_level']].copy()
        
        # Use UPSERT to preserve PRIMARY KEY constraint
        for _, row in snapshot_updates.iterrows():
            state_conn.execute(
                "INSERT INTO risk_snapshots (sku, last_risk_level) VALUES (?, ?) "
                "ON CONFLICT(sku) DO UPDATE SET last_risk_level=excluded.last_risk_level",
                (row['sku'], row['risk_level'])
            )
        state_conn.commit()
        state_conn.close()
        
        conn.close()
        return {"status": "success", "total_scanned": len(df), "escalated_items": escalated_items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

