---
inclusion: fileMatch
fileMatchPattern: "berdo/**/*.py"
---

# Data and calculation rules

- Source sheet: "Buildings & Campuses" in the City's 2026 BERDO disclosure workbook. Header is row 1.
- Do NOT use the column "Site EUI (Energy Use Intensity kBtu/ft²)": in this file it holds emissions intensity, not EUI. Compute EUI = "Total Site Energy Usage (kBtu)" ÷ "Gross Floor Area (sq ft)".
- Emissions = "Total GHG Emissions (kgCO2e)". Floor area = "Gross Floor Area (sq ft)" (includes parking; that is what the City uses for intensity).
- 2025–2029 limit: use "Applicable Emissions Compliance Standard (kgCO2e/sq ft)" when present; otherwise map "Largest Property Type" through `data/property_type_map.csv` to a BERDO use and read `data/berdo_limits.csv`.
- ACP rate: $234 per metric ton CO2e over the limit, per year. Tons = kg ÷ 1000.
- "First Emissions Compliance Year" is 2025 or 2030. Periods that start before it are "not yet covered" and owe $0.
- Natural gas emission factor in this data is 0.05311 kgCO2e per kBtu. Electricity factors differ by building (about 0.145–0.182 kgCO2e/kWh), so use each building's own ratio: electricity emissions ÷ electricity kWh.
- Treat blank cells as 0 for fuel usage and emissions, and as missing for the applicable standard.
- Never weaken a property-based test to make it pass. If a property looks wrong, stop and explain why in a comment.
