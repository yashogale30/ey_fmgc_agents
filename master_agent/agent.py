from google.adk.agents import LlmAgent, SequentialAgent, ParallelAgent
from google.adk.tools import FunctionTool

from sales_agent.agent import sales_agent
from technical_agent.agent import technical_agent
from pricing_agent.agent import pricing_agent

# ============================================================
# MASTER AGENT TOOL — Prepare Technical & Pricing Briefs
# ============================================================
def prepare_briefs(best_sales_rfp: dict) -> dict:
    """
    Reads the selected RFP and creates two tailored briefs:
    - technical_brief: product scope & technical specs
    - pricing_brief: tests, acceptance, warranty, compliance
    """

    sections = best_sales_rfp.get("sections", {})

    technical_brief = {
        "rfp_title": best_sales_rfp.get("project_name"),
        "rfp_reference": best_sales_rfp.get("rfp_reference"),
        "category": best_sales_rfp.get("category"),
        "scope_of_supply": sections.get("2. Scope of Supply", ""),
        "technical_specs": sections.get("3. Technical Specifications", ""),
        "delivery_timeline": sections.get("5. Delivery Timeline", "")
    }

    pricing_brief = {
        "rfp_title": best_sales_rfp.get("project_name"),
        "submission_deadline": best_sales_rfp.get("submission_deadline"),
        "tests_and_acceptance": sections.get("4. Acceptance & Test Requirements", ""),
        "evaluation_criteria": sections.get("7. Evaluation Criteria", ""),
        "warranty_and_pricing_terms": sections.get("6. Pricing Details", "")
    }

    return {
        "technical_brief": technical_brief,
        "pricing_brief": pricing_brief
    }


# ============================================================
# MASTER AGENT — Orchestrator
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
3. Write both briefs to session state.

Do NOT analyze specifications or pricing yourself.
Do NOT invent missing information.
""",
    tools=[FunctionTool(prepare_briefs)],
    output_key="briefs_ready",
    description="Reads the selected RFP and prepares technical and pricing briefs."
)

# ============================================================
# CONSOLIDATOR AGENT — Final Merger
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
1. RFP title, reference number, and submission deadline
2. For each product:
   - Recommended OEM SKU
   - Spec Match %
   - Unit price
3. All required test and certification costs
4. Total material cost
5. Total testing/services cost
6. Grand total

Output a structured, professional response ready for proposal generation.
""",
    output_key="final_rfp_response",
    description="Consolidates technical and pricing outputs into the final RFP response."
)

# ============================================================
# PARALLEL ANALYSIS — Technical + Pricing
# ============================================================
parallel_analysis = ParallelAgent(
    name="ParallelAnalysis",
    sub_agents=[
        technical_agent,   # reads {technical_brief}, outputs {oem_recommendations}
        pricing_agent      # reads {pricing_brief}, outputs {price_table}
    ],
    description="Runs Technical and Pricing agents in parallel."
)

# ============================================================
# ROOT PIPELINE — End-to-End Flow
# ============================================================
root_agent = SequentialAgent(
    name="RFPResponsePipeline",
    sub_agents=[
        sales_agent,        # Step 1: Scrape + select best RFP → {best_sales_rfp}
        master_agent,       # Step 2: Prepare briefs → {technical_brief}, {pricing_brief}
        parallel_analysis,  # Step 3: Technical + Pricing
        consolidator_agent  # Step 4: Final merge
    ],
    description="End-to-end RFP automation pipeline: Scan → Brief → Analyze → Consolidate."
)
