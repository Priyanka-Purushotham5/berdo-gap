# Golden tests — expected values

Four real buildings from the City's 2026 BERDO disclosure (2025 data), copied into `data/golden_buildings.csv`. Expected values were computed by hand with the formulas in `KIRO_SPEC_BRIEF.md` and cross-checked against the City's own compliance status. Tolerance: $0.05.

Formula: excess tons = max(0, emissions − limit × floor area) ÷ 1000; ACP = excess tons × $234; $0 for periods that start before the first compliance year.

## Yearly ACP by period

| Building | 2025–2029 | 2030–2034 | 2035–2039 | 2040–2044 | 2045–2049 | 2050+ |
| --- | --- | --- | --- | --- | --- | --- |
| 100064, 185 Dudley St (Office, first year 2030) | $0.00 (not yet covered) | $1,680.89 | $5,453.35 | $9,225.80 | $12,998.26 | $16,770.71 |
| 100018, 1047 Commonwealth Ave (Multifamily) | **$3,666.73** | $43,764.97 | $57,917.29 | $74,428.33 | $86,221.93 | $100,374.25 |
| 100045, 1455-1459 Tremont St (Multifamily) | $0.00 | $0.00 | $0.00 | $2,261.89 | $6,821.50 | $12,293.03 |
| 100005, 24 School St (Office; electricity + district steam, no gas) | $0.00 | $5,606.64 | $30,839.14 | $56,071.64 | $81,304.14 | $106,536.64 |

**Cross-check with the City:** 100018 is over its 2025 limit by 15.67 tons, and the City lists it as "Action Needed". 100045 and 100005 are under, and the City lists both as "In Compliance". The calculator agrees with the City on all three covered buildings.

Note: 100005 has district steam emissions (262,315.6 kg) but no gas, so the heat-pump slider must change nothing for it.

## Heat-pump scenario (boiler efficiency 0.85, COP 2.5)

Added kWh = f × gas kBtu × 0.85 ÷ (2.5 × 3.412); new emissions = emissions − f × gas emissions + added kWh × (electricity emissions ÷ kWh).

| Building | f | Added kWh | New emissions (kg) | New 2030–2034 ACP |
| --- | --- | --- | --- | --- |
| 100018 | 0.5 | 256,106 | 330,430.3 | $20,711.42 |
| 100018 | 1.0 | 512,211 | 231,910.8 | **$0.00** |
| 100064 | 0.5 | 50,621 | 52,005.0 | $0.00 |
| 100045 | 1.0 | 46,061 | 34,855.5 | $0.00 |

**Demo line:** 1047 Commonwealth Ave faces about $43,800 a year from 2030; converting its gas heat to heat pumps takes that to $0.

## Whole-dataset regression check

Two more expected-value files, computed independently from the City's 2026 disclosure with the same rules (2025 limit = City's applied standard when present, otherwise the mapped use; 2030 limit = mapped use; $0 for periods before the first compliance year):

- `data/expected_by_use.csv`: for each of the 13 BERDO uses and in total, building count, number over the limit and total ACP for 2025–2029 and 2030–2034. Your loaded data must give **1,809 buildings, 63 over in 2025–2029 ($2,880,426.65), 963 over in 2030–2034 ($27,406,457.43)**. Tolerance: count exact, totals within $1.
- `data/expected_sample_40.csv`: 40 buildings by BERDO ID (10 over today, 20 over only from 2030, 10 never over through 2034) with expected per-building ACP. Tolerance $0.05.

If your totals differ, the usual causes are: filtering rows differently (keep total GHG > 0 and floor area > 0), using the Site EUI column, ignoring the City's applied 2025 standard, or charging buildings for periods before their first compliance year.

Note: one Services building alone accounts for about $1.68M of the 2025–2029 total; check it before quoting the citywide figure.
