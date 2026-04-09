import sqlite3
import os
from langchain_core.tools import tool
from pydantic import BaseModel, Field

class RiskAnalysisInput(BaseModel):
    product_name: str = Field(..., description="The exact name of the product to analyze.")

@tool("calculate_inventory_risk", args_schema=RiskAnalysisInput)
def calculate_inventory_risk(product_name: str) -> dict:
    """
    Calculates the supply chain risk score, current stock, and sales velocity for a specific product.
    ONLY use this tool when the user asks for the risk score or stock status of a specific product.
    DO NOT invent product names. If the product name is missing, ask the user.
    """
    db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../database/database.db"))
    
    try:
        # Read-Only (ro) connection constraint as defined in implementation plan
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT current_stock, critical_threshold, sales_velocity_30d FROM products WHERE name LIKE ?", 
            (f"%{product_name}%",)
        )
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return {"error": f"Product '{product_name}' not found in database. Ask user for correct product name."}
            
        current_stock, critical_threshold, sales_velocity_30d = row
        
        # Risk Dynamics
        risk_score = 0
        risk_level = "Low"
        
        # Threshold penalty
        if current_stock < critical_threshold:
            risk_score += 50
        
        # Velocity penalty
        if sales_velocity_30d > current_stock:
            risk_score += 40
            
        if risk_score >= 80:
            risk_level = "High"
        elif risk_score >= 40:
            risk_level = "Medium"
            
        return {
            "risk_score": risk_score,
            "risk_level": risk_level,
            "current_stock": current_stock,
            "critical_threshold": critical_threshold,
            "sales_velocity_30d": sales_velocity_30d,
        }
    except Exception as e:
        return {"error": str(e)}

tools_list = [calculate_inventory_risk]
