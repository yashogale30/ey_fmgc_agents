from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
import pandas as pd
import math
import os
from datetime import datetime
from typing import List, Dict, Any

PRODUCT_DATABASE_PATH = os.getenv("PRODUCT_DB_PATH", "/mnt/data/product_database.xlsx")

# ============================================================
# SCORING WEIGHTS (Research-backed evaluation framework)
# ============================================================
# Based on:
# - McKinsey's procurement best practices (2023)
# - Harvard Business Review on bid evaluation frameworks
# - ISO 9001:2015 supplier evaluation standards
# - Government procurement scoring guidelines (GEM, Public Procurement)

SCORING_WEIGHTS = {
    'technical_match': 0.35,      
    'price_competitiveness': 0.25, 
    'delivery_capability': 0.15,   
    'compliance': 0.15,            
    'risk_score': 0.10             
}

# Price scoring parameters
IDEAL_MARGIN = 0.25          # 25% profit margin benchmark
MAX_PRICE_DEVIATION = 0.50   # ±50% from ideal acceptable


# ============================================================
# TOOL 1 — Load Product Database
# ============================================================
def load_product_database() -> pd.DataFrame:
    """
    Loads the complete product database for scoring calculations.
    
    Required columns:
    - Product_ID, Unit_Price_INR_per_meter, Min_Order_Qty_Meters
    - Lead_Time_Days, BIS_Certified, Standards_Compliance
    - Warranty_Years
    
    Returns:
        DataFrame with product data, or mock DataFrame if file not found
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
    """Creates a mock product database for testing."""
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
# TOOL 2 — Score Technical Match (35% weight)
# ============================================================
def score_technical_match(matches: List[Dict]) -> Dict[str, Any]:
    """
    Score technical specification matching (0-100).
    
    Methodology:
    - Uses weighted average of top matching products
    - Applies exponential decay for lower-ranked matches
    - Rewards product diversity (indicates broad capability)
    
    Args:
        matches: List of matched products with spec_match_percent
    
    Returns:
        Dict with technical_score and details
    """
    if not matches or len(matches) == 0:
        return {
            "technical_score": 0.0,
            "top_match_percent": 0.0,
            "diversity_bonus": 0.0
        }
    
    # Filter valid matches
    valid_matches = [m for m in matches if m and m.get('spec_match_percent', 0) > 0]
    
    if not valid_matches:
        return {
            "technical_score": 0.0,
            "top_match_percent": 0.0,
            "diversity_bonus": 0.0
        }
    
    # Calculate weighted score with exponential decay
    total_score = 0.0
    total_weight = 0.0
    
    for i, match in enumerate(valid_matches[:5]):  # Top 5 matches only
        weight = math.exp(-0.3 * i)  # Exponential decay: 1.0, 0.74, 0.55, 0.41, 0.30
        score = match['spec_match_percent']
        
        total_score += score * weight
        total_weight += weight
    
    weighted_avg = total_score / total_weight if total_weight > 0 else 0
    
    # Diversity bonus: reward having multiple good matches
    good_matches = len([m for m in valid_matches if m['spec_match_percent'] >= 70])
    diversity_multiplier = min(1.0 + (good_matches - 1) * 0.05, 1.15)  # Max 15% bonus
    
    final_score = weighted_avg * diversity_multiplier
    final_score = min(final_score, 100.0)  # Cap at 100
    
    return {
        "technical_score": round(final_score, 2),
        "top_match_percent": valid_matches[0]['spec_match_percent'],
        "diversity_bonus": round((diversity_multiplier - 1.0) * 100, 2),
        "matches_evaluated": len(valid_matches)
    }


# ============================================================
# TOOL 3 — Calculate Product Cost from Database
# ============================================================
def calculate_actual_cost(matches: List[Dict], product_db: pd.DataFrame) -> float:
    """
    Calculate actual product cost from database prices.
    
    Args:
        matches: List of matched products
        product_db: Product database DataFrame
    
    Returns:
        Total actual cost based on unit prices and MOQ
    """
    actual_cost = 0.0
    
    for match in matches:
        if not match:
            continue
        
        product_id = match.get('product_id') or match.get('Product_ID')
        
        if not product_id:
            continue
        
        # Find product in database
        product_row = product_db[product_db['Product_ID'] == product_id]
        
        if not product_row.empty:
            unit_price = product_row['Unit_Price_INR_per_meter'].iloc[0]
            min_qty = product_row['Min_Order_Qty_Meters'].iloc[0]
            
            # Estimate cost (assuming minimum order quantity)
            actual_cost += unit_price * min_qty
    
    return actual_cost


# ============================================================
# TOOL 4 — Score Price Competitiveness (25% weight)
# ============================================================
def score_price_competitiveness(
    estimated_price: float,
    matches: List[Dict]
) -> Dict[str, Any]:
    """
    Score price competitiveness based on cost structure analysis (0-100).
    
    Methodology:
    - Calculates actual cost from matched products
    - Evaluates pricing against ideal margin benchmark (25%)
    - Uses sigmoid function for smooth scoring curve
    - Penalizes unrealistic pricing (too cheap or too expensive)
    
    Args:
        estimated_price: Total estimated/quoted price
        matches: List of matched products
    
    Returns:
        Dict with price_score and margin analysis
    """
    if estimated_price <= 0 or not matches:
        return {
            "price_score": 0.0,
            "margin_percent": 0.0,
            "actual_cost": 0.0,
            "pricing_assessment": "invalid"
        }
    
    # Calculate actual product cost from database
    product_db = load_product_database()
    actual_cost = calculate_actual_cost(matches, product_db)
    
    if actual_cost <= 0:
        # Fallback: use estimated price with assumed cost structure
        actual_cost = estimated_price * 0.70  # Assume 30% margin
    
    # Calculate margin
    margin = (estimated_price - actual_cost) / estimated_price if estimated_price > 0 else 0
    
    # Score based on deviation from ideal margin (25%)
    margin_deviation = abs(margin - IDEAL_MARGIN)
    
    # Sigmoid scoring: best at ideal margin, degrades with deviation
    score = 100 / (1 + math.exp(10 * (margin_deviation - 0.10)))
    
    # Penalty for unrealistic pricing
    pricing_assessment = "optimal"
    if margin < 0.05:  # Less than 5% margin - too cheap, suspicious
        score *= 0.5
        pricing_assessment = "too_low"
    elif margin > 0.50:  # More than 50% margin - too expensive
        score *= 0.6
        pricing_assessment = "too_high"
    
    final_score = max(0.0, min(score, 100.0))
    
    return {
        "price_score": round(final_score, 2),
        "margin_percent": round(margin * 100, 2),
        "actual_cost": round(actual_cost, 2),
        "estimated_price": estimated_price,
        "pricing_assessment": pricing_assessment
    }


# ============================================================
# TOOL 5 — Score Delivery Capability (15% weight)
# ============================================================
def score_delivery_capability(
    matches: List[Dict],
    deadline: str = None
) -> Dict[str, Any]:
    """
    Score delivery capability based on lead times and capacity (0-100).
    
    Methodology:
    - Evaluates aggregate lead time vs tender deadline
    - Considers production capacity (min order quantities)
    - Applies urgency penalties for tight deadlines
    
    Args:
        matches: List of matched products
        deadline: RFP deadline (ISO format string)
    
    Returns:
        Dict with delivery_score and timing analysis
    """
    if not matches:
        return {
            "delivery_score": 0.0,
            "avg_lead_time_days": 0,
            "days_until_deadline": None,
            "urgency_penalty": 0.0
        }
    
    # Calculate average lead time
    lead_times = [m.get('lead_time_days', 0) for m in matches if m]
    avg_lead_time = sum(lead_times) / len(lead_times) if lead_times else 0
    
    base_score = max(0, 100 - (avg_lead_time * 1.1))
    
    # Calculate urgency penalty if deadline provided
    urgency_penalty = 0.0
    days_until_deadline = None
    
    if deadline:
        try:
            deadline_dt = datetime.fromisoformat(deadline.replace('Z', ''))
            days_until_deadline = (deadline_dt - datetime.now()).days
            
            # Penalty if lead time is close to deadline
            if days_until_deadline > 0:
                time_buffer = days_until_deadline - avg_lead_time
                
                if time_buffer < 0:  # Lead time exceeds deadline!
                    urgency_penalty = 50.0  # Major penalty
                elif time_buffer < 14:  # Less than 2 weeks buffer
                    urgency_penalty = 30.0
                elif time_buffer < 30:  # Less than 1 month buffer
                    urgency_penalty = 15.0
        
        except Exception as e:
            print(f"Warning: Could not parse deadline for delivery scoring: {e}")
    
    final_score = max(0, base_score - urgency_penalty)
    
    return {
        "delivery_score": round(final_score, 2),
        "avg_lead_time_days": round(avg_lead_time, 1),
        "days_until_deadline": days_until_deadline,
        "urgency_penalty": urgency_penalty
    }


# ============================================================
# TOOL 6 — Score Compliance (15% weight)
# ============================================================
def score_compliance(matches: List[Dict]) -> Dict[str, Any]:
    """
    Score compliance and certification status (0-100).
    
    Factors:
    - BIS Certification: 40% weight
    - Standards Compliance: 40% weight
    - Warranty Coverage: 20% weight
    
    Args:
        matches: List of matched products
    
    Returns:
        Dict with compliance_score and certification breakdown
    """
    if not matches:
        return {
            "compliance_score": 0.0,
            "bis_certified_percent": 0.0,
            "standards_compliant_percent": 0.0,
            "avg_warranty_years": 0.0
        }
    
    product_db = load_product_database()
    
    bis_count = 0
    standards_count = 0
    total_warranty = 0.0
    valid_count = 0
    
    for match in matches:
        if not match:
            continue
        
        product_id = match.get('product_id') or match.get('Product_ID')
        if not product_id:
            continue
        
        product_row = product_db[product_db['Product_ID'] == product_id]
        
        if not product_row.empty:
            if product_row['BIS_Certified'].iloc[0]:
                bis_count += 1
            
            standards = str(product_row.get('Standards_Compliance', [''])).iloc[0] if 'Standards_Compliance' in product_row else ''
            if standards and standards.lower() != 'nan' and len(standards) > 0:
                standards_count += 1
            
            warranty = product_row.get('Warranty_Years', [0]).iloc[0] if 'Warranty_Years' in product_row else 0
            total_warranty += float(warranty)
            
            valid_count += 1
    
    if valid_count == 0:
        return {
            "compliance_score": 0.0,
            "bis_certified_percent": 0.0,
            "standards_compliant_percent": 0.0,
            "avg_warranty_years": 0.0
        }
    
    bis_percent = (bis_count / valid_count) * 100
    standards_percent = (standards_count / valid_count) * 100
    avg_warranty = total_warranty / valid_count
    
    # Weighted compliance score
    compliance_score = (
        (bis_percent * 0.4) +
        (standards_percent * 0.4) +
        (min(avg_warranty / 2.0, 1.0) * 20)  # 2+ years = max 20 points
    )
    
    return {
        "compliance_score": round(compliance_score, 2),
        "bis_certified_percent": round(bis_percent, 2),
        "standards_compliant_percent": round(standards_percent, 2),
        "avg_warranty_years": round(avg_warranty, 1)
    }


# ============================================================
# TOOL 7 — Score Risk Assessment (10% weight)
# ============================================================
def score_risk_assessment(matches: List[Dict]) -> Dict[str, Any]:
    """
    Score risk factors (0-100).
    
    Factors:
    - Availability risk: Number of matching products (50%)
    - Diversity risk: Category spread (30%)
    - MOQ consistency: Variation in minimum orders (20%)
    
    Args:
        matches: List of matched products
    
    Returns:
        Dict with risk_score and risk factor breakdown
    """
    if not matches:
        return {
            "risk_score": 0.0,
            "availability_score": 0,
            "diversity_score": 0,
            "consistency_score": 0
        }
    
    # 1. Availability score (more products = lower risk)
    # Score = min(num_products * 10, 50)
    availability_score = min(len(matches) * 10, 50)
    
    # 2. Diversity score (category spread)
    categories = set(m.get('category', '') for m in matches if m)
    diversity_score = min(len(categories) * 10, 30)
    
    # 3. Consistency score (MOQ variation)
    product_db = load_product_database()
    moqs = []
    
    for match in matches:
        if not match:
            continue
        product_id = match.get('product_id') or match.get('Product_ID')
        if not product_id:
            continue
        
        product_row = product_db[product_db['Product_ID'] == product_id]
        if not product_row.empty and 'Min_Order_Qty_Meters' in product_row:
            moqs.append(product_row['Min_Order_Qty_Meters'].iloc[0])
    
    if len(moqs) > 1:
        mean_moq = sum(moqs) / len(moqs)
        variance = sum((x - mean_moq) ** 2 for x in moqs) / len(moqs)
        std_dev = math.sqrt(variance)
        cv = (std_dev / mean_moq) if mean_moq > 0 else 0
        
        consistency_score = max(0, 20 - (cv * 40))
    else:
        consistency_score = 20  # Single product or perfect consistency
    
    risk_score = availability_score + diversity_score + consistency_score
    
    return {
        "risk_score": round(risk_score, 2),
        "availability_score": round(availability_score, 2),
        "diversity_score": round(diversity_score, 2),
        "consistency_score": round(consistency_score, 2)
    }


# ============================================================
# TOOL 8 — Generate Recommendation
# ============================================================
def generate_recommendation(final_score: float, grade: str) -> str:
    """
    Generate actionable recommendation based on score and grade.
    
    Args:
        final_score: Overall score (0-100)
        grade: Letter grade (A+, A, B+, B, C, D)
    
    Returns:
        Recommendation text
    """
    recommendations = {
        'A+': f"STRONGLY RECOMMEND pursuing this RFP. Excellent match ({final_score:.1f}/100) across all criteria. High probability of winning with competitive advantage.",
        'A': f"RECOMMEND pursuing this RFP. Very good match ({final_score:.1f}/100) with strong technical alignment and competitive pricing.",
        'B+': f"CONDITIONAL RECOMMENDATION. Good opportunity ({final_score:.1f}/100) but optimize pricing or delivery timeline before submission.",
        'B': f"PROCEED WITH CAUTION. Satisfactory match ({final_score:.1f}/100) but gaps exist. Consider if strategic value justifies effort.",
        'C': f"MARGINAL OPPORTUNITY. Low score ({final_score:.1f}/100) indicates poor fit. Recommend focusing on higher-scoring RFPs.",
        'D': f"DO NOT PURSUE. Poor match ({final_score:.1f}/100) across multiple criteria. Resource investment not justified."
    }
    
    return recommendations.get(grade, f"Score: {final_score:.1f}/100. Evaluate based on strategic priorities.")


# ============================================================
# TOOL 9 — Calculate Final Score
# ============================================================
def calculate_final_score(
    matches: List[Dict],
    estimated_price: float,
    rfp_deadline: str = None
) -> Dict[str, Any]:
    """
    Calculate comprehensive final score with all components.
    
    Args:
        matches: List of matched products
        estimated_price: Total estimated price
        rfp_deadline: RFP submission deadline
    
    Returns:
        Complete scoring breakdown with recommendation
    """
    # Calculate component scores
    tech_result = score_technical_match(matches)
    price_result = score_price_competitiveness(estimated_price, matches)
    delivery_result = score_delivery_capability(matches, rfp_deadline)
    compliance_result = score_compliance(matches)
    risk_result = score_risk_assessment(matches)
    
    # Extract scores
    technical_score = tech_result['technical_score']
    price_score = price_result['price_score']
    delivery_score = delivery_result['delivery_score']
    compliance_score = compliance_result['compliance_score']
    risk_score = risk_result['risk_score']
    
    # Calculate weighted final score
    final_score = (
        technical_score * SCORING_WEIGHTS['technical_match'] +
        price_score * SCORING_WEIGHTS['price_competitiveness'] +
        delivery_score * SCORING_WEIGHTS['delivery_capability'] +
        compliance_score * SCORING_WEIGHTS['compliance'] +
        risk_score * SCORING_WEIGHTS['risk_score']
    )
    
    # Assign grade
    if final_score >= 85:
        grade = 'A+'
    elif final_score >= 75:
        grade = 'A'
    elif final_score >= 65:
        grade = 'B+'
    elif final_score >= 55:
        grade = 'B'
    elif final_score >= 45:
        grade = 'C'
    else:
        grade = 'D'
    
    recommendation = generate_recommendation(final_score, grade)
    
    return {
        'final_score': round(final_score, 2),
        'grade': grade,
        'normalized_score': round(final_score / 100, 3),
        'component_scores': {
            'technical_match': technical_score,
            'price_competitiveness': price_score,
            'delivery_capability': delivery_score,
            'compliance': compliance_score,
            'risk_score': risk_score
        },
        'weighted_contributions': {
            'technical_match': round(technical_score * SCORING_WEIGHTS['technical_match'], 2),
            'price_competitiveness': round(price_score * SCORING_WEIGHTS['price_competitiveness'], 2),
            'delivery_capability': round(delivery_score * SCORING_WEIGHTS['delivery_capability'], 2),
            'compliance': round(compliance_score * SCORING_WEIGHTS['compliance'], 2),
            'risk_assessment': round(risk_score * SCORING_WEIGHTS['risk_score'], 2)
        },
        'detailed_breakdowns': {
            'technical': tech_result,
            'price': price_result,
            'delivery': delivery_result,
            'compliance': compliance_result,
            'risk': risk_result
        },
        'recommendation': recommendation
    }


# ============================================================
# SCORING AGENT
# ============================================================
scoring_agent = LlmAgent(
    name="ScoringAgent",
    model="gemini-2.5-flash-lite",
    instruction="""
