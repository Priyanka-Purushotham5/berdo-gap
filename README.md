# BERDO Gap

BERDO Gap estimates how much a large Boston building may owe each year under
BERDO's emissions limits, where over-the-limit owners pay \$234 per metric ton
over, every year. It shows a building's estimated exposure by compliance period,
lets you model heat-pump and efficiency retrofits that close the gap, and drafts
a one-page board memo. Every figure is an **estimate, not a compliance
determination** - for official answers, contact the City of Boston BERDO team.

**Live demo:** https://berdo-gap-boston.streamlit.app

## Run locally

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
# macOS / Linux:
source .venv/bin/activate
# Windows (PowerShell):
.venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt

# 3. Launch the app
streamlit run app.py
```

### Claude API key (optional)

The board memo is drafted by the Claude API. To enable it, create
`.streamlit/secrets.toml` (gitignored) with your credentials:

```toml
ANTHROPIC_API_KEY = "sk-ant-..."
CLAUDE_MODEL = "claude-..."
```

Without a key, the memo falls back to a deterministic template built from the
calculator's numbers - the rest of the app works unchanged.

## Run the tests

```bash
pytest -q
```

The suite covers the calculator with property-based tests and golden/regression
checks against the City's real data.

## Data sources and licenses

- **Building data:** City of Boston BERDO 2026 disclosure (2025 data), published
  on [Analyze Boston](https://data.boston.gov/) under the Public Domain
  Dedication and License (PDDL).
- **Emissions limits and the \$234 Alternative Compliance Payment rate:** the
  [City of Boston BERDO page](https://www.boston.gov/departments/environment/building-emissions-reduction-and-disclosure).
- **Projected grid emissions factors:** the City of Boston BERDO Policies and
  Procedures (`data/projected_grid_factors.csv`).

## How Kiro was used

This project was built with Kiro using spec-driven development for the
calculator and vibe coding for the UI. See [KIRO_USAGE.md](KIRO_USAGE.md) for the
full write-up.
