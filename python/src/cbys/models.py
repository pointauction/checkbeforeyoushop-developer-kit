"""Typed wire models for the CheckBeforeYouShop public API."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any, Callable, Generic, TypeVar

JsonObject = dict[str, Any]


@dataclass(frozen=True, kw_only=True)
class _Model:
    extra: JsonObject = field(default_factory=dict)


_ModelT = TypeVar("_ModelT", bound=_Model)
_DataT = TypeVar("_DataT", bound=_Model, covariant=True)


def _model(
    cls: type[_ModelT], payload: JsonObject, **decoded: Any
) -> _ModelT:
    names = {item.name for item in fields(cls)} - {"extra", *decoded}
    values = {key: value for key, value in payload.items() if key in names}
    extra = {
        key: value for key, value in payload.items()
        if key not in names and key not in decoded
    }
    return cls(**values, **decoded, extra=extra)


@dataclass(frozen=True, kw_only=True)
class Envelope(_Model, Generic[_DataT]):
    data: _DataT
    data_as_of: str | None
    source: str
    attribution: str
    disclosure: str
    raw: JsonObject = field(repr=False, compare=False)


def _envelope(
    payload: JsonObject, decode: Callable[[JsonObject], _DataT]
) -> Envelope[_DataT]:
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("Missing or invalid data")
    for field in ("attribution", "disclosure"):
        if not isinstance(payload.get(field), str):
            raise ValueError(f"Missing or invalid {field}")
    known = {"data", "data_as_of", "source", "attribution", "disclosure"}
    return Envelope(
        data=decode(data),
        data_as_of=payload["data_as_of"],
        source=payload["source"],
        attribution=payload["attribution"],
        disclosure=payload["disclosure"],
        raw=payload,
        extra={key: value for key, value in payload.items() if key not in known},
    )


@dataclass(frozen=True, kw_only=True)
class SearchResult(_Model):
    kind: str
    slug: str
    name: str
    domain: str | None
    page_url: str
    did_you_mean: bool = False


@dataclass(frozen=True, kw_only=True)
class SearchData(_Model):
    query: str
    count: int
    results: tuple[SearchResult, ...]
    did_you_mean: bool = False

    @classmethod
    def _decode(cls, payload: JsonObject) -> SearchData:
        return _model(
            cls, payload,
            results=tuple(_model(SearchResult, row) for row in payload["results"]),
        )


@dataclass(frozen=True, kw_only=True)
class Merchant(_Model):
    slug: str
    name: str
    domain: str | None
    page_url: str
    portals_tracked: int
    tracked_since: str | None


@dataclass(frozen=True, kw_only=True)
class Verdict(_Model):
    headline: str
    tone: str
    caveats: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class Rate(_Model):
    rate_value: int | float
    rate_unit: str
    rate_kind: str
    rate_display: str
    unit_group: str
    is_up_to: bool | None = None
    is_stale: bool | None = None
    last_confirmed_at: str | None = None


@dataclass(frozen=True, kw_only=True)
class MerchantRate(Rate):
    portal_id: str
    portal_name: str
    program: str
    payout_kind: str | None
    is_up_to: bool = field()
    best_category_value: int | float | None
    best_category_label: str | None
    is_elevated: bool
    is_stale: bool = field()
    last_confirmed_at: str = field()
    go_url: str | None
    listing_label: str | None = None


@dataclass(frozen=True, kw_only=True)
class StoreData(_Model):
    merchant: Merchant
    summary: str
    verdict: Verdict | None
    best_rates: tuple[MerchantRate, ...]
    rates: tuple[MerchantRate, ...]

    @property
    def summary_is_single_unit(self) -> bool:
        """Whether all store rates belong to one native unit and rate kind."""
        groups = {(row.rate_unit, row.rate_kind) for row in (*self.rates, *self.best_rates)}
        return bool(self.rates) and len(groups) == 1

    @classmethod
    def _decode(cls, payload: JsonObject) -> StoreData:
        merchant = payload.get("merchant")
        if not isinstance(merchant, dict):
            raise ValueError("Missing or invalid data.merchant")
        rates = payload.get("rates")
        if not isinstance(rates, list):
            raise ValueError("Missing or invalid data.rates")
        verdict = payload["verdict"]
        return _model(
            cls, payload,
            merchant=_model(Merchant, merchant),
            verdict=(
                _model(Verdict, verdict, caveats=tuple(verdict["caveats"]))
                if verdict is not None else None
            ),
            best_rates=tuple(_model(MerchantRate, row) for row in payload["best_rates"]),
            rates=tuple(_model(MerchantRate, row) for row in rates),
        )


@dataclass(frozen=True, kw_only=True)
class PortalProfile(_Model):
    portal_id: str
    name: str
    program: str
    category: str
    category_label: str
    merchants_tracked: int
    cadence_hours: int
    last_success_at: str | None
    page_url: str
    payout_kind: str | None = None


@dataclass(frozen=True, kw_only=True)
class DirectoryPortal(PortalProfile):
    is_active: bool


@dataclass(frozen=True, kw_only=True)
class PortalsData(_Model):
    count: int
    active_count: int
    portals: tuple[DirectoryPortal, ...]

    @classmethod
    def _decode(cls, payload: JsonObject) -> PortalsData:
        return _model(
            cls, payload,
            portals=tuple(_model(DirectoryPortal, row) for row in payload["portals"]),
        )


@dataclass(frozen=True, kw_only=True)
class PortalRate(Rate):
    merchant_slug: str
    merchant_name: str
    is_up_to: bool = field()
    is_elevated: bool
    is_stale: bool = field()
    page_url: str


@dataclass(frozen=True, kw_only=True)
class PortalData(_Model):
    portal: PortalProfile
    top_rates: tuple[PortalRate, ...]

    @classmethod
    def _decode(cls, payload: JsonObject) -> PortalData:
        return _model(
            cls, payload,
            portal=_model(PortalProfile, payload["portal"]),
            top_rates=tuple(_model(PortalRate, row) for row in payload["top_rates"]),
        )


@dataclass(frozen=True, kw_only=True)
class High(Rate):
    merchant_slug: str
    merchant_name: str
    portal_id: str
    portal_name: str
    program: str
    payout_kind: str | None
    is_all_time_high: bool
    typical_range: str | None
    page_url: str


@dataclass(frozen=True, kw_only=True)
class HighsData(_Model):
    count: int
    highs: tuple[High, ...]

    @classmethod
    def _decode(cls, payload: JsonObject) -> HighsData:
        return _model(
            cls, payload,
            highs=tuple(_model(High, row) for row in payload["highs"]),
        )
