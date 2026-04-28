import pytest
from fastapi.testclient import TestClient
from api.server import router, ChatRequest
from fastapi import FastAPI
import os

app = FastAPI()
app.include_router(router)
client = TestClient(app)

def test_chat_endpoint_valid_request():
    response = client.post("/chat", json={
        "user_id": "test_user_123",
        "message": "Hi, who are you?"
    })
    assert response.status_code == 200
    data = response.json()
    assert "response" in data
    assert "thought_process" in data
    
def test_chat_endpoint_sku_query():
    response = client.post("/chat", json={
        "user_id": "test_user_456",
        "message": "What is the inventory risk for SKU JNE3781-KR-XXXL?"
    })
    assert response.status_code == 200
    data = response.json()
    assert "JNE3781-KR-XXXL" in data.get("response", "") or data.get("tool_used") == "calculate_inventory_risk"
    # requires_alert check will be added later
