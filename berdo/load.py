"""Load, cache, and normalize the City of Boston BERDO 2026 disclosure.

Pure, UI-free data-access layer. This module exposes the normalized column-name
constants and the ``SOURCE_COLUMNS`` mapping used downstream, a ``LoadError``
raised on any load failure, and the column-normalization / filtering / EUI
helpers. The cache, download, and orchestration functions live alongside these
(Task 6.2).

Data rules honored here:
- The source sheet is "Buildings & Campuses" (header row 1).
- The "Site EUI (Energy Use Intensity kBtu/ft^2)" column is NOT used: in this
  file it holds emissions intensity, not EUI. EUI is computed from Total Site
  Energy Usage divided by Gross Floor Area.
- Blank/non-numeric fuel usage and emissions cells are treated as 0.
- A blank Applicable_Standard is treated as missing (NaN).
"""

from __future__ import annotations

import pandas as pd

# ---------------------------------------------------------------------------
# Normalized column-name constants
# ---------------------------------------------------------------------------
COL_BERDO_ID = "berdo_id"
COL_ADDRESS = "address"
COL_PARCEL_ADDRESS = "parcel_address"
COL_ZIP = "zip"
COL_PARCEL_ZIP = "parcel_zip"
COL_FLOOR_AREA = "floor_area_sqft"
COL_LARGEST_PROPERTY_TYPE = "largest_property_type"
COL_TOTAL_SITE_ENERGY = "total_site_energy_kbtu"
COL_NATURAL_GAS_KBTU = "natural_gas_kbtu"
COL_ELECTRICITY_KWH = "electricity_kwh"
COL_TOTAL_GHG = "total_ghg_kgco2e"
COL_NATURAL_GAS_GHG = "natural_gas_kgco2e"
COL_ELECTRICITY_GHG = "electricity_kgco2e"
COL_APPLICABLE_STANDARD = "applicable_standard"
COL_COMPLIANCE_STATUS = "compliance_status"
COL_FIRST_COMPLIANCE_YEAR = "first_compliance_year"
COL_EUI = "eui"

# Source -> normalized header mapping (City's exact names on the left).
SOURCE_COLUMNS: dict[str, str] = {
    "BERDO ID": COL_BERDO_ID,
    "Building Address": COL_ADDRESS,
    "Parcel Address": COL_PARCEL_ADDRESS,
    "Building Address Zip Code": COL_ZIP,
    "Parcel Address Zip Code": COL_PARCEL_ZIP,
    "Gross Floor Area (sq ft)": COL_FLOOR_AREA,
    "Largest Property Type": COL_LARGEST_PROPERTY_TYPE,
    "Total Site Energy Usage (kBtu)": COL_TOTAL_SITE_ENERGY,
    "Natural Gas Usage (kBtu)": COL_NATURAL_GAS_KBTU,
    "Electricity Usage (kWh)": COL_ELECTRICITY_KWH,
    "Total GHG Emissions (kgCO2e)": COL_TOTAL_GHG,
    "Natural Gas Emissions (kgCO2e)": COL_NATURAL_GAS_GHG,
    "Electricity Emissions (kgCO2e)": COL_ELECTRICITY_GHG,
    "Applicable Emissions Compliance Standard (kgCO2e/sq ft)": COL_APPLICABLE_STANDARD,
    "Emissions Compliance Status": COL_COMPLIANCE_STATUS,
    "First Emissions Compliance Year": COL_FIRST_COMPLIANCE_YEAR,
}

# The "Site EUI (Energy Use Intensity kBtu/ft2)" column is deliberately NOT in
# SOURCE_COLUMNS: in this file it holds emissions intensity, not EUI. EUI is
# computed by compute_eui() from total site energy and gross floor area.

# Numeric fuel-usage and emissions columns whose blank/non-numeric cells are
# coerced to 0 during normalization (R1.12).
_NUMERIC_ZERO_COLUMNS: tuple[str, ...] = (
    COL_FLOOR_AREA,
    COL_TOTAL_SITE_ENERGY,
    COL_NATURAL_GAS_KBTU,
    COL_ELECTRICITY_KWH,
    COL_TOTAL_GHG,
    COL_NATURAL_GAS_GHG,
    COL_ELECTRICITY_GHG,
)


