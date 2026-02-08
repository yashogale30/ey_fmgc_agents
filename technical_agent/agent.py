from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
import pandas as pd
import re
import os
from typing import List, Dict

PRODUCT_DATABASE_PATH = os.getenv("PRODUCT_DB_PATH", "/Users/yashogale/codes/ey_agents/OEM_Product_Database.xlsx")


SPEC_WEIGHTS = {
    'voltage': 0.25,       
    'standards': 0.20,    
    'conductor': 0.18,     
    'insulation': 0.15,    
    'cores': 0.12,         
    'armoring': 0.10       
}

MATERIAL_SYNONYMS = {
    'copper': ['cu', 'copper', 'coppper'],
    'aluminum': ['al', 'aluminium', 'aluminum', 'alumunium'],
    'steel': ['st', 'steel', 'stl']
}

INSULATION_SYNONYMS = {
    'xlpe': ['xlpe', 'cross-linked polyethylene', 'cross linked polyethylene'],
    'pvc': ['pvc', 'polyvinyl chloride', 'poly vinyl chloride'],
    'epr': ['epr', 'ethylene propylene rubber']
}

# ============================================================
# TOOL 1 — Load Product Database
# ============================================================
def load_product_database() -> pd.DataFrame:
    """
    Loads the complete OEM product database with all specifications.
    
    Expected columns:
    - Product_ID, Product_Name, Category
    - Voltage_Rating, Standards_Compliance
    - Conductor_Material, Insulation_Type
    - Number_of_Cores, Armoring
    - Unit_Price_INR_per_meter, Lead_Time_Days, BIS_Certified
    
    Returns:
        DataFrame with product data, or empty DataFrame if file not found
    """
    try:
        if not os.path.exists(PRODUCT_DATABASE_PATH):
            print(f"⚠️  Warning: Product database not found at {PRODUCT_DATABASE_PATH}")
            print("    Using mock data for testing...")
            return _create_mock_database()
        
        df = pd.read_excel(PRODUCT_DATABASE_PATH)
        print(f"✓ Loaded {len(df)} products from database")
        return df
    
    except Exception as e:
        print(f"✗ Error loading database: {e}")
        print("  Using mock data for testing...")
        return _create_mock_database()


def _create_mock_database() -> pd.DataFrame:
    """
    Creates a mock product database for testing when actual database is unavailable.
    """
    mock_data = {
        'Product_ID': ['PROD_001', 'PROD_002', 'PROD_003', 'PROD_004', 'PROD_005'],
        'Product_Name': [
            '11kV XLPE 3-Core Cu Cable',
            '11kV XLPE 4-Core Cu Cable', 
            '33kV XLPE 3-Core Al Cable',
            '11kV PVC 3-Core Cu Cable',
            '6.6kV XLPE 3-Core Cu Cable'
        ],
        'Category': ['Power Cables'] * 5,
        'Voltage_Rating': ['11kV', '11kV', '33kV', '11kV', '6.6kV'],
        'Standards_Compliance': ['IS 7098, IEC 60502'] * 5,
        'Conductor_Material': ['Copper', 'Copper', 'Aluminum', 'Copper', 'Copper'],
        'Insulation_Type': ['XLPE', 'XLPE', 'XLPE', 'PVC', 'XLPE'],
        'Number_of_Cores': [3, 4, 3, 3, 3],
        'Armoring': ['SWA', 'SWA', 'SWA', 'None', 'SWA'],
        'Unit_Price_INR_per_meter': [1200, 1500, 2000, 800, 1000],
        'Lead_Time_Days': [30, 35, 45, 25, 28],
        'BIS_Certified': [True, True, True, True, True],
        'Min_Order_Qty_Meters': [1000, 1000, 1500, 800, 1000],
        'Warranty_Years': [2, 2, 3, 1, 2]
    }
    return pd.DataFrame(mock_data)


# ============================================================
# TOOL 2 — Normalize Text
# ============================================================
def normalize_text(text: str) -> str:
    """
    Enhanced normalization with special character handling.
    Removes punctuation and converts to lowercase.
    
    Args:
        text: Raw text string
    
    Returns:
        Normalized text string
    """
    if not text:
        return ""
    # Remove special characters, keep alphanumeric and spaces
    normalized = re.sub(r'[^\w\s]', ' ', str(text).lower().strip())
    # Collapse multiple spaces
    normalized = re.sub(r'\s+', ' ', normalized)
    return normalized


