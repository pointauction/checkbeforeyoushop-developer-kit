import json
from email.message import Message
from io import BytesIO
from urllib.error import URLError
from urllib.request import BaseHandler
from urllib.response import addinfourl

import pytest
import yaml
from openapi_spec_validator import validate

import check_contract as checker

MERCHANT = "/api/v1/merchants/nike.json"
SEARCH = "/api/v1/search.json?q=delta"
DIRECTORY = "/api/v1/portals.json"
PORTAL = "/api/v1/portals/delta-skymiles.json"
HIGHS = "/api/v1/highs.json"
FIXTURES = checker.read_fixtures(checker.FIXTURES_DIR)


@pytest.fixture(scope="module")
def contract():
    return checker.Contract()


def fixture_payload(path):
    file = checker.FIXTURES_DIR / FIXTURES[path]["file"]
    return json.loads(file.read_text(encoding="utf-8"))


def test_openapi_spec_is_valid():
    validate(yaml.safe_load(checker.SPEC_PATH.read_text(encoding="utf-8")))


def test_invalid_spec_exits_with_contract_failure(tmp_path, monkeypatch):
    invalid = tmp_path / "openapi.yaml"
    invalid.write_text("openapi: 3.1.0\n", encoding="utf-8")
    contract_type = checker.Contract
    monkeypatch.setattr(checker, "Contract", lambda: contract_type(invalid))
    assert checker.main(["--offline"]) == 1


@pytest.mark.parametrize("path", FIXTURES)
def test_manifest_fixture_matches_response(contract, path):
    errors, _ = contract.validate_response(path, FIXTURES[path]["status"], fixture_payload(path))
    assert errors == []


@pytest.mark.parametrize("path", [SEARCH, MERCHANT, DIRECTORY, PORTAL, HIGHS])
def test_published_examples_are_valid(contract, path):
    _, response, _ = contract.response(path, 200)
    examples = response["content"]["application/json"]["examples"]
    for example in examples.values():
        assert contract.validate_response(path, 200, example["value"], strict=True) == ([], [])


def test_offline_cli_validates_the_whole_manifest_without_network(monkeypatch, capsys):
    monkeypatch.setenv("CBYS_FIXTURES_DIR", str(checker.FIXTURES_DIR))

    def unexpected_network(*args, **kwargs):
        pytest.fail("Offline validation attempted a network request")

    monkeypatch.setattr(checker, "build_opener", unexpected_network)
    assert checker.main(["--offline", "--strict"]) == 0
    output = capsys.readouterr().out
    assert output.count("PASS /api/v1/") == len(FIXTURES)
    assert f"{len(FIXTURES)} passed, 0 failed" in output


def test_missing_manifest_entry_file_fails_offline(tmp_path, monkeypatch, capsys):
    manifest = {"requests": {MERCHANT: {"status": 200, "file": "missing.json"}}}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setenv("CBYS_FIXTURES_DIR", str(tmp_path))
    assert checker.main(["--offline"]) == 1
    assert "missing.json" in capsys.readouterr().out


@pytest.mark.parametrize("path", [path for path, entry in FIXTURES.items() if entry["status"] >= 400])
def test_malformed_error_body_fails(contract, path):
    errors, _ = contract.validate_response(path, FIXTURES[path]["status"], {"error": 400})
    assert any("$.error" in error for error in errors)


