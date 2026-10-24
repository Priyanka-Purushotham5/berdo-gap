"""BERDO Gap — Streamlit UI.

This is the only Streamlit file. It renders three pages (Building, City view,
About & sources), reads user inputs, calls the pure functions in ``berdo/``, and
formats results for display. The UI performs NO calculation of its own: it only
rounds for display (tons to 1 decimal, dollars to whole dollars) and shows
numbers that came from a ``berdo/`` function or directly from the City's data
file.

A sidebar radio navigates across three pages, each dispatched from ``main``:

- Building: building lookup, the six-period exposure table, the City's
  compliance status, the retrofit scenario sliders, and the board-memo button.
- City view: the per-ZIP 2030-2034 exposure bar chart and over-limit counts.
- About & sources: the data/limit sources and important notes.

The shared disclaimer block (``render_disclaimer``) is rendered near the top of
every result screen so it is visible without scrolling.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

from berdo import load
from berdo.exposure import (
    PERIODS,
    STATUS_NOT_YET_COVERED,
    period_exposure,
)
from berdo.limits import (
    load_limits_table,
    load_property_type_map,
    map_property_type,
    period_limits,
    resolve_2025_2029_limit,
)
from berdo.load import (
    COL_ADDRESS,
    COL_APPLICABLE_STANDARD,
    COL_BERDO_ID,
    COL_COMPLIANCE_STATUS,
    COL_ELECTRICITY_GHG,
    COL_ELECTRICITY_KWH,
    COL_FIRST_COMPLIANCE_YEAR,
    COL_FLOOR_AREA,
    COL_LARGEST_PROPERTY_TYPE,
    COL_NATURAL_GAS_GHG,
    COL_NATURAL_GAS_KBTU,
    COL_PARCEL_ZIP,
    COL_TOTAL_GHG,
    COL_ZIP,
    LoadError,
)
from berdo.memo import (
    build_memo_payload,
    generate_memo,
)
from berdo.scenarios import (
    BOILER_EFFICIENCY_DEFAULT,
    COP_DEFAULT,
    apply_scenario,
)

# ---------------------------------------------------------------------------
# Display constants (phrasing mandated by the product/requirements steering)
# ---------------------------------------------------------------------------
LIMIT_UNKNOWN_TEXT = "limit unknown"
NO_REPORTED_EMISSIONS_TEXT = "No reported emissions — enter your own numbers"
CITY_STATUS_UNAVAILABLE_TEXT = "City status not available"
ESTIMATE_DISCLAIMER_TEXT = (
    "This is an estimated exposure figure, not a compliance determination."
)
UNKNOWN_ZIP_LABEL = "Unknown ZIP"
NO_CITYWIDE_DATA_TEXT = (
    "No citywide exposure data is available — no building with a mapped BERDO "
    "use qualified for the chart."
)

# ---------------------------------------------------------------------------
# Shared disclaimer block (R8) — exact phrasing is mandated by the product
# steering and Requirement 8. Every result screen (Building, City view, and the
# generated memo) shows this block near the top, visible without scrolling
# (R8.1). The strings below are used VERBATIM; do not edit the wording.
# ---------------------------------------------------------------------------
# R8.1 — must be visible without scrolling on every result screen.
DISCLAIMER_ESTIMATE_TEXT = "Estimate, not a compliance determination"
# R8.2 — the data source and year, exact text.
DISCLAIMER_SOURCE_TEXT = (
    "City of Boston BERDO 2026 disclosure, 2025 data, PDDL license"
)
# R8.3 — portfolio / campus / flexibility measures can reduce real exposure.
DISCLAIMER_FLEXIBILITY_TEXT = (
    "Portfolio and campus compliance and flexibility measures can reduce real "
    "exposure."
)
# R8.4 — grid-factors note, exact text (including the file path). Kept as a
# single unbroken literal so the wording is unambiguously verbatim.
DISCLAIMER_GRID_TEXT = "The City projects grid emissions roughly flat through 2034 (data/projected_grid_factors.csv), so 2030 estimates hold; later periods may be lower."
# R8.7 — direction to the City of Boston BERDO team for official answers.
DISCLAIMER_BERDO_TEAM_TEXT = (
    "For official or legal compliance answers, contact the City of Boston "
    "BERDO team."
)
# R8.5 — the term "estimated exposure" must appear on result screens.
DISCLAIMER_ESTIMATED_EXPOSURE_TEXT = (
    "Figures shown are an estimated exposure based on the City's data file and "
    "this calculator."
)


def render_disclaimer() -> None:
    """Render the shared honest-disclaimer block (R8.1–R8.5, R8.7).

    Called near the TOP of every result screen (Building page, City view, and
    alongside the generated memo) so the "Estimate, not a compliance
    determination" line and the rest of the block are visible without scrolling
    (R8.1). Every string is rendered verbatim from the module constants above.

    The block deliberately avoids the two prohibited compliance phrases
    described in R8.8; it speaks only of estimated exposure.
    """
    st.warning(f"**{DISCLAIMER_ESTIMATE_TEXT}.** {DISCLAIMER_ESTIMATED_EXPOSURE_TEXT}")
    st.caption(DISCLAIMER_FLEXIBILITY_TEXT)
    st.caption(DISCLAIMER_GRID_TEXT)
    st.caption(f"Source: {DISCLAIMER_SOURCE_TEXT}.")
    st.caption(DISCLAIMER_BERDO_TEAM_TEXT)

# Human-readable labels for the period status values returned by the calculator.
_STATUS_LABELS: dict[str, str] = {
    STATUS_NOT_YET_COVERED: "not yet covered",
    "covered": "covered",
}


# ---------------------------------------------------------------------------
# Data loading (cached so the download / cache read happens once per session)
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner="Loading the City's BERDO disclosure…")
def get_disclosure() -> pd.DataFrame:
    """Return the normalized, filtered disclosure (cached for the session).

    Wraps ``berdo.load.load_disclosure`` with the default cache path so the
    download / cache read happens only once. Raising is left to the caller so
    the page can render a friendly ``st.error``.
    """
    return load.load_disclosure()


@st.cache_data(show_spinner=False)
def get_limits_table() -> dict[str, dict[str, float]]:
    """Return the per-use, per-period limits table (cached)."""
    return load_limits_table()


@st.cache_data(show_spinner=False)
def get_property_type_map() -> dict[str, str]:
    """Return the property-type -> BERDO use map (cached)."""
    return load_property_type_map()


# ---------------------------------------------------------------------------
# Display helpers (display-only rounding; no calculation)
# ---------------------------------------------------------------------------
def format_tons(value: float) -> str:
    """Format metric tons CO2e for display, rounded to 1 decimal place (R3.7)."""
    return f"{value:,.1f}"


def format_dollars(value: float) -> str:
    """Format an ACP amount for display, rounded to whole dollars (R3.7)."""
    return f"${value:,.0f}"


def resolve_limit_vector(
    applicable_standard: float | None,
    berdo_use: str | None,
    limits_table: dict[str, dict[str, float]],
) -> dict[str, float] | None:
    """Build the six-period limit vector for a building, or ``None``.

    The 2025–2029 entry honors the City's Applicable_Standard when present
    (``resolve_2025_2029_limit``); the later periods come from the mapped use's
    table row (``period_limits``). Returns ``None`` when the use is unmapped or
    absent from the limits table, which the UI renders as "limit unknown".

    This is not a calculation of exposure — it only assembles the limit inputs
    that the pure ``berdo/`` functions produced, so later-period limits are not
    recomputed here.
    """
    limit_2025 = resolve_2025_2029_limit(applicable_standard, berdo_use, limits_table)
    if limit_2025 is None:
        return None
    later = period_limits(berdo_use, limits_table)
    if later is None:
        return None
    vector = dict(later)
    vector[PERIODS[0]] = limit_2025
    return vector


def _coerce_standard(value: Any) -> float | None:
    """Return the Applicable_Standard as a float, or ``None`` when missing/NaN."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_first_compliance_year(value: Any) -> int:
    """Return the First_Compliance_Year as an int, defaulting to 2025.

    The disclosure records 2025 or 2030; a blank/non-numeric value falls back to
    2025 (the earliest period) so every period is evaluated.
    """
    try:
        if value is None or pd.isna(value):
            return 2025
    except (TypeError, ValueError):
        pass
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 2025