# ============================================================
# TOOL 3 — Fuzzy Match with Synonyms
# ============================================================
def fuzzy_match(value: str, text: str, synonyms: dict) -> bool:
    """
    Check if value matches text using fuzzy matching with synonyms.
    
    Args:
        value: Value to find (from database)
        text: Text to search in (from RFP)
        synonyms: Dictionary of synonym lists
    
    Returns:
        True if match found (direct or via synonyms)
    """
    norm_value = normalize_text(value)
    norm_text = normalize_text(text)
    
    # Direct match
    if norm_value in norm_text:
        return True
    
    # Synonym matching
    for canonical, variants in synonyms.items():
        if norm_value in variants or any(v in norm_value for v in variants):
            # Check if any variant is in text
            for variant in variants:
                if variant in norm_text:
                    return True
    
    return False


# ============================================================
# TOOL 4 — Flatten RFP Specifications
# ============================================================
def flatten_rfp_specs(technical_brief: dict) -> str:
    """
    Extracts and flattens all technical specification text from RFP.
    
    Args:
        technical_brief: Dict with RFP technical fields
    
    Returns:
        Concatenated normalized specification text
    """
    if not technical_brief:
        return ""
    
    scope = technical_brief.get("scope_of_supply", "")
    tech_specs = technical_brief.get("technical_specifications", "")
    
    # Flatten nested dictionaries if present
    if isinstance(tech_specs, dict):
        tech_specs = " ".join(str(v) for v in tech_specs.values())
    
    combined_text = f"{scope} {tech_specs}"
    return normalize_text(combined_text)


# ============================================================
# TOOL 5 — Calculate Component Scores
# ============================================================
def calculate_component_scores(product_row: pd.Series, rfp_text: str) -> dict:
    """
    Calculate individual component scores for each specification type.
    
    Args:
        product_row: Single product row from database
        rfp_text: Normalized RFP technical text
    
    Returns:
        Dict with scores for each component (0-100)
    """
    scores = {}
    
    # Voltage matching (exact match required)
    voltage = str(product_row.get('Voltage_Rating', ''))
    if normalize_text(voltage) in rfp_text:
        scores['voltage'] = 100
    else:
        scores['voltage'] = 0
    
    # Standards matching (high priority)
    standards = str(product_row.get('Standards_Compliance', ''))
    if normalize_text(standards) in rfp_text:
        scores['standards'] = 100
    elif any(std in rfp_text for std in ['is', 'iec', 'ieee', 'bis']):
        scores['standards'] = 60  # Partial match if any standard mentioned
    else:
        scores['standards'] = 0
    
    # Conductor material (fuzzy matching)
    conductor = str(product_row.get('Conductor_Material', ''))
    if fuzzy_match(conductor, rfp_text, MATERIAL_SYNONYMS):
        scores['conductor'] = 100
    else:
        scores['conductor'] = 0
    
    # Insulation type (fuzzy matching)
    insulation = str(product_row.get('Insulation_Type', ''))
    if fuzzy_match(insulation, rfp_text, INSULATION_SYNONYMS):
        scores['insulation'] = 100
    else:
        scores['insulation'] = 0
    
    # Number of cores
    cores = str(product_row.get('Number_of_Cores', ''))
    if cores in rfp_text or f"{cores}c" in rfp_text or f"{cores} core" in rfp_text:
        scores['cores'] = 100
    else:
        scores['cores'] = 0
    
    # Armoring
    armoring = str(product_row.get('Armoring', ''))
    if normalize_text(armoring) in rfp_text:
        scores['armoring'] = 100
    else:
        scores['armoring'] = 0
    
    return scores


# ============================================================
# TOOL 6 — Calculate Weighted Match Score
# ============================================================
def calculate_weighted_score(component_scores: dict) -> float:
    """
    Calculate weighted total score based on component scores.
    
    Args:
        component_scores: Dict with individual component scores
    
    Returns:
        Weighted total score (0-100)
    """
    weighted_score = sum(
        component_scores.get(spec, 0) * SPEC_WEIGHTS[spec]
        for spec in SPEC_WEIGHTS.keys()
    )
    
    return round(weighted_score, 2)


