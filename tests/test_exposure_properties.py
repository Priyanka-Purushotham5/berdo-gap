"""Property-based tests for berdo.exposure (Hypothesis).

Covers correctness properties P1, P2, P3 (excess_tons / acp_dollars) and
P4, P9 (period_exposure), per the design document's "Correctness Properties"
section and Hypothesis strategy table.

Per the data-rules steering: a property-based test is NEVER weakened to make
it pass. If a property appears to fail, the cause is investigated and
documented in a comment rather than relaxing the assertion.
"""

from __future__ import annotations

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from berdo.exposure import (
    ACP_RATE_USD_PER_TON,
    PERIOD_START_YEARS,
    STATUS_COVERED,
    acp_dollars,
    excess_tons,
    period_exposure,
)
from berdo.limits import PERIODS, load_limits_table

# At least 100 iterations per property, per the testing strategy.
PBT_SETTINGS = settings(max_examples=200)

# Shared strategies matching the design's strategy table.
emissions_strategy = st.floats(
    min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False
)
limit_strategy = st.floats(
    min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False
)
floor_area_strategy = st.floats(
    min_value=1e-6, max_value=1e7, allow_nan=False, allow_infinity=False
)

# The 13 BERDO uses and their real per-period limit vectors.
_LIMITS_TABLE = load_limits_table()
_BERDO_USES = sorted(_LIMITS_TABLE.keys())


# Feature: berdo-gap, Property 1: Exposure is never negative.
# For all emissions >= 0, limits >= 0, floor areas > 0, both excess_tons and
# acp_dollars produce values >= 0, including when emissions are at or below
# limit * floor_area.
@PBT_SETTINGS
@given(
    emissions=emissions_strategy,
    limit=limit_strategy,
    floor_area=floor_area_strategy,
)
def test_p1_exposure_never_negative(
    emissions: float, limit: float, floor_area: float
) -> None:
    """Validates: Requirements 9.1"""
    tons = excess_tons(emissions, limit, floor_area)
    dollars = acp_dollars(tons)
    assert tons >= 0.0
    assert dollars >= 0.0


# Feature: berdo-gap, Property 2: ACP is non-decreasing in emissions.
# For a fixed limit and floor area, any two emissions e1 <= e2 give
# ACP(e1) <= ACP(e2).
@PBT_SETTINGS
@given(
    e1=emissions_strategy,
    e2=emissions_strategy,
    limit=limit_strategy,
    floor_area=floor_area_strategy,
)
def test_p2_acp_non_decreasing_in_emissions(
    e1: float, e2: float, limit: float, floor_area: float
) -> None:
    """Validates: Requirements 9.2"""
    lo, hi = sorted((e1, e2))
    acp_lo = acp_dollars(excess_tons(lo, limit, floor_area))
    acp_hi = acp_dollars(excess_tons(hi, limit, floor_area))
    assert acp_lo <= acp_hi


# Feature: berdo-gap, Property 3: ACP is non-increasing in the limit.
# For fixed emissions and floor area, any two limits L1 <= L2 give
# ACP(L1) >= ACP(L2).
@PBT_SETTINGS
@given(
    emissions=emissions_strategy,
    l1=limit_strategy,
    l2=limit_strategy,
    floor_area=floor_area_strategy,
)
def test_p3_acp_non_increasing_in_limit(
    emissions: float, l1: float, l2: float, floor_area: float
) -> None:
    """Validates: Requirements 9.3"""
    lo, hi = sorted((l1, l2))
    acp_lo_limit = acp_dollars(excess_tons(emissions, lo, floor_area))
    acp_hi_limit = acp_dollars(excess_tons(emissions, hi, floor_area))
    assert acp_lo_limit >= acp_hi_limit


# Feature: berdo-gap, Property 4: ACP is non-decreasing across later periods.
# For any single building, the ACP of a covered period is <= the ACP of every
# subsequent covered period. BERDO limits decrease over time, so ACP rises.
# Not-yet-covered periods ($0) are excluded from the comparison.
@PBT_SETTINGS
@given(
    emissions=emissions_strategy,
    floor_area=floor_area_strategy,
    berdo_use=st.sampled_from(_BERDO_USES),
    first_compliance_year=st.sampled_from([2025, 2030]),
)
def test_p4_acp_non_decreasing_across_later_periods(
    emissions: float,
    floor_area: float,
    berdo_use: str,
    first_compliance_year: int,
) -> None:
    """Validates: Requirements 9.4"""
    limit_vector = _LIMITS_TABLE[berdo_use]
    result = period_exposure(
        emissions, limit_vector, floor_area, first_compliance_year
    )
    # Collect ACP for covered periods only, in period order.
    covered_acps = [
        float(result[period]["acp_usd"])
        for period in PERIODS
        if result[period]["status"] == STATUS_COVERED
    ]
    for earlier, later in zip(covered_acps, covered_acps[1:]):
        assert earlier <= later


# Feature: berdo-gap, Property 9: Zero limit at 2050+ charges all emissions.
# For all emissions >= 0 and floor areas > 0, when the limit is 0 (the 2050+
# period) the ACP equals total emissions in metric tons (emissions / 1000)
# multiplied by 234.
@PBT_SETTINGS
@given(
    emissions=emissions_strategy,
    floor_area=floor_area_strategy,
    first_compliance_year=st.sampled_from([2025, 2030]),
)
def test_p9_zero_limit_2050_charges_all_emissions(
    emissions: float, floor_area: float, first_compliance_year: int
) -> None:
    """Validates: Requirements 9.9"""
    # Build a limit vector whose 2050+ limit is 0 (as every real BERDO use is).
    limit_vector = {period: 0.0 for period in PERIODS}
    result = period_exposure(
        emissions, limit_vector, floor_area, first_compliance_year
    )
    # 2050+ starts in 2050, always on/after first_compliance_year, so covered.
    assert PERIOD_START_YEARS["2050+"] >= first_compliance_year
    expected_acp = (emissions / 1000.0) * ACP_RATE_USD_PER_TON
    assert result["2050+"]["status"] == STATUS_COVERED
    assert result["2050+"]["acp_usd"] == pytest.approx(expected_acp)
    assert result["2050+"]["excess_tons"] == pytest.approx(emissions / 1000.0)
