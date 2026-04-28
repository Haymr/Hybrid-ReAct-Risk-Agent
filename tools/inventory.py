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
            "SELECT sku, current_stock, critical_threshold FROM inventory WHERE sku LIKE ?", 
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
            
        sku, current_stock, critical_threshold = rows[0]
        
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
            predicted_demand_30d = 0
        else:
            lag_7, lag_14, lag_30 = lag_data
            # 3. Predict Demand via ML Model
            model = get_ml_model()
            X_infer = pd.DataFrame([{'lag_7': lag_7, 'lag_14': lag_14, 'lag_30': lag_30}])
            predicted_demand_30d = max(0, int(model.predict(X_infer)[0])) # Demand can't be negative
            
        # 4. Risk Dynamics Calculation (Refactored to 'Days of Stock' logic)
        if predicted_demand_30d > 0:
            # How many days will the current stock last?
            days_of_stock = current_stock / (predicted_demand_30d / 30)
        else:
            days_of_stock = float('inf')
            
        if current_stock <= critical_threshold:
            risk_score, risk_level = 90, "Critical"
        elif days_of_stock < 7:
            risk_score, risk_level = 70, "High"
        elif days_of_stock < 14:
            risk_score, risk_level = 40, "Medium"
        else:
            risk_score, risk_level = 10, "Low"
            
        return {
            "sku": sku,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "current_stock": current_stock,
            "critical_threshold": critical_threshold,
            "predicted_demand_30d": predicted_demand_30d,
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
