# Requirements Document

## Introduction

BERDO Gap is a Streamlit web application that estimates each large Boston building's yearly Alternative Compliance Payment (ACP) exposure under Boston's Building Emissions Reduction and Disclosure Ordinance (BERDO), shows how retrofit scenarios change that exposure, and drafts a one-page memo for the building's owner or board.

The application serves property managers and condo boards of BERDO-covered buildings, and secondarily City of Boston staff deciding where to focus outreach. The architecture is a single Streamlit UI file (`app.py`) over a pure-Python package (`berdo/`): all calculations are pure functions with type hints in `berdo/`, and the UI only calls them.

This feature covers loading the City disclosure data, mapping each building to a BERDO limit, computing per-period exposure, modeling heat-pump and efficiency retrofit scenarios, generating a board memo through the Claude API, presenting a citywide view, and showing honest disclaimers on every result. Scope this session excludes the blended standard, the green-power scenario, and correctness property P8.

## Glossary

- **System**: The BERDO Gap application, comprising the Streamlit UI (`app.py`) and the `berdo/` calculation package.
- **Loader**: The component (`berdo/load.py`) that downloads, caches, and normalizes the disclosure sheet.
- **Limit_Calculator**: The component (`berdo/limits.py`) that maps property types to BERDO uses and determines per-period emissions limits.
- **Exposure_Calculator**: The component (`berdo/exposure.py`) that computes excess tons and ACP per period.
- **Scenario_Calculator**: The component (`berdo/scenarios.py`) that models heat-pump and efficiency retrofits.
- **Memo_Generator**: The component (`berdo/memo.py`) that calls the Claude API and renders the board memo.
- **BERDO**: Boston's Building Emissions Reduction and Disclosure Ordinance.
- **ACP**: Alternative Compliance Payment, charged at $234 per metric ton of CO2-equivalent emissions over a building's limit, per year.
- **Disclosure_Sheet**: The "Buildings & Campuses" worksheet (header in row 1) of the City of Boston 2026 BERDO disclosure Excel workbook (2025 data).
- **BERDO_Use**: One of the 13 BERDO building-use categories defined in `data/berdo_limits.csv`.
- **Applicable_Standard**: The City's "Applicable Emissions Compliance Standard (kgCO2e/sq ft)" column value for a building.
- **Period**: One of the six BERDO compliance periods: 2025–2029, 2030–2034, 2035–2039, 2040–2044, 2045–2049, and 2050+.
- **First_Compliance_Year**: The building's "First Emissions Compliance Year" (2025 or 2030) from the disclosure.
- **Excess_Tons**: max(0, emissions − limit × floor area) ÷ 1000, measured in metric tons CO2e.
- **Electricity_Factor**: A building's own ratio of electricity emissions ÷ electricity kWh.
- **Compliance_Status**: The City's own "Emissions Compliance Status" column value for a building.
- **EUI**: Energy Use Intensity, computed as Total Site Energy Usage (kBtu) ÷ Gross Floor Area (sq ft).

## Requirements

### Requirement 1: Load and normalize the disclosure data

**User Story:** As a property manager, I want the application to load the City's 2026 BERDO disclosure data, so that I can look up my building's reported emissions and compliance details.

#### Acceptance Criteria

