import json
import time
from pathlib import Path

import pdfplumber
import requests

URL = (
    "https://nsearchives.nseindia.com/annual_reports/"
    "AR_29395_TMPV_2025_2026_A_21445169_15062026215933.pdf"
)
CACHE = Path("cache")
CACHE.mkdir(exist_ok=True)
pdf_path = CACHE / "tmpv_ar_2025_26.pdf"

if not pdf_path.exists():
    r = requests.get(URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=120)
    r.raise_for_status()
    pdf_path.write_bytes(r.content)
    print("downloaded")

start = time.time()
pages = []
with pdfplumber.open(pdf_path) as pdf:
    for page in pdf.pages:
        pages.append(page.extract_text() or "")
print("extraction seconds:", round(time.time() - start))
print("pages with no text:", sum(1 for t in pages if not t.strip()))

(CACHE / "tmpv_ar_2025_26.json").write_text(json.dumps(pages), encoding="utf-8")

KEYWORDS = [
    "Consolidated Statement of Profit and Loss",
    "Consolidated Balance Sheet",
    "Consolidated Statement of Cash Flows",
    "Standalone Balance Sheet",
    "Revenue from operations",
]
for kw in KEYWORDS:
    hits = [i + 1 for i, t in enumerate(pages) if kw.lower() in t.lower()]
    print(f"{kw!r}: {len(hits)} pages, first 15: {hits[:15]}")