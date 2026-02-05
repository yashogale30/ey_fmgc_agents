from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
import pandas as pd

# ============================================================
# TOOL 1 — Load Pricing Dataset
# ============================================================
def load_pricing_dataset() -> list[dict]:
    """
    Loads pricing data for OEM products and tests.
    """
    # Example structure — adjust path / columns if needed
    df = pd.read_excel("/mnt/data/pricing_dataset.xlsx")

    records = []
    for _, row in df.iterrows():
        records.append({
            "sku": str(row.get("SKU", "")).strip(),
            "unit_price": float(row.get("Unit Price", 0)),
            "currency": row.get("Currency", "INR")
        })

    return records


# ============================================================
# TOOL 2 — Lookup Product Price
# ============================================================
def lookup_product_price(sku: str) -> float:
    """
    Returns unit price for a given OEM SKU.
    """
    dataset = load_pricing_dataset()
    for item in dataset:
        if item["sku"] == sku:
            return item["unit_price"]
    return 0.0


# ============================================================
# TOOL 3 — Lookup Test Prices
# ============================================================
def lookup_test_price(test_name: str) -> float:
    """
    Returns price for a given test.
    """
    TEST_PRICE_MAP = {
        "high voltage test": 20000,
        "insulation resistance test": 10000,
        "fire resistance test": 8000,
        "thermal cycling": 15000,
        "vibration test": 12000,
        "electrical acceptance": 18000,
        "ip rating test": 9000
    }

    return TEST_PRICE_MAP.get(test_name.lower(), 0.0)


# ============================================================
# TOOL 4 — Consolidate Pricing
# ============================================================
def consolidate_pricing(
    oem_recommendations: list[dict],
    pricing_brief: dict
) -> dict:
    """
    Builds the final pricing table with material + testing costs.
    """

    products = []
    total_material_cost = 0.0

    for product in oem_recommendations:
        sku = product["sku"]
        unit_price = lookup_product_price(sku)

        products.append({
            "sku": sku,
            "product_name": product["product_name"],
            "spec_match_percentage": product["match_percentage"],
            "unit_price": unit_price
        })

        total_material_cost += unit_price

    # Test costs
    tests_text = pricing_brief.get("tests_and_acceptance", "").lower()
    test_costs = []

    total_test_cost = 0.0
    for test_name in [
        "high voltage test",
        "insulation resistance test",
        "fire resistance test",
        "thermal cycling",
        "vibration test",
        "electrical acceptance",
        "ip rating test"
    ]:
        if test_name in tests_text:
            cost = lookup_test_price(test_name)
            test_costs.append({
                "test": test_name,
                "cost": cost
            })
            total_test_cost += cost

    return {
        "products": products,
        "test_costs": test_costs,
        "total_material_cost": total_material_cost,
        "total_test_cost": total_test_cost,
        "grand_total": total_material_cost + total_test_cost
    }


# ============================================================
# PRICING AGENT
# ============================================================
pricing_agent = LlmAgent(
    name="PricingAgent",
    model="gemini-2.5-flash-lite",
    instruction="""
You are the Pricing Agent.

Inputs from session state:
- {oem_recommendations}: Top OEM SKUs from Technical Agent
- {pricing_brief}: Test and acceptance requirements from Master Agent

Steps:
1. Assign unit prices to each OEM SKU.
2. Identify required tests from pricing_brief.
3. Calculate individual test costs.
4. Build a consolidated pricing table.
5. Output totals and grand total.

Rules:
- Use tools for all pricing calculations.
- Do NOT invent prices.
- Do NOT change returned values.
""",
    tools=[
        FunctionTool(load_pricing_dataset),
        FunctionTool(lookup_product_price),
        FunctionTool(lookup_test_price),
        FunctionTool(consolidate_pricing),
    ],
    output_key="price_table",
    description="Assigns unit prices and test costs, then produces consolidated pricing."
)

root_agent = pricing_agent
