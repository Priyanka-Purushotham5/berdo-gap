"""Claude board memo and templated fallback for BERDO Gap.

Pure-Python memo layer. It assembles a memo payload from ONLY the building's
computed numbers (exposure + scenario results) and values read directly from
the City's data file, asks the Claude API for a strict-JSON memo via tool use,
validates that every dollar amount and tonnage rendered in the memo came from a
calculator, and falls back to a deterministic templated memo on any failure.

This module never imports Streamlit: the model identifier and API key are
passed in as arguments (the UI reads them from Streamlit secrets). The API key
is never passed to any logging call.

Satisfies: Requirements 5.1-5.11.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Exactly the five fields the memo must contain, in render order.
MEMO_FIELDS: tuple[str, ...] = (
    "headline",
    "exposure_summary",
    "recommendation",
    "tradeoffs",
    "next_steps",
)

# The Claude API call is given at most this many seconds (R5.7).
CLAUDE_TIMEOUT_S: float = 20.0

# The $234-per-ton ACP rate and the compliance-period years are structural
# constants, not building-specific calculator outputs, so the memo may cite
# them without a per-building calculator match (R5.4).
_ACP_RATE_USD_PER_TON: float = 234.0

# Display tolerances: dollars to the whole dollar, tons to 0.1 ton (R5.4).
_DOLLAR_TOLERANCE: float = 0.5
_TON_TOLERANCE: float = 0.05

# Scenario slider / assumption values that are always permitted in the memo
# without a calculator match (heat-pump fraction f, efficiency percentage p,
# boiler efficiency, COP). f and p are read from the payload's scenario.
_BOILER_EFFICIENCY_DEFAULT: float = 0.85
_COP_DEFAULT: float = 2.5

# The tool name used to force a strict-JSON response.
_MEMO_TOOL_NAME: str = "board_memo"

# System prompt per CLAUDE_MEMO_PROMPT.md: plain English, only the given
# numbers, never "in violation"/"will be fined", no legal/financial advice.
_SYSTEM_PROMPT: str = (
    "You write one-page memos for the board of a Boston building about BERDO, "
    "the city's building emissions law. Readers are volunteers and property "
    "managers, not engineers. Use only the numbers provided in the input; "
    "never calculate, round differently, or invent a number, date, cost or "
    "rebate. If something is not in the input, say it is not known. Write in "
    "plain English at about an 8th-grade reading level. Call every dollar "
    'figure an "estimated Alternative Compliance Payment." Never say the '
    "building is in violation or will be fined, and never give legal or "
    "financial advice. End by recommending the board confirm details with the "
    "City's BERDO team."
)

# JSON schema forcing exactly the five MEMO_FIELDS via tool use (R5.2).
_MEMO_TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "headline": {
            "type": "string",
            "description": "One sentence with the single most important number.",
        },
        "exposure_summary": {
            "type": "string",
            "description": "2-3 sentences: today vs 2030, using the numbers given.",
        },
        "recommendation": {
            "type": "string",
            "description": "2-3 sentences: what the scenario changes, with its numbers.",
        },
        "tradeoffs": {
            "type": "array",
            "items": {"type": "string"},
            "description": "2-4 short bullets: cost, disruption, what the estimate leaves out.",
        },
        "next_steps": {
            "type": "array",
            "items": {"type": "string"},
            "description": "3 short bullets; the last one: confirm with the City's BERDO team.",
        },
    },
    "required": list(MEMO_FIELDS),
    "additionalProperties": False,
}


class MemoError(Exception):
    """Raised when the Claude memo call fails and the fallback should be used.

    Covers API failure, timeout, a non-JSON response, JSON missing any of the
    five required fields, and rate limiting (R5.8).
    """


def build_memo_payload(
    building: Any, exposure: dict, scenario: dict
) -> dict:
    """Assemble the memo input from ONLY calculator numbers and City data.

    The payload mirrors the structure in ``CLAUDE_MEMO_PROMPT.md``. Every value
    comes from either the building record (City data-file values) or the
    exposure/scenario calculator results. No value from any other source is
    included.

    ``building`` is a ``BuildingRecord``-like object (duck-typed on the
    attributes below). ``exposure`` is the mapping returned by
    ``period_exposure`` plus the building's current emissions in tons and the
    City's compliance status. ``scenario`` holds the chosen slider values and
    the recomputed scenario results.

    Satisfies: R5.1.
    """
    exposure_by_period = [
        {
            "period": period,
            "limit_tons": values.get("limit_tons"),
            "excess_tons": values.get("excess_tons"),
            "acp_usd_per_year": values.get("acp_usd"),
        }
        for period, values in exposure.get("by_period", {}).items()
    ]

    payload: dict[str, Any] = {
        "building": {
            "address": getattr(building, "address", None),
            "berdo_use": getattr(building, "berdo_use", None),
            "floor_area_sqft": getattr(building, "floor_area_sqft", None),
            "first_compliance_year": getattr(building, "first_compliance_year", None),
        },
        "today": {
            "emissions_tons": exposure.get("emissions_tons"),
            "city_status": getattr(building, "compliance_status", None),
        },
        "exposure_by_period": exposure_by_period,
        "scenario": {
            "heat_pump_fraction": scenario.get("heat_pump_fraction"),
            "efficiency_pct": scenario.get("efficiency_pct"),
            "new_emissions_tons": scenario.get("new_emissions_tons"),
            "new_acp_2030_usd_per_year": scenario.get("new_acp_2030_usd_per_year"),
        },
        "assumptions": scenario.get(
            "assumptions",
            [
                f"Boiler efficiency {_BOILER_EFFICIENCY_DEFAULT}",
                f"Heat-pump COP {_COP_DEFAULT}",
                "Emissions held at today's level",
            ],
        ),
        "source": (
            "City of Boston BERDO 2026 disclosure (2025 data); "
            "limits from boston.gov"
        ),
    }
    return payload


def call_claude(
    payload: dict, model: str, api_key: str, timeout: float = CLAUDE_TIMEOUT_S
) -> dict:
    """Call the Claude API via tool use and return the parsed five-field memo.

    Forces a strict-JSON response containing exactly the five ``MEMO_FIELDS``
    by exposing a single tool whose ``input_schema`` requires those fields and
    setting ``tool_choice`` to that tool. Applies a ``timeout``-second limit
    (default 20 s). The API key is never passed to any logging call.

    Raises ``MemoError`` on API failure, timeout, a non-JSON response, JSON
    missing any required field, or a rate-limiting error.

    Satisfies: R5.2, R5.7, R5.8, R5.10, R5.11.
    """
    # Imported here so the module imports cleanly even if anthropic is absent
    # in an environment that only uses the templated fallback.
    import anthropic

    try:
        client = anthropic.Anthropic(api_key=api_key, timeout=timeout)
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            tools=[
                {
                    "name": _MEMO_TOOL_NAME,
                    "description": (
                        "Return the one-page board memo as structured JSON with "
                        "exactly the five required fields."
                    ),
                    "input_schema": _MEMO_TOOL_SCHEMA,
                }
            ],
            tool_choice={"type": "tool", "name": _MEMO_TOOL_NAME},
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Draft the board memo from this building's numbers. "
                        "Use only the values provided.\n\n"
                        + json.dumps(payload)
                    ),
                }
            ],
        )
    except anthropic.RateLimitError as exc:
        # Do not log the exception object verbatim; never log the api_key.
        logger.warning("Claude memo call rate-limited; using templated fallback.")
        raise MemoError("Claude API rate-limited") from exc
    except anthropic.APITimeoutError as exc:
        logger.warning("Claude memo call timed out; using templated fallback.")
        raise MemoError("Claude API timed out") from exc
    except anthropic.APIError as exc:
        logger.warning("Claude memo call failed; using templated fallback.")
        raise MemoError("Claude API call failed") from exc
    except Exception as exc:  # noqa: BLE001 - any client failure -> fallback
        logger.warning("Unexpected error during Claude memo call; using fallback.")
        raise MemoError("Unexpected Claude API error") from exc

    memo = _extract_tool_input(response)
    _require_fields(memo)
    return memo


def _extract_tool_input(response: Any) -> dict:
    """Pull the tool-use JSON input from a Claude response.

    Raises ``MemoError`` if no tool-use block is present or its input does not
    parse as a JSON object.
    """
    content = getattr(response, "content", None)
    if not content:
        raise MemoError("Claude response had no content")

    for block in content:
        if getattr(block, "type", None) == "tool_use":
            tool_input = getattr(block, "input", None)
            # The SDK returns tool input as a dict; tolerate a JSON string too.
            if isinstance(tool_input, str):
                try:
                    tool_input = json.loads(tool_input)
                except (ValueError, TypeError) as exc:
                    raise MemoError("Claude tool input was not valid JSON") from exc
            if not isinstance(tool_input, dict):
                raise MemoError("Claude tool input was not a JSON object")
            return tool_input

    raise MemoError("Claude response contained no tool_use block")


def _require_fields(memo: dict) -> None:
    """Raise ``MemoError`` if the memo is missing any of the five fields."""
    missing = [field for field in MEMO_FIELDS if field not in memo]
    if missing:
        raise MemoError(
            "Claude memo missing required fields: " + ", ".join(missing)
        )


def validate_memo_numbers(
    memo: dict, allowed_dollar_and_ton_values: set[float]
) -> bool:
    """True iff every dollar amount and tonnage in the memo is a known value.

    Extracts dollar amounts (numbers preceded by ``$``) and tonnages (numbers
    followed by ``tons``/``metric tons``) from the rendered memo text, and
    checks each against ``allowed_dollar_and_ton_values`` within display
    tolerance (dollars to the whole dollar, tons to 0.1 ton).

    Compliance-period years (2025, 2030, ...), the $234 ACP rate, and the
    scenario slider/assumption values (heat-pump fraction f, efficiency
    percentage p, boiler efficiency 0.85, COP 2.5) are always permitted, so a
    well-formed Claude memo is not rejected for citing them.

    Satisfies: R5.4, R5.5.
    """
    text = _render_memo_text(memo)

    allowed_dollars = {round(v) for v in allowed_dollar_and_ton_values}
    allowed_tons = set(allowed_dollar_and_ton_values)

    for dollar in _extract_dollar_amounts(text):
        if _is_always_allowed_dollar(dollar):
            continue
        if not any(abs(dollar - v) <= _DOLLAR_TOLERANCE for v in allowed_dollars):
            if not any(
                abs(dollar - v) <= _DOLLAR_TOLERANCE
                for v in allowed_dollar_and_ton_values
            ):
                return False

    for tons in _extract_tonnages(text):
        if _is_always_allowed_ton(tons):
            continue
        if not any(abs(tons - v) <= _TON_TOLERANCE for v in allowed_tons):
            return False

    return True


def _is_always_allowed_dollar(value: float) -> bool:
    """Structural dollar values permitted without a calculator match."""
    return abs(value - _ACP_RATE_USD_PER_TON) <= _DOLLAR_TOLERANCE


def _is_always_allowed_ton(value: float) -> bool:
    """Years and assumption scalars permitted as bare tonnage-position numbers."""
    # Compliance-period years (2025-2050) are structural, not tonnages.
    if 2025 <= value <= 2050 and float(value).is_integer():
        return True
    # Boiler efficiency and COP assumptions.
    if abs(value - _BOILER_EFFICIENCY_DEFAULT) <= _TON_TOLERANCE:
        return True
    if abs(value - _COP_DEFAULT) <= _TON_TOLERANCE:
        return True
    return False


def _render_memo_text(memo: dict) -> str:
    """Flatten the memo's field values (including list items) into one string."""
    parts: list[str] = []
    for field in MEMO_FIELDS:
        value = memo.get(field)
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            parts.extend(str(item) for item in value)
        else:
            parts.append(str(value))
    return "\n".join(parts)


