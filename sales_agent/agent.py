from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
import requests
from datetime import datetime, timedelta
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ---------------- HTTP Session with Retry ---------------- #
session = requests.Session()
retries = Retry(
    total=3,
    backoff_factor=2,
    status_forcelist=[500, 502, 503, 504],
)
session.mount("https://", HTTPAdapter(max_retries=retries))

SCRAPER_API = "https://ey-fmcg.onrender.com/scrape?months=1"

# ---------------- Date Parser ---------------- #
def parse_date(date_str):
    """
    Parse date from multiple formats.
    
    Args:
        date_str: Date string in various formats
    
    Returns:
        datetime object or None if parsing fails
    """
    if not date_str:
        return None
    
    date_str = str(date_str).strip()
    
    formats = [
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%d-%m-%Y",
        "%Y/%m/%d"
    ]
    
    for fmt in formats:
        try:
            clean_date = date_str.replace("Z", "")
            return datetime.strptime(clean_date, fmt)
        except ValueError:
            continue
    
    return None

# -------------------------------
# Tool 1: Scrape and Filter RFPs
# -------------------------------
def scrap() -> dict:
    """
    Fetches live scraped tenders from API and filters for upcoming opportunities.
    Returns filtered RFPs within the next 3 months.
    You MUST call this tool before selecting or reasoning about RFPs.
    
    Returns:
        dict with 'data' key containing list of RFPs, or 'error' key if failed
    """
    print("🔍 Fetching live scraped tenders from API...")
    
    try:
        response = session.get(SCRAPER_API, timeout=120)
        
        if response.status_code != 200:
            error_msg = f"API returned status {response.status_code}"
            print(f"⚠️ Scraper API failed: {error_msg}")
            return {
                "data": [],
                "error": error_msg,
                "status": "api_error"
            }
        
        data = response.json()
        
    except requests.exceptions.Timeout:
        print("⚠️ Scraper API timeout - server took too long to respond")
        return {
            "data": [],
            "error": "API timeout",
            "status": "timeout"
        }
    
    except requests.exceptions.ConnectionError:
        print("⚠️ Scraper API unreachable - connection failed")
        return {
            "data": [],
            "error": "Connection failed",
            "status": "connection_error"
        }
    
    except Exception as e:
        print(f"⚠️ Unexpected error: {e}")
        return {
            "data": [],
            "error": str(e),
            "status": "error"
        }
    
    rfps = data.get("data", [])
    
    if not rfps:
        print("⚠️ No tenders returned by scraper")
        return {
            "data": [],
            "status": "no_data"
        }
    
    print(f"✓ Received {len(rfps)} tenders from API")
    
    # Filter for upcoming tenders (next 3 months)
    today = datetime.today()
    three_months = today + timedelta(days=90)
    upcoming = []
    
    for rfp in rfps:
        # Parse submission deadline
        due_date = parse_date(rfp.get("submission_deadline") or rfp.get("submissionDeadline"))
        
        if not due_date:
            # Skip RFPs without valid deadline
            continue
        
        # Only include RFPs with deadlines between now and 3 months from now
        if not (today <= due_date <= three_months):
            continue
        
        sections = rfp.get("sections", {})
        
        upcoming.append({
            "projectName": rfp.get("project_name") or rfp.get("projectName", ""),
            "project_name": rfp.get("project_name") or rfp.get("projectName", ""),
            "issued_by": rfp.get("issued_by", ""),
            "category": rfp.get("category", ""),
            "submissionDeadline": rfp.get("submission_deadline") or rfp.get("submissionDeadline", ""),
            "submission_deadline": rfp.get("submission_deadline") or rfp.get("submissionDeadline", ""),
            "rfp_reference": rfp.get("rfp_reference", ""),
            "project_overview": sections.get("1. Project Overview", ""),
            "scope_of_supply": sections.get("2. Scope of Supply", ""),
            "technical_specifications": sections.get("3. Technical Specifications", ""),
            "testing_requirements": sections.get("4. Acceptance & Test Requirements", ""),
            "delivery_timeline": sections.get("5. Delivery Timeline", ""),
            "pricing_details": sections.get("6. Pricing Details", ""),
            "evaluation_criteria": sections.get("7. Evaluation Criteria", ""),
            "submission_format": sections.get("8. Submission Format", ""),
            "sections": sections 
        })
    
    if not upcoming:
        print("⚠️ No valid tenders found after filtering (all outside 3-month window or missing deadlines)")
        return {
            "data": [],
            "status": "no_upcoming_rfps"
        }
    
    print(f"✓ Shortlisted {len(upcoming)} tenders within next 3 months")
    return {
        "data": upcoming,
        "status": "success"
    }