# ============================================================
# TOOL 7 — Match Products Against RFP
# ============================================================
def match_products_advanced(
    technical_brief: dict,
    min_score: float = 30.0,
    max_results: int = 10
) -> List[Dict]:
    """
    Find and rank matching products for an RFP using weighted scoring.
    
    Process:
    1. Flatten and normalize RFP technical text
    2. For each product in database:
       - Calculate component scores (voltage, standards, conductor, etc.)
       - Apply weights to get overall score
       - Filter by minimum threshold
    3. Sort by score and return top matches
    
    Args:
        technical_brief: RFP dict with technical specifications
        min_score: Minimum match score to include (0-100)
        max_results: Maximum number of results to return
    
    Returns:
        List of matched products with scores and details
    """
    # Validate input
    if not technical_brief:
        print("⚠️  Warning: Empty technical brief received")
        return []
    
    # Load product database
    product_db = load_product_database()
    
    if product_db.empty:
        print("✗ Error: Product database is empty")
        return []
    
    # Flatten RFP specifications
    rfp_text = flatten_rfp_specs(technical_brief)
    
    if not rfp_text:
        print("⚠️  Warning: No technical specifications found in brief")
        return []
    
    print(f"📋 Matching against {len(product_db)} products...")
    print(f"   RFP text: {rfp_text[:100]}...")
    
    matches = []
    
    # Iterate through all products
    for idx, row in product_db.iterrows():
        # Calculate component scores
        component_scores = calculate_component_scores(row, rfp_text)
        
        # Calculate weighted total
        weighted_score = calculate_weighted_score(component_scores)
        
        # Only include products above threshold
        if weighted_score >= min_score:
            matches.append({
                "product_id": row["Product_ID"],
                "sku": row.get("SKU", row["Product_ID"]),  
                "product_name": row["Product_Name"],
                "category": row["Category"],
                "spec_match_percent": weighted_score,
                "component_scores": component_scores,
                "unit_price": float(row["Unit_Price_INR_per_meter"]),
                "lead_time_days": int(row["Lead_Time_Days"]),
                "bis_certified": bool(row["BIS_Certified"]),
                # Additional product details
                "voltage_rating": str(row["Voltage_Rating"]),
                "conductor_material": str(row["Conductor_Material"]),
                "insulation_type": str(row["Insulation_Type"]),
                "number_of_cores": int(row["Number_of_Cores"])
            })
    
    matches.sort(key=lambda x: x["spec_match_percent"], reverse=True)
    
    print(f"✓ Found {len(matches)} products matching ≥{min_score}% threshold")
    
    return matches[:max_results]


# ============================================================
# TOOL 8 — Get Top N Recommendations
# ============================================================
def get_top_recommendations(
    matched_products: List[Dict],
    top_n: int = 3
) -> List[Dict]:
    """
    Extract top N recommendations from matched products.
    
    Args:
        matched_products: List of all matched products
        top_n: Number of top products to return
    
    Returns:
        List of top N products
    """
    return matched_products[:top_n]


# ============================================================
# TOOL 9 — Format Recommendation Summary
# ============================================================
def format_recommendation_summary(matched_products: List[Dict]) -> dict:
    """
    Creates a formatted summary of product recommendations.
    
    Args:
        matched_products: List of matched products
    
    Returns:
        Structured summary with key metrics
    """
    if not matched_products:
        return {
            "total_matches": 0,
            "top_products": [],
            "average_match_score": 0.0,
            "status": "no_matches_found"
        }
    
    return {
        "total_matches": len(matched_products),
        "top_products": matched_products,
        "average_match_score": round(
            sum(p["spec_match_percent"] for p in matched_products) / len(matched_products),
            2
        ),
        "best_match_score": matched_products[0]["spec_match_percent"],
        "status": "matches_found"
    }