1. WHEN the Loader loads the disclosure, THE Loader SHALL read the "Buildings & Campuses" worksheet using row 1 as the header from the 2026 BERDO disclosure Excel workbook at the URL recorded in `DATA_NOTES.md`.
2. WHERE a valid cached file exists at `data/cache/berdo_2026.parquet` (a readable parquet file containing all required normalized columns), THE Loader SHALL load the disclosure from that cached file instead of downloading the workbook.
3. IF the cached file at `data/cache/berdo_2026.parquet` is unreadable or is missing any required column, THEN THE Loader SHALL re-download the workbook and overwrite the cached file.
4. WHEN the Loader downloads the disclosure workbook, THE Loader SHALL apply a download timeout of 60 seconds.
5. IF the download of the disclosure workbook fails or times out, THEN THE Loader SHALL preserve any existing cached file and SHALL raise a load error.
6. IF the Disclosure_Sheet is missing any required column, THEN THE Loader SHALL raise a load error naming the absent columns and SHALL NOT write the cache file.
7. WHEN the Loader successfully downloads and normalizes the disclosure workbook, THE Loader SHALL write the normalized result to `data/cache/berdo_2026.parquet`.
8. WHEN the Loader processes the Disclosure_Sheet, THE Loader SHALL retain only buildings whose Total GHG Emissions (kgCO2e) is greater than 0 and whose Gross Floor Area (sq ft) is greater than 0.
9. WHEN the Loader processes the Disclosure_Sheet, THE Loader SHALL normalize column names to consistent identifiers for downstream components.
10. WHEN the Loader computes Energy Use Intensity for a retained building, THE Loader SHALL compute EUI as Total Site Energy Usage (kBtu) divided by Gross Floor Area (sq ft).
11. THE Loader SHALL exclude the "Site EUI (Energy Use Intensity kBtu/ft²)" column from all EUI calculations.
12. WHEN the Loader reads a blank, missing, or non-numeric cell for a fuel usage or emissions field, THE Loader SHALL treat that cell as the value 0.
13. WHEN the Loader reads a blank cell for the Applicable_Standard, THE Loader SHALL treat that value as missing.
14. WHEN a building has no reported emissions (Total GHG Emissions equal to 0 or absent), THE System SHALL display the text "No reported emissions — enter your own numbers" for that building.

### Requirement 2: Determine building use and per-period limit

**User Story:** As a property manager, I want each building matched to its BERDO use and emissions limit, so that my exposure is computed against the correct standard.

#### Acceptance Criteria

1. WHEN the Limit_Calculator determines a building's BERDO_Use, THE Limit_Calculator SHALL map the building's "Largest Property Type" to a BERDO_Use using `data/property_type_map.csv`, matching the "Largest Property Type" after trimming leading and trailing whitespace and ignoring letter case.
2. WHERE a building's Applicable_Standard is present (a non-empty numeric value greater than or equal to 0), THE Limit_Calculator SHALL use that Applicable_Standard value verbatim as the 2025–2029 limit, including blended or individual standard values (for example 8.1 or 4.4), without substituting the mapped BERDO_Use's table value.
3. WHERE a building's Applicable_Standard is absent (empty or non-numeric), THE Limit_Calculator SHALL use the mapped BERDO_Use's 2025–2029 value from `data/berdo_limits.csv` as the 2025–2029 limit.
4. WHEN the Limit_Calculator determines limits for the 2030–2034, 2035–2039, 2040–2044, 2045–2049, and 2050+ periods, THE Limit_Calculator SHALL use the mapped BERDO_Use's values from `data/berdo_limits.csv`, where a value of 0 (the 2050+ period) is a valid limit of zero and not treated as a missing value.
5. IF a building's "Largest Property Type" (after trimming and case-insensitive comparison) has no mapping in `data/property_type_map.csv`, THEN THE System SHALL display "limit unknown" for that building.
6. IF a building's "Largest Property Type" (after trimming and case-insensitive comparison) has no mapping in `data/property_type_map.csv`, THEN THE Exposure_Calculator SHALL exclude that building from citywide totals.
7. IF the mapped BERDO_Use has no matching row in `data/berdo_limits.csv`, THEN THE System SHALL display "limit unknown" for that building, THE Exposure_Calculator SHALL exclude that building from citywide totals, and no limit value SHALL be computed for that building.

### Requirement 3: Compute per-period exposure

**User Story:** As a property manager, I want to see my building's estimated ACP for each compliance period, so that I can plan for future costs.

#### Acceptance Criteria

