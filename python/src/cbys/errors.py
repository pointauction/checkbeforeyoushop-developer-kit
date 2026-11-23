"""Exceptions raised by the CBYS client and rate helpers."""

from __future__ import annotations

from .models import Envelope, JsonObject, SearchData, SearchResult


class CBYSError(Exception):
    """Base class for SDK errors."""


class HTTPError(CBYSError):
    def __init__(
        self,
        status: int,
        message: str,
        body: JsonObject | None = None,
        *,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.body = body
        self.retry_after_seconds = retry_after_seconds


class BadRequest(HTTPError):
    """The API rejected the request (HTTP 400)."""


class NotFound(HTTPError):
    def __init__(
        self,
        message: str,
        *,
        suggestions: tuple[SearchResult, ...] = (),
        body: JsonObject | None = None,
        response: Envelope[SearchData] | None = None,
    ):
        super().__init__(404, message, body)
        self.suggestions = suggestions
        self.response = response


class Ambiguous(CBYSError):
    def __init__(
        self,
        query: str,
        candidates: tuple[SearchResult, ...],
        response: Envelope[SearchData],
    ):
        super().__init__(f"Ambiguous store {query!r}. Use an exact store slug.")
        self.candidates = candidates
        self.response = response


class NetworkError(CBYSError):
    """The request or response could not be transported."""


class Timeout(NetworkError):
    """The connection or response timed out."""


class FixtureMissing(CBYSError):
    """An offline request could not be served from the fixture directory."""


class MixedUnitError(CBYSError, ValueError):
    """A comparison would mix rate units or kinds."""