You are the Comprehensive RFP Scoring Agent.

INPUTS (from session state):
- {oem_recommendations}: List of matched products from Technical Agent
- {price_table}: Pricing breakdown from Pricing Agent
- {best_sales_rfp}: RFP details including deadline

EXECUTION WORKFLOW:
1. Extract required data:
   - matches = oem_recommendations
   - estimated_price = price_table['summary']['grand_total']
   - rfp_deadline = best_sales_rfp['submission_deadline']

2. Call calculate_final_score(matches, estimated_price, rfp_deadline)

3. Return the complete scoring result

SCORING METHODOLOGY (Research-backed framework):
Based on McKinsey procurement practices, HBR bid evaluation, ISO 9001:2015 standards.

SCORING FACTORS & WEIGHTS:
1. Technical Match (35%) - Core competency alignment
2. Price Competitiveness (25%) - Cost optimization
3. Delivery Capability (15%) - Timeline feasibility
4. Compliance & Certification (15%) - Quality assurance
5. Risk Assessment (10%) - Risk mitigation

GRADING SYSTEM:
- A+ (Excellent): 85-100 → STRONGLY RECOMMEND
- A (Very Good): 75-84 → RECOMMEND
- B+ (Good): 65-74 → CONDITIONAL (optimize)
- B (Satisfactory): 55-64 → CONDITIONAL (gaps exist)
- C (Marginal): 45-54 → CAUTION
- D (Poor): 0-44 → DO NOT PURSUE