1. WHEN the Exposure_Calculator computes exposure for a Period, THE Exposure_Calculator SHALL compute Excess_Tons as max(0, emissions in kgCO2e − limit × floor area in sq ft) divided by 1000, expressed in metric tons CO2e, using floating-point arithmetic with no intermediate rounding.
2. WHEN the Exposure_Calculator computes the ACP for a Period, THE Exposure_Calculator SHALL compute ACP as Excess_Tons multiplied by 234 dollars.
3. WHEN the Exposure_Calculator computes exposure, THE Exposure_Calculator SHALL compute a result for each of the six Periods in order: 2025–2029, 2030–2034, 2035–2039, 2040–2044, 2045–2049, and 2050+.
4. WHEN the limit for the 2050+ Period is 0, THE Exposure_Calculator SHALL compute ACP as total emissions in metric tons CO2e multiplied by 234 dollars.
5. THE Exposure_Calculator SHALL never produce a negative Excess_Tons or a negative ACP, including when emissions are at or below the limit times floor area.
6. IF a Period's start year is earlier than a building's First_Compliance_Year, THEN THE System SHALL display "not yet covered" and an ACP of $0 for that Period, and THE Exposure_Calculator SHALL exclude that Period's exposure from citywide totals for that Period.
7. WHEN the System displays Excess_Tons and ACP, THE System SHALL round tons to 1 decimal place and dollars to whole dollars for display only, while retaining unrounded float values for computation.

### Requirement 4: Model retrofit scenarios

**User Story:** As a condo board member, I want to adjust heat-pump and efficiency sliders, so that I can see how retrofits reduce my building's estimated exposure.

#### Acceptance Criteria

1. THE System SHALL accept a heat-pump fraction f in the range 0.0 to 1.0 inclusive and an efficiency percentage p in the range 0 to 100 inclusive, and SHALL reject values outside those ranges.
2. WHEN the Scenario_Calculator applies a heat-pump fraction f, THE Scenario_Calculator SHALL reduce the building's natural-gas emissions by f multiplied by the building's natural-gas emissions.
3. WHEN the Scenario_Calculator applies a heat-pump fraction f, THE Scenario_Calculator SHALL compute added kWh as f multiplied by natural-gas kBtu multiplied by the boiler-efficiency assumption, divided by the product of the COP assumption and 3.412.
4. WHEN the Scenario_Calculator applies a heat-pump fraction f, THE Scenario_Calculator SHALL compute added emissions as the added kWh multiplied by the building's Electricity_Factor.
5. IF a building's natural-gas usage is 0 (for example a district-steam-only building), THEN THE Scenario_Calculator SHALL leave the building's emissions unchanged for any heat-pump fraction f.
6. WHILE a building's Electricity_Factor is 0, THE Scenario_Calculator SHALL not increase the building's emissions for any heat-pump fraction f.
7. WHEN the Scenario_Calculator applies an efficiency percentage p, THE Scenario_Calculator SHALL reduce all energy use and all emissions by percentage p.
8. WHEN both an efficiency percentage p and a heat-pump fraction f are applied, THE Scenario_Calculator SHALL apply the efficiency reduction first and then the heat-pump conversion.
9. THE System SHALL display the boiler-efficiency assumption of 0.85 as an editable input accepting values greater than 0 and up to 1.0.
10. THE System SHALL display the heat-pump seasonal COP assumption of 2.5 as an editable input accepting values greater than 0.
11. WHEN the User changes the boiler-efficiency or COP assumption, THE Scenario_Calculator SHALL use the changed value in the heat-pump computation.

### Requirement 5: Generate the board memo

**User Story:** As a property manager, I want a one-page memo drafted from my building's numbers, so that I can present the estimate to my board.

#### Acceptance Criteria

