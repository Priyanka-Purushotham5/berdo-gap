"""Property-based tests for berdo.scenarios (P5, P6, P7).

Per the data-rules steering: a property-based test is NEVER weakened to make
it pass. If a property appears to fail, the cause is investigated and
documented in a comment rather than relaxing the assertion.

Hypothesis strategies follow the design.md strategy table:
- P5: emissions in [0, 1e9], gas_kbtu in [0, 1e8], gas_emissions in
  [0, emissions], elec_factor in [0, 0.3]; p = 0, f = 0.
- P6: building params as above; efficiency pair p1 <= p2 in [0, 100].
- P7: emissions in [0, 1e9], gas_kbtu in [0, 1e8], gas_emissions in
  [0, emissions], elec_factor in [0, 0.3] (plus a fixed elec_factor = 0
  branch), f in [0, 1].

Note on gas_emissions: gas emissions are a subset of total emissions, so the
strategies constrain gas_emissions to [0, emissions].
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from berdo.scenarios import apply_efficiency, apply_heat_pump, apply_scenario

# Shared numeric strategies for building parameters.
EMISSIONS = st.floats(min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False)
GAS_KBTU = st.floats(min_value=0.0, max_value=1e8, allow_nan=False, allow_infinity=False)
ELEC_FACTOR = st.floats(min_value=0.0, max_value=0.3, allow_nan=False, allow_infinity=False)
FRACTION = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
PERCENT = st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)


@st.composite
def building(draw):
    """A building's (emissions, gas_kbtu, gas_emissions, elec_factor).

    gas_emissions is drawn as a fraction of total emissions so it stays a
    subset of total emissions (gas is one component of the total).
    """
    emissions = draw(EMISSIONS)
    gas_kbtu = draw(GAS_KBTU)
    gas_fraction = draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False))
    gas_emissions = emissions * gas_fraction
    elec_factor = draw(ELEC_FACTOR)
    return emissions, gas_kbtu, gas_emissions, elec_factor


# Feature: berdo-gap, Property 5: Scenario identity at p = 0 and f = 0 -
# applying the scenario with efficiency p = 0 and heat-pump fraction f = 0
# returns the original emissions exactly. Validates: Requirements 9.5
@settings(max_examples=200)
@given(bldg=building())
def test_p5_scenario_identity_at_zero(bldg):
    emissions, gas_kbtu, gas_emissions, elec_factor = bldg
    result = apply_scenario(
        emissions_kg=emissions,
        gas_kbtu=gas_kbtu,
        gas_emissions_kg=gas_emissions,
        elec_factor=elec_factor,
        f=0.0,
        p=0.0,
    )
    # Exact equality: the identity must hold bit-for-bit (no float drift).
    assert result == emissions


# Feature: berdo-gap, Property 6: Emissions are non-increasing in efficiency -
# for any two efficiency percentages p1 <= p2 in [0, 100], emissions after p1
# are >= emissions after p2 (both for apply_efficiency and apply_scenario).
# Validates: Requirements 9.6
@settings(max_examples=200)
@given(
    bldg=building(),
    f=FRACTION,
    ps=st.tuples(PERCENT, PERCENT),
)
def test_p6_emissions_non_increasing_in_efficiency(bldg, f, ps):
    emissions, gas_kbtu, gas_emissions, elec_factor = bldg
    p1, p2 = sorted(ps)  # ensure p1 <= p2

    # apply_efficiency: scaling a non-negative value by a larger efficiency
    # percentage never increases it.
    eff1 = apply_efficiency(emissions, p1)
    eff2 = apply_efficiency(emissions, p2)
    assert eff1 >= eff2

    # apply_scenario: with the same heat-pump fraction f, a larger efficiency
    # percentage scales emissions and the gas feed down further, so the
    # resulting total emissions are non-increasing in p.
    scen1 = apply_scenario(
        emissions_kg=emissions,
        gas_kbtu=gas_kbtu,
        gas_emissions_kg=gas_emissions,
        elec_factor=elec_factor,
        f=f,
        p=p1,
    )
    scen2 = apply_scenario(
        emissions_kg=emissions,
        gas_kbtu=gas_kbtu,
        gas_emissions_kg=gas_emissions,
        elec_factor=elec_factor,
        f=f,
        p=p2,
    )
    assert scen1 >= scen2


# Feature: berdo-gap, Property 7: Heat-pump emissions stay valid - for any
# heat-pump fraction f in [0, 1], apply_heat_pump produces emissions >= 0; and
# when the building's electricity factor is 0, the resulting emissions are
# <= the original emissions for any f. Validates: Requirements 9.7, 9.8
@settings(max_examples=200)
@given(bldg=building(), f=FRACTION)
def test_p7_heat_pump_emissions_non_negative(bldg, f):
    emissions, gas_kbtu, gas_emissions, elec_factor = bldg
    result = apply_heat_pump(
        emissions_kg=emissions,
        gas_kbtu=gas_kbtu,
        gas_emissions_kg=gas_emissions,
        elec_factor=elec_factor,
        f=f,
    )
    assert result >= 0.0


# Feature: berdo-gap, Property 7: Heat-pump emissions stay valid - fixed
# elec_factor == 0 branch: when the added electricity carries no emissions,
# emissions never increase versus the original for any f.
# Validates: Requirements 9.7, 9.8
@settings(max_examples=200)
@given(
    emissions=EMISSIONS,
    gas_kbtu=GAS_KBTU,
    gas_fraction=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    f=FRACTION,
)
def test_p7_heat_pump_non_increasing_when_elec_factor_zero(emissions, gas_kbtu, gas_fraction, f):
    gas_emissions = emissions * gas_fraction  # gas is a subset of total emissions
    result = apply_heat_pump(
        emissions_kg=emissions,
        gas_kbtu=gas_kbtu,
        gas_emissions_kg=gas_emissions,
        elec_factor=0.0,
        f=f,
    )
    assert result >= 0.0
    assert result <= emissions
