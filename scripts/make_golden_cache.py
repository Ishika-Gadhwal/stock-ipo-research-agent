"""Free. Recreates cache/tmpv_ar_2025_26.json, the file the two golden tests read.

Downloads the TMPV FY2025-26 annual report from NSE once (no API keys, no search
credits) and saves its page text. The first run takes about 90 seconds.
cache/ is gitignored, so each machine makes its own copy.
"""

import json
from pathlib import Path

from stock_ipo_research_agent.models import CompanyCandidate
from stock_ipo_research_agent.tools.financial_facts import VerifiedReportLoader

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

pages, _, _ = VerifiedReportLoader().load(URL, company)
out = Path("cache") / "tmpv_ar_2025_26.json"
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(pages), encoding="utf-8")
print(f"Saved {len(pages)} pages to {out}")