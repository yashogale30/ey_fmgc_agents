from google.adk.agents import LlmAgent, SequentialAgent, ParallelAgent
from google.adk.tools import FunctionTool

from sales_agent.agent import sales_agent
from technical_agent.agent import technical_agent
from pricing_agent.agent import pricing_agent

# ============================================================
# MASTER AGENT TOOL – Prepare Technical & Pricing Briefs
# ============================================================
def prepare_briefs(best_sales_rfp: dict) -> dict:
    """
    Reads the selected RFP and creates two tailored briefs:
    - technical_brief: product scope & technical specs
    - pricing_brief: tests, acceptance, warranty, compliance
    
    Returns both briefs in a structured format for session state.
    """
    
    # Validate input
    if not best_sales_rfp or best_sales_rfp.get("error"):
        return {
            "error": "Invalid or missing RFP data",
            "technical_brief": None,
            "pricing_brief": None
        }
    
    sections = best_sales_rfp.get("sections", {})
    
    # If sections is missing, try to extract from flattened structure
    if not sections:
        sections = {
            "2. Scope of Supply": best_sales_rfp.get("scope_of_supply", ""),
            "3. Technical Specifications": best_sales_rfp.get("technical_specifications", ""),
            "4. Acceptance & Test Requirements": best_sales_rfp.get("testing_requirements", ""),
            "5. Delivery Timeline": best_sales_rfp.get("delivery_timeline", ""),
            "6. Pricing Details": best_sales_rfp.get("pricing_details", ""),
            "7. Evaluation Criteria": best_sales_rfp.get("evaluation_criteria", "")
        }

    technical_brief = {
        "rfp_title": best_sales_rfp.get("project_name") or best_sales_rfp.get("projectName", ""),
        "rfp_reference": best_sales_rfp.get("rfp_reference", ""),
        "category": best_sales_rfp.get("category", ""),
        "scope_of_supply": sections.get("2. Scope of Supply", ""),
        "technical_specifications": sections.get("3. Technical Specifications", ""),
        "delivery_timeline": sections.get("5. Delivery Timeline", "")
    }

    pricing_brief = {
        "rfp_title": best_sales_rfp.get("project_name") or best_sales_rfp.get("projectName", ""),
        "submission_deadline": best_sales_rfp.get("submission_deadline") or best_sales_rfp.get("submissionDeadline", ""),
        "tests_and_acceptance": sections.get("4. Acceptance & Test Requirements", ""),
        "evaluation_criteria": sections.get("7. Evaluation Criteria", ""),
        "warranty_and_pricing_terms": sections.get("6. Pricing Details", "")
    }

    return {
        "technical_brief": technical_brief,
        "pricing_brief": pricing_brief,
        "status": "success"
    }


# ============================================================
# MASTER AGENT – Orchestrator
# ============================================================
master_agent = LlmAgent(
    name="MasterAgent",
    model="gemini-2.5-flash-lite",
    instruction="""
You are the Master Agent orchestrator.

The Sales Agent has already selected the best RFP.
You will receive it in session state as {best_sales_rfp}.

Your responsibilities:
1. Read and understand the full RFP document.
2. Call the prepare_briefs tool to create:
   - technical_brief (for Technical Agent)
   - pricing_brief (for Pricing Agent)
3. The tool will return both briefs - ensure they are properly stored.

IMPORTANT:
- Verify that best_sales_rfp contains valid data before processing
- Check that the prepare_briefs output contains both technical_brief and pricing_brief
- Do NOT analyze specifications or pricing yourself
- Do NOT invent missing information
- If data is missing, report it clearly

OUTPUT:
Return the complete output from prepare_briefs, which includes:
- technical_brief
- pricing_brief
- status
""",
    tools=[FunctionTool(prepare_briefs)],
    output_key="master_output",
    description="Reads the selected RFP and prepares technical and pricing briefs."
)

