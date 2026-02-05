from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
import requests
from datetime import datetime


def scrap(rfp_url: str) -> dict:
    """
    Scrapes RFP data from the government RFP scraper service.
    """
    params = {"months": 3}

    response = requests.get(
    "https://ey-fmcg.onrender.com/scrape",
    params=params,
    timeout=(10, 60)
    )

    response.raise_for_status()
    return response.json()


def select_best_rfp(scraped_data: dict) -> dict:
    """
    Sales-oriented selection of the best RFP.
    """
    rfps = scraped_data.get("data", [])
    if not rfps:
        return {"error": "no_rfps_found"}

    SALES_KEYWORDS = [
        "power", "cable", "electrical", "supply",
        "infrastructure", "metro", "substation"
    ]

    def score(rfp: dict) -> float:
        s = 0.0

        text = (
            rfp.get("project_name", "") +
            " " +
            rfp.get("sections", {}).get("1. Project Overview", "")
        ).lower()

        # Sales relevance
        for k in SALES_KEYWORDS:
            if k in text:
                s += 5

        # Deadline urgency (sales priority)
        try:
            deadline = datetime.strptime(
                rfp["submission_deadline"], "%d/%m/%Y"
            )
            days_left = (deadline - datetime.now()).days
            s += max(0, 20 - days_left)
        except Exception:
            pass

        return s

    scored = [
        {**rfp, "sales_score": score(rfp)}
        for rfp in rfps
    ]

    scored.sort(key=lambda x: x["sales_score"], reverse=True)
    return scored[0]   # best RFP only


# --- Sales Agent Definition ---
sales_agent = LlmAgent(
    name="SalesAgent",
    model="gemini-2.5-flash-lite",  # lite is enough
    instruction="""
You are an autonomous Sales Agent.

You do NOT ask the user any questions.

Your task:
1. Automatically scrape the government RFP website using the scrap tool.
2. Select the single best RFP using the select_best_rfp tool.
3. Output ONLY the selected RFP as a structured dictionary.

Do NOT ask for URLs.
Do NOT request clarification.
Do NOT interact with the user.
""",
    tools=[
        FunctionTool(scrap),
        FunctionTool(select_best_rfp)
    ],
    output_key="best_sales_rfp",
    description="Scrapes government RFPs and selects the best one."
)


root_agent = sales_agent


# if __name__ == "__main__":
#     result = scrap("https://ey-fmcg.onrender.com/scrape")
#     best = select_best_rfp(result)
#     print(best)
