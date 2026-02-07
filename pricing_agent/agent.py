from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
import pandas as pd
import random
import os

# ============================================================
# CONFIGURATION - UPDATE THESE PATHS
# ============================================================
# TODO: Replace with actual path to your pricing database
PRICING_DATABASE_PATH = os.getenv("PRICING_DB_PATH", "/Users/yashogale/codes/ey_agents/OEM_Product_Database.xlsx")

# ============================================================
# TOOL 1 — Load Product Database
# ============================================================
def load_product_database() -> pd.DataFrame:
    """
    Loads the complete product database with pricing information.
    Returns DataFrame with columns: Product_ID, Unit_Price_INR_per_meter, Min_Order_Qty_Meters, etc.
    
    Returns:
        DataFrame with product data, or mock DataFrame if file not found
    """
    try:
        if not os.path.exists(PRICING_DATABASE_PATH):
            print(f"⚠️  Warning: Pricing database not found at {PRICING_DATABASE_PATH}")
            print("    Using mock data for testing...")
            return _create_mock_pricing_database()
        
        df = pd.read_excel(PRICING_DATABASE_PATH)
        print(f"✓ Loaded pricing data for {len(df)} products")
        return df
    
    except Exception as e:
        print(f"✗ Error loading pricing database: {e}")
        print("  Using mock data for testing...")
        return _create_mock_pricing_database()


def _create_mock_pricing_database() -> pd.DataFrame:
    """
    Creates a mock pricing database for testing when actual database is unavailable.
    """
    mock_data = {
        'Product_ID': ['PROD_001', 'PROD_002', 'PROD_003', 'PROD_004', 'PROD_005'],
        'Unit_Price_INR_per_meter': [1200, 1500, 2000, 800, 1000],
        'Min_Order_Qty_Meters': [1000, 1000, 1500, 800, 1000],
        'Lead_Time_Days': [30, 35, 45, 25, 28],
        'BIS_Certified': [True, True, True, True, True],
        'Warranty_Years': [2, 2, 3, 1, 2]
    }
    return pd.DataFrame(mock_data)


# ============================================================
# TOOL 2 — Get Product Pricing
# ============================================================
def get_product_pricing(product_id: str) -> dict:
    """
    Returns pricing details for a specific product ID.
    
    Args:
        product_id: Product identifier
    
    Returns:
        dict with unit_price, min_order_qty, or None if not found
    """
    product_db = load_product_database()
    
    if product_db.empty:
        return {
            "found": False,
            "unit_price": 0.0,
            "min_order_qty": 0.0,
            "fallback_estimate": 50000.0
        }
    
    product_row = product_db[product_db["Product_ID"] == product_id]
    
    if product_row.empty:
        print(f"⚠️  Product {product_id} not found in pricing database")
        return {
            "found": False,
            "unit_price": 0.0,
            "min_order_qty": 0.0,
            "fallback_estimate": 50000.0
        }
    
    return {
        "found": True,
        "product_id": product_id,
        "unit_price": float(product_row["Unit_Price_INR_per_meter"].iloc[0]),
        "min_order_qty": float(product_row["Min_Order_Qty_Meters"].iloc[0]),
        "fallback_estimate": 0.0
    }


# ============================================================
# TOOL 3 — Calculate Product Cost
# ============================================================
def calculate_product_cost(
    unit_price: float,
    min_order_qty: float,
    quantity_multiplier: float = 1.0
) -> float:
    """
    Calculates total cost for a product based on pricing and quantity.
    
    Args:
        unit_price: Price per meter/unit
        min_order_qty: Minimum order quantity
        quantity_multiplier: Multiplier for quantity estimation (default: 1.0)
    
    Returns:
        Total product cost
    """
    total_meters = min_order_qty * quantity_multiplier
    product_cost = unit_price * total_meters
    return product_cost


