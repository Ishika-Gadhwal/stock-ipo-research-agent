import io

import pdfplumber
import requests

URL = (
    "https://nsearchives.nseindia.com/annual_reports/"
    "AR_29395_TMPV_2025_2026_A_21445169_15062026215933.pdf"
)
TERMS = ["INE155A01022", "TMPV", "Tata Motors Passenger Vehicles"]

r = requests.get(URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
print("status:", r.status_code, "| MB:", round(len(r.content) / 1e6, 1),
      "| type:", r.headers.get("content-type"))

if r.ok:
    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        print("pages:", len(pdf.pages))
        for term in TERMS:
            hits = [
                i + 1
                for i, page in enumerate(pdf.pages[:15])
                if term.lower() in (page.extract_text() or "").lower()
            ]
            print(f"{term!r} found on pages (first 15 only):", hits or "NOT FOUND")