@pytest.mark.parametrize(
    ("updates", "expected"),
    [
        ({"rate_unit": "unrecognized"}, "$.data.rates[0].rate_unit"),
        ({"rate_unit": "flat_cash", "rate_kind": "earn_rate"}, "expected one_time_bonus"),
        ({"rate_unit": "pct_cash", "rate_kind": "one_time_bonus"}, "expected earn_rate"),
        ({"go_url": "https://checkbeforeyoushop.com/m/nike?plc=api"}, "outbound /go/"),
        ({"go_url": "https://checkbeforeyoushop.com/go/rakuten?plc=widget"}, "plc=api"),
        ({"go_url": "https://checkbeforeyoushop.com/go/rakuten?plc=api&plc=widget"}, "plc=api"),
        ({"go_url": "https://other.example/go/rakuten?plc=api"}, "absolute HTTPS URL"),
        ({"last_confirmed_at": "2026-02-30T02:00:00Z"}, "$.data.rates[0].last_confirmed_at"),
        ({"last_confirmed_at": "2026-11-22T02:00:00"}, "$.data.rates[0].last_confirmed_at"),
    ],
)
def test_invalid_rate_row(contract, updates, expected):
    payload = fixture_payload(MERCHANT)
    assert contract.validate_response(MERCHANT, 200, payload) == ([], [])
    payload["data"]["rates"][0].update(updates)
    errors, _ = contract.validate_response(MERCHANT, 200, payload)
    assert any(expected in error for error in errors)


def test_valid_flat_and_gallon_units(contract):
    payload = fixture_payload(MERCHANT)
    row = payload["data"]["rates"][-1]
    row.update(rate_unit="flat_points", rate_kind="one_time_bonus", unit_group="Points")
    assert contract.validate_response(MERCHANT, 200, payload) == ([], [])
    row.update(rate_unit="cents_per_gallon", rate_kind="earn_rate", unit_group="Other")
    assert contract.validate_response(MERCHANT, 200, payload) == ([], [])


@pytest.mark.parametrize(
    ("path", "row", "url"),
    [
        (MERCHANT, lambda data: data["merchant"], "http://checkbeforeyoushop.com/m/nike"),
        (SEARCH, lambda data: data["results"][0], "https://checkbeforeyoushop.com.example/m/nike"),
        (DIRECTORY, lambda data: data["portals"][0], "https://checkbeforeyoushop.com@other.example/p/id"),
        (PORTAL, lambda data: data["top_rates"][0], "ftp://checkbeforeyoushop.com/m/nike"),
        (HIGHS, lambda data: data["highs"][0], "/m/nike"),
    ],
)
def test_invalid_page_url(contract, path, row, url):
    payload = fixture_payload(path)
    assert contract.validate_response(path, 200, payload) == ([], [])
    row(payload["data"])["page_url"] = url
    errors, _ = contract.validate_response(path, 200, payload)
    assert any(".page_url" in error for error in errors)


def test_leaders_are_unique_per_native_unit(contract):
    payload = fixture_payload(MERCHANT)
    assert contract.validate_response(MERCHANT, 200, payload) == ([], [])
    best = payload["data"]["best_rates"]
    best.append(best[0].copy())
    errors, _ = contract.validate_response(MERCHANT, 200, payload)
    assert any("duplicate leader" in error for error in errors)


def test_leader_matches_full_row_including_rate_qualifiers(contract):
    payload = fixture_payload(MERCHANT)
    assert contract.validate_response(MERCHANT, 200, payload) == ([], [])
    best = payload["data"]["best_rates"][0]
    best["is_up_to"] = not best["is_up_to"]
    errors, _ = contract.validate_response(MERCHANT, 200, payload)
    assert any("no matching entry in rates" in error for error in errors)


def test_listing_label_is_required_on_full_rows(contract):
    payload = fixture_payload(MERCHANT)
    assert contract.validate_response(MERCHANT, 200, payload) == ([], [])
    del payload["data"]["rates"][0]["listing_label"]
    errors, _ = contract.validate_response(MERCHANT, 200, payload)
    assert any("'listing_label' is a required property" in error for error in errors)


def test_merchant_can_return_no_lead_with_labelled_stale_rows(contract):
    payload = fixture_payload(MERCHANT)
    data = payload["data"]
    for row in data["rates"]:
        row["is_stale"] = True
    data["rates"][0]["listing_label"] = "Example listing name"
    data.update(summary=None, verdict=None, best_rates=[])
    assert contract.validate_response(MERCHANT, 200, payload, strict=True) == ([], [])


