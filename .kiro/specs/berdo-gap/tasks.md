# Implementation Plan: BERDO Gap

## Overview

This plan builds the BERDO Gap application bottom-up: the pure-Python `berdo/` calculation core first (limits, exposure, scenarios, load), each paired with its property-based or unit tests, then the whole-dataset golden/regression tests, then the Claude memo layer, and finally the Streamlit `app.py` UI that wires every calculator into the three pages. All money and tonnage are computed in floats in `berdo/`; rounding happens only at the display boundary in `app.py`. Per the steering rule, every calculation function is paired with a property-based test in the same or an adjacent task. Property P8, the blended standard, the green-power scenario, login, geocoding, map tiles, and a database are out of scope and have no tasks.

## Tasks

- [x] 1. Set up project scaffolding and dependencies
  - Create the `berdo/` package directory with an `__init__.py` and the `tests/` directory with an `__init__.py`
  - Add a `pytest.ini` (or `pyproject.toml`/`setup.cfg`) configuring test discovery under `tests/`
  - Confirm the existing `.venv` has pandas, openpyxl, pyarrow, streamlit, plotly, anthropic, pytest, and hypothesis installed (install any missing)
  - Ensure `data/cache/` is gitignored (verify/extend `.gitignore`; create `data/cache/` with a `.gitkeep` if needed)
  - _Requirements: tech/structure steering_

