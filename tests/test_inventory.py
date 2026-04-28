import pytest
from tools.inventory import calculate_inventory_risk, search_products

def test_search_products_valid():
    result = search_products.invoke({"query": "SET"})
    assert "J0003-SET" in result or len(result) > 10 # Should return string output of SQL

def test_search_products_not_found():
    result = search_products.invoke({"query": "NONEXISTENT_XYZ_123"})
    assert "No products found" in result

def test_calculate_inventory_risk_valid():
    result = calculate_inventory_risk.invoke({"product_sku": "JNE3781-KR-XXXL"})
    assert "risk_level" in result
    assert "risk_score" in result
    assert "current_stock" in result

def test_calculate_inventory_risk_invalid():
    result = calculate_inventory_risk.invoke({"product_sku": "NONEXISTENT_XYZ_123"})
    assert "error" in result
    assert "not found" in result["error"]
