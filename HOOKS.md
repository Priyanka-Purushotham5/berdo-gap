# Hooks to create in Kiro (Agent Hooks panel)

Describe each one in plain words and let Kiro generate it. Screenshot each, and note in `KIRO_USAGE.md` whenever one catches something.

## 1. Tests on save
- **When:** a file in `berdo/` or `tests/` is saved.
- **Do:** "Run `pytest -q`. If anything fails, show the failing test or the Hypothesis counterexample in one line and propose the smallest fix. Never weaken a property to make it pass; flag it for me instead."

## 2. Golden check on calculator change
- **When:** `berdo/exposure.py`, `berdo/limits.py` or `berdo/scenarios.py` is saved.
- **Do:** "Run `pytest tests/test_golden.py -q` and print the four buildings' 2025 and 2030 ACP next to the expected values in GOLDEN_TESTS.md."

## 3. No unsourced numbers in the UI
- **When:** `app.py` is saved.
- **Do:** "List any number, percentage or dollar amount hard-coded in user-visible text. Each must come from a calculator result, the data file or a labeled assumption input."

## MCP (optional, good for the write-up)
Add the `fetch` MCP server in Kiro's MCP panel (command `uvx`, args `mcp-server-fetch`; needs `pip install uv`). Use it once from Kiro chat to read the boston.gov BERDO page and confirm the limits table matches `data/berdo_limits.csv`. Screenshot it. That is a real, honest MCP use.