def building_label(row: pd.Series) -> str:
    """Return a 'BERDO ID — Address' label for the selectbox."""
    berdo_id = str(row.get(COL_BERDO_ID, "")).strip()
    address = str(row.get(COL_ADDRESS, "")).strip()
    if address:
        return f"{berdo_id} — {address}"
    return berdo_id


# ---------------------------------------------------------------------------
# Building page
# ---------------------------------------------------------------------------
def render_building_page(df: pd.DataFrame) -> None:
    """Render the Building page: lookup, exposure table, and City status."""
    st.header("Building")
    st.caption(
        "Look up a BERDO-covered building to see its estimated exposure by "
        "compliance period."
    )

    # Shared disclaimer near the top so it's visible without scrolling (R8.1).
    render_disclaimer()

    # The loaded frame contains only buildings with reported emissions and floor
    # area (the Loader filters the rest out). A building that is not in this
    # frame has no reported emissions (R1.14).
    if df.empty:
        st.info(NO_REPORTED_EMISSIONS_TEXT)
        return

    # --- 1. Building lookup ------------------------------------------------
    labels = {building_label(row): idx for idx, row in df.iterrows()}
    search = st.text_input(
        "Search by BERDO ID or address",
        value="",
        help="Type part of a BERDO ID or street address to narrow the list.",
    ).strip()

    options = sorted(labels.keys())
    if search:
        needle = search.lower()
        filtered = [label for label in options if needle in label.lower()]
    else:
        filtered = options

    if not filtered:
        # No building matched the search box; treat as "no reported building".
        st.info(NO_REPORTED_EMISSIONS_TEXT)
        return

    selected_label = st.selectbox("Building", filtered, index=0)
    row = df.loc[labels[selected_label]]

    # --- Building identity ------------------------------------------------
    address = str(row.get(COL_ADDRESS, "")).strip()
    berdo_id = str(row.get(COL_BERDO_ID, "")).strip()
    st.subheader(address or berdo_id)
    meta_cols = st.columns(3)
    meta_cols[0].metric("BERDO ID", berdo_id or "—")
    zip_code = str(row.get(COL_ZIP, "")).strip()
    meta_cols[1].metric("ZIP", zip_code or "—")
    property_type = str(row.get(COL_LARGEST_PROPERTY_TYPE, "")).strip()
    meta_cols[2].metric("Largest property type", property_type or "—")

    # --- 2. Map property type to a BERDO use ------------------------------
    type_map = get_property_type_map()
    limits_table = get_limits_table()
    berdo_use = map_property_type(property_type, type_map)

    # --- 3. Build the six-period limit vector -----------------------------
    applicable_standard = _coerce_standard(row.get(COL_APPLICABLE_STANDARD))
    limit_vector = resolve_limit_vector(applicable_standard, berdo_use, limits_table)

    # City's official compliance status is shown regardless of limit mapping.
    _render_city_status(row)

    if limit_vector is None:
        # Unmapped property type, or a mapped use absent from the limits table
        # (R2.5, R2.7): show "limit unknown" and do not crash.
        st.warning(
            f"{LIMIT_UNKNOWN_TEXT} — this building's property type "
            f"('{property_type or 'blank'}') is not mapped to a BERDO use, so "
            "no emissions limit can be applied."
        )
        return

    # --- 4. Compute exposure (all numbers come from berdo/) ---------------
    emissions_kg = float(row.get(COL_TOTAL_GHG, 0.0) or 0.0)
    floor_area_sqft = float(row.get(COL_FLOOR_AREA, 0.0) or 0.0)
    first_compliance_year = _coerce_first_compliance_year(
        row.get(COL_FIRST_COMPLIANCE_YEAR)
    )

    exposure = period_exposure(
        emissions_kg=emissions_kg,
        limit_vector=limit_vector,
        floor_area_sqft=floor_area_sqft,
        first_compliance_year=first_compliance_year,
    )

    _render_exposure_table(exposure, berdo_use)

    # --- 5. Retrofit scenario (Task 11.2) ---------------------------------
    _render_scenario_section(
        row=row,
        address=address or berdo_id,
        berdo_use=berdo_use,
        limit_vector=limit_vector,
        emissions_kg=emissions_kg,
        floor_area_sqft=floor_area_sqft,
        first_compliance_year=first_compliance_year,
        exposure=exposure,
    )