# ============================================================
# TECHNICAL AGENT
# ============================================================
technical_agent = LlmAgent(
    name="TechnicalAgent",
    model="gemini-2.5-flash-lite",
    instruction="""
You are the Advanced Technical Matching Agent.

INPUTS (from session state):
- {master_output}: Contains technical_brief and pricing_brief

CRITICAL FIRST STEP:
Before doing anything else, extract the technical_brief from master_output:
    technical_brief = master_output["technical_brief"]

EXECUTION WORKFLOW:
1. Extract technical_brief from master_output (as shown above)
2. Call match_products_advanced(technical_brief)
   The tool will:
   a. Load product database (with fallback to mock data if unavailable)
   b. Flatten and normalize RFP technical text
   c. For EACH product in database:
      - Calculate component scores using weighted algorithm:
        * Voltage: 25% weight (critical - exact match required)
        * Standards: 20% weight (mandatory compliance)
        * Conductor: 18% weight (performance impact)
        * Insulation: 15% weight (safety)
        * Cores: 12% weight (capacity)
        * Armoring: 10% weight (protection)
      - Apply fuzzy matching for material/insulation synonyms
      - Calculate weighted total score (0-100)
   d. Filter products with score ≥ 30%
   e. Sort by score (descending)
   f. Return top 10 matches with detailed breakdown

3. Return the matched products directly - they are already in the correct format

MATCHING ALGORITHM:
- Uses weighted scoring (not all specs are equal importance)
- Fuzzy matching handles spelling variations (copper/cu, aluminum/al)
- Synonym matching for materials and insulation types
- Partial credit for standards compliance
- Configurable minimum threshold (default: 30%)

ERROR HANDLING:
- If master_output is missing, return empty list
- If technical_brief is missing or empty inside master_output, return empty list
- If database fails to load, use mock data for testing
- If no matches found, return empty list with status message

STRICT RULES:
- ALWAYS extract technical_brief from master_output first
- Use ONLY the provided tools for all calculations
- DO NOT invent specifications or scores
- DO NOT modify the SPEC_WEIGHTS configuration
- Always show component score breakdown for transparency
- Handle missing/partial data gracefully

OUTPUT to {oem_recommendations}:
List of matched products with:
- product_id (required for pricing agent)
- sku
- product_name
- category
- spec_match_percent (overall match score)
- component_scores (breakdown by spec type)
- unit_price
- lead_time_days
- bis_certified
- voltage_rating, conductor_material, insulation_type, number_of_cores
""",
    tools=[
        FunctionTool(load_product_database),
        FunctionTool(normalize_text),
        FunctionTool(fuzzy_match),
        FunctionTool(flatten_rfp_specs),
        FunctionTool(calculate_component_scores),
        FunctionTool(calculate_weighted_score),
        FunctionTool(match_products_advanced),
        FunctionTool(get_top_recommendations),
        FunctionTool(format_recommendation_summary),
    ],
    output_key="oem_recommendations",
    description="Advanced technical matching with weighted scoring and fuzzy matching algorithm."
)

root_agent = technical_agent


# ============================================================
# TEST EXECUTION
# ============================================================
# if __name__ == "__main__":
#     print("\n" + "="*60)
#     print("Testing Technical Matching Agent")
#     print("="*60 + "\n")
    
#     # Mock technical brief (as would come from Master Agent)
#     mock_technical_brief = {
#         "rfp_title": "Metro Phase 3 Power Cable Supply",
#         "category": "power cables",
#         "scope_of_supply": """
#         Supply of 11kV XLPE insulated power cables for metro project.
#         Cables must be 3-core with copper conductor.
#         """,
#         "technical_specifications": """
#         Voltage Rating: 11 kV
#         Conductor: Copper (Cu)
#         Insulation: XLPE (Cross-linked Polyethylene)
#         Cores: 3-core
#         Standards: IS 7098 Part 2, IEC 60502
#         Armoring: SWA (Steel Wire Armored)
#         BIS Certification: Required
#         """
#     }
    
#     print("Step 1: Flattening RFP specifications...")
#     rfp_text = flatten_rfp_specs(mock_technical_brief)
#     print(f"✓ Normalized RFP text: {rfp_text[:100]}...\n")
    
#     print("Step 2: Matching products with weighted scoring...")
#     matched_products = match_products_advanced(
#         technical_brief=mock_technical_brief,
#         min_score=30.0,
#         max_results=10
#     )
#     print(f"✓ Found {len(matched_products)} matching products\n")
    
#     if matched_products:
#         print("Step 3: Getting top 3 recommendations...")
#         top_3 = get_top_recommendations(matched_products, top_n=3)
        
#         print("\n" + "="*60)
#         print("TOP 3 PRODUCT RECOMMENDATIONS")
#         print("="*60 + "\n")
        
#         for i, product in enumerate(top_3, 1):
#             print(f"#{i} - {product['product_name']}")
#             print(f"    Product ID: {product['product_id']}")
#             print(f"    Match Score: {product['spec_match_percent']}%")
#             print(f"    Component Breakdown:")
#             for component, score in product['component_scores'].items():
#                 weight = SPEC_WEIGHTS[component] * 100
#                 print(f"      - {component.capitalize()}: {score}/100 (weight: {weight}%)")
#             print(f"    Unit Price: ₹{product['unit_price']}/meter")
#             print(f"    Lead Time: {product['lead_time_days']} days")
#             print(f"    BIS Certified: {product['bis_certified']}")
#             print()
        
#         print("="*60)
        
#         # Summary
#         summary = format_recommendation_summary(top_3)
#         print(f"\nSummary:")
#         print(f"  Total Matches: {summary['total_matches']}")
#         print(f"  Average Score: {summary['average_match_score']}%")
#         print(f"  Best Score: {summary['best_match_score']}%")
#         print("="*60 + "\n")
#     else:
#         print("⚠️  No matching products found")
#         print("="*60 + "\n")
