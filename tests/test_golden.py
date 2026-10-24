"""Golden-building and whole-dataset regression tests.

Two layers of verification against reference data (Requirement 10):

- Golden-building tests (Task 8.1, R10.1): the four hand-checked buildings in
  ``data/golden_buildings.csv`` must reproduce every per-period ACP in
  ``GOLDEN_TESTS.md`` within $0.05, including the heat-pump scenario rows, and
  building 100005 (24 School St, Office, electricity + district steam, no gas)
  must be unchanged by any heat-pump fraction.

- Whole-dataset regression tests (Task 8.2, R10.2-R10.6): the full City
  disclosure must retain exactly 1,809 buildings and reproduce the citywide
  totals, the per-use breakdown in ``data/expected_by_use.csv``, and the
  per-building ACP for the 40 buildings in ``data/expected_sample_40.csv``.

These are example-based regression tests, not property-based tests. Per the
data-rules steering: a reference value is NEVER weakened to make a test pass.
If a golden value genuinely mismatched, the cause would be documented here and
the test left failing rather than relaxed.

The whole-dataset tests need the full disclosure. They load it through the real
``berdo.load`` pipeline (cache when present, otherwise a live download) and skip
with a clear reason when neither a cache nor network access is available. They
never fall back to fabricated numbers.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

import pytest

from berdo.exposure import period_exposure
from berdo.limits import (
    PERIODS,
    load_limits_table,
    load_property_type_map,
    map_property_type,
    period_limits,
    resolve_2025_2029_limit,
)
from berdo.load import (
    COL_APPLICABLE_STANDARD,
    COL_BERDO_ID,
    COL_ELECTRICITY_GHG,
    COL_ELECTRICITY_KWH,
    COL_FIRST_COMPLIANCE_YEAR,
    COL_FLOOR_AREA,
    COL_LARGEST_PROPERTY_TYPE,
    COL_TOTAL_GHG,
    DEFAULT_DISCLOSURE_URL,
    LoadError,
    filter_reported,
    is_cache_valid,
    normalize_columns,
    read_disclosure_excel,
)
from berdo.scenarios import apply_heat_pump

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
CACHE_PATH = DATA_DIR / "cache" / "berdo_2026.parquet"

# Tolerances from GOLDEN_TESTS.md / Requirement 10.
GOLDEN_TOL = 0.05  # per-building / per-period ACP, dollars
TOTAL_TOL = 1.0  # citywide and per-use totals, dollars

# Heat-pump scenario constants from GOLDEN_TESTS.md.
BOILER_EFF = 0.85
COP = 2.5


# ---------------------------------------------------------------------------
# Task 8.1 — Golden-building tests (R10.1)
# ---------------------------------------------------------------------------

# Expected per-period ACP for the four golden buildings, transcribed from the
# "Yearly ACP by period" table in GOLDEN_TESTS.md. Order matches PERIODS.
GOLDEN_PERIOD_ACP: dict[int, dict[str, float]] = {
    100064: {
        "2025-2029": 0.00,
        "2030-2034": 1680.89,
        "2035-2039": 5453.35,
        "2040-2044": 9225.80,
        "2045-2049": 12998.26,
        "2050+": 16770.71,
    },
    100018: {
        "2025-2029": 3666.73,
        "2030-2034": 43764.97,
        "2035-2039": 57917.29,
        "2040-2044": 74428.33,
        "2045-2049": 86221.93,
        "2050+": 100374.25,
    },
    100045: {
        "2025-2029": 0.00,
        "2030-2034": 0.00,
        "2035-2039": 0.00,
        "2040-2044": 2261.89,
        "2045-2049": 6821.50,
        "2050+": 12293.03,
    },
    100005: {
        "2025-2029": 0.00,
        "2030-2034": 5606.64,
        "2035-2039": 30839.14,
        "2040-2044": 56071.64,
        "2045-2049": 81304.14,
        "2050+": 106536.64,
    },
}

# Heat-pump scenario expectations from the "Heat-pump scenario" table: the new
# 2030-2034 ACP after converting fraction f of gas heat to heat pumps.
GOLDEN_HEAT_PUMP_ACP_2030: list[tuple[int, float, float]] = [
    # (berdo_id, f, expected 2030-2034 ACP)
    (100018, 0.5, 20711.42),
    (100018, 1.0, 0.00),
    (100064, 0.5, 0.00),
    (100045, 1.0, 0.00),
]


def _load_golden_buildings() -> dict[int, dict[str, object]]:
    """Return ``{berdo_id: row}`` from ``data/golden_buildings.csv``.

    The golden CSV carries its own self-contained columns (already normalized
    to BERDO use, with the City's applied 2025 standard and first compliance
    year), so the golden tests do not depend on the live disclosure download.
    """
    path = DATA_DIR / "golden_buildings.csv"
    buildings: dict[int, dict[str, object]] = {}
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            berdo_id = int(row["berdo_id"])
            std = row["city_applicable_standard_2025"].strip()
            buildings[berdo_id] = {
                "address": row["address"],
                "berdo_use": row["berdo_use"].strip(),
                "floor_area": float(row["gross_floor_area_sqft"]),
                "emissions": float(row["total_ghg_kgco2e"]),
                "gas_kbtu": float(row["natural_gas_kbtu"]),
                "gas_kgco2e": float(row["natural_gas_kgco2e"]),
                "elec_kwh": float(row["electricity_kwh"]),
                "elec_kgco2e": float(row["electricity_kgco2e"]),
                "applicable_standard": float(std) if std else None,
                "first_compliance_year": int(row["first_compliance_year"]),
            }
    return buildings


def _golden_limit_vector(
    building: dict[str, object],
    limits_table: dict[str, dict[str, float]],
) -> dict[str, float]:
    """Build a building's six-period limit vector the way the app does.

    2025-2029 uses the City's applied standard when present, otherwise the
    mapped-use table value; later periods come straight from the mapped use.
    """
    use = building["berdo_use"]
    base = period_limits(use, limits_table)
    assert base is not None, f"golden use {use!r} missing from limits table"
    vector = dict(base)
    vector["2025-2029"] = resolve_2025_2029_limit(
        building["applicable_standard"], use, limits_table
    )
    return vector


def _elec_factor(building: dict[str, object]) -> float:
    """Each building's own electricity emissions / kWh ratio (0 when no kWh)."""
    kwh = building["elec_kwh"]
    return building["elec_kgco2e"] / kwh if kwh else 0.0