def _render_exposure_table(
    exposure: dict[str, dict[str, Any]], berdo_use: str
) -> None:
    """Render the six-period estimated-exposure table with display rounding."""
    st.markdown("### Estimated exposure by period")
    st.caption(f"BERDO use: **{berdo_use}** · Estimate, not a compliance determination.")

    rows: list[dict[str, str]] = []
    for period in PERIODS:
        result = exposure[period]
        status_raw = str(result["status"])
        status_label = _STATUS_LABELS.get(status_raw, status_raw)
        if status_raw == STATUS_NOT_YET_COVERED:
            tons_display = "—"
            acp_display = format_dollars(0.0)
        else:
            tons_display = format_tons(float(result["excess_tons"]))
            acp_display = format_dollars(float(result["acp_usd"]))
        rows.append(
            {
                "Period": period,
                "Status": status_label,
                "Excess tons (CO2e)": tons_display,
                "Estimated exposure (ACP)": acp_display,
            }
        )

    table = pd.DataFrame(rows, columns=[
        "Period",
        "Status",
        "Excess tons (CO2e)",
        "Estimated exposure (ACP)",
    ])
    st.table(table)


def _render_city_status(row: pd.Series) -> None:
    """Render the City's Compliance_Status verbatim as a separate official field.

    The City's status (R7.1, R7.2) is shown in its own clearly labeled field,
    visually distinct from the System's estimated exposure. When the status is
    missing, blank, or whitespace-only, a placeholder is shown instead (R7.3),
    and the estimate is still displayed. The field is accompanied by text noting
    the exposure figure is an estimate, not a compliance determination (R7.4).
    """
    raw_status = row.get(COL_COMPLIANCE_STATUS, "")
    try:
        if pd.isna(raw_status):
            raw_status = ""
    except (TypeError, ValueError):
        pass
    status_text = str(raw_status).strip()

    with st.container():
        st.markdown("#### City's official status")
        if status_text:
            # Verbatim, from the City's data file.
            st.info(status_text)
        else:
            st.info(CITY_STATUS_UNAVAILABLE_TEXT)
        st.caption(ESTIMATE_DISCLAIMER_TEXT)


