from google.adk.agents import LlmAgent, SequentialAgent, ParallelAgent
from google.adk.tools import FunctionTool

# Import the base agents
from sales_agent.agent import sales_agent, scrap, select_best_rfp # <--- IMPORT ADDED
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
    
    if not best_sales_rfp or best_sales_rfp.get("error"):
        return {
            "error": "Invalid or missing RFP data",
            "technical_brief": None,
            "pricing_brief": None
        }
    
    sections = best_sales_rfp.get("sections", {})
    
    # Ensure sections dict exists, fallback to flat keys if missing
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
You are the Master Agent orchestrator. Your goal is to prepare technical and pricing briefs using the prepare_briefs tool.

To do this, you need the 'best_sales_rfp' data.

INSTRUCTIONS:
1. Check the conversation history to see if the Sales Agent has already provided the selected RFP data (best_sales_rfp).
2. If the data is NOT present in the history (or if there was an error), you MUST generate it yourself by calling the following tools in order:
   a. Call scrap() to get tenders.
   b. Call select_best_rfp(scraped_data) to select the best one.
3. Once you have the RFP data (either from history or by calling tools), call the prepare_briefs tool with this data.

IMPORTANT:
- Do NOT invent RFP data. Use tools if data is missing.
- The final output should be the result of the prepare_briefs tool.
""",
    tools=[
        FunctionTool(prepare_briefs),
        FunctionTool(scrap),             # <--- TOOL ADDED
        FunctionTool(select_best_rfp)    # <--- TOOL ADDED
    ],
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

Read the following from session state or conversation history:
- best_sales_rfp: Selected RFP details
- oem_recommendations: OEM SKUs and Spec Match % from Technical Agent
- price_table: Unit prices and test costs from Pricing Agent

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
# ROOT PIPELINE – End-to-End Flow
# ============================================================
root_agent = SequentialAgent(
    name="RFPResponsePipeline",
    sub_agents=[
        sales_agent,        # Step 1: Scrape + select best RFP
        master_agent,       # Step 2: Prepare briefs (Now handles missing data)
        technical_agent,    # Step 3: Technical matching
        pricing_agent,      # Step 4: Pricing calculation
        consolidator_agent  # Step 5: Final merge
    ],
    description="End-to-end RFP automation pipeline: Scan -> Brief -> Technical -> Pricing -> Consolidate."
)