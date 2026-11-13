# Stock & IPO Research Agent

A research assistant for Indian listed companies and IPOs, built as a [CrewAI](https://crewai.com) Flow.

For **stocks**, code reads the company's annual report PDF and produces every figure with its page, unit and basis. The LLM only picks documents and writes a short summary whose numbers are checked. For **IPOs**, an LLM summarises recent news, and the report says plainly that this is unverified.

> **Disclaimer:** This is an educational project. It is not investment advice, and it is not a SEBI-registered research or advisory service.

## What it does

**Stock mode.** You give a company name. The tool finds the company, finds its latest annual report, and writes `output/report.md` with:

- the sources it found, each labelled `official` or `unverified`
- a table of four headline profit and loss figures (revenue from operations, other income, total income, profit), for standalone and consolidated statements, each with its year, unit and PDF page
- a short LLM summary of those figures, with a number check
- if the report cannot be read, a clearly labelled **UNVERIFIED** summary from web search instead

**IPO mode.** You give an IPO name. One agent reads recent news and writes a report with a summary, the IPO stage (upcoming, open, closed or listed), pros, cons, a cautious lean, and its sources. The whole report is labelled **UNVERIFIED**. If the IPO has already closed or listed, the report says applying is no longer possible instead of giving a lean.

## Design rules

1. **Numbers come from code.** In the verified path, the LLM never produces a figure. Code extracts it from the PDF with its page.
2. **The LLM selects and writes.** It picks which document to read and writes narrative.
3. **Every LLM number is checked.** The writer's numbers must match the extracted figures. Web and IPO numbers must appear in a search snippet from the same run. Anything else is flagged in the report.
4. **Fail loudly, never guess.** A missing row, an arithmetic mismatch or an ambiguous page produces a refusal with a reason, not a made-up number.
5. **Never an empty report.** If the verified path fails, a labelled UNVERIFIED section is added. If a summary step crashes, the report is still saved with a note.

## How a stock run works

1. **Identity** (LLM, then you): 3 searches find listed entities matching the name. Companies get renamed and demerged, so one name can match several. You choose one in the terminal.
2. **Source finder** (LLM): up to 3 searches for official sources. Code drops any URL that no search returned.
3. **Report picker** (LLM, no tools): picks the annual report URL. If that fails, code ranks annual report PDFs found by search and uses the best one.
4. **Reader** (code): downloads the PDF, caches it in `cache/`, records its SHA-256, and checks that the company name and identifiers appear in the first pages. A wide page holding two printed pages side by side is read as a left half and a right half.
5. **Locator and extractor** (code): finds the standalone and consolidated profit and loss statements and reads four rows. A check requires revenue plus other income to equal total income. A missing row or a mismatch means the statement is refused.
6. **Writer** (LLM, no tools): at most 5 sentences from the verified figures only. Code flags any number that is not one of them.
7. **Fallback** (LLM with search, only if step 5 gave no figures): up to 2 searches. Code keeps only URLs that a search returned, flags numbers that appear in no snippet, and flags numbers that also appear next to a quarter or half-year mention (a quarterly figure may have been labelled annual).

Every crew call retries temporary model errors (503, 429, timeouts), up to 3 attempts with waits of 5 and 20 seconds. Other errors fail at once.

## How an IPO run works

One agent makes up to 3 searches (news, price band and subscription, risks) and returns a summary, stage, pros, cons, lean, confidence, reason and source URLs. Code then:

- keeps only URLs that a search really returned, and shows each source's date (a relative date such as "2 days ago" also gets an approximate absolute date)
- flags numbers that appear in no search snippet
- forces the lean to "undecided, low confidence" if no source URL can be confirmed
- replaces the lean with "applying is no longer possible" when the stage is closed or listed

The lean is a reading of news snippets. It cannot know your goals, finances or risk tolerance. This path does not read the DRHP or RHP.

## Example output

Excerpt from a stock run for Tata Motors Passenger Vehicles Limited (FY2025-26 annual report):

| Basis | Item | Year ended | Value (INR crore) | PDF page |
|---|---|---|---|---|
| Consolidated | Total revenue from operations | March 31, 2026 | 335,582 | 332 |
| Consolidated | Other income | March 31, 2026 | 5,787 | 332 |
| Consolidated | Total income | March 31, 2026 | 341,369 | 332 |
| Consolidated | Profit from continuing operations | March 31, 2026 | -1,377 | 332 |

Excerpt from an IPO run for an IPO that had already listed:

> **Stage: listed.** The issue has closed and the shares are already listed, so applying is no longer possible. The news below is a post-listing review, not an apply-or-skip view.

## Measured results

I tested the extractor on the FY2025-26 annual reports of 10 non-bank companies. Before I generalised the locator and extractor, **1 of 10 worked** (TMPV, the report they were first written for). Now:

| Company | Result |
|---|---|
| Tata Motors Passenger Vehicles, Infosys, Tata Steel, ITC, L&T, Sun Pharma, Hindustan Unilever, Maruti Suzuki | standalone and consolidated both verified |
| Reliance Industries | standalone verified; consolidated refused because the report also contains subsidiary statements (for example Jio Platforms) |
| Asian Paints | refused: it prints no "Revenue from operations" total, only component lines. The UNVERIFIED web fallback runs instead |

**9 of 10 give at least one verified statement, and 8 of 10 give both.** Statement pages were checked offline with the real locator and extractor. TMPV and Asian Paints were also run end to end. The rules were tuned while looking at 9 of these 10 reports, so expect lower accuracy on companies it has not seen.

## Scope and limits

- Only four headline rows. No balance sheet, EPS or cash flow.
- The year end must be March 31. Units must be crore, million or lakh, in INR.
- Banks, insurers and NBFCs use different statements and are not supported.
- If a report prints no revenue total, the statement is refused. The tool never adds lines up.
- If more than one page matches a statement (for example subsidiary statements in the same report), the tool refuses and does not pick one.
- A statement page whose title is not in the extracted text cannot be found.
- `official` means the link is on an exchange or SEBI website. It does not prove that the document belongs to the company.
- The web fallback and the IPO path are LLM summaries of search snippets. Numbers are traced to snippets, but a real number can still carry the wrong period or meaning. This has happened: a quarterly figure was labelled annual, and a pro point was garbled.
- Search results come from [Serper](https://serper.dev), and dates are whatever the search shows.

## Setup

You need Python 3.12 (3.10 to 3.13 are allowed), a [Google AI Studio](https://aistudio.google.com) Gemini API key, and a [Serper](https://serper.dev) API key.

```bash
git clone https://github.com/Ishika-Gadhwal/stock-ipo-research-agent.git
cd stock-ipo-research-agent
uv sync        # or: python -m venv .venv, activate it, then: pip install -e .
```

Create a `.env` file in the project root (it is gitignored):

```
GEMINI_API_KEY=your-gemini-key
SERPER_API_KEY=your-serper-key
```

All agents use `gemini/gemini-3.5-flash-lite`. To change the model, edit the `llm:` line in each crew's `config/agents.yaml`.

## Run

Stock mode on the default company (Tata Motors). The tool asks you to choose among the matches:

```bash
crewai run
```

Any company or IPO:

```bash
python -c "from stock_ipo_research_agent.main import ResearchFlow; ResearchFlow().kickoff({'crewai_trigger_payload': {'company': 'Infosys', 'mode': 'stock'}})"
python -c "from stock_ipo_research_agent.main import ResearchFlow; ResearchFlow().kickoff({'crewai_trigger_payload': {'company': 'COMPANY NAME', 'mode': 'ipo'}})"
```

The report is saved to `output/report.md`.

**Cost per run (observed, approximate).** A stock run uses about 5 to 8 Serper searches and about 8 to 11 Gemini calls. An IPO run uses up to 3 searches and about 4 calls. A retry repeats a whole crew. The first run on a new report spends about 90 seconds extracting text from a 585-page PDF. After that it is cached in `cache/`.

## Tests

```bash
python -m unittest discover tests
```

Every LLM and search call is mocked, so no keys or credits are needed. Two golden tests check the real TMPV report. They are skipped unless that report is cached locally. To enable them, run `python scripts/make_golden_cache.py` once. It downloads the report from NSE, takes about 90 seconds, and costs no credits.

Other scripts in `scripts/` are small developer checks: `facts_check.py` (free, runs the extractor on the TMPV report), `search_live_check.py` (one live search), `smoke_test.py` (one LLM call) and `list_models.py` (lists Gemini models).

## Project layout

```
src/stock_ipo_research_agent/
  main.py            the Flow: router, stock and IPO paths, retry
  models.py          data models
  report.py          report builders and status lines
  crews/             identity, content (finder + picker), narrative (writer),
                     web_fallback, ipo_news
  tools/
    search.py, source_search_tool.py, source_checks.py   search and URL checks
    annual_report_reader.py                              PDF download, cache, identity check
    statement_locator.py, statement_extractor.py         find and read the statements
    financial_facts.py, facts_selection.py               extraction pipeline and fallback ranking
    numbers_check.py, narrative_input.py                 number checks, writer input
tests/               offline tests
scripts/             developer checks
```