# ============================================================
# TOOL 4 — Apply Pricing Margin
# ============================================================
def apply_pricing_margin(base_cost: float) -> dict:
    """
    Applies realistic margin based on tender size with variation.
    
    Margin structure:
    - Large tenders (>500k): 15% ± 5%
    - Medium tenders (200k-500k): 20% ± 5%
    - Small tenders (<200k): 25% ± 5%
    
    Args:
        base_cost: Total cost before margin
    
    Returns:
        dict with margin_percentage, quoted_price
    """
    if base_cost == 0:
        return {
            "base_cost": 0.0,
            "margin_percentage": 0.0,
            "quoted_price": 0.0
        }
    
    # Determine base margin based on tender size
    if base_cost > 500000:
        base_margin = 0.15  # 15% for large tenders
    elif base_cost > 200000:
        base_margin = 0.20  # 20% for medium tenders
    else:
        base_margin = 0.25  # 25% for small tenders
    
    # Add randomness to margin (±5%)
    margin_variation = random.uniform(-0.05, 0.05)
    final_margin = base_margin + margin_variation
    
    # Ensure margin stays reasonable
    final_margin = max(0.10, min(final_margin, 0.35))  # Between 10-35%
    
    quoted_price = base_cost * (1 + final_margin)
    
    return {
        "base_cost": round(base_cost, 2),
        "margin_percentage": round(final_margin * 100, 2),
        "quoted_price": round(quoted_price, 2)
    }


# ============================================================
# TOOL 5 — Calculate Tender Pricing
# ============================================================
def calculate_tender_pricing(oem_recommendations: list) -> dict:
    """
    Calculates complete pricing for a tender based on matched products.
    
    Process:
    1. For each matched product, get unit price and MOQ from database
    2. Calculate total cost = sum(unit_price × MOQ × quantity_estimate)
    3. Add realistic margin (15-30% based on tender size)
    4. Handle missing/unmatched products gracefully
    
    Args:
        oem_recommendations: List of matched products with product_id
    
    Returns:
        dict with product_costs, base_total, margin_info, final_price
    """
    product_costs = []
    tender_total = 0.0
    
    # Validate input
    if not oem_recommendations:
        print("⚠️  Warning: No product recommendations provided")
        return {
            "product_costs": [],
            "base_total": 0.0,
            "margin_percentage": 0.0,
            "final_price": 0.0,
            "error": "No product recommendations provided"
        }
    
    print(f"💰 Calculating pricing for {len(oem_recommendations)} products...")
    
    for match in oem_recommendations:
        if not match:
            continue
        
        # Get product ID (handle both formats)
        product_id = match.get("product_id") or match.get("sku") or match.get("Product_ID")
        
        if not product_id:
            print(f"⚠️  Skipping product with no ID: {match.get('product_name', 'Unknown')}")
            continue
        
        # Get pricing from database
        pricing_info = get_product_pricing(product_id)
        
        if not pricing_info["found"]:
            # Product not found - use fallback estimate
            fallback_cost = pricing_info["fallback_estimate"]
            tender_total += fallback_cost
            
            product_costs.append({
                "product_id": product_id,
                "product_name": match.get("product_name", "Unknown"),
                "status": "not_found",
                "cost": fallback_cost,
                "note": "Fallback estimate used - product not in pricing database"
            })
            continue
        
        # Calculate actual product cost
        unit_price = pricing_info["unit_price"]
        min_order_qty = pricing_info["min_order_qty"]
        
        # Conservative quantity estimate (can be improved with RFP parsing)
        quantity_multiplier = 1.0
        
        product_cost = calculate_product_cost(
            unit_price=unit_price,
            min_order_qty=min_order_qty,
            quantity_multiplier=quantity_multiplier
        )
        
        tender_total += product_cost
        
        product_costs.append({
            "product_id": product_id,
            "product_name": match.get("product_name", "Unknown"),
            "unit_price": unit_price,
            "min_order_qty": min_order_qty,
            "quantity_multiplier": quantity_multiplier,
            "product_cost": round(product_cost, 2),
            "status": "calculated"
        })
    
    if tender_total == 0:
        print("⚠️  Warning: Total tender cost is zero")
        return {
            "product_costs": product_costs,
            "base_total": 0.0,
            "margin_percentage": 0.0,
            "final_price": 0.0,
            "error": "Could not calculate any product costs"
        }
    
    # Apply margin
    margin_info = apply_pricing_margin(tender_total)
    
    print(f"✓ Base cost: ₹{margin_info['base_cost']:,.2f}")
    print(f"✓ Margin: {margin_info['margin_percentage']}%")
    print(f"✓ Material total: ₹{margin_info['quoted_price']:,.2f}")
    
    return {
        "product_costs": product_costs,
        "base_total": margin_info["base_cost"],
        "margin_percentage": margin_info["margin_percentage"],
        "final_price": margin_info["quoted_price"],
        "products_analyzed": len(product_costs)
    }