# A dollar amount: "$" then a number with optional thousands separators/decimals.
_DOLLAR_RE = re.compile(r"\$\s*([0-9][0-9,]*(?:\.[0-9]+)?)")

# A tonnage: a number immediately before "ton"/"tons"/"metric ton(s)".
_TON_RE = re.compile(
    r"([0-9][0-9,]*(?:\.[0-9]+)?)\s*(?:metric\s+)?tons?\b",
    re.IGNORECASE,
)


def _extract_dollar_amounts(text: str) -> list[float]:
    """Return every dollar amount appearing in ``text``."""
    values: list[float] = []
    for match in _DOLLAR_RE.finditer(text):
        values.append(float(match.group(1).replace(",", "")))
    return values


def _extract_tonnages(text: str) -> list[float]:
    """Return every tonnage appearing in ``text``."""
    values: list[float] = []
    for match in _TON_RE.finditer(text):
        values.append(float(match.group(1).replace(",", "")))
    return values


def templated_memo(payload: dict) -> dict:
    """Return a deterministic five-field memo built from payload numbers.

    Used when a Claude secret is missing or any Claude call/validation fails.
    Notes the drafted memo was unavailable and that the result is an estimate,
    not a compliance determination. Excludes "in violation"/"will be fined" and
    any legal or financial advice. Every number comes from the payload, so the
    templated memo always passes ``validate_memo_numbers``.

    Satisfies: R5.5, R5.6, R5.8, R5.9.
    """
    building = payload.get("building", {})
    address = building.get("address") or "this building"

    by_period = payload.get("exposure_by_period", [])
    primary = _primary_period(by_period)

    scenario = payload.get("scenario", {})
    new_acp = scenario.get("new_acp_2030_usd_per_year")

    period_label = primary.get("period") if primary else None
    acp = primary.get("acp_usd_per_year") if primary else None
    excess = primary.get("excess_tons") if primary else None

    acp_text = _format_dollars(acp)
    new_acp_text = _format_dollars(new_acp)
    excess_text = _format_tons(excess)

    if period_label and acp is not None:
        headline = (
            f"Estimated Alternative Compliance Payment for {address} in "
            f"{period_label}: {acp_text} per year."
        )
    else:
        headline = (
            f"Estimated Alternative Compliance Payment for {address}: "
            "see the figures below."
        )

    exposure_summary_parts = [
        "An automatic draft of this memo was not available, so these numbers "
        "come straight from the calculator.",
    ]
    if period_label and acp is not None:
        exposure_summary_parts.append(
            f"For {period_label}, the building is an estimated {excess_text} "
            f"over its limit, for an estimated Alternative Compliance Payment "
            f"of about {acp_text} per year."
        )
    exposure_summary = " ".join(exposure_summary_parts)

    if new_acp is not None:
        recommendation = (
            "With the selected changes, the estimated Alternative Compliance "
            f"Payment for the 2030-2034 period is about {new_acp_text} per "
            "year. Compare that figure with the cost of the work before "
            "deciding."
        )
    else:
        recommendation = (
            "Review the retrofit options above and compare their estimated "
            "Alternative Compliance Payment savings with the cost of the work "
            "before deciding."
        )

    tradeoffs = [
        "These figures are an estimate, not a compliance determination.",
        "Retrofit work has upfront cost and can disrupt building operations.",
        "Portfolio and campus compliance, flexibility measures, and a cleaner "
        "electric grid can lower real exposure below this estimate.",
    ]

    next_steps = [
        "Review these estimated figures with the board.",
        "Get quotes for the retrofit options you are considering.",
        "Confirm the details with the City of Boston BERDO team for the "
        "official answer.",
    ]

    return {
        "headline": headline,
        "exposure_summary": exposure_summary,
        "recommendation": recommendation,
        "tradeoffs": tradeoffs,
        "next_steps": next_steps,
    }


