"""Standard-library client for the CheckBeforeYouShop public JSON API."""

from .client import Client
from .errors import (
    Ambiguous, BadRequest, CBYSError, FixtureMissing, HTTPError, MixedUnitError,
    NetworkError, NotFound, Timeout,
)
from .models import (
    DirectoryPortal, Envelope, High, HighsData, Merchant, MerchantRate, PortalData,
    PortalProfile, PortalRate, PortalsData, Rate, SearchData, SearchResult, StoreData, Verdict,
)
from .rates import (
    Freshness, best_per_unit, compare_rates, filter_program, format_rate, freshness, group_by_unit,
)

__all__ = [
    "Ambiguous", "BadRequest", "CBYSError", "Client", "DirectoryPortal", "Envelope",
    "FixtureMissing", "Freshness", "HTTPError", "High", "HighsData", "Merchant",
    "MerchantRate", "MixedUnitError", "NetworkError", "NotFound", "PortalData", "PortalProfile",
    "PortalRate", "PortalsData", "Rate", "SearchData", "SearchResult", "StoreData", "Timeout",
    "Verdict", "best_per_unit", "compare_rates", "filter_program", "format_rate", "freshness",
    "group_by_unit",
]