# ---------------------------------------------------------------------------
# Retrofit scenario section + board memo (Task 11.2)
# ---------------------------------------------------------------------------
# A min_value strictly greater than 0 for the editable boiler-efficiency and COP
# inputs. Streamlit's number_input enforces [min_value, max_value], so using a
# tiny positive lower bound rejects 0 and negatives (R4.9, R4.10) while still
# admitting any realistic value.
_POSITIVE_MIN = 0.01


def _electricity_factor(row: pd.Series) -> float:
    """Return the building's own electricity emission factor (kgCO2e/kWh).

    Computed as the building's electricity emissions divided by its electricity
    kWh (the per-building ratio the data rules require), guarding divide-by-zero
    by returning 0.0 when the building reports no electricity use. This is a
    direct ratio of two City data-file values, not a modeled estimate.
    """
    elec_kwh = float(row.get(COL_ELECTRICITY_KWH, 0.0) or 0.0)
    elec_ghg = float(row.get(COL_ELECTRICITY_GHG, 0.0) or 0.0)
    if elec_kwh == 0.0:
        return 0.0
    return elec_ghg / elec_kwh


def _render_scenario_section(
    row: pd.Series,
    address: str,
    berdo_use: str,
    limit_vector: dict[str, float],
    emissions_kg: float,
    floor_area_sqft: float,
    first_compliance_year: int,
    exposure: dict[str, dict[str, Any]],
) -> None:
    """Render the retrofit-scenario sliders, scenario exposure, and memo button.

    The sliders feed ``apply_scenario`` (efficiency first, then heat-pump
    conversion); the transformed emissions are re-run through
    ``period_exposure`` with the SAME limit vector, floor area, and first
    compliance year so the scenario table is directly comparable to the base
    table. The board-memo button assembles a payload from ONLY calculator
    outputs and City data-file values and renders the returned five-field memo.

    Satisfies: R4.1, R4.9, R4.10, R4.11, R5.1, R5.3.
    """
    st.markdown("### Retrofit scenario")
    st.caption(
        "Model a heat-pump conversion and an efficiency upgrade to see how they "
        "change this building's estimated exposure. Estimate, not a compliance "
        "determination."
    )

    # --- Scenario inputs ---------------------------------------------------
    input_cols = st.columns(2)
    # Heat-pump fraction f in [0.0, 1.0] (R4.1).
    f = input_cols[0].slider(
        "Heat-pump fraction (share of gas heat converted)",
        min_value=0.0,
        max_value=1.0,
        value=0.0,
        step=0.05,
        help="0.0 keeps today's gas heat; 1.0 converts all of it to heat pumps.",
    )
    # Efficiency percentage p in [0, 100] (R4.1).
    p = input_cols[1].slider(
        "Efficiency improvement (%)",
        min_value=0,
        max_value=100,
        value=0,
        step=1,
        help="Percent reduction in energy use and emissions from efficiency work.",
    )

    assumption_cols = st.columns(2)
    # Editable boiler efficiency in (0, 1.0]; widget min/max reject out-of-range
    # values (R4.9).
    boiler_eff = assumption_cols[0].number_input(
        "Boiler efficiency assumption",
        min_value=_POSITIVE_MIN,
        max_value=1.0,
        value=BOILER_EFFICIENCY_DEFAULT,
        step=0.01,
        help="Share of fuel energy delivered as useful heat. Greater than 0, up to 1.0.",
    )
    # Editable COP > 0; widget min rejects 0 and negatives (R4.10).
    cop = assumption_cols[1].number_input(
        "Heat-pump seasonal COP assumption",
        min_value=_POSITIVE_MIN,
        value=COP_DEFAULT,
        step=0.1,
        help="Heat-pump coefficient of performance. Must be greater than 0.",
    )

    # --- Transform emissions and re-run exposure --------------------------
    natural_gas_kbtu = float(row.get(COL_NATURAL_GAS_KBTU, 0.0) or 0.0)
    natural_gas_kgco2e = float(row.get(COL_NATURAL_GAS_GHG, 0.0) or 0.0)
    elec_factor = _electricity_factor(row)

    # All scenario arithmetic lives in berdo/scenarios.py (R4.11): the changed
    # boiler-efficiency and COP values flow straight into the heat-pump math.
    new_emissions_kg = apply_scenario(
        emissions_kg,
        natural_gas_kbtu,
        natural_gas_kgco2e,
        elec_factor,
        f,
        float(p),
        boiler_eff,
        cop,
    )

    scenario_exposure = period_exposure(
        emissions_kg=new_emissions_kg,
        limit_vector=limit_vector,
        floor_area_sqft=floor_area_sqft,
        first_compliance_year=first_compliance_year,
    )

    # Prominent 2030-2034 scenario exposure figure.
    period_2030 = PERIODS[1]
    scenario_2030 = scenario_exposure[period_2030]
    base_2030 = exposure[period_2030]
    if str(scenario_2030["status"]) == STATUS_NOT_YET_COVERED:
        st.metric(
            "Scenario estimated exposure, 2030–2034",
            "not yet covered",
        )
    else:
        scenario_acp_2030 = float(scenario_2030["acp_usd"])
        base_acp_2030 = float(base_2030["acp_usd"])
        delta = scenario_acp_2030 - base_acp_2030
        st.metric(
            "Scenario estimated exposure, 2030–2034",
            format_dollars(scenario_acp_2030),
            # Negative delta (savings) is the good direction, so flag a drop as
            # "inverse" (green). Shows the change vs the base estimate.
            delta=format_dollars(delta),
            delta_color="inverse",
        )

    st.markdown("#### Scenario exposure by period")
    _render_exposure_table(scenario_exposure, berdo_use)

    # --- Board memo -------------------------------------------------------
    if st.button("Draft board memo"):
        _render_board_memo(
            row=row,
            address=address,
            berdo_use=berdo_use,
            limit_vector=limit_vector,
            floor_area_sqft=floor_area_sqft,
            first_compliance_year=first_compliance_year,
            emissions_kg=emissions_kg,
            exposure=exposure,
            scenario_exposure=scenario_exposure,
            new_emissions_kg=new_emissions_kg,
            f=f,
            p=float(p),
            boiler_eff=boiler_eff,
            cop=cop,
        )


