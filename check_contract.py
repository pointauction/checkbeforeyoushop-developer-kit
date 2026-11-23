#!/usr/bin/env python3
"""Validate the public API against OpenAPI using committed fixtures or a live sample."""

import argparse
import json
import os
import re
import time
from collections import defaultdict
from datetime import datetime
from http.client import HTTPException
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError
from openapi_spec_validator import validate
from openapi_spec_validator.exceptions import OpenAPISpecValidatorError
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

ROOT = Path(__file__).resolve().parent
SPEC_PATH = ROOT / "openapi.yaml"
FIXTURES_DIR = ROOT / "fixtures" / "live-2026-11-22"
SPEC_URI = "urn:checkbeforeyoushop:openapi"
BASE = "https://checkbeforeyoushop.com"
HOST = urlsplit(BASE).netloc
LIVE_DELAY = 1.5
LIVE_SAMPLES = (
    ("/api/v1/search.json?q=nikke", 200),
    ("/api/v1/merchants/nike.json", 200),
    ("/api/v1/portals.json", 200),
    ("/api/v1/portals/delta-skymiles.json", 200),
    ("/api/v1/highs.json", 200),
    ("/api/v1/search.json?q=a", 400),
    ("/api/v1/merchants/does-not-exist-zzq.json", 404),
    ("/api/v1/portals/does-not-exist-zzq.json", 404),
)
RATE_COLLECTIONS = {
    "merchant": ("best_rates", "rates"),
    "portal": ("top_rates",),
    "highs": ("highs",),
}
PAGE_LINKS = {
    "search": {"results": (None, "slug")},
    "merchant": {"merchant": ("m", "slug")},
    "portals": {"portals": ("p", "portal_id")},
    "portal": {"portal": ("p", "portal_id"), "top_rates": ("m", "merchant_slug")},
    "highs": {"highs": ("m", "merchant_slug")},
}


