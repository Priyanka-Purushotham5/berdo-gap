"""Property-type mapping and per-period BERDO emissions limits.

Pure functions only: load the limits table and the property-type map from CSV,
map a building's Largest Property Type to a BERDO use, and resolve per-period
limits. All lookups are case- and whitespace-insensitive where the spec requires
it. Unmapped or table-absent cases surface as ``None`` so the UI can render
"limit unknown" and the exposure layer can exclude the building from citywide
totals.
"""

from __future__ import annotations

import csv

# The six BERDO compliance periods, in order. Used as the column keys in the
# limits table and as the ordered key set for the per-period limit vector.
PERIODS: tuple[str, ...] = (
    "2025-2029",
    "2030-2034",
    "2035-2039",
    "2040-2044",
    "2045-2049",
    "2050+",
)


def load_limits_table(path: str = "data/berdo_limits.csv") -> dict[str, dict[str, float]]:
    """Return ``{berdo_use: {period: limit_kgco2e_per_sqft}}``.

    Reads ``data/berdo_limits.csv`` whose header is ``berdo_use`` followed by the
    six period columns. Every use maps to a full six-period vector. A value of 0
    (the 2050+ period) is a valid zero limit, not a missing value.

    Satisfies: R2.4.
    """
    table: dict[str, dict[str, float]] = {}
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            use = (row["berdo_use"] or "").strip()
            if not use:
                continue
            table[use] = {period: float(row[period]) for period in PERIODS}
    return table


def load_property_type_map(path: str = "data/property_type_map.csv") -> dict[str, str]:
    """Return ``{normalized_portfolio_type: berdo_use}``.

    Keys are the City's ``portfolio_manager_type`` values trimmed of leading and
    trailing whitespace and lower-cased, so lookups are case-insensitive. Values
    are the mapped BERDO use verbatim.

    Satisfies: R2.1.
    """
    type_map: dict[str, str] = {}
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            raw_key = row.get("portfolio_manager_type") or ""
            key = raw_key.strip().lower()
            if not key:
                continue
            berdo_use = (row.get("berdo_use") or "").strip()
            if berdo_use:
                type_map[key] = berdo_use
    return type_map


def map_property_type(
    largest_property_type: str, type_map: dict[str, str]
) -> str | None:
    """Map a building's Largest Property Type to a BERDO use.

    Trims leading/trailing whitespace and ignores letter case. Returns ``None``
    when the property type has no mapping.

    Satisfies: R2.1, R2.5, R2.6.
    """
    if largest_property_type is None:
        return None
    key = largest_property_type.strip().lower()
    if not key:
        return None
    return type_map.get(key)


def period_limits(
    berdo_use: str, limits_table: dict[str, dict[str, float]]
) -> dict[str, float] | None:
    """Return the six-period limit vector for a BERDO use.

    Returns ``None`` when the use has no row in the table. The 2050+ value of 0
    is a valid zero limit, not treated as missing.

    Satisfies: R2.4, R2.7.
    """
    if berdo_use is None:
        return None
    limits = limits_table.get(berdo_use)
    if limits is None:
        return None
    return {period: limits[period] for period in PERIODS}


def resolve_2025_2029_limit(
    applicable_standard: float | None,
    berdo_use: str | None,
    limits_table: dict[str, dict[str, float]],
) -> float | None:
    """Return the 2025-2029 limit for a building.

    When ``applicable_standard`` is present (numeric and >= 0), use it verbatim,
    including blended or individual standard values such as 8.1 or 4.4, without
    substituting the mapped use's table value. Otherwise fall back to the mapped
    use's 2025-2029 table value. Returns ``None`` when the use is unmapped or
    absent from the table.

    Satisfies: R2.2, R2.3, R2.7.
    """
    if applicable_standard is not None and applicable_standard >= 0:
        return float(applicable_standard)
    if berdo_use is None:
        return None
    limits = limits_table.get(berdo_use)
    if limits is None:
        return None
    return limits["2025-2029"]