def _read_secret(name: str) -> str | None:
    """Return a Streamlit secret, or ``None`` when secrets are unavailable.

    Reads defensively so a missing ``.streamlit/secrets.toml`` does not crash
    the page: accessing ``st.secrets`` with no secrets file raises, so any
    failure (missing file, missing key) maps to ``None``. Passing ``None`` to
    ``generate_memo`` makes it return the templated memo (R5.9). The secret
    value is returned as-is and never logged (R5.11).
    """
    try:
        value = st.secrets.get(name)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 - no secrets file / backend -> templated memo
        return None
    if not value:
        return None
    return str(value)


def _render_board_memo(
    row: pd.Series,
    address: str,
    berdo_use: str,
    limit_vector: dict[str, float],
    floor_area_sqft: float,
    first_compliance_year: int,
    emissions_kg: float,
    exposure: dict[str, dict[str, Any]],
    scenario_exposure: dict[str, dict[str, Any]],
    new_emissions_kg: float,
    f: float,
    p: float,
    boiler_eff: float,
    cop: float,
) -> None:
    """Build the memo payload from calculator outputs and render the memo.

    Every value fed to ``build_memo_payload`` comes from either the City data
    file (address, use, floor area, first compliance year, compliance status)
    or a ``berdo/`` calculator result (per-period exposure, the scenario's new
    emissions and 2030–2034 ACP). Tons = emissions_kg / 1000, a display-only
    conversion. The model id and API key come from Streamlit secrets read
    defensively, so a missing secrets file yields the templated memo rather than
    a crash. The returned five-field memo is rendered with the shared disclaimer
    so the memo carries it too (R5.1, R5.3, R8).
    """
    # City's compliance status, verbatim (blank -> None).
    raw_status = row.get(COL_COMPLIANCE_STATUS, "")
    try:
        if pd.isna(raw_status):
            raw_status = ""
    except (TypeError, ValueError):
        pass
    compliance_status = str(raw_status).strip() or None

    # Building shim in the shape build_memo_payload duck-types on.
    building = SimpleNamespace(
        address=address,
        berdo_use=berdo_use,
        floor_area_sqft=floor_area_sqft,
        first_compliance_year=first_compliance_year,
        compliance_status=compliance_status,
        emissions=emissions_kg,
    )

    # Exposure dict in the shape build_memo_payload reads: per-period limit,
    # excess tons, and ACP, plus today's emissions in tons. Values are the
    # calculator's unrounded floats (display rounding happens in the memo). The
    # per-period limit in tons is limit (kgCO2e/sqft) * floor area / 1000 — a
    # conversion of two data-file / calculator values, not a new estimate.
    by_period = {
        period: {
            "limit_tons": (
                limit_vector[period] * floor_area_sqft / 1000.0
            ),
            "excess_tons": float(values["excess_tons"]),
            "acp_usd": float(values["acp_usd"]),
        }
        for period, values in exposure.items()
    }
    exposure_payload = {
        "by_period": by_period,
        "emissions_tons": emissions_kg / 1000.0,
    }

    # Scenario dict: chosen slider values, the recomputed scenario emissions in
    # tons, the scenario's 2030–2034 ACP, and the assumption bullets.
    scenario_2030_acp = float(scenario_exposure[PERIODS[1]]["acp_usd"])
    scenario_payload = {
        "heat_pump_fraction": f,
        "efficiency_pct": p,
        "new_emissions_tons": new_emissions_kg / 1000.0,
        "new_acp_2030_usd_per_year": scenario_2030_acp,
        "assumptions": [
            f"Boiler efficiency {boiler_eff}",
            f"Heat-pump COP {cop}",
            "Emissions held at today's level",
        ],
    }

    payload = build_memo_payload(building, exposure_payload, scenario_payload)

    model = _read_secret("CLAUDE_MODEL")
    api_key = _read_secret("ANTHROPIC_API_KEY")

    with st.spinner("Drafting the board memo…"):
        memo = generate_memo(payload, model, api_key)

    _render_memo(memo)