@pytest.fixture(scope="module")
def golden_buildings() -> dict[int, dict[str, object]]:
    return _load_golden_buildings()


@pytest.fixture(scope="module")
def limits_table() -> dict[str, dict[str, float]]:
    return load_limits_table()


@pytest.mark.parametrize("berdo_id", sorted(GOLDEN_PERIOD_ACP))
def test_golden_period_acp_matches_reference(
    berdo_id, golden_buildings, limits_table
):
    """Each golden building reproduces every per-period ACP within $0.05.

    Validates: Requirements 10.1
    """
    building = golden_buildings[berdo_id]
    vector = _golden_limit_vector(building, limits_table)
    exposure = period_exposure(
        building["emissions"],
        vector,
        building["floor_area"],
        building["first_compliance_year"],
    )
    for period in PERIODS:
        actual = exposure[period]["acp_usd"]
        expected = GOLDEN_PERIOD_ACP[berdo_id][period]
        assert actual == pytest.approx(expected, abs=GOLDEN_TOL), (
            f"building {berdo_id} period {period}: "
            f"ACP {actual:.2f} != expected {expected:.2f}"
        )


@pytest.mark.parametrize(
    "berdo_id, fraction, expected_acp", GOLDEN_HEAT_PUMP_ACP_2030
)
def test_golden_heat_pump_2030_acp(
    berdo_id, fraction, expected_acp, golden_buildings, limits_table
):
    """Heat-pump conversion reproduces the reference 2030-2034 ACP within $0.05.

    Validates: Requirements 10.1
    """
    building = golden_buildings[berdo_id]
    vector = _golden_limit_vector(building, limits_table)
    new_emissions = apply_heat_pump(
        building["emissions"],
        building["gas_kbtu"],
        building["gas_kgco2e"],
        _elec_factor(building),
        fraction,
        BOILER_EFF,
        COP,
    )
    exposure = period_exposure(
        new_emissions,
        vector,
        building["floor_area"],
        building["first_compliance_year"],
    )
    actual = exposure["2030-2034"]["acp_usd"]
    assert actual == pytest.approx(expected_acp, abs=GOLDEN_TOL), (
        f"building {berdo_id} f={fraction}: 2030-2034 ACP "
        f"{actual:.2f} != expected {expected_acp:.2f}"
    )


