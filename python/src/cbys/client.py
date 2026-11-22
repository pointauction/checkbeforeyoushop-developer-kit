"""Read-only client for the public CheckBeforeYouShop API."""

from __future__ import annotations

from datetime import datetime, timezone
from email.message import Message
from email.utils import parsedate_to_datetime
from http.client import HTTPException
import json
import os
from pathlib import Path
import re
import time
from typing import IO, Callable, TypeVar
from urllib.error import HTTPError as UrllibHTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .errors import Ambiguous, BadRequest, FixtureMissing, HTTPError, NetworkError, NotFound, Timeout
from .models import (
    Envelope, HighsData, JsonObject, PortalData, PortalsData, SearchData, SearchResult,
    StoreData, _Model, _envelope,
)

BASE_URL = "https://checkbeforeyoushop.com"
USER_AGENT = "cbys-developer-kit-python/0.1"
_DataT = TypeVar("_DataT", bound=_Model)
_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


class _NoRedirects(HTTPRedirectHandler):
    """Keep requests on the API endpoint, including when it returns a redirect."""

    def redirect_request(
        self, req: Request, fp: IO[bytes], code: int, msg: str,
        headers: Message, newurl: str,
    ) -> None:
        return None


_open = build_opener(_NoRedirects()).open


class Client:
    """Read the API over HTTP or from a directory containing manifest.json."""

    def __init__(
        self,
        base_url: str = BASE_URL,
        timeout: float = 10,
        retries: int = 2,
        user_agent: str = USER_AGENT,
        fixtures_dir: str | os.PathLike[str] | None = None,
    ) -> None:
        parts = urlsplit(base_url)
        if (
            parts.scheme not in {"http", "https"} or not parts.hostname
            or parts.username is not None or parts.password is not None
            or parts.path not in {"", "/"} or parts.query or parts.fragment
        ):
            raise ValueError("base_url must be an HTTP or HTTPS origin")
        if retries < 0:
            raise ValueError("retries must be zero or greater")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = retries
        self.user_agent = user_agent
        fixture_path = fixtures_dir if fixtures_dir is not None else os.getenv("CBYS_FIXTURES_DIR")
        self.fixtures_dir = Path(fixture_path) if fixture_path is not None else None
        self._fixtures: JsonObject | None = None

    def search(self, query: str) -> Envelope[SearchData]:
        path = "/api/v1/search.json"
        normalized = query.strip()
        return self._get(
            path + "?" + urlencode({"q": normalized}),
            SearchData._decode,
            fixture_key=f"{path}?q={normalized.lower()}",
        )

    def get_store(self, slug: str) -> Envelope[StoreData]:
        return self._get(_store_path(slug), StoreData._decode)

    def list_portals(self) -> Envelope[PortalsData]:
        return self._get("/api/v1/portals.json", PortalsData._decode)

    def get_portal(self, portal_id: str) -> Envelope[PortalData]:
        return self._get(f"/api/v1/portals/{quote(portal_id, safe='')}.json", PortalData._decode)

    def get_highs(self) -> Envelope[HighsData]:
        return self._get("/api/v1/highs.json", HighsData._decode)

    def resolve_store(self, query: str) -> SearchResult:
        """Resolve an exact slug, name, or domain, or report candidates."""
        match, _ = self._resolve_store(query)
        return match

    def _resolve_store(self, query: str) -> tuple[SearchResult, Envelope[StoreData] | None]:
        identity = query.strip()
        slug = identity.lower()
        # The search endpoint need not return an exact slug. In fixture mode it
        # may also have no search capture for a slug whose detail was recorded.
        if len(slug) >= 2 and _SLUG.fullmatch(slug):
            if self.fixtures_dir is None or _store_path(slug) in self._manifest():
                try:
                    store = self.get_store(slug)
                except NotFound:
                    pass
                else:
                    merchant = store.data.merchant
                    return SearchResult(
                        kind="merchant", slug=merchant.slug, name=merchant.name,
                        domain=merchant.domain, page_url=merchant.page_url,
                    ), store

        response = self.search(identity)
        merchants = tuple(row for row in response.data.results if row.kind == "merchant")
        folded = identity.casefold()
        for attr in ("slug", "name", "domain"):
            exact = tuple(
                row for row in merchants if (getattr(row, attr) or "").casefold() == folded
            )
            if len(exact) == 1:
                return exact[0], None
            if exact:
                raise Ambiguous(query, exact, response)

        candidates = tuple(row for row in merchants if not row.did_you_mean)
        if len(candidates) > 1:
            raise Ambiguous(query, candidates, response)
        raise NotFound(
            f"No exact tracked store found for {query!r}.",
            suggestions=merchants,
            response=response,
        )

    def _get(
        self,
        path: str,
        decode: Callable[[JsonObject], _DataT],
        *,
        fixture_key: str | None = None,
    ) -> Envelope[_DataT]:
        if self.fixtures_dir is None:
            status, content = self._request(path)
        else:
            status, content = self._fixture(self.fixtures_dir, fixture_key or path)
        payload = _json_object(content)
        if not 200 <= status < 300:
            raise _http_error(status, payload)
        if payload is None:
            raise HTTPError(status, "API returned an invalid JSON object")
        try:
            return _envelope(payload, decode)
        except (KeyError, TypeError, AttributeError) as exc:
            raise HTTPError(status, f"API returned an invalid response for {path}") from exc

    def _manifest(self) -> JsonObject:
        if self._fixtures is None:
            assert self.fixtures_dir is not None
            try:
                manifest = json.loads((self.fixtures_dir / "manifest.json").read_bytes())
                requests = manifest["requests"]
                if not isinstance(requests, dict):
                    raise TypeError("requests must be an object")
            except (OSError, ValueError, TypeError, KeyError) as exc:
                raise FixtureMissing(f"Cannot read manifest.json in fixtures {self.fixtures_dir}") from exc
            self._fixtures = requests
        return self._fixtures

    def _fixture(self, directory: Path, key: str) -> tuple[int, bytes]:
        try:
            entry = self._manifest()[key]
        except KeyError as exc:
            raise FixtureMissing(f"{key} is not in fixtures {directory}") from exc
        try:
            path = (directory / entry["file"]).resolve()
            if not path.is_relative_to(directory.resolve()):
                raise ValueError("fixture file is outside the fixture directory")
            return int(entry["status"]), path.read_bytes()
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise FixtureMissing(f"Cannot read fixture for {key} in {directory}") from exc

    def _request(self, path: str) -> tuple[int, bytes]:
        request = Request(
            self.base_url + path, method="GET",
            headers={"Accept": "application/json", "User-Agent": self.user_agent},
        )
        for attempt in range(self.retries + 1):
            try:
                status, content, retry_after = _send(request, self.timeout)
            except (URLError, OSError, HTTPException) as exc:
                if attempt == self.retries:
                    reason = exc.reason if isinstance(exc, URLError) else exc
                    if isinstance(reason, TimeoutError):
                        raise Timeout(f"Request timed out for {path}") from exc
                    raise NetworkError(f"Network error for {path}: {reason}") from exc
                retry_after = None
            else:
                if attempt == self.retries or not (status == 429 or 500 <= status < 600):
                    return status, content
            delay = _retry_after_seconds(retry_after)
            time.sleep(delay if delay is not None else 1.5 * 2 ** attempt)
        raise AssertionError("HTTP retry loop exhausted")