def _render_memo(memo: dict[str, Any]) -> None:
    """Render the five-field board memo and the shared disclaimer (R5.3).

    Renders ``headline``, ``exposure_summary``, ``recommendation`` as text, and
    ``tradeoffs`` and ``next_steps`` as bullet lists, in the fixed MEMO_FIELDS
    order. The shared disclaimer block is rendered with the memo so the memo
    screen carries it too (R8).
    """
    st.markdown("### Board memo")
    render_disclaimer()

    headline = memo.get("headline")
    if headline:
        st.markdown(f"**{headline}**")

    exposure_summary = memo.get("exposure_summary")
    if exposure_summary:
        st.markdown("#### Exposure summary")
        st.write(exposure_summary)

    recommendation = memo.get("recommendation")
    if recommendation:
        st.markdown("#### Recommendation")
        st.write(recommendation)

    tradeoffs = memo.get("tradeoffs") or []
    if tradeoffs:
        st.markdown("#### Tradeoffs")
        for item in tradeoffs:
            st.markdown(f"- {item}")

    next_steps = memo.get("next_steps") or []
    if next_steps:
        st.markdown("#### Next steps")
        for item in next_steps:
            st.markdown(f"- {item}")


# ---------------------------------------------------------------------------
# City view page (Task 12.1)
# ---------------------------------------------------------------------------
def _resolve_zip(row: pd.Series) -> str:
    """Return the ZIP for a building for the citywide chart.

    Uses the Building Address Zip Code when present; falls back to the Parcel
    Address Zip Code when the building ZIP is blank/missing; groups a building
    with neither under a single "Unknown ZIP" category (R6.3, R6.4).

    ZIP codes arrive from the disclosure as ints, floats (e.g. 2134.0), or
    strings; they are normalized to a clean string (no ".0" float artifact, and
    Boston's leading-zero ZIPs padded to 5 digits) so the same ZIP groups into a
    single bar.
    """
    for col in (COL_ZIP, COL_PARCEL_ZIP):
        text = _normalize_zip(row.get(col))
        if text:
            return text
    return UNKNOWN_ZIP_LABEL


