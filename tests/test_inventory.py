import pytest
from tools.inventory import calculate_inventory_risk, search_products

def test_search_products_valid():
    result = search_products.invoke({"query": "SET"})
    # Result is a dict like {"matching_products": [...]} or string if error
    if isinstance(result, dict) and "matching_products" in result:
        assert any("SET" in item for item in result["matching_products"]) or len(result["matching_products"]) > 10
    else:
        assert "SET" in str(result)

def test_search_products_not_found():
    result = search_products.invoke({"query": "NONEXISTENT_XYZ_123"})
    if isinstance(result, dict):
        assert "No products found" in result.get("error", "")
    else:
        assert "No products found" in str(result)

def test_calculate_inventory_risk_valid():
    result = calculate_inventory_risk.invoke({"product_sku": "JNE3781-KR-XXXL"})
    assert "risk_level" in result
    assert "risk_score" in result
    assert "current_stock" in result

def test_calculate_inventory_risk_invalid():
    result = calculate_inventory_risk.invoke({"product_sku": "NONEXISTENT_XYZ_123"})
    assert "error" in result
    assert "not found" in result["error"]
