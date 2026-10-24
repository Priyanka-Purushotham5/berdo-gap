"""Excess tons and ACP by period.

Pure functions that turn emissions, a per-period limit vector, and floor area
into excess metric tons CO2e and the Alternative Compliance Payment (ACP) for
each of BERDO's six compliance periods. All money and tonnage are computed in
floats with no intermediate rounding; display rounding lives in ``app.py``.

Satisfies: Requirements 3.1-3.6, 9.1 (P1), 9.4 (P4), 9.9 (P9).
"""

from __future__ import annotations

try:
    # Period ordering is owned by berdo.limits (the single source of truth).
    from berdo.limits import PERIODS
except ImportError:  # pragma: no cover - limits.py may not exist yet
    PERIODS: tuple[str, ...] = (
        "2025-2029",
        "2030-2034",
        "2035-2039",
        "2040-2044",
        "2045-2049",
        "2050+",
    )

# $234 per metric ton CO2e over the limit, per year.
ACP_RATE_USD_PER_TON: float = 234.0

# Start year of each compliance period, used for the first-compliance-year gate.
PERIOD_START_YEARS: dict[str, int] = {
    "2025-2029": 2025,
    "2030-2034": 2030,
    "2035-2039": 2035,
    "2040-2044": 2040,
    "2045-2049": 2045,
    "2050+": 2050,
}

# Status strings used by period_exposure.
STATUS_COVERED: str = "covered"
STATUS_NOT_YET_COVERED: str = "not yet covered"


def excess_tons(
    emissions_kg: float, limit_per_sqft: float, floor_area_sqft: float
) -> float:
    """Return excess emissions over the limit, in metric tons CO2e.

    Computes ``max(0, emissions_kg - limit_per_sqft * floor_area_sqft) / 1000``
    using floats with no intermediate rounding. Never negative (a building at or
    below its limit has 0 excess tons).

    Satisfies: R3.1, R3.5, R9.1 (P1).
    """
    allowed_kg = limit_per_sqft * floor_area_sqft
    excess_kg = emissions_kg - allowed_kg
    if excess_kg < 0.0:
        excess_kg = 0.0
    return excess_kg / 1000.0


def acp_dollars(excess_tons_value: float) -> float:
    """Return the ACP in dollars for a given excess-tons value.

    Computes ``excess_tons_value * 234.0``. Never negative.

    Satisfies: R3.2, R3.5, R9.1 (P1).
    """
    dollars = excess_tons_value * ACP_RATE_USD_PER_TON
    if dollars < 0.0:
        dollars = 0.0
    return dollars


def period_exposure(
    emissions_kg: float,
    limit_vector: dict[str, float],
    floor_area_sqft: float,
    first_compliance_year: int,
) -> dict[str, dict[str, float | str]]:
    """Return per-period excess tons, ACP, and status for all six periods.

    The result maps each period key to ``{"excess_tons": float,
    "acp_usd": float, "status": str}`` and is ordered by ``PERIODS``.

    A period whose start year is earlier than ``first_compliance_year`` is
    reported with status "not yet covered", excess_tons 0.0, and acp_usd 0.0
    (the caller excludes these from citywide totals). The 2050+ period limit of
    0 means ACP equals total emissions in tons * 234.

    No intermediate rounding; all returned numbers are unrounded floats.

    Satisfies: R3.1-R3.6, R9.4 (P4), R9.9 (P9).
    """
    result: dict[str, dict[str, float | str]] = {}
    for period in PERIODS:
        start_year = PERIOD_START_YEARS[period]
        if start_year < first_compliance_year:
            result[period] = {
                "excess_tons": 0.0,
                "acp_usd": 0.0,
                "status": STATUS_NOT_YET_COVERED,
            }
            continue

        limit_per_sqft = limit_vector[period]
        tons = excess_tons(emissions_kg, limit_per_sqft, floor_area_sqft)
        result[period] = {
            "excess_tons": tons,
            "acp_usd": acp_dollars(tons),
            "status": STATUS_COVERED,
        }
    return result