1. WHEN the User requests a memo, THE Memo_Generator SHALL call the Claude API with only the building's computed numbers from the Exposure_Calculator and Scenario_Calculator and the chosen scenario, excluding any value not produced by those calculators or the City's data file.
2. WHEN the Memo_Generator calls the Claude API, THE Memo_Generator SHALL request a strict JSON response via tool use containing exactly the fields headline, exposure_summary, recommendation, tradeoffs, and next_steps.
3. WHEN the Memo_Generator receives a JSON response that parses successfully and contains all five required fields, THE System SHALL render the response as a one-page board memo.
4. THE Memo_Generator SHALL render in the memo only numeric values that match the values provided by the Exposure_Calculator and Scenario_Calculator exactly, with tons displayed to 1 decimal place and dollars displayed as whole dollars.
5. IF the rendered memo would contain a numeric value that does not match a value provided by the Exposure_Calculator or Scenario_Calculator, THEN THE System SHALL render the templated memo instead.
6. THE Memo_Generator SHALL exclude from the memo any statement that the building is in violation, will be fined, or that constitutes legal or financial advice, and SHALL include the text that the result is an estimate, not a compliance determination.
7. WHEN the Memo_Generator calls the Claude API, THE Memo_Generator SHALL apply a timeout of 20 seconds.
8. IF the Claude API call fails, times out after 20 seconds, returns a response that does not parse as JSON, returns JSON missing any of the five required fields, or returns a rate-limiting error, THEN THE System SHALL render a templated memo that indicates the drafted memo was unavailable.
9. IF either the Streamlit secret `CLAUDE_MODEL` or `ANTHROPIC_API_KEY` is missing or empty, THEN THE Memo_Generator SHALL skip the Claude API call and THE System SHALL render a templated memo.
10. WHEN the secrets are present, THE Memo_Generator SHALL read the model identifier from the Streamlit secret `CLAUDE_MODEL` and the API key from the Streamlit secret `ANTHROPIC_API_KEY`.
11. THE Memo_Generator SHALL exclude the value of the API key from all log output.

### Requirement 6: Display the citywide view

**User Story:** As a City of Boston staff member, I want a citywide view of ACP exposure, so that I can decide where to focus outreach.

#### Acceptance Criteria

1. WHEN the User opens the City view, THE System SHALL display a bar chart of total 2030–2034 ACP exposure in whole dollars grouped by ZIP code, including only buildings whose BERDO use is mapped (not "limit unknown").
2. WHEN the User opens the City view, THE System SHALL sort the bar chart in descending order of total 2030–2034 ACP exposure, so that the ZIP code with the highest exposure appears first.
3. IF a building's ZIP code is missing or blank, THEN THE System SHALL use the Parcel Address Zip Code as the ZIP code for that building in the bar chart.
4. IF a building has no ZIP code and no Parcel Address Zip Code, THEN THE System SHALL group that building under a single "Unknown ZIP" category in the bar chart rather than excluding it.
5. IF no building qualifies for the bar chart after filtering out "limit unknown" buildings, THEN THE System SHALL display a message indicating that no citywide exposure data is available instead of an empty chart.
6. WHEN the User opens the City view, THE System SHALL display the count of buildings over the limit in the 2025–2029 Period as a non-negative whole number, counting only buildings whose BERDO use is mapped.
7. WHEN the User opens the City view, THE System SHALL display the count of buildings over the limit in the 2030–2034 Period as a non-negative whole number, counting only buildings whose BERDO use is mapped.

### Requirement 7: Display the City's compliance status

**User Story:** As a property manager, I want to see the City's own compliance status beside the estimate, so that I can compare the estimate with the City's official determination.

#### Acceptance Criteria

1. WHEN a building is shown and the City's Compliance_Status is present and non-blank, THE System SHALL display the Compliance_Status value verbatim as provided in the City's data file, next to the building's estimated exposure.
2. WHEN the City's Compliance_Status is displayed, THE System SHALL label it as the City's official status and visually distinguish it from the System's estimated exposure so that the two values are presented as separate, clearly identified fields.
3. IF the City's Compliance_Status is missing, blank, or contains only whitespace, THEN THE System SHALL display a placeholder indicating the City's status is not available for that building and SHALL still display the building's estimated exposure.
4. WHEN the City's Compliance_Status is displayed, THE System SHALL accompany it with text indicating that the System's exposure figure is an estimate and not a compliance determination.

### Requirement 8: Present honest disclaimers

**User Story:** As a property manager, I want every result screen to be clearly labeled as an estimate with its data source, so that I do not mistake it for an official compliance determination.

#### Acceptance Criteria

