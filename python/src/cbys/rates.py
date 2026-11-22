"""Native-unit comparisons and display helpers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import re
from typing import TypeVar

from .errors import MixedUnitError
from .models import High, MerchantRate, Rate

_RateT = TypeVar("_RateT", bound=Rate)
_ProgramRateT = TypeVar("_ProgramRateT", MerchantRate, High)
_PROGRAM_ALIASES = {"delta": "delta skymiles"}

_UNIT_MARKERS = {
    "pct_cash": re.compile(r"%"),
    "miles_per_dollar": re.compile(r"\b(?:mi/\$|miles? per \$)", re.I),
    "points_per_dollar": re.compile(r"\b(?:pts?/\$|points? per \$)", re.I),
    "cents_per_gallon": re.compile(r"¢/gal"),
    "flat_cash": re.compile(r"\$"),
    "flat_miles": re.compile(r"\bmiles?\b", re.I),
    "flat_points": re.compile(r"\b(?:pts?|points?)\b", re.I),
}


@dataclass(frozen=True)
class Freshness:
    is_stale: bool | None
    last_confirmed_at: str | None


def freshness(rate: Rate) -> Freshness:
    """Return the row's stale flag and confirmation time, when supplied."""
    return Freshness(rate.is_stale, rate.last_confirmed_at)


def group_by_unit(rates: Iterable[_RateT]) -> dict[str, list[_RateT]]:
    """Group rows in first-appearance order without ranking them."""
    groups: dict[str, list[_RateT]] = {}
    for rate in rates:
        groups.setdefault(rate.rate_unit, []).append(rate)
    return groups


def _rank_key(rate: Rate) -> tuple[int, int | float, int]:
    # Fresh, then unspecified, then stale. At equal values, prefer an
    # explicitly fixed rate to an unknown qualifier or an up-to rate.
    stale = {False: 0, None: 1, True: 2}[rate.is_stale]
    ceiling = {False: 0, None: 1, True: 2}[rate.is_up_to]
    return stale, -rate.rate_value, ceiling


def _ranked(rates: Iterable[_RateT]) -> list[_RateT]:
    rows = list(rates)
    if len({(row.rate_unit, row.rate_kind) for row in rows}) > 1:
        raise MixedUnitError("Rank one rate unit and kind at a time.")
    return sorted(rows, key=_rank_key)


def compare_rates(left: Rate, right: Rate) -> int:
    """Return -1 if left ranks first, +1 if right ranks first, or 0 for a tie."""
    if left.rate_unit != right.rate_unit or left.rate_kind != right.rate_kind:
        raise MixedUnitError("Compare one rate unit and kind at a time.")
    left_key, right_key = _rank_key(left), _rank_key(right)
    return (left_key > right_key) - (left_key < right_key)


def best_per_unit(rates: Iterable[_RateT]) -> dict[str, _RateT]:
    """Return each unit's leader. Pass a single kind per unit."""
    return {unit: _ranked(group)[0] for unit, group in group_by_unit(rates).items()}


def filter_program(rates: Iterable[_ProgramRateT], program: str) -> list[_ProgramRateT]:
    """Match an exact program name, case-insensitively, or a known alias."""
    requested = program.strip().casefold()
    requested = _PROGRAM_ALIASES.get(requested, requested)
    return [rate for rate in rates if rate.program.casefold() == requested]


def format_rate(rate: Rate) -> str:
    """Format the native-unit display with its bonus, ceiling, and stale qualifiers."""
    display = rate.rate_display
    marker = _UNIT_MARKERS.get(rate.rate_unit)
    if marker is None or not marker.search(display):
        display = f"{display} {rate.rate_unit}"
    if rate.is_up_to and not display.casefold().startswith("up to "):
        display = f"up to {display}"
    if rate.is_up_to is None and not display.casefold().startswith("up to "):
        display += " (up-to status unavailable)"
    if rate.rate_kind == "one_time_bonus":
        display += " (one-time bonus)"
    if rate.is_stale:
        display += " [STALE]"
    return display