@pytest.mark.parametrize("fraction", [0.0, 0.25, 0.5, 0.75, 1.0])
def test_golden_no_gas_building_unchanged_by_heat_pump(
    fraction, golden_buildings, limits_table
):
    """Building 100005 (no gas) is unchanged by any heat-pump fraction.

    24 School St reports district-steam emissions but zero natural gas, so a
    heat-pump conversion has nothing to shift: emissions and every per-period
    ACP must be identical for any fraction f.

    Validates: Requirements 10.1
    """
    building = golden_buildings[100005]
    assert building["gas_kbtu"] == 0.0
    vector = _golden_limit_vector(building, limits_table)

    new_emissions = apply_heat_pump(
        building["emissions"],
        building["gas_kbtu"],
        building["gas_kgco2e"],
        _elec_factor(building),
        fraction,
        BOILER_EFF,
        COP,
    )
    # Emissions must be bit-for-bit unchanged (no gas to convert).
    assert new_emissions == building["emissions"]

    exposure = period_exposure(
        new_emissions,
        vector,
        building["floor_area"],
        building["first_compliance_year"],
    )
    for period in PERIODS:
        actual = exposure[period]["acp_usd"]
        expected = GOLDEN_PERIOD_ACP[100005][period]
        assert actual == pytest.approx(expected, abs=GOLDEN_TOL), (
            f"100005 f={fraction} period {period}: "
            f"ACP {actual:.2f} != expected {expected:.2f}"
        )


# ---------------------------------------------------------------------------
# Task 8.2 — Whole-dataset regression tests (R10.2-R10.6)
# ---------------------------------------------------------------------------


def _load_full_dataset():
    """Return the normalized, filtered full disclosure, or skip if unavailable.

    Prefers an existing valid parquet cache. Otherwise downloads the workbook
    and runs the real ``normalize_columns`` / ``filter_reported`` pipeline (the
    same steps ``load_disclosure`` performs before caching). When neither a
    cache nor network access is available, the test is skipped with a clear
    reason -- the regression assertions are never run against fabricated data.
    """
    import pandas as pd

    if is_cache_valid(str(CACHE_PATH)):
        return pd.read_parquet(CACHE_PATH)
    try:
        raw = read_disclosure_excel(DEFAULT_DISCLOSURE_URL, 30.0)
    except LoadError as exc:
        pytest.skip(
            "Full disclosure unavailable (no cache and download failed): "
            f"{exc}"
        )
    return filter_reported(normalize_columns(raw))


