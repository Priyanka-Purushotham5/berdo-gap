"""BERDO Gap - Streamlit UI.

This is the only Streamlit file. It renders three pages (Building, City view,
About & sources), reads user inputs, calls the pure functions in ``berdo/``, and
formats results for display. The UI performs NO calculation of its own: it only
rounds for display (tons to 1 decimal, dollars to whole dollars) and shows
numbers that came from a ``berdo/`` function or directly from the City's data
file.

A sidebar radio navigates across three pages. The Building page is organized
into three tabs (Overview, Retrofit planner, Board memo); the "Estimate, not a
compliance determination" banner is shown once per page (R8.1) and the rest of
the Requirement 8 disclosures live in a single "About this estimate" expander.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pandas as pd
import plotly.graph_objects as go
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
NO_REPORTED_EMISSIONS_TEXT = "No reported emissions - enter your own numbers"
CITY_STATUS_UNAVAILABLE_TEXT = "City status not available"
UNKNOWN_ZIP_LABEL = "Unknown ZIP"
NO_CITYWIDE_DATA_TEXT = (
    "No citywide exposure data is available - no building with a mapped BERDO "
    "use qualified for the chart."
)

# Theme colors (match .streamlit/config.toml primaryColor).
COLOR_LIMIT = "#1B7F5A"      # green: the City limit
COLOR_EMISSIONS = "#C2410C"  # burnt orange: today's emissions
COLOR_SCENARIO = "#1B7F5A"   # green: scenario emissions line
COLOR_GAP = "rgba(194,65,12,0.18)"  # translucent red/orange: the over-limit gap

# Chart x-axis: the first year of each compliance period plus the 2050 endpoint.
PERIOD_START_YEARS: dict[str, int] = {
    "2025-2029": 2025,
    "2030-2034": 2030,
    "2035-2039": 2035,
    "2040-2044": 2040,
    "2045-2049": 2045,
    "2050+": 2050,
}
CHART_END_YEAR = 2050

# ---------------------------------------------------------------------------
# Requirement 8 disclosures - exact phrasing mandated by the product steering.
# The strings below are used VERBATIM; do not edit the wording.
# ---------------------------------------------------------------------------
DISCLAIMER_ESTIMATE_TEXT = "Estimate, not a compliance determination"
DISCLAIMER_SOURCE_TEXT = (
    "City of Boston BERDO 2026 disclosure, 2025 data, PDDL license"
)
DISCLAIMER_FLEXIBILITY_TEXT = (
    "Portfolio and campus compliance and flexibility measures can reduce real "
    "exposure."
)
DISCLAIMER_GRID_TEXT = "The City projects grid emissions roughly flat through 2034 (data/projected_grid_factors.csv), so 2030 estimates hold; later periods may be lower."
DISCLAIMER_BERDO_TEAM_TEXT = (
    "For official or legal compliance answers, contact the City of Boston "
    "BERDO team."
)
DISCLAIMER_ESTIMATED_EXPOSURE_TEXT = (
    "Figures shown are an estimated exposure based on the City's data file and "
    "this calculator."
)


def render_disclaimer() -> None:
    """Render the shared Requirement 8 disclosure block, once per page (R8).

    A single one-line warning banner carries the "Estimate, not a compliance
    determination" line so it is visible without scrolling (R8.1). The remaining
    disclosure lines (R8.2-R8.5, R8.7) live in one "About this estimate"
    expander. Callers invoke this exactly once per page so the banner is not
    repeated. Every string is rendered verbatim from the module constants above.
    """
    st.warning(f"**{DISCLAIMER_ESTIMATE_TEXT}.** {DISCLAIMER_ESTIMATED_EXPOSURE_TEXT}")
    with st.expander("About this estimate"):
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
# Visual theme: CSS + original inline SVG (no external images)
# ---------------------------------------------------------------------------
# Per-page accent gradients (card color == page header band color).
PAGE_GRADIENTS: dict[str, str] = {
    "building": "linear-gradient(135deg, #0F766E 0%, #14B8A6 100%)",   # teal
    "city": "linear-gradient(135deg, #3730A3 0%, #6366F1 100%)",        # indigo
    "about": "linear-gradient(135deg, #334155 0%, #64748B 100%)",       # slate
}

_GLOBAL_CSS = """
<style>
/* Metric tiles as white cards with soft shadow and rounded corners. */
div[data-testid="stMetric"] {
    background: #FFFFFF;
    border: 1px solid #E6ECEA;
    border-radius: 14px;
    padding: 1rem 1.1rem;
    box-shadow: 0 6px 18px rgba(16, 24, 40, 0.06);
}
div[data-testid="stMetric"] label p { color: #5B6B66; font-weight: 600; }

/* Full-bleed hero. */
.bg-hero {
    position: relative;
    border-radius: 18px;
    overflow: hidden;
    background: linear-gradient(135deg, #064E3B 0%, #0F766E 55%, #14B8A6 100%);
    color: #F8FFFC;
    padding: 2.6rem 2.2rem 0 2.2rem;
    margin-bottom: 1.4rem;
    box-shadow: 0 12px 34px rgba(6, 78, 59, 0.28);
}
.bg-hero h1 { font-size: 2.3rem; line-height: 1.15; margin: 0 0 0.6rem 0; color: #F8FFFC; }
.bg-hero p.sub { font-size: 1.12rem; max-width: 46rem; margin: 0; color: #D7F5EC; }
.bg-hero .skyline { display: block; width: 100%; height: 96px; margin-top: 1.6rem; }

/* Gradient page header band. */
.bg-band {
    border-radius: 16px;
    padding: 1.4rem 1.6rem;
    margin-bottom: 1.2rem;
    color: #FFFFFF;
    box-shadow: 0 8px 22px rgba(16, 24, 40, 0.14);
}
.bg-band h2 { margin: 0 0 0.25rem 0; color: #FFFFFF; font-size: 1.55rem; }
.bg-band p { margin: 0; color: rgba(255,255,255,0.92); font-size: 1rem; }

/* Landing stat cards. */
.stat-grid { display: flex; gap: 1rem; flex-wrap: wrap; margin: 0.4rem 0 1.6rem 0; }
.stat-card {
    flex: 1 1 220px;
    background: #FFFFFF;
    border: 1px solid #E6ECEA;
    border-radius: 16px;
    padding: 1.3rem 1.4rem;
    box-shadow: 0 8px 22px rgba(16, 24, 40, 0.07);
}
.stat-card .v { font-size: 2rem; font-weight: 700; color: #0F766E; line-height: 1.1; }
.stat-card .k { font-size: 0.95rem; color: #5B6B66; margin-top: 0.35rem; }

/* Landing navigation cards. */
.nav-grid { display: flex; gap: 1rem; flex-wrap: wrap; margin-top: 0.3rem; }
.nav-card {
    flex: 1 1 240px;
    border-radius: 16px;
    padding: 1.4rem 1.4rem 1.2rem 1.4rem;
    color: #FFFFFF;
    box-shadow: 0 10px 26px rgba(16, 24, 40, 0.16);
    min-height: 130px;
}
.nav-card .title { font-size: 1.2rem; font-weight: 700; margin: 0.4rem 0 0.25rem 0; }
.nav-card .desc { font-size: 0.95rem; color: rgba(255,255,255,0.92); }
</style>
"""


def inject_css() -> None:
    """Inject the global CSS once per page render (R: original visuals only)."""
    st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)


def _skyline_svg() -> str:
    """Return an original inline SVG city-skyline silhouette for the hero.

    Hand-drawn rectangles/paths only; no external image. The silhouette uses a
    translucent light fill so it reads as a skyline band at the hero's bottom.
    """
    return """
<svg class="skyline" viewBox="0 0 1200 120" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">
  <g fill="rgba(248,255,252,0.16)">
    <rect x="0"   y="70" width="70"  height="50"/>
    <rect x="80"  y="48" width="54"  height="72"/>
    <rect x="150" y="60" width="40"  height="60"/>
    <rect x="205" y="30" width="60"  height="90"/>
    <rect x="280" y="54" width="46"  height="66"/>
    <rect x="340" y="18" width="40"  height="102"/>
    <rect x="395" y="64" width="58"  height="56"/>
    <rect x="470" y="40" width="50"  height="80"/>
    <rect x="535" y="8"  width="34"  height="112"/>
    <rect x="585" y="56" width="60"  height="64"/>
    <rect x="660" y="36" width="48"  height="84"/>
    <rect x="722" y="66" width="52"  height="54"/>
    <rect x="790" y="24" width="42"  height="96"/>
    <rect x="848" y="58" width="56"  height="62"/>
    <rect x="918" y="44" width="46"  height="76"/>
    <rect x="978" y="14" width="36"  height="106"/>
    <rect x="1028" y="62" width="58" height="58"/>
    <rect x="1100" y="40" width="48" height="80"/>
    <rect x="1160" y="70" width="40" height="50"/>
  </g>
  <g fill="rgba(248,255,252,0.28)">
    <rect x="212" y="42" width="8" height="10"/>
    <rect x="228" y="42" width="8" height="10"/>
    <rect x="347" y="30" width="7" height="9"/>
    <rect x="542" y="20" width="7" height="9"/>
    <rect x="558" y="20" width="7" height="9"/>
    <rect x="985" y="26" width="7" height="9"/>
  </g>
</svg>
"""


def gradient_header(key: str, title: str, subtitle: str) -> None:
    """Render a page's gradient header band in its accent color (landing nav)."""
    gradient = PAGE_GRADIENTS.get(key, PAGE_GRADIENTS["building"])
    st.markdown(
        f"""
<div class="bg-band" style="background:{gradient};">
  <h2>{title}</h2>
  <p>{subtitle}</p>
</div>
""",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Data loading (cached so the download / cache read happens once per session)
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner="Loading the City's BERDO disclosure...")
def get_disclosure() -> pd.DataFrame:
    """Return the normalized, filtered disclosure (cached for the session)."""
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


def _format_signed_dollars(value: float) -> str:
    """Format a signed dollar delta with the sign before the dollar sign.

    A negative delta renders as "-$43,765" (minus before "$") and a positive
    delta as "+$43,765". Display-only rounding to whole dollars (R3.7).
    """
    rounded = round(value)
    sign = "-" if rounded < 0 else "+"
    return f"{sign}${abs(rounded):,.0f}"


def resolve_limit_vector(
    applicable_standard: float | None,
    berdo_use: str | None,
    limits_table: dict[str, dict[str, float]],
) -> dict[str, float] | None:
    """Build the six-period limit vector for a building, or ``None``.

    The 2025-2029 entry honors the City's Applicable_Standard when present
    (``resolve_2025_2029_limit``); the later periods come from the mapped use's
    table row (``period_limits``). Returns ``None`` when the use is unmapped or
    absent from the limits table, which the UI renders as "limit unknown".
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
    """Return the First_Compliance_Year as an int, defaulting to 2025."""
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
    """Return a 'BERDO ID - Address' label for the selectbox."""
    berdo_id = str(row.get(COL_BERDO_ID, "")).strip()
    address = str(row.get(COL_ADDRESS, "")).strip()
    if address:
        return f"{berdo_id} - {address}"
    return berdo_id


# ---------------------------------------------------------------------------
# Building page
# ---------------------------------------------------------------------------
BERDO_INTRO = (
    "Large Boston buildings have greenhouse-gas limits under BERDO that tighten "
    "every five years.\n\n"
    "A building whose emissions exceed its limit owes an estimated $234 for each "
    "metric ton over, every year.\n\n"
    "This tool estimates what a building would owe and shows which retrofits "
    "close the gap."
)


def render_building_page(df: pd.DataFrame) -> None:
    """Render the Building page: intro, picker, and the three result tabs.

    A plain-language intro and the search/picker sit at the top. Below the
    picker a one-sentence summary built from calculator outputs, then the single
    Requirement 8 banner (shown once per page), then three tabs: Overview,
    Retrofit planner, and Board memo.
    """
    inject_css()
    gradient_header(
        "building",
        "Check a building",
        "Look up a BERDO-covered building and see its estimated exposure, the "
        "gap chart, and retrofit scenarios.",
    )

    st.markdown("### What is BERDO?")
    st.markdown(BERDO_INTRO)

    if df.empty:
        render_disclaimer()
        st.info(NO_REPORTED_EMISSIONS_TEXT)
        return

    # --- Search box + building picker, directly under the intro ----------
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
        render_disclaimer()
        st.info(NO_REPORTED_EMISSIONS_TEXT)
        return

    # Default the picker to BERDO ID 100018 (1047 Commonwealth Ave) when present.
    default_index = 0
    for pos, label in enumerate(filtered):
        if label.startswith("100018 "):
            default_index = pos
            break
    selected_label = st.selectbox("Building", filtered, index=default_index)
    row = df.loc[labels[selected_label]]

    # --- Building identity + exposure (all numbers from berdo/) ----------
    address = str(row.get(COL_ADDRESS, "")).strip()
    berdo_id = str(row.get(COL_BERDO_ID, "")).strip()
    property_type = str(row.get(COL_LARGEST_PROPERTY_TYPE, "")).strip()
    zip_code = str(row.get(COL_ZIP, "")).strip()
    display_name = address or berdo_id

    type_map = get_property_type_map()
    limits_table = get_limits_table()
    berdo_use = map_property_type(property_type, type_map)

    applicable_standard = _coerce_standard(row.get(COL_APPLICABLE_STANDARD))
    limit_vector = resolve_limit_vector(applicable_standard, berdo_use, limits_table)
    city_status = _city_status_text(row)

    if limit_vector is None:
        # Unmapped property type, or a mapped use absent from the limits table.
        render_disclaimer()
        st.subheader(display_name)
        st.markdown(f"**Largest property type:** {property_type or '-'}")
        _render_headline(None, None, city_status)
        st.warning(
            f"{LIMIT_UNKNOWN_TEXT} - this building's property type "
            f"('{property_type or 'blank'}') is not mapped to a BERDO use, so "
            "no emissions limit can be applied."
        )
        return

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

    # --- One-sentence plain-English summary from calculator outputs ------
    st.markdown(
        f"#### {display_name}"
    )
    st.info(
        _plain_summary(display_name, exposure, emissions_kg, floor_area_sqft,
                       limit_vector)
    )

    # --- Single Requirement 8 banner for the whole page (R8.1) -----------
    render_disclaimer()

    # --- Tabs: Overview | Retrofit planner | Board memo ------------------
    overview_tab, planner_tab, memo_tab = st.tabs(
        ["Overview", "Retrofit planner", "Board memo"]
    )

    with overview_tab:
        st.markdown(f"**Largest property type:** {property_type or '-'}")
        id_cols = st.columns(2)
        id_cols[0].metric("BERDO ID", berdo_id or "-")
        id_cols[1].metric("ZIP", zip_code or "-")
        _render_headline(
            _period_acp_display(exposure, PERIODS[0]),
            _period_acp_display(exposure, PERIODS[1]),
            city_status,
        )
        st.markdown("#### The gap")
        _render_gap_chart(
            emissions_kg, floor_area_sqft, limit_vector, first_compliance_year,
            key="gap_overview",
        )
        _render_exposure_table(exposure, berdo_use)

    with planner_tab:
        _render_retrofit_planner(
            row=row,
            berdo_use=berdo_use,
            limit_vector=limit_vector,
            emissions_kg=emissions_kg,
            floor_area_sqft=floor_area_sqft,
            first_compliance_year=first_compliance_year,
            exposure=exposure,
        )

    with memo_tab:
        _render_memo_tab(
            row=row,
            address=display_name,
            berdo_use=berdo_use,
            limit_vector=limit_vector,
            floor_area_sqft=floor_area_sqft,
            first_compliance_year=first_compliance_year,
            emissions_kg=emissions_kg,
            exposure=exposure,
        )


def _city_status_text(row: pd.Series) -> str:
    """Return the City's Compliance_Status verbatim, or "" when missing/blank."""
    raw_status = row.get(COL_COMPLIANCE_STATUS, "")
    try:
        if pd.isna(raw_status):
            raw_status = ""
    except (TypeError, ValueError):
        pass
    return str(raw_status).strip()


def _period_acp_display(exposure: dict[str, dict[str, Any]], period: str) -> str:
    """Return the display ACP for a period, or a 'not yet covered' label."""
    result = exposure[period]
    if str(result["status"]) == STATUS_NOT_YET_COVERED:
        return "not yet covered"
    return format_dollars(float(result["acp_usd"]))


def _plain_summary(
    name: str,
    exposure: dict[str, dict[str, Any]],
    emissions_kg: float,
    floor_area_sqft: float,
    limit_vector: dict[str, float],
) -> str:
    """Return a one-sentence plain-English summary from calculator outputs.

    Uses only numbers the calculator produced: the excess tons for the first
    covered period and the 2030-2034 estimated payment. All display rounding;
    no calculation here.
    """
    period_2025, period_2030 = PERIODS[0], PERIODS[1]
    r2025 = exposure[period_2025]
    r2030 = exposure[period_2030]

    # Lead with the earliest covered period's over-limit tons when it applies.
    if str(r2025["status"]) != STATUS_NOT_YET_COVERED and float(r2025["excess_tons"]) > 0:
        tons = format_tons(float(r2025["excess_tons"]))
        lead = f"{name} is {tons} tons over its 2025 limit."
    elif str(r2030["status"]) != STATUS_NOT_YET_COVERED and float(r2030["excess_tons"]) > 0:
        tons = format_tons(float(r2030["excess_tons"]))
        lead = f"{name} is within its 2025 limit but {tons} tons over the 2030 limit."
    else:
        lead = f"{name} is within its BERDO limits in the periods shown."

    if str(r2030["status"]) == STATUS_NOT_YET_COVERED:
        tail = "Its 2030-2034 period is not yet covered, so no payment is estimated then."
    else:
        acp = format_dollars(float(r2030["acp_usd"]))
        if float(r2030["acp_usd"]) > 0:
            tail = (
                f"When the limit tightens in 2030, its estimated payment is "
                f"{acp} a year."
            )
        else:
            tail = "When the limit tightens in 2030, its estimated payment stays at $0 a year."
    return f"{lead} {tail}"


def _render_headline(
    acp_2025: str | None, acp_2030: str | None, city_status: str
) -> None:
    """Render the three headline tiles (R7.1, R7.2)."""
    tiles = st.columns(3)
    tiles[0].metric(
        "Estimated payment 2025-2029 ($/yr)",
        acp_2025 if acp_2025 is not None else LIMIT_UNKNOWN_TEXT,
    )
    tiles[1].metric(
        "Estimated payment 2030-2034 ($/yr)",
        acp_2030 if acp_2030 is not None else LIMIT_UNKNOWN_TEXT,
    )
    tiles[2].metric(
        "City compliance status",
        city_status or CITY_STATUS_UNAVAILABLE_TEXT,
    )


def _limit_tons_by_year(
    limit_vector: dict[str, float], floor_area_sqft: float
) -> tuple[list[int], list[float]]:
    """Return step-line (years, limit tons/yr) points for the gap chart.

    The limit in tons/yr for a period is ``limit_per_sqft * floor_area / 1000``
    (a display conversion of the calculator's limit inputs, not a new estimate).
    The step line holds each period's limit from its start year until the next
    period starts, with a final point at 2050.
    """
    years: list[int] = []
    tons: list[float] = []
    ordered = list(PERIODS)
    for period in ordered:
        start = PERIOD_START_YEARS[period]
        limit_t = limit_vector[period] * floor_area_sqft / 1000.0
        years.append(start)
        tons.append(limit_t)
    # The last period ("2050+") already anchors at CHART_END_YEAR (2050), so no
    # extra endpoint is needed; plotly's "hv" line shape draws the vertical drop
    # between successive period levels.
    return years, tons


def _render_gap_chart(
    emissions_kg: float,
    floor_area_sqft: float,
    limit_vector: dict[str, float],
    first_compliance_year: int,
    scenario_emissions_kg: float | None = None,
    key: str | None = None,
) -> None:
    """Render "The gap": emissions vs the stepped-down City limit, 2025-2050.

    The building's emissions are a flat line in tons/yr; the City limit is a
    step line that drops at each compliance period. The area where emissions
    exceed the limit is shaded. When a scenario is supplied, its emissions are
    added as a second flat line. All tonnages are display conversions of
    calculator inputs (kg / 1000); no exposure is recomputed here.
    """
    emissions_tons = emissions_kg / 1000.0
    years, limit_tons = _limit_tons_by_year(limit_vector, floor_area_sqft)

    fig = go.Figure()

    # City limit: green step line that drops at each period.
    fig.add_trace(
        go.Scatter(
            x=years,
            y=limit_tons,
            mode="lines",
            line={"color": COLOR_LIMIT, "width": 3, "shape": "hv"},
            name="City limit (tons/yr)",
        )
    )

    # Today's emissions: flat line across the whole horizon.
    fig.add_trace(
        go.Scatter(
            x=[years[0], CHART_END_YEAR],
            y=[emissions_tons, emissions_tons],
            mode="lines",
            line={"color": COLOR_EMISSIONS, "width": 3},
            name="Emissions (tons/yr)",
        )
    )

    # Shade the over-limit gap: fill between the step limit and the flat
    # emissions line wherever emissions exceed the limit. We build the emissions
    # level sampled on the same x points and fill to the previous trace.
    emis_on_steps = [emissions_tons for _ in years]
    gap_y = [max(e, l) for e, l in zip(emis_on_steps, limit_tons)]
    fig.add_trace(
        go.Scatter(
            x=years,
            y=limit_tons,
            mode="lines",
            line={"color": "rgba(0,0,0,0)", "shape": "hv"},
            showlegend=False,
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=years,
            y=gap_y,
            mode="lines",
            line={"color": "rgba(0,0,0,0)", "shape": "hv"},
            fill="tonexty",
            fillcolor=COLOR_GAP,
            name="Estimated gap (over limit)",
            hoverinfo="skip",
        )
    )

    # Scenario emissions line (green) when sliders changed the emissions.
    if scenario_emissions_kg is not None:
        scen_tons = scenario_emissions_kg / 1000.0
        fig.add_trace(
            go.Scatter(
                x=[years[0], CHART_END_YEAR],
                y=[scen_tons, scen_tons],
                mode="lines",
                line={"color": COLOR_SCENARIO, "width": 3, "dash": "dash"},
                name="Scenario emissions (tons/yr)",
            )
        )

    fig.update_layout(
        title="The gap",
        xaxis_title="Year",
        yaxis_title="Metric tons CO2e per year",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02},
        margin={"t": 60, "r": 20, "b": 40, "l": 60},
    )
    fig.update_xaxes(range=[years[0], CHART_END_YEAR], dtick=5)
    fig.update_yaxes(rangemode="tozero")
    st.plotly_chart(fig, use_container_width=True, key=key)


def _render_exposure_table(
    exposure: dict[str, dict[str, Any]], berdo_use: str, show_heading: bool = True
) -> None:
    """Render the six-period estimated-exposure table with display rounding."""
    if show_heading:
        st.markdown("#### Estimated exposure by period")
    st.caption(f"BERDO use: **{berdo_use}** - Estimate, not a compliance determination.")

    rows: list[dict[str, str]] = []
    for period in PERIODS:
        result = exposure[period]
        status_raw = str(result["status"])
        status_label = _STATUS_LABELS.get(status_raw, status_raw)
        if status_raw == STATUS_NOT_YET_COVERED:
            tons_display = "-"
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


# ---------------------------------------------------------------------------
# Retrofit planner tab + board memo
# ---------------------------------------------------------------------------
# A min_value strictly greater than 0 for the editable boiler-efficiency and COP
# inputs. Streamlit's number_input enforces [min_value, max_value] (R4.9, R4.10).
_POSITIVE_MIN = 0.01


def _electricity_factor(row: pd.Series) -> float:
    """Return the building's own electricity emission factor (kgCO2e/kWh).

    Electricity emissions / electricity kWh (the per-building ratio the data
    rules require), guarding divide-by-zero with 0.0 when there is no kWh.
    """
    elec_kwh = float(row.get(COL_ELECTRICITY_KWH, 0.0) or 0.0)
    elec_ghg = float(row.get(COL_ELECTRICITY_GHG, 0.0) or 0.0)
    if elec_kwh == 0.0:
        return 0.0
    return elec_ghg / elec_kwh


def _render_retrofit_planner(
    row: pd.Series,
    berdo_use: str,
    limit_vector: dict[str, float],
    emissions_kg: float,
    floor_area_sqft: float,
    first_compliance_year: int,
    exposure: dict[str, dict[str, Any]],
) -> None:
    """Render the Retrofit planner tab.

    Sliders + editable assumptions feed ``apply_scenario``; the transformed
    emissions are re-run through ``period_exposure`` with the SAME limit vector,
    floor area, and first compliance year. Shows before/after tiles, the gap
    chart with the scenario line, a grouped baseline-vs-scenario bar chart by
    period, and the scenario exposure table.

    Satisfies: R4.1, R4.9, R4.10, R4.11.
    """
    st.caption(
        "Model a heat-pump conversion and an efficiency upgrade to see how they "
        "change this building's estimated exposure."
    )

    input_cols = st.columns(2)
    f = input_cols[0].slider(
        "Heat-pump fraction (share of gas heat converted)",
        min_value=0.0, max_value=1.0, value=0.0, step=0.05,
        help="0.0 keeps today's gas heat; 1.0 converts all of it to heat pumps.",
    )
    p = input_cols[1].slider(
        "Efficiency improvement (%)",
        min_value=0, max_value=100, value=0, step=1,
        help="Percent reduction in energy use and emissions from efficiency work.",
    )

    with st.expander("Assumptions"):
        assumption_cols = st.columns(2)
        boiler_eff = assumption_cols[0].number_input(
            "Boiler efficiency assumption",
            min_value=_POSITIVE_MIN, max_value=1.0,
            value=BOILER_EFFICIENCY_DEFAULT, step=0.01,
            help="Share of fuel energy delivered as useful heat. Greater than 0, up to 1.0.",
        )
        cop = assumption_cols[1].number_input(
            "Heat-pump seasonal COP assumption",
            min_value=_POSITIVE_MIN, value=COP_DEFAULT, step=0.1,
            help="Heat-pump coefficient of performance. Must be greater than 0.",
        )

    # Transform emissions and re-run exposure (all math in berdo/, R4.11).
    natural_gas_kbtu = float(row.get(COL_NATURAL_GAS_KBTU, 0.0) or 0.0)
    natural_gas_kgco2e = float(row.get(COL_NATURAL_GAS_GHG, 0.0) or 0.0)
    elec_factor = _electricity_factor(row)
    new_emissions_kg = apply_scenario(
        emissions_kg, natural_gas_kbtu, natural_gas_kgco2e, elec_factor,
        f, float(p), boiler_eff, cop,
    )
    scenario_exposure = period_exposure(
        emissions_kg=new_emissions_kg,
        limit_vector=limit_vector,
        floor_area_sqft=floor_area_sqft,
        first_compliance_year=first_compliance_year,
    )

    changed = round(new_emissions_kg) != round(emissions_kg)

    # --- Before / after tiles (2030-2034) --------------------------------
    period_2030 = PERIODS[1]
    base_2030 = exposure[period_2030]
    scen_2030 = scenario_exposure[period_2030]
    st.markdown("#### Before and after (2030-2034)")
    ba = st.columns(2)
    if str(base_2030["status"]) == STATUS_NOT_YET_COVERED:
        ba[0].metric("Baseline payment ($/yr)", "not yet covered")
        ba[1].metric("With this scenario ($/yr)", "not yet covered")
    else:
        base_acp = float(base_2030["acp_usd"])
        scen_acp = float(scen_2030["acp_usd"])
        delta = scen_acp - base_acp
        ba[0].metric("Baseline payment ($/yr)", format_dollars(base_acp))
        delta_display = _format_signed_dollars(delta) if round(delta) != 0 else None
        ba[1].metric(
            "With this scenario ($/yr)",
            format_dollars(scen_acp),
            delta=delta_display,
            delta_color="inverse",
        )

    # --- Gap chart with the scenario line when sliders changed -----------
    st.markdown("#### The gap with this scenario")
    _render_gap_chart(
        emissions_kg, floor_area_sqft, limit_vector, first_compliance_year,
        scenario_emissions_kg=new_emissions_kg if changed else None,
        key="gap_planner",
    )

    # --- Grouped bar chart: baseline vs scenario ACP by period -----------
    st.markdown("#### Baseline vs scenario by period")
    _render_grouped_bars(exposure, scenario_exposure)

    # --- Scenario exposure table -----------------------------------------
    st.markdown("#### Exposure by period with this scenario")
    _render_exposure_table(scenario_exposure, berdo_use, show_heading=False)

    # Stash the scenario in session for the Board memo tab.
    st.session_state["_scenario"] = {
        "new_emissions_kg": new_emissions_kg,
        "scenario_exposure": scenario_exposure,
        "f": f,
        "p": float(p),
        "boiler_eff": boiler_eff,
        "cop": cop,
    }


def _render_grouped_bars(
    exposure: dict[str, dict[str, Any]],
    scenario_exposure: dict[str, dict[str, Any]],
) -> None:
    """Render a grouped bar chart of baseline vs scenario ACP by period."""
    records: list[dict[str, Any]] = []
    for period in PERIODS:
        base = exposure[period]
        scen = scenario_exposure[period]
        base_acp = 0.0 if str(base["status"]) == STATUS_NOT_YET_COVERED else round(float(base["acp_usd"]))
        scen_acp = 0.0 if str(scen["status"]) == STATUS_NOT_YET_COVERED else round(float(scen["acp_usd"]))
        records.append({"Period": period, "Scenario": "Baseline", "Estimated payment ($/yr)": base_acp})
        records.append({"Period": period, "Scenario": "With retrofit", "Estimated payment ($/yr)": scen_acp})
    chart_df = pd.DataFrame(records)
    fig = px.bar(
        chart_df,
        x="Period",
        y="Estimated payment ($/yr)",
        color="Scenario",
        barmode="group",
        color_discrete_map={"Baseline": COLOR_EMISSIONS, "With retrofit": COLOR_SCENARIO},
    )
    fig.update_layout(
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02},
        margin={"t": 40, "r": 20, "b": 40, "l": 60},
    )
    st.plotly_chart(fig, use_container_width=True, key="grouped_bars")


def _render_memo_tab(
    row: pd.Series,
    address: str,
    berdo_use: str,
    limit_vector: dict[str, float],
    floor_area_sqft: float,
    first_compliance_year: int,
    emissions_kg: float,
    exposure: dict[str, dict[str, Any]],
) -> None:
    """Render the Board memo tab: button + generated memo.

    Uses the scenario stashed by the Retrofit planner tab when present,
    otherwise a no-change baseline scenario, so the memo reflects the planner.
    """
    st.caption(
        "Draft a one-page board memo from this building's estimated figures."
    )
    scenario = st.session_state.get("_scenario")
    if scenario is None:
        # No planner interaction yet: use a no-change baseline scenario.
        scenario = {
            "new_emissions_kg": emissions_kg,
            "scenario_exposure": exposure,
            "f": 0.0,
            "p": 0.0,
            "boiler_eff": BOILER_EFFICIENCY_DEFAULT,
            "cop": COP_DEFAULT,
        }

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
            scenario_exposure=scenario["scenario_exposure"],
            new_emissions_kg=scenario["new_emissions_kg"],
            f=scenario["f"],
            p=scenario["p"],
            boiler_eff=scenario["boiler_eff"],
            cop=scenario["cop"],
        )


def _read_secret(name: str) -> str | None:
    """Return a Streamlit secret, or ``None`` when secrets are unavailable."""
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
    """Build the memo payload from calculator outputs and render the memo."""
    raw_status = row.get(COL_COMPLIANCE_STATUS, "")
    try:
        if pd.isna(raw_status):
            raw_status = ""
    except (TypeError, ValueError):
        pass
    compliance_status = str(raw_status).strip() or None

    building = SimpleNamespace(
        address=address,
        berdo_use=berdo_use,
        floor_area_sqft=floor_area_sqft,
        first_compliance_year=first_compliance_year,
        compliance_status=compliance_status,
        emissions=emissions_kg,
    )

    by_period = {
        period: {
            "limit_tons": limit_vector[period] * floor_area_sqft / 1000.0,
            "excess_tons": float(values["excess_tons"]),
            "acp_usd": float(values["acp_usd"]),
        }
        for period, values in exposure.items()
    }
    exposure_payload = {
        "by_period": by_period,
        "emissions_tons": emissions_kg / 1000.0,
    }

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
    with st.spinner("Drafting the board memo..."):
        memo = generate_memo(payload, model, api_key)
    _render_memo(memo)


def _render_memo(memo: dict[str, Any]) -> None:
    """Render the five-field board memo (R5.3).

    Dollar signs are escaped ("$" -> "\\$") before rendering so Streamlit's
    Markdown does not treat the text between two "$" as a LaTeX math span.
    """
    st.markdown("#### Board memo")
    headline = memo.get("headline")
    if headline:
        st.markdown(f"**{_escape_dollars(headline)}**")
    exposure_summary = memo.get("exposure_summary")
    if exposure_summary:
        st.markdown("##### Exposure summary")
        st.write(_escape_dollars(exposure_summary))
    recommendation = memo.get("recommendation")
    if recommendation:
        st.markdown("##### Recommendation")
        st.write(_escape_dollars(recommendation))
    tradeoffs = memo.get("tradeoffs") or []
    if tradeoffs:
        st.markdown("##### Tradeoffs")
        for item in tradeoffs:
            st.markdown(f"- {_escape_dollars(str(item))}")
    next_steps = memo.get("next_steps") or []
    if next_steps:
        st.markdown("##### Next steps")
        for item in next_steps:
            st.markdown(f"- {_escape_dollars(str(item))}")


def _escape_dollars(text: str) -> str:
    """Escape "$" as "\\$" so Streamlit Markdown does not render math spans."""
    return str(text).replace("$", "\\$")


# ---------------------------------------------------------------------------
# City view page
# ---------------------------------------------------------------------------
EEIF_CONTEXT = (
    "Payments go to the City's Equitable Emissions Investment Fund for "
    "environmental-justice communities."
)


def _resolve_zip(row: pd.Series) -> str:
    """Return the ZIP for a building for the citywide chart (R6.3, R6.4)."""
    for col in (COL_ZIP, COL_PARCEL_ZIP):
        text = _normalize_zip(row.get(col))
        if text:
            return text
    return UNKNOWN_ZIP_LABEL


def _normalize_zip(value: Any) -> str:
    """Return a cleaned 5-digit ZIP string, or "" when blank/missing."""
    try:
        if value is None or pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(value, float):
        text = str(int(value)) if value.is_integer() else str(value)
    elif isinstance(value, int):
        text = str(value)
    else:
        text = str(value).strip()
    if not text:
        return ""
    if text.isdigit():
        return text.zfill(5)
    return text


@st.cache_data(show_spinner="Aggregating citywide exposure...")
def aggregate_city_exposure(df: pd.DataFrame) -> dict[str, Any]:
    """Aggregate per-ZIP 2030-2034 ACP, counts, and the citywide total.

    Iterates the loaded buildings, maps each Largest Property Type to a BERDO
    use, and SKIPS buildings with no mapping or no limits-table row (R6.1,
    R2.6, R2.7). All computation lives in the ``berdo/`` pure functions; this
    helper only sums the calculator's outputs and tallies counts.
    """
    type_map = get_property_type_map()
    limits_table = get_limits_table()
    period_2025, period_2030 = PERIODS[0], PERIODS[1]

    zip_totals: dict[str, float] = {}
    over_2025 = 0
    over_2030 = 0
    total_2030 = 0.0
    mapped_buildings = 0

    for _, row in df.iterrows():
        property_type = str(row.get(COL_LARGEST_PROPERTY_TYPE, "")).strip()
        berdo_use = map_property_type(property_type, type_map)
        if berdo_use is None:
            continue
        applicable_standard = _coerce_standard(row.get(COL_APPLICABLE_STANDARD))
        limit_vector = resolve_limit_vector(applicable_standard, berdo_use, limits_table)
        if limit_vector is None:
            continue

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

        mapped_buildings += 1
        if acp_2025 > 0.0:
            over_2025 += 1
        if acp_2030 > 0.0:
            over_2030 += 1
        total_2030 += acp_2030

        zip_code = _resolve_zip(row)
        zip_totals[zip_code] = zip_totals.get(zip_code, 0.0) + acp_2030

    return {
        "zip_totals": zip_totals,
        "over_2025": over_2025,
        "over_2030": over_2030,
        "total_2030": total_2030,
        "mapped_buildings": mapped_buildings,
    }


def render_city_view(df: pd.DataFrame) -> None:
    """Render the City view page: headline tiles, context, and the ZIP chart."""
    inject_css()
    gradient_header(
        "city",
        "City view",
        "Citywide estimated exposure by ZIP, for outreach planning.",
    )

    render_disclaimer()

    if df.empty:
        st.info(NO_CITYWIDE_DATA_TEXT)
        return

    aggregated = aggregate_city_exposure(df)
    zip_totals: dict[str, float] = aggregated["zip_totals"]
    over_2030 = int(aggregated["over_2030"])
    total_2030 = float(aggregated["total_2030"])
    reported = int(len(df))

    # --- Three headline tiles --------------------------------------------
    tiles = st.columns(3)
    tiles[0].metric("Buildings with reported emissions", f"{reported:,d}")
    tiles[1].metric("Buildings over the limit, 2030-2034", f"{over_2030:,d}")
    tiles[2].metric(
        "Total estimated 2030-2034 payment ($/yr)", format_dollars(total_2030)
    )
    st.caption(EEIF_CONTEXT)

    # --- ZIP bar chart ----------------------------------------------------
    st.markdown("### Top 15 ZIPs by estimated 2030-2034 exposure")
    if not zip_totals:
        st.info(NO_CITYWIDE_DATA_TEXT)
        return

    ordered = sorted(zip_totals.items(), key=lambda item: item[1], reverse=True)
    top = ordered[:15]
    exposure_col = "Estimated 2030-2034 exposure ($)"
    chart_df = pd.DataFrame(
        {
            "ZIP": [str(zip_code) for zip_code, _ in top],
            exposure_col: [round(total) for _, total in top],
        }
    )
    chart_df["ZIP"] = chart_df["ZIP"].astype(str)
    # Color each bar by its exposure on a green (low) -> red (high) scale.
    fig = px.bar(
        chart_df, x=exposure_col, y="ZIP", orientation="h", title=None,
        color=exposure_col,
        color_continuous_scale=["#1B7F5A", "#EAB308", "#DC2626"],
    )
    fig.update_layout(
        yaxis={
            "type": "category",
            "categoryorder": "array",
            "categoryarray": chart_df["ZIP"].tolist()[::-1],
            "title": "ZIP code",
        },
        xaxis_title=exposure_col,
        coloraxis_colorbar={"title": "$ / yr"},
        margin={"t": 20, "r": 20, "b": 40, "l": 70},
    )
    st.plotly_chart(fig, use_container_width=True, key="city_zip_chart")


# ---------------------------------------------------------------------------
# About & sources page
# ---------------------------------------------------------------------------
def render_about() -> None:
    """Render the About & sources page: data/limit sources and the disclaimer."""
    inject_css()
    gradient_header(
        "about",
        "About & sources",
        "Where the limits, payment rate, and building data come from.",
    )
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
    st.markdown(f"- {DISCLAIMER_ESTIMATE_TEXT}. {DISCLAIMER_FLEXIBILITY_TEXT}")
    st.markdown(f"- {DISCLAIMER_GRID_TEXT}")
    st.markdown(f"- {DISCLAIMER_BERDO_TEAM_TEXT}")


# ---------------------------------------------------------------------------
# Landing page (default) + navigation
# ---------------------------------------------------------------------------
HERO_HEADLINE = "Boston's big buildings have a carbon deadline."
HERO_SUBHEAD = (
    "BERDO caps building emissions and tightens every five years. Over the "
    "limit, owners pay $234 per ton, every year."
)


def _render_hero() -> None:
    """Render the full-width hero: gradient background + inline SVG skyline."""
    st.markdown(
        f"""
<div class="bg-hero">
  <h1>{HERO_HEADLINE}</h1>
  <p class="sub">{HERO_SUBHEAD}</p>
  {_skyline_svg()}
</div>
""",
        unsafe_allow_html=True,
    )


def _render_stat_cards(df: pd.DataFrame) -> None:
    """Render three stat cards computed from the loaded data (display-only)."""
    reported = int(len(df))
    aggregated = aggregate_city_exposure(df)
    over_2030 = int(aggregated["over_2030"])
    total_2030 = float(aggregated["total_2030"])

    st.markdown(
        f"""
<div class="stat-grid">
  <div class="stat-card">
    <div class="v">{reported:,d}</div>
    <div class="k">Buildings with reported emissions</div>
  </div>
  <div class="stat-card">
    <div class="v">{over_2030:,d}</div>
    <div class="k">Buildings over the 2030-2034 limit</div>
  </div>
  <div class="stat-card">
    <div class="v">{format_dollars(total_2030)}</div>
    <div class="k">Total estimated 2030-2034 payment / yr</div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )
    st.caption(f"{EEIF_CONTEXT} {DISCLAIMER_ESTIMATE_TEXT}.")


def _nav_card(key: str, title: str, desc: str) -> None:
    """Render one colored nav card (HTML visual) above its page_link button."""
    gradient = PAGE_GRADIENTS[key]
    st.markdown(
        f"""
<div class="nav-card" style="background:{gradient};">
  <div class="title">{title}</div>
  <div class="desc">{desc}</div>
</div>
""",
        unsafe_allow_html=True,
    )


def build_landing_page(df: pd.DataFrame) -> None:
    """Render the landing page: hero, stat cards, and three nav cards."""
    inject_css()
    _render_hero()

    if df is not None and not df.empty:
        _render_stat_cards(df)

    st.markdown("### Where do you want to go?")
    cols = st.columns(3)
    with cols[0]:
        _nav_card("building", "Check a building",
                  "Estimate one building's payments and model retrofits.")
        st.page_link(BUILDING_PAGE, label="Open")
    with cols[1]:
        _nav_card("city", "City view",
                  "See citywide exposure by ZIP for outreach planning.")
        st.page_link(CITY_PAGE, label="Open")
    with cols[2]:
        _nav_card("about", "About & sources",
                  "Data sources, the payment rate, and important notes.")
        st.page_link(ABOUT_PAGE, label="Open")


# ---------------------------------------------------------------------------
# Page wrappers: st.Page targets take no arguments, so each fetches the cached
# dataset itself and renders a friendly error on load failure.
# ---------------------------------------------------------------------------
def _load_df_or_error() -> pd.DataFrame | None:
    """Return the cached disclosure, or render an error and return ``None``."""
    try:
        return get_disclosure()
    except LoadError as exc:
        st.error(
            "Could not load the City's BERDO disclosure data. "
            f"Please try again later.\n\nDetails: {exc}"
        )
        return None


def landing_page() -> None:
    df = _load_df_or_error()
    build_landing_page(df if df is not None else pd.DataFrame())


def building_page() -> None:
    df = _load_df_or_error()
    if df is None:
        return
    render_building_page(df)


def city_page() -> None:
    df = _load_df_or_error()
    if df is None:
        return
    render_city_view(df)


def about_page() -> None:
    render_about()


# st.Page objects, referenced by the landing nav cards and st.navigation.
HOME_PAGE = st.Page(landing_page, title="Home", icon=":material/home:", default=True)
BUILDING_PAGE = st.Page(building_page, title="Check a building", icon=":material/apartment:")
CITY_PAGE = st.Page(city_page, title="City view", icon=":material/map:")
ABOUT_PAGE = st.Page(about_page, title="About & sources", icon=":material/description:")


def main() -> None:
    """Configure the app and dispatch via st.navigation."""
    st.set_page_config(page_title="BERDO Gap", page_icon=":material/apartment:", layout="wide")
    nav = st.navigation([HOME_PAGE, BUILDING_PAGE, CITY_PAGE, ABOUT_PAGE])
    nav.run()


main()
