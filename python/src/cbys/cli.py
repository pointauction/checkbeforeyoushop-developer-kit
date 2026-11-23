"""Command-line access to the CheckBeforeYouShop public JSON API."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterable, Sequence
from itertools import islice, zip_longest
import json
import sys
from typing import Any, NoReturn, TextIO, TypeVar
from urllib.parse import urlencode

from .client import BASE_URL, Client
from .errors import Ambiguous, CBYSError, NetworkError, NotFound
from .models import (
    Envelope, High, HighsData, MerchantRate, PortalData, PortalRate, PortalsData,
    Rate, SearchData, SearchResult, StoreData,
)
from .rates import _ranked, filter_program, format_rate, freshness, group_by_unit

_RateT = TypeVar("_RateT", bound=Rate)
_Response = Envelope[StoreData | SearchData | PortalsData | PortalData | HighsData]

_FALLBACK_ATTRIBUTION = (
    "Data from CheckBeforeYouShop (checkbeforeyoushop.com), free to use with attribution "
    "and a link to each item's page_url."
)
_FALLBACK_DISCLOSURE = (
    "Rates are read from each portal's pages and can change or go stale, so always confirm "
    "on the portal before shopping. Some portal links may earn us a referral bonus. "
    "That never changes the rates or their order."
)

_HEADINGS = {
    "pct_cash": "Cash back (%)",
    "miles_per_dollar": "Airline miles per $",
    "points_per_dollar": "Points per $",
    "cents_per_gallon": "Cents per gallon",
    "flat_cash": "One-time bonus - cash",
    "flat_miles": "One-time bonus - airline miles",
    "flat_points": "One-time bonus - points",
}
_FLAT_UNITS = {"flat_cash", "flat_miles", "flat_points"}


class _ArgumentParser(argparse.ArgumentParser):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(allow_abbrev=False, **kwargs)

    def error(self, message: str) -> NoReturn:
        try:
            super().error(message)
        finally:
            _footer(None, BASE_URL, file=sys.stderr)


def _nonnegative(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("limit must be zero or greater")
    return number


def _parser() -> argparse.ArgumentParser:
    shared = _ArgumentParser(add_help=False)
    shared.add_argument("--fixtures", metavar="DIR", default=argparse.SUPPRESS,
                        help="read responses from a local fixture directory")
    shared.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                        help="print the raw API envelope")
    parser = _ArgumentParser(
        prog="cbys", description="CheckBeforeYouShop shopping portal rates", parents=[shared],
    )
    commands = parser.add_subparsers(dest="command", required=True)

    search = commands.add_parser("search", parents=[shared], help="find stores or portals")
    search.add_argument("query", metavar="Q")

    store = commands.add_parser("store", parents=[shared], help="show a store's tracked rates")
    store.add_argument("query", metavar="NAME_OR_SLUG")
    store.add_argument("--program", metavar="P")
    store.add_argument("--unit", choices=tuple(_HEADINGS))
    stale = store.add_mutually_exclusive_group()
    stale.add_argument("--include-stale", dest="include_stale", action="store_true")
    stale.add_argument("--hide-stale", dest="include_stale", action="store_false")
    store.set_defaults(include_stale=True)

    commands.add_parser("portals", parents=[shared], help="list tracked portals")
    portal = commands.add_parser("portal", parents=[shared], help="show a portal's tracked rates")
    portal.add_argument("portal_id", metavar="ID")

    highs = commands.add_parser("highs", parents=[shared], help="show rates near observed highs")
    highs.add_argument("--unit", choices=tuple(_HEADINGS))
    highs.add_argument("--kind", choices=["earn_rate", "one_time_bonus"])
    highs.add_argument("--limit", type=_nonnegative, metavar="N",
                       help="cap human output at N rows, taking turns among groups")
    return parser


def _footer(
    response: _Response | None, page_url: str, *, file: TextIO | None = None,
) -> None:
    attribution = response.attribution if response is not None else _FALLBACK_ATTRIBUTION
    disclosure = response.disclosure if response is not None else _FALLBACK_DISCLOSURE
    print(f"{attribution} {page_url}", file=file)
    print(disclosure, file=file)


def _as_of(response: _Response) -> None:
    if response.data_as_of:
        print(f"Data as of {response.data_as_of}")


def _search_page(query: str) -> str:
    return f"{BASE_URL}/search?" + urlencode({"q": query})


def _search_row(row: SearchResult, *, file: TextIO | None = None) -> None:
    suggestion = " (suggested)" if row.did_you_mean else ""
    print(f"- {row.name} ({row.kind}, {row.slug}){suggestion} | {row.page_url}", file=file)


def _heading(unit: str, kind: str) -> str:
    heading = _HEADINGS.get(unit, unit)
    if kind == "one_time_bonus" and unit not in _FLAT_UNITS:
        return f"One-time bonus - {heading}"
    if kind != "one_time_bonus" and (unit in _FLAT_UNITS or kind != "earn_rate"):
        return f"{unit} ({kind})"
    return heading


def _print_rates(
    rates: Iterable[_RateT],
    describe: Callable[[_RateT], str],
    *,
    limit: int | None = None,
) -> None:
    groups: list[tuple[str, list[_RateT]]] = []
    for unit, rows in group_by_unit(rates).items():
        kinds: dict[str, list[_RateT]] = {}
        for row in rows:
            kinds.setdefault(row.rate_kind, []).append(row)
        groups.extend((_heading(unit, kind), _ranked(group)) for kind, group in kinds.items())
    if limit is not None:
        # Allocate the total row limit across groups without comparing their rates.
        counts = [0] * len(groups)
        slots = (
            index
            for batch in zip_longest(*(rows for _, rows in groups))
            for index, row in enumerate(batch)
            if row is not None
        )
        available = sum(len(rows) for _, rows in groups)
        for index in islice(slots, min(limit, available)):
            counts[index] += 1
        groups = [(label, rows[:count]) for (label, rows), count in zip(groups, counts) if count]
    if not groups:
        print("No tracked rate rows match this selection.")
    for label, rows in groups:
        print(label)
        for row in rows:
            print(describe(row))


def _rate_and_freshness(row: Rate) -> str:
    stamp = freshness(row)
    confirmation = f"confirmed {stamp.last_confirmed_at}" if stamp.last_confirmed_at else (
        "confirmation time unavailable"
    )
    stale = " | staleness unknown" if stamp.is_stale is None else ""
    return f"{format_rate(row)} | {confirmation}{stale}"


def _program_label(program: str, payout_kind: str | None) -> str:
    return f"{program} (gift card payout)" if payout_kind == "gift_card" else program


def _merchant_rate(row: MerchantRate) -> str:
    label = f" ({row.listing_label})" if row.listing_label else ""
    program = _program_label(row.program, row.payout_kind)
    outbound = f" | {row.go_url}" if row.go_url else ""
    return (
        f"- {row.portal_name}{label} / {program} | "
        f"{_rate_and_freshness(row)}{outbound}"
    )


def _portal_rate(row: PortalRate) -> str:
    return f"- {row.merchant_name} | {_rate_and_freshness(row)} | {row.page_url}"


def _high(row: High) -> str:
    program = _program_label(row.program, row.payout_kind)
    return (
        f"- {row.merchant_name} / {row.portal_name} / {program} | "
        f"{_rate_and_freshness(row)} | {row.page_url}"
    )


def _run(args: argparse.Namespace, client: Client) -> int:
    command = args.command
    response: _Response
    if command == "store":
        match, loaded_store = client._resolve_store(args.query)
        try:
            response = loaded_store if loaded_store is not None else client.get_store(match.slug)
        except NotFound:
            print(
                f"Search matched {match.name}, but its tracked listings are unavailable.",
                file=sys.stderr,
            )
            _footer(None, match.page_url, file=sys.stderr)
            return 5
    elif command == "search":
        response = client.search(args.query)
    elif command == "portals":
        response = client.list_portals()
    elif command == "portal":
        response = client.get_portal(args.portal_id)
    else:
        response = client.get_highs()
    if getattr(args, "json", False):
        print(json.dumps(response.raw, ensure_ascii=False, indent=2))
        return 0

    if client.fixtures_dir is not None:
        print("Recorded fixture data")
    _as_of(response)
    data = response.data

    if isinstance(data, StoreData):
        print(data.merchant.name)
        if data.verdict is not None:
            print(f"Store verdict · {data.verdict.headline.replace('—', ' - ')}")
            for caveat in data.verdict.caveats:
                print(caveat.replace("—", " - "))
        rows: Sequence[MerchantRate] = data.rates
        if args.program is not None:
            rows = filter_program(rows, args.program)
        rows = [row for row in rows if (args.unit is None or row.rate_unit == args.unit)
                and (args.include_stale or not row.is_stale)]
        _print_rates(rows, _merchant_rate)
        page_url = data.merchant.page_url
    elif isinstance(data, SearchData):
        if not data.results:
            print("No tracked results.")
        for result in data.results:
            _search_row(result)
        page_url = _search_page(args.query)
    elif isinstance(data, PortalsData):
        print(f"{data.active_count} active portals")
        for portal in data.portals:
            status = "" if portal.is_active else " (inactive)"
            program = _program_label(portal.program, portal.payout_kind)
            print(f"- {portal.name}{status} ({portal.portal_id}) / {program} | {portal.page_url}")
        page_url = f"{BASE_URL}/portals"
    elif isinstance(data, PortalData):
        profile = data.portal
        payout_kind = profile.payout_kind
        # The portal detail endpoint may omit Capital One Shopping's payout kind.
        if payout_kind is None and profile.portal_id == "capitalone-shopping":
            payout_kind = "gift_card"
        print(f"{profile.name} / {_program_label(profile.program, payout_kind)}")
        _print_rates(data.top_rates, _portal_rate)
        page_url = profile.page_url
    elif isinstance(data, HighsData):
        rates = [row for row in data.highs if (args.unit is None or row.rate_unit == args.unit)
                 and (args.kind is None or row.rate_kind == args.kind)]
        _print_rates(rates, _high, limit=args.limit)
        page_url = f"{BASE_URL}/highs"
    else:
        raise AssertionError("Unexpected response model")
    _footer(response, page_url)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    client = Client(fixtures_dir=getattr(args, "fixtures", None))
    try:
        return _run(args, client)
    except CBYSError as exc:
        print(exc, file=sys.stderr)
        if isinstance(exc, Ambiguous):
            for row in exc.candidates:
                _search_row(row, file=sys.stderr)
            _footer(exc.response, _search_page(args.query), file=sys.stderr)
            return 3
        if isinstance(exc, NotFound) and (exc.response is not None or args.command == "portal"):
            for row in exc.suggestions:
                _search_row(row, file=sys.stderr)
            page_url = _search_page(args.query) if exc.response is not None else BASE_URL
            _footer(exc.response, page_url, file=sys.stderr)
            return 4
        _footer(None, BASE_URL, file=sys.stderr)
        return 2 if isinstance(exc, NetworkError) else 1