def _coerce_berdo_id(value: object) -> str:
    """Return a BERDO id as a clean string, free of float artifacts.

    Building ids arrive as ints or floats (100005 / 100005.0) and campus ids as
    strings ("C10002"). A whole-valued float is rendered as an integer string
    ("100005", never "100005.0"); everything else is stringified and trimmed.
    """
    if isinstance(value, float):
        if pd.isna(value):
            return ""
        if value.is_integer():
            return str(int(value))
        return str(value)
    if isinstance(value, int):
        return str(value)
    return str(value).strip()


class LoadError(Exception):
    """Raised when the disclosure cannot be loaded.

    Covers download failure/timeout (cache preserved) and a source sheet that
    is missing one or more required columns (cache not written).
    """


def normalize_columns(raw: pd.DataFrame) -> pd.DataFrame:
    """Rename source headers to normalized identifiers and coerce cell types.

    Renames the City's exact headers to normalized identifiers via
    ``SOURCE_COLUMNS``, coerces every fuel-usage and emissions column to numeric
    with blanks/non-numeric values becoming 0, and treats a blank
    Applicable_Standard as missing (NaN). When a building's Building Address
    (``COL_ADDRESS``) is blank, its Parcel Address (``COL_PARCEL_ADDRESS``) is
    used as the display address.

    Raises ``LoadError`` naming any absent required source columns; the cache is
    not written in that case.

    Satisfies: R1.6, R1.9, R1.12, R1.13.
    """
    missing = [source for source in SOURCE_COLUMNS if source not in raw.columns]
    if missing:
        raise LoadError(
            "Disclosure sheet is missing required column(s): "
            + ", ".join(missing)
        )

    # Keep only the source columns we understand, then rename to normalized ids.
    df = raw[list(SOURCE_COLUMNS.keys())].rename(columns=SOURCE_COLUMNS).copy()

    # Coerce berdo_id to a consistent string type. The source mixes plain
    # building ids (ints like 100005) with campus ids (strings like "C10002"),
    # which makes the column object-typed and unwritable to parquet by pyarrow.
    # Normalizing to string keeps the column parquet-writable and matches the
    # dataclass field ``berdo_id: str``. Numeric ids that pandas may have read
    # as floats (e.g. 100005.0) are rendered without the ".0" artifact; genuine
    # campus strings like "C10002" are preserved verbatim.
    df[COL_BERDO_ID] = df[COL_BERDO_ID].map(_coerce_berdo_id).astype(str)

    # Coerce fuel/emission fields: blanks and non-numeric cells become 0 (R1.12).
    for col in _NUMERIC_ZERO_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0).astype(float)

    # A blank/non-numeric Applicable_Standard is missing, not 0 (R1.13).
    df[COL_APPLICABLE_STANDARD] = pd.to_numeric(
        df[COL_APPLICABLE_STANDARD], errors="coerce"
    )

    # Display address falls back to Parcel Address when Building Address is blank.
    address = df[COL_ADDRESS].astype("string")
    parcel = df[COL_PARCEL_ADDRESS].astype("string")
    blank_address = address.isna() | (address.str.strip() == "")
    df[COL_ADDRESS] = address.where(~blank_address, parcel).fillna("").astype(str)
    df[COL_PARCEL_ADDRESS] = parcel.fillna("").astype(str)

    return df


def filter_reported(df: pd.DataFrame) -> pd.DataFrame:
    """Retain only buildings with reported emissions and floor area.

    Keeps rows where ``total_ghg_kgco2e > 0`` AND ``floor_area_sqft > 0``.

    Satisfies: R1.8, R10.2.
    """
    keep = (df[COL_TOTAL_GHG] > 0) & (df[COL_FLOOR_AREA] > 0)
    return df[keep].reset_index(drop=True)


def compute_eui(total_site_energy_kbtu: float, floor_area_sqft: float) -> float:
    """Return EUI as Total Site Energy Usage (kBtu) / Gross Floor Area (sq ft).

    Never derived from the City's "Site EUI" column. Returns 0.0 when floor area
    is 0 to avoid a divide-by-zero (filtered rows always have floor area > 0).

    Satisfies: R1.10, R1.11.
    """
    if floor_area_sqft <= 0:
        return 0.0
    return total_site_energy_kbtu / floor_area_sqft


