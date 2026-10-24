"""Retrofit scenario transforms for BERDO Gap.

Pure functions that model how efficiency and heat-pump retrofits change a
building's emissions. Efficiency scales energy and emissions down by a
percentage; a heat-pump conversion moves a fraction of gas heat onto
electricity. All values are floats with no intermediate rounding; the UI
rounds only for display.
"""

BOILER_EFFICIENCY_DEFAULT: float = 0.85
COP_DEFAULT: float = 2.5
KBTU_PER_KWH: float = 3.412


def apply_efficiency(value: float, p: float) -> float:
    """Scale an energy or emissions value by the efficiency percentage p.

    Returns ``value * (1 - p / 100)`` for p in ``0..100``. At p == 0 the value
    is returned unchanged.
    Satisfies: R4.7, R9.6 (P6).
    """
    return value * (1 - p / 100)


def added_kwh(
    gas_kbtu: float,
    f: float,
    boiler_eff: float = BOILER_EFFICIENCY_DEFAULT,
    cop: float = COP_DEFAULT,
) -> float:
    """Electricity added when converting fraction f of gas heat to heat pumps.

    Returns ``f * gas_kbtu * boiler_eff / (cop * 3.412)``. The useful heat
    delivered by burning ``gas_kbtu`` at ``boiler_eff`` is supplied instead by
    a heat pump at coefficient of performance ``cop``; dividing by
    ``cop * KBTU_PER_KWH`` converts that heat demand into added kWh.
    Satisfies: R4.3, R4.11.
    """
    return f * gas_kbtu * boiler_eff / (cop * KBTU_PER_KWH)


def apply_heat_pump(
    emissions_kg: float,
    gas_kbtu: float,
    gas_emissions_kg: float,
    elec_factor: float,
    f: float,
    boiler_eff: float = BOILER_EFFICIENCY_DEFAULT,
    cop: float = COP_DEFAULT,
) -> float:
    """New total emissions after converting fraction f of gas heat to heat pumps.

    Returns
    ``emissions_kg - f * gas_emissions_kg + added_kwh(...) * elec_factor``.

    When ``gas_kbtu`` is 0 the building has no gas heat to convert, so emissions
    are returned unchanged for any f (both the reduction and the addition rest
    on gas usage / gas emissions being present). When ``elec_factor`` is 0 the
    added electricity carries no emissions, so emissions never increase. The
    result is clamped at 0 so emissions are never negative.
    Satisfies: R4.2, R4.3, R4.4, R4.5, R4.6, R9.7 (P7).
    """
    if gas_kbtu == 0:
        return emissions_kg
    added = added_kwh(gas_kbtu, f, boiler_eff, cop) * elec_factor
    new_emissions = emissions_kg - f * gas_emissions_kg + added
    return max(0.0, new_emissions)


def apply_scenario(
    emissions_kg: float,
    gas_kbtu: float,
    gas_emissions_kg: float,
    elec_factor: float,
    f: float,
    p: float,
    boiler_eff: float = BOILER_EFFICIENCY_DEFAULT,
    cop: float = COP_DEFAULT,
) -> float:
    """Apply efficiency p first, then the heat-pump conversion f.

    The efficiency percentage scales total emissions and the gas values that
    feed the heat-pump step (gas kBtu and gas emissions), then the heat-pump
    conversion runs on those reduced values.

    When ``p == 0`` and ``f == 0`` the original ``emissions_kg`` is returned
    exactly (no float drift): the function short-circuits before any arithmetic
    so the identity property P5 holds bit-for-bit.
    Satisfies: R4.8, R9.5 (P5).
    """
    if p == 0 and f == 0:
        return emissions_kg

    scaled_emissions = apply_efficiency(emissions_kg, p)
    scaled_gas_kbtu = apply_efficiency(gas_kbtu, p)
    scaled_gas_emissions = apply_efficiency(gas_emissions_kg, p)

    return apply_heat_pump(
        scaled_emissions,
        scaled_gas_kbtu,
        scaled_gas_emissions,
        elec_factor,
        f,
        boiler_eff,
        cop,
    )
