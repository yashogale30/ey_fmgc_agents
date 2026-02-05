from google.adk.agents import LlmAgent, SequentialAgent, ParallelAgent
from google.adk.tools import FunctionTool

# Import sub-agents (in production, ADK auto-discovers these)
from sales_agent.agent import sales_agent
from technical_agent.agent import technical_agent
from pricing_agent.agent import pricing_agent

# ============================================================
# MASTER AGENT — Prepares briefs for Technical and Pricing Agents
# ============================================================
def prepare_briefs(rfp_summary: dict) -> dict:
    """Reads the RFP and creates two tailored briefs:
      - technical_brief: product scope & specs (for Technical Agent)
      - pricing_brief: tests & acceptance criteria (for Pricing Agent)
    Args:
        rfp_summary: The selected RFP info from Sales Agent
    Returns:
        Dict with both briefs."""
    # STUB: In production, parse the actual RFP document here
    return {
        "technical_brief": {
            "rfp_title": rfp_summary["selected_rfp"]["title"],
            "rfp_url": rfp_summary["selected_rfp"]["url"],
            "scope": "Extract all products in scope of supply and their specs"
        },
        "pricing_brief": {
            "tests_required": ["thermal_cycling", "vibration_test",
                          "electrical_acceptance", "ip_rating_test"],
            "acceptance_criteria": "All units must pass 100% acceptance testing before shipment"
        }
    }

master_agent = LlmAgent(
    name="MasterAgent",
    model="gemini-2.0-flash",
    instruction="""You are the Master Agent orchestrator.
    The Sales Agent has selected an RFP (available in session state as {rfp_summary}).
    Use the prepare_briefs tool to create:
      - A technical_brief for the Technical Agent (product specs focus)
      - A pricing_brief for the Pricing Agent (tests & acceptance focus)
    Write both briefs to session state so downstream agents can read them.""",
    tools=[FunctionTool(prepare_briefs)],
    output_key="briefs_ready",  # Signal that briefs are in state
    description="Reads the selected RFP and prepares tailored briefs for Technical and Pricing agents."
)

# ============================================================
# CONSOLIDATOR — Final step: merges all outputs into RFP response
# ============================================================
consolidator_agent = LlmAgent(
    name="ConsolidatorAgent",
    model="gemini-2.0-flash",
    instruction="""You are the final consolidation step. Combine all outputs into a complete RFP response.
    
    Read from session state:
    - {rfp_summary}: The selected RFP details
    - {oem_recommendations}: OEM SKUs and Spec Match % from Technical Agent
    - {price_table}: Unit prices and test costs from Pricing Agent
    
    Produce a final consolidated RFP response containing:
    1. RFP title and due date
    2. For each product: recommended OEM SKU, Spec Match %, unit price
    3. All required test costs
    4. Total material cost, total services cost, and grand total""",
    output_key="final_rfp_response",
    description="Consolidates all agent outputs into the final RFP response document."
)

# ============================================================
# PARALLEL GROUP — Technical + Pricing run concurrently
# ============================================================
parallel_analysis = ParallelAgent(
    name="ParallelAnalysis",
    sub_agents=[technical_agent, pricing_agent],
    description="Runs Technical and Pricing agents concurrently."
)

# ============================================================
# ROOT AGENT — The full sequential pipeline
# ============================================================
root_agent = SequentialAgent(
    name="RFPResponsePipeline",
    sub_agents=[
        sales_agent,          # Step 1: Scan & select RFP
        master_agent,         # Step 2: Prepare briefs for downstream
        parallel_analysis,    # Step 3: Tech + Pricing run in parallel
        consolidator_agent,   # Step 4: Merge everything → final response
    ],
    description="Full RFP response pipeline: Scan → Brief → Analyze → Consolidate."
)