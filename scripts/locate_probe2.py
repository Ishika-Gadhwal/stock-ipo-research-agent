import json
import re
from pathlib import Path

pages = json.loads(Path("cache/tmpv_ar_2025_26.json").read_text(encoding="utf-8"))

TITLE = re.compile(
    r"^(consolidated\s+)?"
    r"(balance sheet|statement of profit and loss|statement of cash flows|statement of changes in equity)\b"
)

print("== Pages whose text STARTS with a statement title ==")
for number, text in enumerate(pages, start=1):
    flat = re.sub(r"\s+", " ", text).strip().casefold()
    m = TITLE.match(flat)
    if m and "in crore" in flat[:200]:
        scope = "consolidated" if m.group(1) else "standalone"
        print(f"PDF {number:>3} | {scope:<12} | {m.group(2)}")

print()
print("== First 150 chars of pages we still need to understand ==")
for number in (336, 337, 458, 459):
    flat = re.sub(r"\s+", " ", pages[number - 1]).strip().casefold()
    print(f"PDF {number}: {ascii(flat[:150])}")