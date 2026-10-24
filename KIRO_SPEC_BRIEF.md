# Kiro Spec brief — BERDO Gap

Paste everything below the line into Kiro **Spec** mode. Let Kiro write `requirements.md`, `design.md` and `tasks.md`. Review each, change at least one thing you disagree with (note it in `KIRO_USAGE.md`), then run the tasks one at a time.

---

Build **BERDO Gap**, a Streamlit web app that estimates each large Boston building's yearly Alternative Compliance Payment (ACP) exposure under Boston's Building Emissions Reduction and Disclosure Ordinance (BERDO), shows how retrofits change it, and drafts a one-page memo for the building's owner or board.

**Users:** property managers and condo boards of buildings covered by BERDO; secondarily, City of Boston staff deciding where to focus outreach.

**Data (already in the repo or downloadable):**
- `data/berdo_limits.csv`: emissions limits in kgCO2e per sq ft per year for 13 building uses and 6 periods (2025–2029 … 2050+), from boston.gov.
- `data/property_type_map.csv`: maps ENERGY STAR Portfolio Manager property types to the 13 BERDO building uses.
- The City's 2026 BERDO disclosure (2025 data), Excel sheet "Buildings & Campuses", downloaded from Analyze Boston (URL in `DATA_NOTES.md`). Cache it locally as parquet after first load.
- `data/golden_buildings.csv`: four real buildings with hand-checked expected results.

Write requirements in EARS form ("WHEN … THE SYSTEM SHALL …"). Cover:

1. **Loading.** Load the disclosure sheet, keep buildings with total GHG > 0 and floor area > 0, and normalize column names. Never use the file's "Site EUI" column (it is wrong in the source); compute EUI as total site energy ÷ floor area.
2. **Building use and limit.** Map the largest property type to a BERDO use with the mapping file. The 2025–2029 limit is the City's "Applicable Emissions Compliance Standard" when present, otherwise the mapped use's value. Later periods use the mapped use's values. Unmapped types are shown as "limit unknown" and excluded from totals.
3. **Blended standard (optional toggle).** Parse "All Property Types and GFAs" and compute a floor-area-weighted limit; show it beside the default.
4. **Exposure.** For each period: excess tons = max(0, emissions − limit × floor area) ÷ 1000; ACP = excess tons × $234. Periods before the building's first compliance year show "not yet covered" and $0.
5. **Retrofit scenarios** (sliders, all math in code):
   - Heat pumps: convert a fraction f of natural-gas use to electricity: gas emissions fall by f × gas emissions; added kWh = f × gas kBtu × 0.85 ÷ (2.5 × 3.412); added emissions = added kWh × the building's own electricity factor (electricity emissions ÷ kWh).
   - Efficiency: reduce all energy use and emissions by a percentage p.
   - Green power: reduce electricity emissions by a percentage g.
   Assumptions (boiler efficiency 0.85, heat-pump seasonal COP 2.5) are shown on screen as editable inputs.
6. **Memo.** A button calls the Claude API with only the building's computed numbers and the chosen scenario, and renders a one-page board memo. Claude must not compute or invent numbers. If the call fails, show a templated memo.
7. **City view.** Total 2030–2034 ACP exposure by ZIP code (bar chart), plus counts of buildings over the limit now and in 2030.
8. **Honesty.** Every screen shows "Estimate, not a compliance determination," the data source and year, and notes that portfolio/campus compliance and a cleaner grid can reduce exposure.

**Correctness properties (generate Hypothesis property-based tests for each):**

- P1: Excess tons and ACP are never negative.
- P2: ACP is non-decreasing as emissions increase (floor area and limit fixed).
- P3: ACP is non-increasing as the limit increases.
- P4: For any building, ACP is non-decreasing across later periods (limits only tighten).
- P5: Efficiency p = 0 and heat pumps f = 0 and green power g = 0 return the original emissions exactly.
- P6: Increasing efficiency p never increases emissions.
- P7: Any heat-pump fraction f in [0, 1] never makes emissions negative; with electricity factor 0, emissions never increase.
- P8: The blended limit always lies between the smallest and largest limit of the building's uses.
- P9: At 2050+ (limit 0), ACP equals total emissions in tons × $234.

**Golden tests:** the four buildings in `data/golden_buildings.csv` must reproduce the expected values in `GOLDEN_TESTS.md` to within $0.05.

**Regression tests:** on the full loaded dataset, per-use counts and ACP totals must match `data/expected_by_use.csv` (counts exact, totals within $1), and the 40 buildings in `data/expected_sample_40.csv` must match within $0.05.

Non-goals: no login, no address geocoding, no map tiles, no database.