- [x] 2. Implement property-type mapping and per-period limits (`berdo/limits.py`)
  - [x] 2.1 Implement limits-table and property-map loaders and resolvers
    - Define `PERIODS` tuple and implement `load_limits_table`, `load_property_type_map` (keys trimmed + lower-cased), `map_property_type` (trim + case-insensitive, `None` when unmapped), `period_limits` (6-period vector, `None` when the use is absent, 2050+ value of 0 is a valid zero), and `resolve_2025_2029_limit` (use the Applicable_Standard verbatim when present and ≥ 0, else the mapped use's table value, `None` when unmapped/absent)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

  - [ ]* 2.2 Write property tests for mapping and limit resolution (optional, skipped today)
    - Create `tests/test_limits_properties.py`
    - Property: `map_property_type` is insensitive to leading/trailing whitespace and letter case
    - Property: a present non-negative Applicable_Standard is always used verbatim for the 2025–2029 limit
    - _Requirements: 2.1, 2.2, 2.3_

- [x] 3. Implement exposure calculation (`berdo/exposure.py`)
  - [x] 3.1 Implement excess tons, ACP, and per-period exposure
    - Define `ACP_RATE_USD_PER_TON = 234.0`; implement `excess_tons` (`max(0, emissions_kg - limit_per_sqft * floor_area_sqft) / 1000`, floats, never negative), `acp_dollars` (`excess_tons * 234.0`, never negative), and `period_exposure` returning `{period: {excess_tons, acp_usd, status}}` for all six periods in order, marking periods starting before `first_compliance_year` as "not yet covered" with $0, and treating the 2050+ zero limit as charging all emissions in tons × 234
    - No intermediate rounding; return unrounded floats
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [x] 3.2 Write property tests for exposure (P1, P2, P3)
    - Create `tests/test_exposure_properties.py`
    - **Property 1: Exposure is never negative** — `excess_tons`, `acp_dollars` — **Validates: Requirements 9.1**
    - **Property 2: ACP is non-decreasing in emissions** — `excess_tons`, `acp_dollars` — **Validates: Requirements 9.2**
    - **Property 3: ACP is non-increasing in the limit** — `excess_tons`, `acp_dollars` — **Validates: Requirements 9.3**

  - [x] 3.3 Write property tests for per-period exposure (P4, P9)
    - Add to `tests/test_exposure_properties.py`
    - **Property 4: ACP is non-decreasing across later periods** — `period_exposure` — **Validates: Requirements 9.4**
    - **Property 9: Zero limit at 2050+ charges all emissions** — `period_exposure` — **Validates: Requirements 9.9**

- [x] 4. Checkpoint - Ensure all tests pass
  - Ensure all limits and exposure tests pass, ask the user if questions arise.

- [x] 5. Implement retrofit scenarios (`berdo/scenarios.py`)
  - [x] 5.1 Implement efficiency and heat-pump transforms
    - Define `BOILER_EFFICIENCY_DEFAULT = 0.85`, `COP_DEFAULT = 2.5`, `KBTU_PER_KWH = 3.412`; implement `apply_efficiency` (`value * (1 - p/100)`), `added_kwh` (`f * gas_kbtu * boiler_eff / (cop * 3.412)`), `apply_heat_pump` (reduce gas emissions by `f`, add `added_kwh * elec_factor`; unchanged when `gas_kbtu` is 0; never increases when `elec_factor` is 0; never negative), and `apply_scenario` (efficiency `p` first, then heat-pump `f`; exact identity when `p == 0` and `f == 0`)
    - _Requirements: 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.11_

  - [x] 5.2 Write property tests for scenarios (P5, P6, P7)
    - Create `tests/test_scenarios_properties.py`
    - **Property 5: Scenario identity at p = 0 and f = 0** — `apply_scenario` — **Validates: Requirements 9.5**
    - **Property 6: Emissions are non-increasing in efficiency** — `apply_efficiency`, `apply_scenario` — **Validates: Requirements 9.6**
    - **Property 7: Heat-pump emissions stay valid** — `apply_heat_pump` (emissions ≥ 0 for any f in [0,1]; non-increasing when `elec_factor` is 0) — **Validates: Requirements 9.7, 9.8**

- [x] 6. Implement load, cache, and normalize (`berdo/load.py`)
  - [x] 6.1 Implement column normalization, filtering, and EUI
    - Define the normalized column-name constants and `SOURCE_COLUMNS` mapping (including "Parcel Address" → `COL_PARCEL_ADDRESS`, and deliberately excluding the "Site EUI" column); implement `normalize_columns` (rename via `SOURCE_COLUMNS`, coerce fuel/emission blanks and non-numerics to 0, treat blank Applicable_Standard as missing, fall back to "Parcel Address" for the normalized address when "Building Address" is blank, raise `LoadError` naming absent required columns), `filter_reported` (keep rows with `total_ghg_kgco2e > 0` and `floor_area_sqft > 0`), and `compute_eui` (`total_site_energy_kbtu / floor_area_sqft`, never from the Site EUI column)
    - _Requirements: 1.6, 1.8, 1.9, 1.10, 1.11, 1.12, 1.13_

  - [x] 6.2 Implement cache handling and the load orchestrator
    - Implement `is_cache_valid` (readable parquet with every required column), `write_cache` (parquet via pyarrow), `read_disclosure_excel` (download "Buildings & Campuses" sheet, header row 1, 60 s timeout, raise `LoadError` on failure/timeout while preserving the cache), and `load_disclosure` (read valid cache else download → normalize → filter → write cache; re-download when the cache is unreadable or missing a column; do not write cache on missing-column error)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.7_

  - [ ]* 6.3 Write unit tests for the loader
    - Create loader example tests (in `tests/`) for cache-valid vs re-download behavior, missing-column `LoadError` that names the absent columns, and blank-cell coercion to 0 / blank Applicable_Standard to missing
    - _Requirements: 1.2, 1.3, 1.6, 1.12, 1.13_

- [x] 7. Checkpoint - Ensure all tests pass
  - Ensure all scenario and loader tests pass, ask the user if questions arise.

- [x] 8. Implement golden and regression verification tests
  - [x] 8.1 Write golden-building tests
    - Create `tests/test_golden.py`; load the 4 buildings in `data/golden_buildings.csv` and assert each period's ACP matches `GOLDEN_TESTS.md` within $0.05, including heat-pump scenario rows, and assert building 100005 (24 School St, Office, no gas) is unchanged by any heat-pump fraction
    - _Requirements: 10.1_

  - [x] 8.2 Write whole-dataset regression tests
    - Add to `tests/test_golden.py` over the full loaded dataset: Loader retains exactly 1,809 buildings; 2025–2029 has 63 buildings over the limit totaling $2,880,426.65 within $1; 2030–2034 has 963 buildings over the limit totaling $27,406,457.43 within $1; per-use counts match `data/expected_by_use.csv` exactly with totals within $1; and the 40 buildings in `data/expected_sample_40.csv` match per-building ACP within $0.05
    - _Requirements: 10.2, 10.3, 10.4, 10.5, 10.6_

- [x] 9. Implement the Claude memo layer (`berdo/memo.py`)
  - [x] 9.1 Implement payload, Claude call, validation, fallback, and orchestrator
    - Define `MEMO_FIELDS` and `CLAUDE_TIMEOUT_S = 20.0`; implement `build_memo_payload` (only calculator numbers and City data-file values), `call_claude` (tool-use request for strict JSON with exactly the five fields, 20 s timeout, raise `MemoError` on failure/timeout/non-JSON/missing field/rate limit, never log the API key), `validate_memo_numbers` (every rendered DOLLAR AMOUNT and TONNAGE matches a calculator value within display tolerance; years like 2025, 2030, …, the $234 ACP rate, and the scenario slider/assumption values — heat-pump fraction f, efficiency percentage p, boiler efficiency 0.85, COP 2.5 — are allowed without requiring a calculator match), `templated_memo` (deterministic five-field memo built from payload numbers, notes the draft was unavailable and that the result is an estimate not a compliance determination, excludes "in violation"/"will be fined" and legal/financial advice), and `generate_memo` (templated when either secret is missing/empty, else `call_claude` with templated fallback on any `MemoError` or validation failure)
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10, 5.11_

  - [ ]* 9.2 Write mocked unit tests for the memo layer
    - Mock the anthropic client to verify the tool-use request shape and five-field contract; assert the templated fallback on each failure mode (timeout, non-JSON, missing field, missing secret) and that the API key never appears in log output
    - _Requirements: 5.2, 5.5, 5.8, 5.9, 5.11_

- [x] 10. Checkpoint - Ensure all tests pass
  - Ensure golden, regression, and memo tests pass, ask the user if questions arise.

- [x] 11. Implement the Building page (`app.py`)
  - [x] 11.1 Build building lookup, exposure table, and compliance status display
    - Create `app.py` with a Building page that looks up a building, calls `period_exposure`, renders the six-period exposure table with display rounding (tons to 1 decimal, dollars to whole dollars), shows the City's Compliance_Status verbatim beside the estimate as a separately labeled official field (placeholder when missing/blank), shows "No reported emissions — enter your own numbers" when no reported building is returned, and "limit unknown" when the use is unmapped or absent from the table
    - _Requirements: 1.14, 2.5, 2.7, 3.7, 7.1, 7.2, 7.3, 7.4_

  - [x] 11.2 Build scenario sliders and memo button on the Building page
    - Add the heat-pump fraction slider (0.0–1.0), efficiency percentage input (0–100), editable boiler-efficiency input ((0, 1.0]) and editable COP input (> 0), rejecting out-of-range values; call `apply_scenario` and re-run exposure on the transformed emissions; add a memo button that calls `generate_memo` with only computed numbers and renders the returned five-field memo
    - _Requirements: 4.1, 4.9, 4.10, 4.11, 5.1, 5.3_

- [x] 12. Implement the City view page (`app.py`)
  - [x] 12.1 Build the ZIP bar chart and over-limit counts
    - Add a City view page with a Plotly bar chart of total 2030–2034 ACP in whole dollars grouped by ZIP (fall back to Parcel Address Zip Code, group missing-both under "Unknown ZIP"), sorted descending by exposure, including only mapped-use buildings; show the empty-state message when no building qualifies; display the non-negative whole-number counts of buildings over the limit in 2025–2029 and in 2030–2034 (mapped uses only)
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_

- [x] 13. Implement the About & sources page and shared disclaimers (`app.py`)
  - [x] 13.1 Build the About page and apply disclaimers to every result screen
    - Add the About & sources page citing the boston.gov BERDO page and the City of Boston BERDO 2026 disclosure (PDDL); implement a shared disclaimer block shown without scrolling on every result screen (Building, City view, memo) containing "Estimate, not a compliance determination", the exact source text "City of Boston BERDO 2026 disclosure, 2025 data, PDDL license", the portfolio/campus/flexibility text, the exact grid-factors text, use of the term "estimated exposure", direction to the City of Boston BERDO team for official answers, and never the phrases "in violation" or "will be fined"; ensure only calculator- or data-file-sourced numbers are displayed
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8_

- [x] 14. Final wiring and integration pass
  - [x] 14.1 Wire the pages together
    - Add page navigation across Building, City view, and About & sources so each calculator is reachable from the UI with no orphaned code
    - _Requirements: 6.5, 8.1, 8.2_

  - [ ]* 14.2 Write UI example tests (optional, skipped today)
    - Add `app.py` example tests for disclaimer text presence, "limit unknown" display, and the City-view empty-state message
    - _Requirements: 6.5, 8.1, 8.2_

- [x] 15. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional. Property tests P1–P7 and P9 (tasks 3.2, 3.3, 5.2) are REQUIRED, and the golden and regression tests (8.1, 8.2) are REQUIRED, alongside the core calculation functions, the memo layer, and the three UI pages. The optional tasks skipped today are 2.2 (mapping/limit property tests), 6.3 (loader unit tests), 9.2 (mocked memo tests), and 14.2 (app.py example tests).
- Each task references specific requirements for traceability.
- Checkpoints ensure incremental validation.
- Property-based tests validate the universal correctness properties; unit tests validate specific examples and edge cases.
- Per the data-rules steering, a property-based test is never weakened to make it pass; if a property appears to fail, the cause is investigated and documented in a comment.
- Property P8, the blended standard, the green-power scenario, login, geocoding, map tiles, and a database are out of scope and intentionally have no tasks.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2.1", "3.1", "5.1", "6.1"] },
    { "id": 2, "tasks": ["2.2", "3.2", "3.3", "5.2", "6.2"] },
    { "id": 3, "tasks": ["6.3", "9.1"] },
    { "id": 4, "tasks": ["8.1", "8.2", "9.2"] },
    { "id": 5, "tasks": ["11.1", "12.1", "13.1"] },
    { "id": 6, "tasks": ["11.2"] },
    { "id": 7, "tasks": ["14.1", "14.2"] }
  ]
}
```
