import sqlite3
import os
import pickle
import pandas as pd
import xgboost as xgb
from langchain_core.tools import tool
from pydantic import BaseModel, Field

# Model Loading Helper (To avoid loading pickle on every invocation)
_model = None

def get_ml_model():
    global _model
    if _model is None:
        model_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../models/xgboost_demand_forecaster.pkl"))
        with open(model_path, "rb") as f:
            _model = pickle.load(f)
    return _model

def reload_model():
    """Forces the model to be reloaded from disk on the next invocation."""
    global _model
    _model = None

class RiskAnalysisInput(BaseModel):
    product_sku: str = Field(..., description="The exact SKU of the product to analyze.")

@tool("calculate_inventory_risk", args_schema=RiskAnalysisInput)
def calculate_inventory_risk(product_sku: str) -> dict:
    """
    Dynamically predicts the 30-day demand using an ML model and calculates the risk score based on current stock.
    ONLY use this tool when the user asks for the risk score or stock status of a specific product SKU.
    DO NOT invent SKUs. If the SKU is missing or ambiguous, use 'search_products' tool to clarify.
    """
    db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../database/amazon_sales.db"))
    
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cursor = conn.cursor()
        
        # 1. Fetch Inventory Status
        cursor.execute(
            "SELECT sku, current_stock, critical_threshold, COALESCE(lead_time_days, 7) FROM inventory WHERE sku LIKE ?",
            (f"%{product_sku}%",)
        )
        rows = cursor.fetchall()
        
        if not rows:
            conn.close()
            return {"error": f"Product SKU '{product_sku}' not found in inventory. Ask user for correct SKU or use search_products."}
            
        if len(rows) > 1:
            skus = [r[0] for r in rows]
            conn.close()
            return {"error": f"Multiple SKUs found containing '{product_sku}': {skus}. Please ask the user to clarify which specific SKU they mean."}
            
        sku, current_stock, critical_threshold, lead_time_days = rows[0]
        
        # 2. Fetch Historical Lags for ML Model
        cursor.execute("""
            WITH last_date AS (SELECT MAX(date) as max_d FROM sales_history WHERE sku = ?)
            SELECT 
                COALESCE(SUM(CASE WHEN date > date(max_d, '-7 days') THEN qty ELSE 0 END), 0) as lag_7,
                COALESCE(SUM(CASE WHEN date > date(max_d, '-14 days') THEN qty ELSE 0 END), 0) as lag_14,
                COALESCE(SUM(CASE WHEN date > date(max_d, '-30 days') THEN qty ELSE 0 END), 0) as lag_30
            FROM sales_history, last_date
            WHERE sku = ?
        """, (sku, sku))
        
        lag_data = cursor.fetchone()
        conn.close()
        
        if not lag_data or lag_data == (0, 0, 0):
            # No sales history found, fallback to 0 demand
            lag_7, lag_14, lag_30 = 0, 0, 0
            p10, p50, p90 = 0, 0, 0
        else:
            lag_7, lag_14, lag_30 = lag_data
            velocity_ratio = lag_7 / (lag_30 + 1)
            is_no_history = 1 if lag_30 == 0 else 0
            
            # 3. Predict Demand via ML Model
            model = get_ml_model()
            X_infer = pd.DataFrame([{
                'lag_7': lag_7, 
                'lag_14': lag_14, 
                'lag_30': lag_30,
                'velocity_ratio': velocity_ratio,
                'is_no_history': is_no_history
            }])
            preds = model.predict(X_infer)[0] # Shape is (1, 3), [0] gives array of 3
            
            p10 = max(0, int(preds[0]))
            p50 = max(0, int(preds[1]))
            p90 = max(0, int(preds[2]))
            
        # 4. Risk Dynamics Calculation (using P50 as main estimate)
        if p50 > 0:
            # How many days will the current stock last based on median demand?
            days_of_stock = current_stock / (p50 / 30)
        else:
            days_of_stock = float('inf')
            
        if current_stock <= critical_threshold:
            risk_score, risk_level = 90, "Critical"
        elif days_of_stock < lead_time_days:
            # Stock won't even cover the replenishment lead time
            risk_score, risk_level = 70, "High"
        elif days_of_stock < lead_time_days * 2:
            # Safety margin is thin — 1 lead time of buffer only
            risk_score, risk_level = 40, "Medium"
        else:
            risk_score, risk_level = 10, "Low"
            
        return {
            "sku": sku,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "current_stock": current_stock,
            "critical_threshold": critical_threshold,
            "lead_time_days": lead_time_days,
            "days_of_stock": round(days_of_stock, 1) if days_of_stock != float('inf') else None,
            "demand_forecast": {
                "optimistic_p10": p10,
                "median_p50": p50,
                "conservative_p90": p90
            },
            "business_metrics": {
                "tail_risk_demand_p90": p90,
                "var_90_units": p90
            },
            "historical_lags": {
                "last_7_days": lag_7,
                "last_14_days": lag_14,
                "last_30_days": lag_30
            }
        }
    except Exception as e:
        return {"error": str(e)}

class SearchInput(BaseModel):
    query: str = Field(..., description="The general product category or partial SKU to search for (e.g., 'kurta', 'JNE').")

@tool("search_products", args_schema=SearchInput)
def search_products(query: str) -> dict:
    """
    Searches the database for available product SKUs matching a general category or partial name.
    Returns a maximum of 5 SKUs to prevent context bloat.
    ONLY returns the SKUs, NOT the risk scores or stock levels.
    """
    db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../database/amazon_sales.db"))
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cursor = conn.cursor()
        
        # LIMIT 5 prevents Context Window Denial of Service (DoS) and context bloat.
        cursor.execute(
            "SELECT sku FROM inventory WHERE sku LIKE ? LIMIT 5", 
            (f"%{query}%",)
        )
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            return {"error": f"No products found matching '{query}'."}
            
        product_names = [r[0] for r in rows]
        return {"matching_products": product_names}
        
    except Exception as e:
        return {"error": str(e)}

tools_list = [calculate_inventory_risk, search_products]