# ============================================================
# CONSOLIDATOR AGENT – Final Merger
# ============================================================
consolidator_agent = LlmAgent(
    name="ConsolidatorAgent",
    model="gemini-2.5-flash-lite",
    instruction="""
You are the final consolidation agent.

Read the following from session state:
- {best_sales_rfp}: Selected RFP details
- {oem_recommendations}: OEM SKUs and Spec Match % from Technical Agent
- {price_table}: Unit prices and test costs from Pricing Agent

Produce a final consolidated RFP response containing:

HEADER SECTION:
1. RFP title and reference number
2. Issued by
3. Submission deadline
4. Category

TECHNICAL RECOMMENDATIONS:
For each recommended product:
- Product Name
- OEM SKU / Product ID
- Specification Match %
- Key specifications (voltage, conductor, insulation)
- BIS Certification status

PRICING BREAKDOWN:
1. Material Costs:
   - Individual product costs with quantities
   - Subtotal (before margin)
   - Margin percentage applied
   - Material total (after margin)

2. Testing & Certification Costs:
   - Individual test costs
   - Testing subtotal

3. FINAL TOTALS:
   - Total Material Cost
   - Total Testing Cost
   - GRAND TOTAL

ERROR HANDLING:
- If oem_recommendations is empty, note "No matching products found"
- If price_table is missing, note "Pricing calculation failed"
- Always provide what data is available

Output a structured, professional response ready for proposal generation.
""",
    output_key="final_rfp_response",
    description="Consolidates technical and pricing outputs into the final RFP response."
)

# ============================================================
# PARALLEL ANALYSIS – Technical + Pricing
# ============================================================
parallel_analysis = ParallelAgent(
    name="ParallelAnalysis",
    sub_agents=[
        technical_agent,   # reads {technical_brief}, outputs {oem_recommendations}
        pricing_agent      # reads {pricing_brief} AND {oem_recommendations}, outputs {price_table}
    ],
    description="Runs Technical and Pricing agents in parallel."
)

# ============================================================
# ROOT PIPELINE – End-to-End Flow
# ============================================================
root_agent = SequentialAgent(
    name="RFPResponsePipeline",
    sub_agents=[
        sales_agent,        # Step 1: Scrape + select best RFP → {best_sales_rfp}
        master_agent,       # Step 2: Prepare briefs → {master_output} containing briefs
        parallel_analysis,  # Step 3: Technical + Pricing (reads from master_output)
        consolidator_agent  # Step 4: Final merge
    ],
    description="End-to-end RFP automation pipeline: Scan → Brief → Analyze → Consolidate."
)


# ============================================================
# TEST EXECUTION
# ============================================================
if __name__ == "__main__":
    print("\n" + "="*60)
    print("Testing Master Agent Brief Preparation")
    print("="*60 + "\n")
    
    # Mock RFP data (as would come from Sales Agent)
    mock_rfp = {
        "projectName": "Metro Phase 3 Power Cable Supply",
        "project_name": "Metro Phase 3 Power Cable Supply",
        "issued_by": "Delhi Metro Rail Corporation",
        "category": "Power Cables",
        "submissionDeadline": "2026-04-15T00:00:00",
        "submission_deadline": "2026-04-15T00:00:00",
        "rfp_reference": "DMRC/2026/PC/001",
        "sections": {
            "1. Project Overview": "Supply of power cables for metro expansion",
            "2. Scope of Supply": "11kV XLPE cables, 3-core, copper conductor",
            "3. Technical Specifications": "Voltage: 11kV, Conductor: Copper, Insulation: XLPE, Cores: 3, Standards: IS 7098",
            "4. Acceptance & Test Requirements": "High voltage test, Insulation resistance test, Fire resistance test",
            "5. Delivery Timeline": "90 days from order",
            "6. Pricing Details": "Per meter pricing, 2-year warranty required",
            "7. Evaluation Criteria": "Technical 40%, Price 35%, Delivery 25%"
        }
    }
    
    print("Step 1: Testing brief preparation...")
    result = prepare_briefs(mock_rfp)
    
    if result.get("status") == "success":
        print("✓ Briefs prepared successfully\n")
        
        print("="*60)
        print("TECHNICAL BRIEF:")
        print("="*60)
        for key, value in result["technical_brief"].items():
            print(f"{key}: {value[:100] if isinstance(value, str) and len(value) > 100 else value}")
        
        print("\n" + "="*60)
        print("PRICING BRIEF:")
        print("="*60)
        for key, value in result["pricing_brief"].items():
            print(f"{key}: {value[:100] if isinstance(value, str) and len(value) > 100 else value}")
        
        print("\n" + "="*60)
        print("✓ Master Agent test completed successfully")
        print("="*60 + "\n")
    else:
        print(f"✗ Error: {result.get('error')}")