def _store_path(slug: str) -> str:
    return f"/api/v1/merchants/{quote(slug, safe='')}.json"


def _send(request: Request, timeout: float) -> tuple[int, bytes, str | None]:
    try:
        response = _open(request, timeout=timeout)
    except UrllibHTTPError as exc:
        with exc:
            return exc.code, exc.read(), exc.headers.get("Retry-After") if exc.headers else None
    with response:
        return response.status, response.read(), response.headers.get("Retry-After")


def _retry_after_seconds(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(max(0, int(value)))
    except (ValueError, OverflowError):
        pass
    try:
        date = parsedate_to_datetime(value)
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        return max(0.0, (date - datetime.now(timezone.utc)).total_seconds())
    except (ValueError, TypeError, OverflowError):
        return None


def _json_object(content: bytes) -> JsonObject | None:
    try:
        payload = json.loads(content)
    except (ValueError, UnicodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _http_error(status: int, payload: JsonObject | None) -> HTTPError:
    detail = payload.get("error") if payload is not None else None
    message = detail if isinstance(detail, str) else f"HTTP {status} from CheckBeforeYouShop"
    if status == 404:
        return NotFound(message, body=payload)
    if status == 400:
        return BadRequest(status, message, payload)
    return HTTPError(status, message, payload)