def _primary_period(by_period: list[dict]) -> dict | None:
    """Return the 2030-2034 period entry if present, else the first entry."""
    if not by_period:
        return None
    for entry in by_period:
        if entry.get("period") == "2030-2034":
            return entry
    return by_period[0]


def _format_dollars(value: float | None) -> str:
    """Format a dollar amount to whole dollars for display, or a placeholder."""
    if value is None:
        return "an amount that is not known"
    return f"${round(value):,}"


def _format_tons(value: float | None) -> str:
    """Format a tonnage to one decimal for display, or a placeholder."""
    if value is None:
        return "an amount that is not known"
    return f"{value:.1f} tons"


def generate_memo(
    payload: dict, model: str | None, api_key: str | None
) -> dict:
    """Orchestrate memo generation with a templated fallback.

    If either the model identifier or the API key is missing or empty, skip the
    Claude call and return the templated memo. Otherwise call Claude; on any
    ``MemoError`` or number-validation failure, return the templated memo.

    Satisfies: R5.3, R5.5, R5.8, R5.9.
    """
    if not model or not api_key:
        return templated_memo(payload)

    try:
        memo = call_claude(payload, model, api_key)
    except MemoError:
        return templated_memo(payload)

    allowed = _allowed_values_from_payload(payload)
    if not validate_memo_numbers(memo, allowed):
        return templated_memo(payload)

    return memo


def _allowed_values_from_payload(payload: dict) -> set[float]:
    """Collect every calculator dollar amount and tonnage from the payload.

    These are the values a Claude-drafted memo is allowed to cite (R5.4): the
    per-period limits, excess tons, and ACP figures, plus today's and the
    scenario's emissions and ACP.
    """
    allowed: set[float] = set()

    today = payload.get("today", {})
    _add_value(allowed, today.get("emissions_tons"))

    for entry in payload.get("exposure_by_period", []):
        _add_value(allowed, entry.get("limit_tons"))
        _add_value(allowed, entry.get("excess_tons"))
        _add_value(allowed, entry.get("acp_usd_per_year"))

    scenario = payload.get("scenario", {})
    _add_value(allowed, scenario.get("new_emissions_tons"))
    _add_value(allowed, scenario.get("new_acp_2030_usd_per_year"))

    return allowed


def _add_value(target: set[float], value: Any) -> None:
    """Add a numeric value to the allowed set, ignoring None/non-numeric."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        target.add(float(value))
