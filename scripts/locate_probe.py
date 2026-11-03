import json
import re
from pathlib import Path

TITLES = [
    "balance sheet",
    "statement of profit and loss",
    "statement of cash flows",
    "cash flow statement",
    "statement of changes in equity",
]

files = [Path("cache/tmpv_ar_2025_26.json")]
if not files[0].exists():
    raise SystemExit("cache/tmpv_ar_2025_26.json not found.")

pages = json.loads(files[0].read_text(encoding="utf-8"))
print("Using:", files[0].name, "| pages:", len(pages))

for number, text in enumerate(pages, start=1):
    flat = re.sub(r"\s+", " ", text).casefold()
    head = flat[:400]
    hits = [t for t in TITLES if t in head]
    if hits and "in crore" in flat:
        print(f"PDF {number:>3} | {hits} | {ascii(head[:90])}")