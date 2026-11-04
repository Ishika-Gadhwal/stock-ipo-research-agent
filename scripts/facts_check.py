"""Free, local check on the cached TMPV report. No LLM, no search credits.

The first run extracts text from all 585 pages (about 90 seconds) and saves it,
so later runs are instant.
"""

from stock_ipo_research_agent.models import CompanyCandidate
from stock_ipo_research_agent.tools.financial_facts import extract_pl_facts, format_facts

URL = (
    "https://nsearchives.nseindia.com/annual_reports/"
    "AR_29395_TMPV_2025_2026_A_21445169_15062026215933.pdf"
)
company = CompanyCandidate(
    legal_name="Tata Motors Passenger Vehicles Limited",
    nse_symbol="TMPV",
    bse_code="500570",
    isin="INE155A01022",
    business="Passenger vehicles",
    source_url=URL,
)

facts = extract_pl_facts(URL, company)
# Escape non-ASCII characters so the Windows console cannot crash on them.
print(format_facts(facts).encode("ascii", "backslashreplace").decode("ascii"))