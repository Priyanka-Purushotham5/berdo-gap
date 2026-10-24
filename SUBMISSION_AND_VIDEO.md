# Video script, description and write-up outline

## Video (target 2:40; hard limit 3:00)

| Time | Show | Say (roughly) |
| --- | --- | --- |
| 0:00–0:15 | City view: bar chart by ZIP | "Boston's BERDO law caps building emissions. Go over, and you pay $234 a ton, every year. From the City's own 2025 data: 900 buildings that owe nothing today will be over the limit in 2030." |
| 0:15–0:45 | Search "1047 Commonwealth" | "This apartment building is already 16 tons over. About $3,700 a year now, about $43,800 a year from 2030." |
| 0:45–1:15 | Drag heat-pump slider 0 → 100% | "Move its gas heat to heat pumps and the 2030 bill goes to zero. The assumptions are on screen and editable." |
| 1:15–1:40 | Click "Draft board memo" | "Claude turns those numbers into a one-page memo for the condo board, using only figures from the calculator." |
| 1:40–2:20 | Kiro: spec files, a hook running tests, a Hypothesis counterexample, steering file, MCP fetch | "Built with Kiro, spec-first: nine correctness properties became property-based tests, and four real buildings match the City's own compliance status." |
| 2:20–2:40 | About & sources page | "Every number comes from City data. It's an estimate, not a ruling. Next: every Massachusetts town adopting a building performance standard." |

Record at 1080p; no music with copyright. Upload as **Public** on YouTube and test the link in a private window.

## Text description (paste and edit)

**BERDO Gap** estimates what each large Boston building will owe under BERDO, the city's building emissions law, and shows which retrofit removes that cost. It uses the City of Boston's 2026 BERDO disclosure (2025 data, 1,809 buildings with reported emissions) and the official limits for 13 building uses through 2050.

For a chosen building it shows estimated yearly Alternative Compliance Payments ($234 per ton over the limit) for every compliance period, lets the owner test heat pumps, efficiency and green power with editable assumptions, and uses Claude to draft a one-page board memo from the calculated numbers. A city view shows where 2030 exposure concentrates by ZIP code.

Our calculator agrees with the City's compliance status for the covered buildings we tested. Estimates, not compliance determinations: portfolio or campus compliance and a cleaner grid can lower real costs.

**Data:** City of Boston BERDO disclosure 2026 (Analyze Boston, PDDL); limits from boston.gov. **Built with:** Kiro, Python, Streamlit, Claude API.

## Kiro write-up outline
Copy from `KIRO_USAGE.md`, organized under the rules' headings: tools used; spec-driven development (and the piece you vibe-coded for comparison); hooks; steering (which rule mattered most: probably the Site-EUI trap); MCP; property-based testing (the counterexample it found); powers. Add one line: "Planning notes, the limits-table check and golden test values were prepared with Claude; all application code was generated in Kiro."