def test_strict_reports_extra_fields_as_warnings(contract):
    payload = fixture_payload(MERCHANT)
    payload["later"] = {"page_url": "off-schema"}
    payload["data"]["best_rates"][0]["future_leader_field"] = True
    payload["data"]["rates"][0]["later_rate_field"] = 1
    assert contract.validate_response(MERCHANT, 200, payload) == ([], [])
    errors, warnings = contract.validate_response(MERCHANT, 200, payload, strict=True)
    assert errors == []
    assert warnings == [
        "$.data.best_rates[0].future_leader_field: undocumented field",
        "$.data.rates[0].later_rate_field: undocumented field",
        "$.later: undocumented field",
    ]


def test_valid_suggestions_and_invalid_aggregate_flag(contract):
    payload = fixture_payload(SEARCH)
    data = payload["data"]
    data["results"][0]["did_you_mean"] = True
    data["did_you_mean"] = True
    assert contract.validate_response(SEARCH, 200, payload) == ([], [])
    data["did_you_mean"] = False
    errors, _ = contract.validate_response(SEARCH, 200, payload)
    assert any("$.data.did_you_mean" in error for error in errors)


def test_search_rejects_more_than_25_results(contract):
    path = "/api/v1/search.json?q=american"
    payload = fixture_payload(path)
    assert contract.validate_response(path, 200, payload) == ([], [])
    payload["data"]["results"].append(payload["data"]["results"][0].copy())
    errors, _ = contract.validate_response(path, 200, payload)
    assert any("$.data.results" in error for error in errors)


def headers_for(status):
    headers = Message()
    headers["Access-Control-Allow-Origin"] = "*"
    headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    headers["Access-Control-Allow-Headers"] = "*"
    headers["Content-Type"] = "application/json; charset=utf-8"
    headers["Cache-Control"] = "public, max-age=300" if status == 200 else "no-store"
    return headers


@pytest.mark.parametrize("status", [200, 400, 404])
def test_live_application_headers(status):
    headers = headers_for(status)
    assert list(checker.header_issues(status, headers)) == []
    del headers["Access-Control-Allow-Origin"]
    headers.replace_header("Cache-Control", "private")
    errors = list(checker.header_issues(status, headers))
    assert any("Access-Control-Allow-Origin" in error for error in errors)
    assert any("Cache-Control" in error for error in errors)


@pytest.mark.parametrize(("mode", "exit_code"), [("pass", 0), ("invalid", 1), ("unavailable", 2)])
def test_live_check_is_bounded_and_serial(contract, monkeypatch, mode, exit_code):
    calls = []

    def fake_fetch(opener, path):
        calls.append(path)
        if path.endswith("?q=nikke"):
            if mode == "unavailable":
                raise URLError("test connection failure")
            fixture_path = SEARCH
        else:
            fixture_path = path
        status = FIXTURES[fixture_path]["status"]
        payload = fixture_payload(fixture_path)
        if mode == "invalid" and path == MERCHANT:
            del payload["source"]
        return status, headers_for(status), json.dumps(payload).encode()

    monkeypatch.setattr(checker, "fetch", fake_fetch)
    monkeypatch.setattr(checker.time, "sleep", lambda seconds: calls.append(seconds))
    assert checker.check_live(contract, strict=True) == exit_code
    assert 0 < len(checker.LIVE_SAMPLES) <= 8
    assert calls[::2] == [path for path, _ in checker.LIVE_SAMPLES]
    assert calls[1::2] == [checker.LIVE_DELAY] * (len(checker.LIVE_SAMPLES) - 1)
    assert checker.LIVE_DELAY >= 1.5


def test_live_fetch_refuses_a_redirect_without_a_second_request():
    class RedirectingTransport(BaseHandler):
        handler_order = 0

        def __init__(self):
            self.urls = []

        def https_open(self, request):
            self.urls.append(request.full_url)
            headers = Message()
            headers["Location"] = checker.BASE + "/go/rakuten?plc=api"
            response = addinfourl(BytesIO(), headers, request.full_url, code=302)
            response.msg = "Found"
            return response

    transport = RedirectingTransport()
    opener = checker.build_opener(transport, checker.NoRedirect())
    status, _, _ = checker.fetch(opener, MERCHANT)
    assert status == 302
    assert transport.urls == [checker.BASE + MERCHANT]