# -------------------------------
# Tool 2: Select Best RFP
# -------------------------------
def select_best_rfp(scraped_data: dict) -> dict:
    """
    Selects the single best RFP from scraped JSON data based on scoring.
    Input MUST be the output of the scrap tool.
    
    Args:
        scraped_data: Output from scrap() tool containing 'data' key with RFP list
    
    Returns:
        Best scoring RFP dict, or error dict if no RFPs available
    """
    # Validate input
    if not scraped_data:
        print("⚠️ No scraped data provided")
        return {"error": "no_input_data"}
    
    if scraped_data.get("error"):
        print(f"⚠️ Scraper returned error: {scraped_data['error']}")
        return {"error": scraped_data["error"]}
    
    rfps = scraped_data.get("data", [])
    
    if not rfps:
        print("⚠️ No RFPs available for selection")
        return {"error": "no_rfps_found"}
    
    print(f"📊 Scoring {len(rfps)} RFPs...")
    
    SALES_KEYWORDS = [
        "power", "cable", "electrical", "supply",
        "infrastructure", "metro", "substation", "transformer",
        "hvac", "switchgear", "transmission", "distribution"
    ]
    
    def score(rfp: dict) -> float:
        """
        Calculate relevance score for an RFP.
        
        Scoring factors:
        - Keyword relevance (max 50 points)
        - Deadline urgency (max 30 points)
        - Category match (max 20 points)
        """
        s = 0.0
        
        # Combine text fields for keyword matching
        text = " ".join([
            str(rfp.get("projectName", "")),
            str(rfp.get("project_name", "")),
            str(rfp.get("project_overview", "")),
            str(rfp.get("scope_of_supply", "")),
            str(rfp.get("category", ""))
        ]).lower()
        
        # 1. Keyword relevance scoring (max 50 points)
        keyword_count = sum(1 for k in SALES_KEYWORDS if k in text)
        s += min(keyword_count * 5, 50)  # 5 points per keyword, max 50
        
        # 2. Deadline urgency scoring (max 30 points)
        try:
            due_date = parse_date(rfp.get("submissionDeadline") or rfp.get("submission_deadline"))
            if due_date:
                days_left = (due_date - datetime.now()).days
                # More points for closer deadlines (more urgent)
                # 30 points for <7 days, scaling down to 0 for >90 days
                urgency_score = max(0, 30 - (days_left * 0.33))
                s += urgency_score
        except Exception as e:
            print(f"  Warning: Could not parse deadline for scoring: {e}")
        
        # 3. Category bonus (20 points for high-priority categories)
        category = str(rfp.get("category", "")).lower()
        if any(term in category for term in ["power", "electrical", "cable", "infrastructure"]):
            s += 20
        
        return round(s, 2)
    
    # Score all RFPs
    scored = []
    for rfp in rfps:
        rfp_score = score(rfp)
        scored.append({
            **rfp,
            "sales_score": rfp_score
        })
    
    # Sort by score (descending)
    scored.sort(key=lambda x: x["sales_score"], reverse=True)
    
    # Select best RFP
    best = scored[0]
    
    print(f"🏆 Selected best RFP: {best.get('projectName') or best.get('project_name')}")
    print(f"   Score: {best.get('sales_score'):.2f}")
    print(f"   Category: {best.get('category')}")
    print(f"   Deadline: {best.get('submissionDeadline') or best.get('submission_deadline')}")
    
    return best

# -------------------------------
# Sales Agent Definition
# -------------------------------
sales_agent = LlmAgent(
    name="SalesAgent",
    model="gemini-2.5-flash-lite",
    instruction="""
You are an autonomous Sales Agent for RFP selection.

STRICT EXECUTION RULES:
1. ALWAYS call the `scrap` tool first to fetch and filter RFP data
2. ALWAYS pass the scrap tool's output to `select_best_rfp` tool
3. You MUST call BOTH tools in sequence - no exceptions
4. Output ONLY the final selected RFP dictionary
5. Never say you cannot access external data - you have tools for that

Your workflow:
Step 1: Call scrap() to fetch filtered RFP opportunities from the API
Step 2: Call select_best_rfp(scraped_data) to identify the top opportunity
Step 3: Return the selected RFP to session state

ERROR HANDLING:
- If scrap() returns an error, note the error but still attempt selection
- If no RFPs found, return an error dict clearly stating the issue
- If API is down, clearly communicate that to downstream agents

No explanations. No commentary. Execute the workflow.
""",
    tools=[
        FunctionTool(scrap),
        FunctionTool(select_best_rfp)
    ],
    output_key="best_sales_rfp",
    description="Fetches RFPs from API and selects the best sales opportunity."
)

root_agent = sales_agent

# -------------------------------
# Test Execution
# -------------------------------
# if __name__ == "__main__":
#     print("\n" + "="*50)
#     print("Testing Sales Agent Pipeline")
#     print("="*50 + "\n")
    
#     # Test scraping
#     print("=" * 50)
#     print("STEP 1: Scraping RFPs")
#     print("=" * 50 + "\n")
    
#     result = scrap()
    
#     if result.get("status") == "success":
#         print(f"\n✓ Successfully scraped {len(result.get('data', []))} RFPs\n")
#     else:
#         print(f"\n✗ Scraping failed: {result.get('error', 'Unknown error')}")
#         print(f"   Status: {result.get('status', 'unknown')}\n")
    
#     # Test selection
#     print("=" * 50)
#     print("STEP 2: Selecting Best RFP")
#     print("=" * 50 + "\n")
    
#     if result.get('data'):
#         best = select_best_rfp(result)
        
#         if not best.get("error"):
#             print("\n" + "="*50)
#             print("BEST RFP SELECTED:")
#             print("="*50)
#             print(f"Project: {best.get('projectName') or best.get('project_name')}")
#             print(f"Issued by: {best.get('issued_by')}")
#             print(f"Category: {best.get('category')}")
#             print(f"Deadline: {best.get('submissionDeadline') or best.get('submission_deadline')}")
#             print(f"Score: {best.get('sales_score')}")
#             print(f"Reference: {best.get('rfp_reference')}")
#             print("="*50 + "\n")
#         else:
#             print(f"✗ Selection failed: {best.get('error')}\n")
#     else:
#         print("⚠️ No RFPs available for selection\n")
        
#     print("="*50)
#     print("Test Complete")
#     print("="*50 + "\n")