class Contract:
    def __init__(self, spec_path=SPEC_PATH):
        self.spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
        if not isinstance(self.spec, dict):
            raise ValueError("Expected an OpenAPI object")
        validate(self.spec)
        resource = Resource.from_contents(self.spec, default_specification=DRAFT202012)
        self.registry = Registry().with_resource(SPEC_URI, resource)
        self.formats = FormatChecker(formats=("date-time", "uri"))
        self.routes = []
        for path, item in self.spec["paths"].items():
            if "get" in item:
                pieces = re.split(r"(\{[^}]+\})", path)
                pattern = "".join(
                    "[^/]+" if i % 2 else re.escape(piece) for i, piece in enumerate(pieces)
                )
                pointer = path.replace("~", "~0").replace("/", "~1")
                self.routes.append((re.compile(pattern), item["get"], pointer))

    def response(self, request_path, status):
        path = urlsplit(request_path).path
        for pattern, operation, template_pointer in self.routes:
            if pattern.fullmatch(path):
                responses = operation["responses"]
                response = responses.get(str(status))
                if response is None:
                    raise ValueError(f"Undocumented status {status} for {path}")
                if "$ref" in response:
                    ref = response["$ref"]
                    response = self.resolve(ref)
                    pointer = ref.removeprefix("#")
                else:
                    pointer = f"/paths/{template_pointer}/get/responses/{status}"
                return operation["operationId"], response, pointer
        raise ValueError(f"No GET operation for {path}")

    def resolve(self, ref):
        return self.registry.resolver(SPEC_URI).lookup(ref).contents

    def schema_parts(self, schema):
        # Published object shapes use properties, local references, and allOf.
        # Combine them before checking extras so inherited fields are known.
        if "$ref" in schema:
            yield from self.schema_parts(self.resolve(schema["$ref"]))
        for part in schema.get("allOf", ()):
            yield from self.schema_parts(part)
        yield schema

    def properties(self, schemas):
        fields = defaultdict(list)
        for schema in schemas:
            for part in self.schema_parts(schema):
                for name, field in part.get("properties", {}).items():
                    fields[name].append(field)
        return fields

    def inspect_fields(self, value, schemas, location, errors, warnings, strict):
        if isinstance(value, dict):
            properties = self.properties(schemas)
            for name, child in value.items():
                field = f"{location}.{name}"
                if name not in properties:
                    if strict and properties:
                        warnings.append(f"{field}: undocumented field")
                    continue
                if name == "go_url" and isinstance(child, str):
                    issue = go_url_issue(child)
                    if issue:
                        errors.append(f"{field}: {issue}")
                self.inspect_fields(child, properties[name], field, errors, warnings, strict)
        elif isinstance(value, list):
            items = [
                part["items"]
                for schema in schemas
                for part in self.schema_parts(schema)
                if "items" in part
            ]
            for i, child in enumerate(value):
                self.inspect_fields(child, items, f"{location}[{i}]", errors, warnings, strict)
        elif strict and isinstance(value, str):
            for schema in schemas:
                for part in self.schema_parts(schema):
                    known = part.get("x-extensible-enum")
                    if known is not None and value not in known:
                        warnings.append(f"{location}: unknown display value {value!r}")
                        return

    def validate_response(self, request_path, status, payload, *, strict=False):
        operation, response, pointer = self.response(request_path, status)
        content = response.get("content", {}).get("application/json")
        if content is None:
            raise ValueError(f"No JSON schema for {request_path} with status {status}")

        # Escape the media type's slash as a JSON Pointer token.
        ref = f"{SPEC_URI}#{pointer}/content/application~1json/schema"
        validator = Draft202012Validator(
            {"$ref": ref}, registry=self.registry, format_checker=self.formats
        )
        errors = [
            f"{error.json_path}: {error.message}" for error in validator.iter_errors(payload)
        ]
        warnings = []
        if not errors and status == 200:
            errors.extend(self.data_issues(operation, payload))
        self.inspect_fields(payload, [content["schema"]], "$", errors, warnings, strict)
        return errors, warnings

    def data_issues(self, operation, payload):
        data = payload["data"]
        envelope_fields = self.spec["components"]["schemas"]["Envelope"]["properties"]
        for name in ("attribution", "disclosure"):
            minimum = envelope_fields[name]["minLength"]
            if len(payload[name].strip()) < minimum:
                yield f"$.{name}: expected at least {minimum} characters after trimming"

        for field, (prefix, identity) in PAGE_LINKS[operation].items():
            value = data[field]
            is_collection = isinstance(value, list)
            rows = value if is_collection else [value]
            for index, row in enumerate(rows):
                route = prefix or ("p" if row["kind"] == "portal" else "m")
                expected = f"{BASE}/{route}/{row[identity]}"
                if row["page_url"] != expected:
                    location = f"$.data.{field}" + (f"[{index}]" if is_collection else "")
                    yield f"{location}.page_url: expected {expected}"

        for collection in RATE_COLLECTIONS.get(operation, ()):
            for index, row in enumerate(data[collection]):
                expected_kind = (
                    "one_time_bonus" if row["rate_unit"].startswith("flat_") else "earn_rate"
                )
                if row["rate_kind"] != expected_kind:
                    yield f"$.data.{collection}[{index}].rate_kind: expected {expected_kind}"

        if operation == "merchant":
            newest = max(timestamp_key(row["last_confirmed_at"]) for row in data["rates"])
            if timestamp_key(payload["data_as_of"]) != newest:
                yield "$.data_as_of: must equal the newest rates[].last_confirmed_at"

            fields = self.properties([self.spec["components"]["schemas"]["BestRate"]])
            # Compare all shared, documented fields across the two projections.
            full_rows = {tuple(row[name] for name in fields) for row in data["rates"]}
            seen = set()
            for index, row in enumerate(data["best_rates"]):
                location = f"$.data.best_rates[{index}]"
                unit = row["rate_unit"]
                if unit in seen:
                    yield f"{location}.rate_unit: duplicate leader for {unit}"
                seen.add(unit)
                if tuple(row[name] for name in fields) not in full_rows:
                    yield f"{location}: no matching entry in rates"
            required_units = {
                row["rate_unit"]
                for row in data["rates"]
                if not row["is_stale"] and row["rate_value"] > 0
            }
            for unit in sorted(required_units - seen):
                yield f"$.data.best_rates: missing leader for fresh positive unit {unit}"

        if operation == "search":
            results = data["results"]
            if data["count"] != len(results):
                yield "$.data.count: must equal the number of results"
            if data["did_you_mean"] != any(row["did_you_mean"] for row in results):
                yield "$.data.did_you_mean: must indicate whether a returned result is a suggestion"

        if operation == "portals":
            portals = data["portals"]
            if data["count"] != len(portals):
                yield "$.data.count: must equal the number of portals"
            if data["active_count"] != sum(row["is_active"] for row in portals):
                yield "$.data.active_count: must equal the number of active portals"

        if operation == "highs":
            highs = data["highs"]
            if data["count"] != len(highs):
                yield "$.data.count: must equal the number of highs"
            seen_bonus = False
            for index, row in enumerate(highs):
                if row["rate_kind"] == "one_time_bonus":
                    seen_bonus = True
                elif seen_bonus:
                    yield f"$.data.highs[{index}].rate_kind: earn rates must precede one-time bonuses"
                    break


def timestamp_key(value):
    # The schema has already validated RFC 3339. Keep the fractional digits
    # separate so comparison works with offsets and precision beyond microseconds.
    value = value.upper().replace("Z", "+00:00")
    whole, offset = value[:-6], value[-6:]
    seconds, _, fraction = whole.partition(".")
    return datetime.fromisoformat(seconds + offset), fraction.rstrip("0")