# ============================================================
# TOOL 6 — Lookup Test Prices
# ============================================================
def lookup_test_price(test_name: str) -> float:
    """
    Returns price for a given test.
    
    Args:
        test_name: Name of the test
    
    Returns:
        Price in INR
    """
    TEST_PRICE_MAP = {
        "high voltage test": 20000,
        "insulation resistance test": 10000,
        "fire resistance test": 8000,
        "thermal cycling": 15000,
        "vibration test": 12000,
        "electrical acceptance": 18000,
        "ip rating test": 9000,
        "routine test": 5000,
        "type test": 25000
    }
    
    return TEST_PRICE_MAP.get(test_name.lower(), 0.0)


# ============================================================
# TOOL 7 — Calculate Test Costs
# ============================================================
def calculate_test_costs(pricing_brief: dict) -> dict:
    """
    Identifies and calculates costs for all required tests.
    
    Args:
        pricing_brief: Dict containing 'tests_and_acceptance' field
    
    Returns:
        dict with test_costs list and total_test_cost
    """
    if not pricing_brief:
        print("⚠️  Warning: Empty pricing brief received")
        return {
            "test_costs": [],
            "total_test_cost": 0.0,
            "tests_identified": 0
        }
    
    tests_text = pricing_brief.get("tests_and_acceptance", "").lower()
    test_costs = []
    total_test_cost = 0.0
    
    all_tests = [
        "high voltage test",
        "insulation resistance test",
        "fire resistance test",
        "thermal cycling",
        "vibration test",
        "electrical acceptance",
        "ip rating test",
        "routine test",
        "type test"
    ]
    
    print(f"🔬 Analyzing test requirements...")
    
    for test_name in all_tests:
        if test_name in tests_text:
            cost = lookup_test_price(test_name)
            test_costs.append({
                "test": test_name.title(),
                "cost": cost
            })
            total_test_cost += cost
            print(f"   ✓ Found: {test_name.title()} - ₹{cost:,}")
    
    if not test_costs:
        print("   ℹ️  No specific tests identified in requirements")
    
    return {
        "test_costs": test_costs,
        "total_test_cost": total_test_cost,
        "tests_identified": len(test_costs)
    }


# ============================================================
# TOOL 8 — Consolidate Final Pricing
# ============================================================
def consolidate_final_pricing(
    tender_pricing: dict,
    test_costs_info: dict
) -> dict:
    """
    Consolidates material costs and test costs into final pricing breakdown.
    
    Args:
        tender_pricing: Output from calculate_tender_pricing
        test_costs_info: Output from calculate_test_costs
    
    Returns:
        Complete pricing table with all components
    """
    return {
        "material_costs": {
            "products": tender_pricing.get("product_costs", []),
            "base_total": tender_pricing.get("base_total", 0.0),
            "margin_percentage": tender_pricing.get("margin_percentage", 0.0),
            "material_total": tender_pricing.get("final_price", 0.0)
        },
        "testing_costs": {
            "tests": test_costs_info.get("test_costs", []),
            "testing_total": test_costs_info.get("total_test_cost", 0.0)
        },
        "summary": {
            "material_cost": tender_pricing.get("final_price", 0.0),
            "testing_cost": test_costs_info.get("total_test_cost", 0.0),
            "grand_total": tender_pricing.get("final_price", 0.0) + test_costs_info.get("total_test_cost", 0.0),
            "products_count": tender_pricing.get("products_analyzed", 0),
            "tests_count": test_costs_info.get("tests_identified", 0)
        }
    }


