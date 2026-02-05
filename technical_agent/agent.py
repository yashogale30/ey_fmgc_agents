from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
import pandas as pd

# ============================================================
# TOOL 1 — Load OEM Dataset
# ============================================================
def load_oem_dataset() -> list[dict]:
    """
    Loads the OEM dataset from Excel and normalizes it.
    """
    df = pd.read_excel(
        "dataset_link"
    )

    records = []
    for _, row in df.iterrows():
        records.append({
            "sku": str(row.get("SKU", "")).strip(),
            "product_name": str(row.get("Product Name", "")).strip(),
            "category": str(row.get("Category", "")).lower(),
            "specs": str(row.get("Specifications", "")).lower()
        })

    return records


# ============================================================
# TOOL 2 — Extract RFP Technical Specs
# ============================================================
def get_rfp_specs(technical_brief: dict) -> dict:
    """
    Extracts required specs from the RFP technical brief.
    """
    return {
        "category": technical_brief.get("category", "").lower(),
        "scope": technical_brief.get("scope_of_supply", "").lower(),
        "technical_specs": technical_brief.get("technical_specs", "").lower()
    }


# ============================================================
# TOOL 3 — Filter OEM Catalog
# ============================================================
def search_oem_catalog(
    rfp_specs: dict,
    oem_dataset: list[dict]
) -> list[dict]:
    """
    Filters OEM products relevant to the RFP category.
    """
    results = []
    for product in oem_dataset:
        if rfp_specs["category"] in product["category"]:
            results.append(product)
    return results


# ============================================================
# TOOL 4 — Calculate Spec Match %
# ============================================================
def calculate_spec_match(
    rfp_specs: dict,
    oem_product: dict
) -> float:
    """
    Calculates percentage match between RFP specs and OEM specs.
    """

    keywords = [
        "xlpe", "pvc", "copper", "aluminium",
        "11 kv", "1.1 kv", "ht", "lt",
        "is 7098", "iec 60502", "bis"
    ]

    score = 0
    total = len(keywords)

    for key in keywords:
        if key in rfp_specs["technical_specs"] and key in oem_product["specs"]:
            score += 1

    return round((score / total) * 100, 2)


# ============================================================
# TOOL 5 — Match Products (FINAL OUTPUT)
# ============================================================
def match_products(technical_brief: dict) -> list[dict]:
    """
    Matches RFP specs with OEM products and returns top 3 matches.
    """
    rfp_specs = get_rfp_specs(technical_brief)
    oem_dataset = load_oem_dataset()
    candidates = search_oem_catalog(rfp_specs, oem_dataset)

    scored_products = []

    for product in candidates:
        match_pct = calculate_spec_match(rfp_specs, product)
        scored_products.append({
            "sku": product["sku"],
            "product_name": product["product_name"],
            "match_percentage": match_pct
        })

    scored_products.sort(
        key=lambda x: x["match_percentage"],
        reverse=True
    )

    return scored_products[:3]


# ============================================================
# TECHNICAL AGENT
# ============================================================
technical_agent = LlmAgent(
    name="TechnicalAgent",
    model="gemini-2.5-flash-lite",
    instruction="""
You are the Technical Agent.

Input:
- Read technical input from session state key {technical_brief}.

Steps:
1. Load the OEM dataset.
2. Extract RFP technical specifications.
3. Match OEM products against RFP specs.
4. Select the Top 3 OEM products by Spec Match %.
5. Output a structured recommendation table.

Rules:
- Do NOT invent specifications.
- Do NOT modify scoring logic.
- Use tools for all computations.
""",
    tools=[
        FunctionTool(load_oem_dataset),
        FunctionTool(get_rfp_specs),
        FunctionTool(search_oem_catalog),
        FunctionTool(calculate_spec_match),
        FunctionTool(match_products),
    ],
    output_key="oem_recommendations",
    description="Matches RFP technical requirements with OEM dataset and returns top 3 matching products."
)

root_agent = technical_agent
