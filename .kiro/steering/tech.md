# Tech

- Python 3.11. pandas, openpyxl, pyarrow, streamlit, plotly, anthropic, pytest, hypothesis.
- One Streamlit app (`app.py`) over a pure-Python package (`berdo/`). All calculations live in `berdo/` as pure functions with type hints; the UI only calls them.
- Money and tons: compute in floats, round only for display (tons to 1 decimal, dollars to whole dollars).
- Claude API: model and key come from Streamlit secrets (`ANTHROPIC_API_KEY`, `CLAUDE_MODEL`). Never log the key or put it in the repo. Ask for the memo as strict JSON via tool use (fields: headline, exposure_summary, recommendation, tradeoffs, next_steps) and render it in the UI. Timeout 20 s; on any error, render the templated memo.
- Cache the downloaded disclosure as `data/cache/berdo_2026.parquet` (gitignored) and load from cache when present.
- Whenever a function in `berdo/` changes, add or update its property-based test.