def _applicable_standard(value) -> float | None:
    """Coerce a raw Applicable_Standard cell to float or None (missing)."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    return float(value)


def _compute_full_exposure(df):
    """Return citywide and per-use ACP aggregates plus per-building ACP.

    Mirrors the app's exposure pipeline over every loaded building:
    map Largest Property Type to a BERDO use, resolve the 2025-2029 limit from
    the City's applied standard when present, pull later-period limits from the
    mapped use, gate periods by first compliance year, and sum ACP. Buildings
    whose property type has no BERDO-use mapping carry no limit and are excluded
    from citywide totals (per R2 / R10 semantics).
    """
    limits_table = load_limits_table()
    type_map = load_property_type_map()

    over_2025 = 0
    over_2030 = 0
    total_2025 = 0.0
    total_2030 = 0.0
    by_use: dict[str, dict[str, float]] = {}
    per_building: dict[int, dict[str, float]] = {}

    for _, row in df.iterrows():
        use = map_property_type(row[COL_LARGEST_PROPERTY_TYPE], type_map)
        base = period_limits(use, limits_table)
        if base is None:
            continue  # unmapped use: excluded from citywide totals

        emissions = float(row[COL_TOTAL_GHG])
        floor = float(row[COL_FLOOR_AREA])
        fcy = int(row[COL_FIRST_COMPLIANCE_YEAR])

        vector = dict(base)
        vector["2025-2029"] = resolve_2025_2029_limit(
            _applicable_standard(row[COL_APPLICABLE_STANDARD]), use, limits_table
        )

        exposure = period_exposure(emissions, vector, floor, fcy)
        acp_2025 = exposure["2025-2029"]["acp_usd"]
        acp_2030 = exposure["2030-2034"]["acp_usd"]

        total_2025 += acp_2025
        total_2030 += acp_2030
        if acp_2025 > 0:
            over_2025 += 1
        if acp_2030 > 0:
            over_2030 += 1

        bucket = by_use.setdefault(
            use,
            {"buildings": 0, "over_2025": 0, "total_2025": 0.0,
             "over_2030": 0, "total_2030": 0.0},
        )
        bucket["buildings"] += 1
        bucket["over_2025"] += 1 if acp_2025 > 0 else 0
        bucket["total_2025"] += acp_2025
        bucket["over_2030"] += 1 if acp_2030 > 0 else 0
        bucket["total_2030"] += acp_2030

        # berdo_id is normalized to a string ("100005" / "C10002"); key by it.
        per_building[row[COL_BERDO_ID]] = {
            "acp_2025": acp_2025,
            "acp_2030": acp_2030,
        }

    return {
        "over_2025": over_2025,
        "over_2030": over_2030,
        "total_2025": total_2025,
        "total_2030": total_2030,
        "by_use": by_use,
        "per_building": per_building,
    }


def _read_expected_by_use() -> dict[str, dict[str, float]]:
    path = DATA_DIR / "expected_by_use.csv"
    expected: dict[str, dict[str, float]] = {}
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            expected[row["berdo_use"].strip()] = {
                "buildings": int(row["buildings"]),
                "over_2025": int(row["over_2025_2029"]),
                "total_2025": float(row["expected_acp_2025_2029_total"]),
                "over_2030": int(row["over_2030_2034"]),
                "total_2030": float(row["expected_acp_2030_2034_total"]),
            }
    return expected


def _read_expected_sample_40() -> dict[int, dict[str, float]]:
    path = DATA_DIR / "expected_sample_40.csv"
    expected: dict[int, dict[str, float]] = {}
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            expected[int(row["berdo_id"])] = {
                "acp_2025": float(row["expected_acp_2025_2029"]),
                "acp_2030": float(row["expected_acp_2030_2034"]),
            }
    return expected


@pytest.fixture(scope="module")
def full_dataset():
    return _load_full_dataset()


@pytest.fixture(scope="module")
def full_exposure(full_dataset):
    return _compute_full_exposure(full_dataset)


def test_loader_retains_1809_buildings(full_dataset):
    """The loader retains exactly 1,809 buildings.

    Validates: Requirements 10.2
    """
    assert len(full_dataset) == 1809


def test_citywide_2025_2029_totals(full_exposure):
    """2025-2029: 63 buildings over the limit totaling $2,880,426.65 within $1.

    Validates: Requirements 10.3
    """
    assert full_exposure["over_2025"] == 63
    assert full_exposure["total_2025"] == pytest.approx(
        2_880_426.65, abs=TOTAL_TOL
    )


def test_citywide_2030_2034_totals(full_exposure):
    """2030-2034: 963 buildings over the limit totaling $27,406,457.43 within $1.

    Validates: Requirements 10.4
    """
    assert full_exposure["over_2030"] == 963
    assert full_exposure["total_2030"] == pytest.approx(
        27_406_457.43, abs=TOTAL_TOL
    )


def test_per_use_breakdown_matches_expected(full_exposure):
    """Per-use counts match expected exactly and totals match within $1.

    The "ALL" row in expected_by_use.csv is the citywide aggregate, checked by
    the citywide total tests; here we compare each of the 13 BERDO uses.

    Validates: Requirements 10.5
    """
    expected_by_use = _read_expected_by_use()
    actual_by_use = full_exposure["by_use"]

    for use, expected in expected_by_use.items():
        if use == "ALL":
            continue
        actual = actual_by_use.get(use)
        assert actual is not None, f"BERDO use {use!r} missing from results"
        assert actual["buildings"] == expected["buildings"], (
            f"{use}: building count {actual['buildings']} != "
            f"{expected['buildings']}"
        )
        assert actual["over_2025"] == expected["over_2025"], (
            f"{use}: 2025-2029 over-limit count {actual['over_2025']} != "
            f"{expected['over_2025']}"
        )
        assert actual["over_2030"] == expected["over_2030"], (
            f"{use}: 2030-2034 over-limit count {actual['over_2030']} != "
            f"{expected['over_2030']}"
        )
        assert actual["total_2025"] == pytest.approx(
            expected["total_2025"], abs=TOTAL_TOL
        ), f"{use}: 2025-2029 total mismatch"
        assert actual["total_2030"] == pytest.approx(
            expected["total_2030"], abs=TOTAL_TOL
        ), f"{use}: 2030-2034 total mismatch"


def test_sample_40_per_building_acp(full_exposure):
    """The 40 sample buildings reproduce per-building ACP within $0.05.

    Validates: Requirements 10.6
    """
    expected = _read_expected_sample_40()
    per_building = full_exposure["per_building"]

    for berdo_id, want in expected.items():
        # per_building is keyed by the normalized string berdo_id ("100018");
        # the expected CSV parses ids as ints, so match on the string form.
        got = per_building.get(str(berdo_id))
        assert got is not None, f"sample building {berdo_id} missing from results"
        assert got["acp_2025"] == pytest.approx(want["acp_2025"], abs=GOLDEN_TOL), (
            f"building {berdo_id}: 2025-2029 ACP {got['acp_2025']:.2f} != "
            f"expected {want['acp_2025']:.2f}"
        )
        assert got["acp_2030"] == pytest.approx(want["acp_2030"], abs=GOLDEN_TOL), (
            f"building {berdo_id}: 2030-2034 ACP {got['acp_2030']:.2f} != "
            f"expected {want['acp_2030']:.2f}"
        )