def _normalize_zip(value: Any) -> str:
    """Return a cleaned ZIP string, or "" when blank/missing.

    Strips float artifacts ("2134.0" -> "2134"), trims whitespace, and pads a
    purely numeric ZIP to five digits so Boston's leading-zero ZIPs (e.g. 02134)
    group consistently. A non-numeric value is returned trimmed and verbatim.
    """
    try:
        if value is None or pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(value, float):
        if value.is_integer():
            text = str(int(value))
        else:
            text = str(value)
    elif isinstance(value, int):
        text = str(value)
    else:
        text = str(value).strip()
    if not text:
        return ""
    if text.isdigit():
        return text.zfill(5)
    return text


@st.cache_data(show_spinner="Aggregating citywide exposure…")
def aggregate_city_exposure(df: pd.DataFrame) -> dict[str, Any]:
    """Aggregate per-ZIP 2030–2034 ACP and over-limit counts across the city.

    Iterates the loaded buildings, maps each Largest Property Type to a BERDO
    use, and SKIPS buildings with no mapping or no limits-table row (unmapped
    use is excluded from citywide totals and the chart — R6.1, R2.6, R2.7). For
    each mapped building it builds the six-period limit vector (via
    ``resolve_limit_vector``) and calls ``period_exposure``; the 2030–2034 ACP
    feeds the chart and the over-limit counts.

    Returns a dict with:
      - ``zip_totals``: ``{zip: summed 2030–2034 ACP (unrounded float)}``
      - ``over_2025``: count of mapped buildings with 2025–2029 ACP > 0
      - ``over_2030``: count of mapped buildings with 2030–2034 ACP > 0

    All computation (excess tons, ACP) lives in the ``berdo/`` pure functions;
    this helper only sums the calculator's outputs and tallies counts. Cached on
    the (hashable) DataFrame so the heavy per-building pass runs once per load.
    """
    type_map = get_property_type_map()
    limits_table = get_limits_table()

    period_2025 = PERIODS[0]
    period_2030 = PERIODS[1]

    zip_totals: dict[str, float] = {}
    over_2025 = 0
    over_2030 = 0

    for _, row in df.iterrows():
        property_type = str(row.get(COL_LARGEST_PROPERTY_TYPE, "")).strip()
        berdo_use = map_property_type(property_type, type_map)
        if berdo_use is None:
            continue  # unmapped use: excluded from citywide totals (R6.1, R2.6)

        applicable_standard = _coerce_standard(row.get(COL_APPLICABLE_STANDARD))
        limit_vector = resolve_limit_vector(
            applicable_standard, berdo_use, limits_table
        )
        if limit_vector is None:
            continue  # mapped use absent from limits table (R2.7)

        emissions_kg = float(row.get(COL_TOTAL_GHG, 0.0) or 0.0)
        floor_area_sqft = float(row.get(COL_FLOOR_AREA, 0.0) or 0.0)
        first_compliance_year = _coerce_first_compliance_year(
            row.get(COL_FIRST_COMPLIANCE_YEAR)
        )

        exposure = period_exposure(
            emissions_kg=emissions_kg,
            limit_vector=limit_vector,
            floor_area_sqft=floor_area_sqft,
            first_compliance_year=first_compliance_year,
        )

        acp_2025 = float(exposure[period_2025]["acp_usd"])
        acp_2030 = float(exposure[period_2030]["acp_usd"])

        if acp_2025 > 0.0:
            over_2025 += 1
        if acp_2030 > 0.0:
            over_2030 += 1

        zip_code = _resolve_zip(row)
        zip_totals[zip_code] = zip_totals.get(zip_code, 0.0) + acp_2030

    return {
        "zip_totals": zip_totals,
        "over_2025": over_2025,
        "over_2030": over_2030,
    }