ERROR HANDLING:
- If inputs are missing, use defaults (empty matches, 0 price)
- If database unavailable, mock data will be used automatically

STRICT RULES:
- Use ONLY the provided tools for all calculations
- DO NOT invent scores or modify weights
- Always provide detailed component breakdowns
- Handle missing data gracefully

OUTPUT to {detailed_scores}:
- Final score (0-100) and grade
- Component scores with weights applied
- Detailed breakdowns
- Actionable recommendation
""",
    tools=[
        FunctionTool(load_product_database),
        FunctionTool(calculate_actual_cost),
        FunctionTool(score_technical_match),
        FunctionTool(score_price_competitiveness),
        FunctionTool(score_delivery_capability),
        FunctionTool(score_compliance),
        FunctionTool(score_risk_assessment),
        FunctionTool(generate_recommendation),
        FunctionTool(calculate_final_score),
    ],
    output_key="detailed_scores",
    description="Comprehensive multi-factor RFP scoring with research-backed weighted evaluation."
)

root_agent = scoring_agent


# ============================================================
# TEST EXECUTION
# ============================================================
# if __name__ == "__main__":
#     print("\n" + "="*70)
#     print("Testing Comprehensive RFP Scoring Agent")
#     print("="*70 + "\n")
    
#     # Mock matched products
#     mock_matches = [
#         {
#             "product_id": "PROD_001",
#             "product_name": "11kV XLPE Cable",
#             "category": "Power Cables",
#             "spec_match_percent": 92.5,
#             "lead_time_days": 30
#         },
#         {
#             "product_id": "PROD_002",
#             "product_name": "33kV Power Cable",
#             "category": "Power Cables",
#             "spec_match_percent": 85.0,
#             "lead_time_days": 35
#         },
#         {
#             "product_id": "PROD_003",
#             "product_name": "Control Cable",
#             "category": "Control Cables",
#             "spec_match_percent": 78.5,
#             "lead_time_days": 28
#         }
#     ]
    
#     mock_estimated_price = 850000.0
#     mock_deadline = "2026-05-15T00:00:00"
    
#     print("="*70)
#     print("INPUTS:")
#     print("="*70)
#     print(f"Matched Products: {len(mock_matches)}")
#     print(f"Estimated Price: ₹{mock_estimated_price:,.2f}")
#     print(f"Deadline: {mock_deadline}\n")
    
#     # Calculate comprehensive score
#     print("Calculating comprehensive RFP score...\n")
#     score_result = calculate_final_score(
#         matches=mock_matches,
#         estimated_price=mock_estimated_price,
#         rfp_deadline=mock_deadline
#     )
    
#     print("="*70)
#     print("SCORING RESULTS")
#     print("="*70)
#     print(f"Final Score: {score_result['final_score']}/100")
#     print(f"Grade: {score_result['grade']}")
#     print(f"Normalized Score: {score_result['normalized_score']}")
#     print()
    
#     print("─"*70)
#     print("COMPONENT SCORES (Raw):")
#     print("─"*70)
#     for component, score in score_result['component_scores'].items():
#         weight = SCORING_WEIGHTS[component] * 100
#         print(f"  {component.replace('_', ' ').title():30s}: {score:6.2f}/100 (weight: {weight:.0f}%)")
#     print()
    
#     print("─"*70)
#     print("WEIGHTED CONTRIBUTIONS:")
#     print("─"*70)
#     for component, contribution in score_result['weighted_contributions'].items():
#         print(f"  {component.replace('_', ' ').title():30s}: {contribution:6.2f} points")
#     print()
    
#     print("="*70)
#     print("RECOMMENDATION:")
#     print("="*70)
#     print(f"{score_result['recommendation']}")
#     print("="*70 + "\n")