# ---------------------------------------------------------------------------
# Cache handling, download, and load orchestration (Task 6.2)
# ---------------------------------------------------------------------------

# Default disclosure workbook URL, recorded in DATA_NOTES.md (2026 BERDO data
# disclosure, 2025 data, PDDL license).
DEFAULT_DISCLOSURE_URL = (
    "https://data.boston.gov/dataset/"
    "b09a8b71-274b-4365-9ce6-49b8b44602ef/resource/"
    "c6edf41e-eb53-45a4-9c52-837b865bf19f/download/"
    "2026-berdo-data-disclosure-9.30.26.xlsx"
)

# The worksheet to read and its header row (row 1 => 0-indexed header 0).
_DISCLOSURE_SHEET = "Buildings & Campuses"
_DISCLOSURE_HEADER_ROW = 0

# The normalized columns downstream code needs: the values of SOURCE_COLUMNS.
_REQUIRED_NORMALIZED_COLUMNS: tuple[str, ...] = tuple(SOURCE_COLUMNS.values())


def is_cache_valid(cache_path: str) -> bool:
    """Return True iff the parquet at ``cache_path`` is a valid cache.

    A valid cache is a readable parquet file that contains every required
    normalized column (the values of ``SOURCE_COLUMNS``). Any read failure
    (missing file, corrupt parquet, permissions) yields False so the caller
    re-downloads.

    Satisfies: R1.2, R1.3.
    """
    try:
        cached = pd.read_parquet(cache_path)
    except Exception:
        return False
    return all(col in cached.columns for col in _REQUIRED_NORMALIZED_COLUMNS)


def write_cache(df: pd.DataFrame, cache_path: str) -> None:
    """Write the normalized DataFrame to ``cache_path`` as parquet via pyarrow.

    Creates the parent directory if it does not exist.

    Satisfies: R1.7.
    """
    import os

    parent = os.path.dirname(cache_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    df.to_parquet(cache_path, engine="pyarrow", index=False)


def read_disclosure_excel(url: str, timeout: float) -> pd.DataFrame:
    """Download and read the "Buildings & Campuses" sheet (header row 1).

    Downloads the workbook from ``url`` with the given ``timeout`` (seconds) and
    reads the disclosure sheet with ``openpyxl``. Any download failure or
    timeout raises ``LoadError``; the caller preserves any existing cache in
    that case (this function never touches the cache).

    Satisfies: R1.1, R1.4, R1.5.
    """
    import io

    import requests

    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
    except Exception as exc:  # network error, HTTP error, or timeout
        raise LoadError(
            f"Failed to download the disclosure workbook from {url}: {exc}"
        ) from exc

    try:
        return pd.read_excel(
            io.BytesIO(response.content),
            sheet_name=_DISCLOSURE_SHEET,
            header=_DISCLOSURE_HEADER_ROW,
            engine="openpyxl",
        )
    except Exception as exc:
        raise LoadError(
            f"Failed to read sheet {_DISCLOSURE_SHEET!r} from the "
            f"downloaded workbook: {exc}"
        ) from exc


def load_disclosure(
    cache_path: str = "data/cache/berdo_2026.parquet",
    url: str | None = None,
    timeout: float = 60.0,
) -> pd.DataFrame:
    """Return the normalized, filtered disclosure as a DataFrame.

    If a valid cached parquet exists at ``cache_path`` (readable and containing
    every required normalized column), load from it. Otherwise download the
    workbook from ``url`` (default: the URL recorded in DATA_NOTES.md) with the
    given ``timeout``, normalize, filter, write the cache, and return the
    result. The cache is re-downloaded when it is unreadable or missing a
    required column. A missing-column ``LoadError`` during normalization leaves
    the cache unwritten.

    Satisfies: R1.1, R1.2, R1.3, R1.4, R1.5, R1.7.
    """
    if is_cache_valid(cache_path):
        return pd.read_parquet(cache_path)

    source_url = url if url is not None else DEFAULT_DISCLOSURE_URL
    raw = read_disclosure_excel(source_url, timeout)

    # normalize_columns raises LoadError (naming absent columns) before any
    # cache write, so a missing-column failure never clobbers the cache.
    normalized = normalize_columns(raw)
    filtered = filter_reported(normalized)
    write_cache(filtered, cache_path)
    return filtered
