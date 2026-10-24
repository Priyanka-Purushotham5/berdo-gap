# Data notes (checked 11:15 AM, Oct 24 2026)

## Building data — use the 2026 disclosure, not the portal's 2021 file

The event portal links a 2021 BERDO table. The City has since published the **2026 disclosure (2025 data)**, the first year of emissions limits, with each building's applied limit and compliance status. Use it.

- Dataset page: https://data.boston.gov/dataset/b09a8b71-274b-4365-9ce6-49b8b44602ef (license PDDL)
- File (1.5 MB Excel): https://data.boston.gov/dataset/b09a8b71-274b-4365-9ce6-49b8b44602ef/resource/c6edf41e-eb53-45a4-9c52-837b865bf19f/download/2026-berdo-data-disclosure-9.30.26.xlsx
- Sheet: **"Buildings & Campuses"**, header in row 1, 5,591 buildings. Other sheets: Summary, Building Portfolios, Data Dictionary.
- Load: `pd.read_excel(URL, sheet_name="Buildings & Campuses")` (needs `openpyxl`). If the download is slow, open the URL in a browser and save it to `data/cache/`.

### Columns you need (exact names)

| Use | Column |
| --- | --- |
| ID | `BERDO ID` |
| Address | `Building Address` (blank for some; fall back to `Parcel Address`) |
| ZIP | `Building Address Zip Code` (fall back to `Parcel Address Zip Code`) |
| Floor area | `Gross Floor Area (sq ft)` |
| Use | `Largest Property Type`, `All Property Types and GFAs (sq ft)` (e.g. `Office (236426.0),Food Sales (12300.0)`) |
| Energy | `Total Site Energy Usage (kBtu)`, `Natural Gas Usage (kBtu)`, `Electricity Usage (kWh)` |
| Emissions | `Total GHG Emissions (kgCO2e)`, `Natural Gas Emissions (kgCO2e)`, `Electricity Emissions (kgCO2e)`, plus district steam/hot water/chilled water and fuel oil columns |
| City's limit | `Applicable Emissions Compliance Standard (kgCO2e/sq ft)` |
| Status | `Emissions Compliance Status`, `First Emissions Compliance Year`, `Flexibility Measures` |

Skip `Parcel Owner Name` in the UI. Owners will search their own building; there is no need to display or rank owners.

### Traps found in the file

1. **`Site EUI (Energy Use Intensity kBtu/ft²)` is wrong:** in 1,788 of 1,809 rows it holds emissions intensity. Compute EUI yourself.
2. Only **1,809** buildings have emissions > 0. The rest are "Pending Reporting", reported as a portfolio (1,464) or campus, or not covered until 2030. Show "No reported emissions — enter your own numbers" for those.
3. `Applicable Emissions Compliance Standard` is blank for buildings first covered in 2030; use the mapped use's value.
4. A few limits (e.g. 8.1, 4.4) are not in the table. Those are blended standards or individual schedules chosen by the owner; use the City's value for 2025–2029.

### Numbers computed from this file (estimates, per building, today's emissions held constant)

| Measure | Value |
| --- | --- |
| Buildings with reported emissions | 1,809 |
| First covered in 2025 / 2030 (all buildings) | 3,795 / 1,794 |
| Over the 2025–2029 limit (first covered 2025) | 63 buildings, ≈ $2.88M per year |
| Over the 2030–2034 limit | 963 buildings, ≈ $27.4M per year |
| …of which owe nothing today | 900 |
| Top ZIPs by 2030 exposure | 02128 ≈ $4.5M · 02115 ≈ $3.3M · 02135 ≈ $1.9M |

Totals include the nine judgment-mapped property types; the exact per-use totals are in `data/expected_by_use.csv`. Your app will recompute these; if your numbers differ slightly, trust the code and check why.

## Limits table (`data/berdo_limits.csv`)
From the City's BERDO page: https://www.boston.gov/departments/environment/building-emissions-reduction-and-disclosure (kgCO2e per sq ft per year; 13 uses × 6 periods). Checked against the 2026 data: every applied 2025 limit matches a table value except blended or individual cases.

## Property-type mapping (`data/property_type_map.csv`)
The 13 BERDO limits for 2025–2029 are all different numbers, so each Portfolio Manager type's BERDO use was read off the limit the City actually applied (57 types, record counts in the file). Nine types with no City record were assigned by judgment and marked "assumed". Say this in the README.

## Fixed facts
- ACP: $234 per metric ton over the limit, per year ([Facilities Dive](https://www.facilitiesdive.com/news/what-to-know-about-berdo-bostons-building-performance-standards-law/725082/); City compliance guide).
- Coverage: from 2025, non-residential ≥ 35,000 sq ft and residential ≥ 35 units; from 2030, non-residential 20,000–34,999 sq ft and residential 15–34 units.
- Gas factor in the data: 0.05311 kgCO2e/kBtu (all buildings). Electricity factor: 0.145–0.182 kgCO2e/kWh, varying by building; use each building's own ratio.

## Assumptions to show on screen (editable)
- Boiler efficiency 0.85; heat-pump seasonal COP 2.5; all gas use is space and water heating.
- Emissions stay at today's level in future periods (no grid cleanup), which makes the estimate conservative (high).

## Added 3:15 PM: the City's projected grid emissions factors (optional, high value)

`data/projected_grid_factors.csv` comes from the City's **BERDO Policies and Procedures (Sept 2026), Appendix B** (https://www.boston.gov/sites/default/files/file/2026/09/BERDO%20Policies%20and%20Procedures_1.pdf). These are the City's own projections; the Review Board may update them before 2030.

Key finding: the projected factor **rises** 2027–2029 and averages about 248 kg/MWh over 2030–2034, the same as 2025 (249). So holding emissions at today's level for the 2030 period matches the City's own projection. The grid only gets meaningfully cleaner after 2035 (231 → 150 by 2050). Replace the old caveat "a cleaner grid lowers exposure" with: "The City projects a flat grid through 2034, so 2030 estimates hold; later periods may be lower."

How to use it (only if ahead of schedule): scale each building's electricity emissions for a period by (average factor over that period ÷ 249). Don't replace the building's own factor with these absolute values; the disclosure's per-building factors are lower (0.145–0.182 kg/kWh), so mixing them would overstate emissions.

## Pitch line (no build cost)
The City's compliance guide says Alternative Compliance Payments go to the **Equitable Emissions Investment Fund**, which funds projects in environmental-justice communities. So the ~$27M/yr of 2030 exposure is also money that would flow to EJ neighborhoods; say this in the video's closing.