def go_url_issue(value):
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.netloc.lower() != HOST:
        return "expected an absolute HTTPS URL on checkbeforeyoushop.com"
    if (
        not re.fullmatch(r"/go/[^/]+", parsed.path)
        or parse_qs(parsed.query, keep_blank_values=True).get("plc") != ["api"]
    ):
        return "expected an outbound /go/ URL with plc=api"
    return None


def read_fixtures(directory):
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    requests = manifest["requests"]
    if not isinstance(requests, dict) or not requests:
        raise ValueError("Expected a nonempty requests map in the fixture manifest")
    return requests


class NoRedirect(HTTPRedirectHandler):
    """Keep the sample on its explicit paths and never follow outbound links."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch(opener, path):
    request = Request(
        BASE + path,
        headers={"Accept": "application/json", "User-Agent": "cbys-developer-kit-contract/0.1"},
        method="GET",
    )
    try:
        response = opener.open(request, timeout=15)
    except HTTPError as error:
        response = error
    with response:
        return response.code, response.headers, response.read()


def header_issues(status, headers):
    expected = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "*",
    }
    for name, value in expected.items():
        if headers.get(name) != value:
            yield f"{name}: expected {value!r}"
    if headers.get_content_type() != "application/json":
        yield "Content-Type: expected application/json"
    cache = headers.get("Cache-Control", "")
    directives = {part.strip().lower() for part in cache.split(",")}
    if status == 200:
        if directives != {"no-store"} and not {"public", "max-age=300"} <= directives:
            yield f"Cache-Control: expected public, max-age=300 or no-store, received {cache!r}"
    elif directives != {"no-store"}:
        yield f"Cache-Control: expected no-store, received {cache!r}"


def report(path, errors, warnings=()):
    for warning in warnings:
        print(f"WARNING {path} {warning}")
    for error in errors:
        print(f"FAIL {path} {error}")
    if not errors:
        print(f"PASS {path}")


def check_offline(contract, directory, strict):
    try:
        fixtures = read_fixtures(directory)
    except (KeyError, OSError, TypeError, ValueError) as error:
        print(f"FAIL {directory / 'manifest.json'} {error}")
        return 1

    failed = 0
    for path, fixture in fixtures.items():
        try:
            payload = json.loads((directory / fixture["file"]).read_text(encoding="utf-8"))
            errors, warnings = contract.validate_response(
                path, fixture["status"], payload, strict=strict
            )
        except (KeyError, OSError, TypeError, ValueError) as error:
            errors, warnings = [str(error)], []
        report(path, errors, warnings)
        failed += bool(errors)

    print(f"Offline fixtures: {len(fixtures) - failed} passed, {failed} failed.")
    return int(failed > 0)


def check_live(contract, strict):
    opener = build_opener(NoRedirect())
    passed = failed = unavailable = 0
    for index, (path, expected_status) in enumerate(LIVE_SAMPLES):
        if index:
            time.sleep(LIVE_DELAY)
        try:
            status, headers, body = fetch(opener, path)
        except (URLError, OSError, HTTPException) as error:
            print(f"UNAVAILABLE {path} {error}")
            unavailable += 1
            continue
        if status == 429 or status >= 500:
            print(f"UNAVAILABLE {path} HTTP {status}")
            unavailable += 1
            continue

        warnings = []
        if status != expected_status:
            errors = [f"expected HTTP {expected_status}, received {status}"]
        else:
            errors = list(header_issues(status, headers))
            try:
                body_errors, warnings = contract.validate_response(
                    path, status, json.loads(body), strict=strict
                )
                errors.extend(body_errors)
            except (ValueError, UnicodeError) as error:
                errors.append(str(error))
        report(path, errors, warnings)
        failed += bool(errors)
        passed += not errors

    print(f"Live GETs: {passed} passed, {failed} failed, {unavailable} unavailable.")
    if failed:
        return 1
    return 2 if unavailable else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="validate every manifest fixture locally")
    parser.add_argument(
        "--strict", action="store_true", help="warn about undocumented fields and display values"
    )
    args = parser.parse_args(argv)

    try:
        contract = Contract()
    except (
        OSError,
        ValueError,
        yaml.YAMLError,
        ValidationError,
        OpenAPISpecValidatorError,
    ) as error:
        print(f"FAIL {SPEC_PATH} {error}")
        return 1
    print("OpenAPI spec: valid.")
    if args.offline:
        directory = Path(os.environ.get("CBYS_FIXTURES_DIR") or FIXTURES_DIR)
        return check_offline(contract, directory, args.strict)
    return check_live(contract, args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
