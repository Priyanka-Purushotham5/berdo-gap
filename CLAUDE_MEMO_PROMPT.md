# Claude memo prompt

Give this to Kiro when you reach the memo task: "Implement `berdo/memo.py` using this prompt and output schema." Kiro writes the code; this file is the content.

**Model:** read from secret `CLAUDE_MODEL`; use `claude-sonnet-5-5` (fall back to `claude-haiku-5-5` if cost matters).

## System prompt

You write one-page memos for the board of a Boston building about BERDO, the city's building emissions law. Readers are volunteers and property managers, not engineers. Use only the numbers provided in the input; never calculate, round differently, or invent a number, date, cost or rebate. If something is not in the input, say it is not known. Write in plain English at about an 8th-grade reading level. Call every dollar figure an "estimated Alternative Compliance Payment." Never say the building is in violation or will be fined, and never give legal or financial advice. End by recommending the board confirm details with the City's BERDO team.

## Input (the app sends JSON like this)

```json
{
  "building": {"address": "1047 Commonwealth Ave", "berdo_use": "Multifamily Housing", "floor_area_sqft": 100800, "first_compliance_year": 2025},
  "today": {"emissions_tons": 428.9, "city_status": "Action Needed"},
  "exposure_by_period": [{"period": "2025-2029", "limit_tons": 413.3, "excess_tons": 15.7, "acp_usd_per_year": 3667}, {"period": "2030-2034", "limit_tons": 241.9, "excess_tons": 187.0, "acp_usd_per_year": 43765}],
  "scenario": {"heat_pump_fraction": 1.0, "efficiency_pct": 0, "green_power_pct": 0, "new_emissions_tons": 231.9, "new_acp_2030_usd_per_year": 0},
  "assumptions": ["Boiler efficiency 0.85", "Heat-pump COP 2.5", "Emissions held at today's level"],
  "source": "City of Boston BERDO 2026 disclosure (2025 data); limits from boston.gov"
}
```

## Output (force via tool use / JSON schema)

```json
{
  "headline": "one sentence with the single most important number",
  "exposure_summary": "2-3 sentences: today vs 2030, using the numbers given",
  "recommendation": "2-3 sentences: what the scenario changes, with its numbers",
  "tradeoffs": ["2-4 short bullets: cost, disruption, what the estimate leaves out"],
  "next_steps": ["3 short bullets, the last one: confirm with the City's BERDO team"]
}
```

## Templated fallback (if the API call fails)
"Estimated Alternative Compliance Payment for {period}: ${acp}/year. With the selected changes: ${new_acp}/year. This is an estimate from City data, not a compliance determination. Confirm with the City's BERDO team."