1. WHEN the System displays any result screen (Building view, City view, or generated memo), THE System SHALL display the text "Estimate, not a compliance determination" visible without scrolling or further interaction on that screen.
2. WHEN the System displays any result screen (Building view, City view, or generated memo), THE System SHALL display the data source and year as the exact text "City of Boston BERDO 2026 disclosure, 2025 data, PDDL license".
3. WHEN the System displays any result screen (Building view, City view, or generated memo), THE System SHALL display text stating that portfolio and campus compliance and flexibility measures can reduce real exposure.
4. WHEN the System displays any result screen (Building view, City view, or generated memo), THE System SHALL display the text "The City projects grid emissions roughly flat through 2034 (data/projected_grid_factors.csv), so 2030 estimates hold; later periods may be lower."
5. WHEN the System describes a building's exposure on any result screen, THE System SHALL use the term "estimated exposure".
6. THE System SHALL display only numeric values that were returned by a calculator function in the berdo package or read directly from the City's data file, and SHALL display no building-specific or exposure number from any other source.
7. WHEN a User requests an official or legal compliance answer, THE System SHALL display text directing the User to the City of Boston BERDO team for official answers.
8. THE System SHALL never display the phrase "in violation" or the phrase "will be fined" on any result screen or in any generated memo.

## Correctness Properties

These properties constrain the pure functions in `berdo/` and are the basis for property-based tests. (Property P8, the blended-limit bounds property, is out of scope this session and is intentionally omitted.)

### Requirement 9: Calculation correctness properties

**User Story:** As a developer, I want the calculation functions to satisfy well-defined correctness properties, so that the estimates are trustworthy and testable.

#### Acceptance Criteria

1. THE Exposure_Calculator SHALL produce Excess_Tons values greater than or equal to 0 and ACP values greater than or equal to 0. (P1)
2. WHILE floor area and limit are held fixed, THE Exposure_Calculator SHALL produce an ACP that is non-decreasing as emissions increase. (P2)
3. WHILE floor area and emissions are held fixed, THE Exposure_Calculator SHALL produce an ACP that is non-increasing as the limit increases. (P3)
4. THE Exposure_Calculator SHALL produce, for any single building, an ACP that is non-decreasing across later Periods. (P4)
5. WHEN the efficiency percentage p is 0 and the heat-pump fraction f is 0, THE Scenario_Calculator SHALL return the original emissions exactly. (P5)
6. WHEN the efficiency percentage p increases, THE Scenario_Calculator SHALL produce emissions that are non-increasing. (P6)
7. WHEN the heat-pump fraction f is any value in the range 0 to 1 inclusive, THE Scenario_Calculator SHALL produce emissions greater than or equal to 0. (P7)
8. WHILE a building's Electricity_Factor is 0, THE Scenario_Calculator SHALL produce emissions that are non-increasing for any heat-pump fraction f. (P7)
9. WHEN the limit is 0 at the 2050+ Period, THE Exposure_Calculator SHALL produce an ACP equal to total emissions in tons multiplied by 234 dollars. (P9)

### Requirement 10: Verification against reference data

**User Story:** As a developer, I want the calculations validated against hand-checked golden values and whole-dataset totals, so that regressions are caught.

#### Acceptance Criteria

1. WHEN the Exposure_Calculator computes ACP for the four buildings in `data/golden_buildings.csv`, THE Exposure_Calculator SHALL reproduce the expected values in `GOLDEN_TESTS.md` within $0.05.
2. WHEN the Loader loads the full disclosure dataset, THE Loader SHALL retain 1,809 buildings.
3. WHEN the Exposure_Calculator computes the 2025–2029 totals over the full dataset, THE Exposure_Calculator SHALL produce 63 buildings over the limit with a total ACP of $2,880,426.65 within $1.
4. WHEN the Exposure_Calculator computes the 2030–2034 totals over the full dataset, THE Exposure_Calculator SHALL produce 963 buildings over the limit with a total ACP of $27,406,457.43 within $1.
5. WHEN the Exposure_Calculator computes per-use results over the full dataset, THE Exposure_Calculator SHALL match the counts in `data/expected_by_use.csv` exactly and the totals within $1.
6. WHEN the Exposure_Calculator computes ACP for the 40 buildings in `data/expected_sample_40.csv`, THE Exposure_Calculator SHALL reproduce the expected per-building values within $0.05.

## Non-Goals

- The System SHALL NOT provide user login or authentication.
- The System SHALL NOT perform address geocoding.
- The System SHALL NOT display map tiles.
- The System SHALL NOT use a database.
- The blended standard ("All Property Types and GFAs" weighting) is out of scope this session.
- The green-power retrofit scenario is out of scope this session.