def render_city_view(df: pd.DataFrame) -> None:
    """Render the City view page: ZIP bar chart and over-limit counts.

    Shows a Plotly bar chart of total 2030–2034 ACP (whole dollars) grouped by
    ZIP, sorted descending by exposure, for mapped-use buildings only (R6.1,
    R6.2). When no building qualifies, shows an empty-state message instead of
    an empty chart (R6.5). Displays the non-negative whole-number counts of
    buildings over the limit in 2025–2029 and 2030–2034 (R6.6, R6.7).
    """
    st.header("City view")
    st.caption(
        "Citywide estimated exposure for outreach planning. Estimate, not a "
        "compliance determination."
    )

    # Shared disclaimer near the top so it's visible without scrolling (R8.1).
    render_disclaimer()

    if df.empty:
        st.info(NO_CITYWIDE_DATA_TEXT)
        return

    aggregated = aggregate_city_exposure(df)
    zip_totals: dict[str, float] = aggregated["zip_totals"]
    over_2025 = int(aggregated["over_2025"])
    over_2030 = int(aggregated["over_2030"])

    # --- Over-limit counts (non-negative whole numbers) -------------------
    count_cols = st.columns(2)
    count_cols[0].metric("Buildings over the limit, 2025–2029", f"{over_2025:,d}")
    count_cols[1].metric("Buildings over the limit, 2030–2034", f"{over_2030:,d}")

    # --- ZIP bar chart ----------------------------------------------------
    st.markdown("### Total estimated 2030–2034 exposure by ZIP")

    if not zip_totals:
        # No mapped building qualified: show a message, not an empty chart (R6.5).
        st.info(NO_CITYWIDE_DATA_TEXT)
        return

    # Sort descending by total exposure so the highest-exposure ZIP is first.
    ordered = sorted(zip_totals.items(), key=lambda item: item[1], reverse=True)
    chart_df = pd.DataFrame(
        {
            "ZIP": [zip_code for zip_code, _ in ordered],
            # Whole dollars for display (R6.1). Computation already done in berdo/.
            "Estimated 2030–2034 exposure ($)": [
                round(total) for _, total in ordered
            ],
        }
    )

    fig = px.bar(
        chart_df,
        x="ZIP",
        y="Estimated 2030–2034 exposure ($)",
        title=None,
    )
    # Preserve the descending sort (don't let plotly re-sort categorically).
    fig.update_layout(
        xaxis={"categoryorder": "array", "categoryarray": chart_df["ZIP"].tolist()},
        yaxis_title="Estimated 2030–2034 exposure ($)",
        xaxis_title="ZIP code",
    )
    st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# About & sources page (Task 13.1)
# ---------------------------------------------------------------------------
def render_about() -> None:
    """Render the About & sources page: data/limit sources and the disclaimer.

    Cites the boston.gov BERDO page for the emissions limits and ACP, and the
    City of Boston BERDO 2026 disclosure (2025 data, published on Analyze Boston
    under the PDDL license) as the building-data source (R8.2). Includes the
    shared disclaimer block (R8.1–R8.5, R8.7) so the About screen, like every
    result screen, is clearly labeled as an estimate.
    """
    st.header("About & sources")

    # Shared disclaimer near the top so it's visible without scrolling (R8.1).
    render_disclaimer()

    st.markdown(
        "BERDO Gap estimates how much a large Boston building may owe each year "
        "under BERDO's emissions limits (the $234-per-ton Alternative "
        "Compliance Payment), shows which retrofit removes that estimated "
        "exposure, and drafts a one-page memo for the owner's board. Every "
        "figure shown is an estimated exposure, not a compliance determination."
    )

    st.markdown("### Sources")
    st.markdown(
        "- **Emissions limits and the Alternative Compliance Payment:** "
        "[City of Boston BERDO page](https://www.boston.gov/departments/"
        "environment/building-emissions-reduction-and-disclosure)."
    )
    st.markdown(
        "- **Building data:** "
        f"{DISCLAIMER_SOURCE_TEXT}, published on "
        "[Analyze Boston](https://data.boston.gov/) under the Public Domain "
        "Dedication and License (PDDL)."
    )
    st.markdown(
        "- **Projected grid emissions factors:** "
        "`data/projected_grid_factors.csv`, from the City of Boston BERDO "
        "Policies and Procedures (Appendix B)."
    )

    st.markdown("### Important notes")
    st.markdown(
        f"- {DISCLAIMER_ESTIMATE_TEXT}. {DISCLAIMER_FLEXIBILITY_TEXT}"
    )
    st.markdown(f"- {DISCLAIMER_GRID_TEXT}")
    st.markdown(f"- {DISCLAIMER_BERDO_TEAM_TEXT}")


# ---------------------------------------------------------------------------
# App entry point
# ---------------------------------------------------------------------------
def main() -> None:
    """Configure the page and dispatch to the selected page."""
    st.set_page_config(page_title="BERDO Gap", page_icon="🏢", layout="wide")
    st.title("BERDO Gap")

    page = st.sidebar.radio(
        "Page",
        ("Building", "City view", "About & sources"),
        index=0,
    )

    # Load the dataset once (cached). A load failure is shown as a friendly
    # error rather than a traceback, and the page returns early.
    df: pd.DataFrame | None = None
    try:
        df = get_disclosure()
    except LoadError as exc:
        st.error(
            "Could not load the City's BERDO disclosure data. "
            f"Please try again later.\n\nDetails: {exc}"
        )

    if page == "Building":
        if df is None:
            return
        render_building_page(df)
    elif page == "City view":
        if df is None:
            return
        render_city_view(df)
    else:
        render_about()


if __name__ == "__main__":
    main()