# ============================================================
# PRICING AGENT
# ============================================================
pricing_agent = LlmAgent(
    name="PricingAgent",
    model="gemini-2.5-flash-lite",
    instruction="""
You are the Pricing Agent responsible for realistic cost calculation.

INPUTS (from session state):
- {oem_recommendations}: List of matched products from Technical Agent
- {pricing_brief}: Test and acceptance requirements from Master Agent (in master_output)

EXECUTION WORKFLOW:
1. Calculate material costs:
   - Call calculate_tender_pricing(oem_recommendations)
   - This fetches real product prices from database (or uses mock data if unavailable)
   - Applies realistic margins (15-30%) based on tender size
   - Handles missing products with fallback estimates

2. Calculate testing costs:
   - Call calculate_test_costs(pricing_brief)
   - Identifies all required tests from requirements
   - Assigns standard test costs

3. Consolidate final pricing:
   - Call consolidate_final_pricing(tender_pricing, test_costs_info)
   - Produces complete breakdown with grand total

ERROR HANDLING:
- If oem_recommendations is empty, still proceed but note the issue
- If pricing database is unavailable, mock data will be used automatically
- If product not found in database, use fallback estimate (₹50,000)
- If no tests identified, testing cost will be ₹0

STRICT RULES:
- Use ONLY the provided tools for all calculations
- DO NOT invent prices or use placeholder values
- DO NOT modify returned values from tools
- Handle missing products gracefully with fallback estimates
- Always include margin calculation in final pricing

OUTPUT to {price_table}:
Complete pricing table with:
- Individual product costs (with unit prices and quantities)
- Material subtotal with margin
- Individual test costs
- Testing subtotal
- Grand total
- Error notes if applicable
""",
    tools=[
        FunctionTool(load_product_database),
        FunctionTool(get_product_pricing),
        FunctionTool(calculate_product_cost),
        FunctionTool(apply_pricing_margin),
        FunctionTool(calculate_tender_pricing),
        FunctionTool(lookup_test_price),
        FunctionTool(calculate_test_costs),
        FunctionTool(consolidate_final_pricing),
    ],
    output_key="price_table",
    description="Calculates realistic pricing from product database with margins and test costs."
)

root_agent = pricing_agent


# ============================================================
# TEST EXECUTION
# ============================================================
if __name__ == "__main__":
    print("\n" + "="*60)
    print("Testing Pricing Agent")
    print("="*60 + "\n")
    
    # Mock OEM recommendations (as would come from Technical Agent)
    mock_oem_recommendations = [
        {
            "product_id": "PROD_001",
            "product_name": "11kV XLPE Cable",
            "spec_match_percent": 95
        },
        {
            "product_id": "PROD_002",
            "product_name": "33kV Power Cable",
            "spec_match_percent": 88
        }
    ]
    
    # Mock pricing brief (as would come from Master Agent)
    mock_pricing_brief = {
        "rfp_title": "Metro Phase 3 Power Cable Supply",
        "tests_and_acceptance": """
        All products must undergo:
        - High voltage test at 50kV
        - Insulation resistance test
        - Fire resistance test as per IS standards
        - Electrical acceptance testing
        """
    }
    
    # Test tender pricing calculation
    print("Step 1: Calculating tender pricing...")
    tender_pricing = calculate_tender_pricing(mock_oem_recommendations)
    
    if "error" not in tender_pricing:
        print(f"✓ Base total: ₹{tender_pricing['base_total']:,.2f}")
        print(f"✓ Margin: {tender_pricing['margin_percentage']}%")
        print(f"✓ Material total: ₹{tender_pricing['final_price']:,.2f}\n")
    else:
        print(f"✗ Error: {tender_pricing['error']}\n")
    
    # Test test costs calculation
    print("Step 2: Calculating test costs...")
    test_costs_info = calculate_test_costs(mock_pricing_brief)
    print(f"✓ Tests identified: {test_costs_info['tests_identified']}")
    print(f"✓ Testing total: ₹{test_costs_info['total_test_cost']:,.2f}\n")
    
    # Consolidate final pricing
    print("Step 3: Consolidating final pricing...")
    final_pricing = consolidate_final_pricing(tender_pricing, test_costs_info)
    
    print("\n" + "="*60)
    print("FINAL PRICING BREAKDOWN")
    print("="*60)
    print(f"Material Cost:  ₹{final_pricing['summary']['material_cost']:,.2f}")
    print(f"Testing Cost:   ₹{final_pricing['summary']['testing_cost']:,.2f}")
    print(f"{'─'*60}")
    print(f"GRAND TOTAL:    ₹{final_pricing['summary']['grand_total']:,.2f}")
    print("="*60 + "\n")
    
    # Detailed breakdown
    print("Product Details:")
    for product in final_pricing['material_costs']['products']:
        print(f"  • {product['product_name']} ({product['product_id']})")
        if product['status'] == 'calculated':
            print(f"    ₹{product['unit_price']}/m × {product['min_order_qty']}m = ₹{product['product_cost']:,.2f}")
        else:
            print(f"    {product['note']}: ₹{product['cost']:,.2f}")
    
    print(f"\nTest Details:")
    for test in final_pricing['testing_costs']['tests']:
        print(f"  • {test['test']}: ₹{test['cost']:,}")
    
    print("\n" + "="*60 + "\n")
