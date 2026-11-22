import copy
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from email.message import Message
from email.utils import format_datetime
from http.client import IncompleteRead
from io import BytesIO, StringIO
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import call, patch
from urllib.error import HTTPError as UrllibHTTPError, URLError

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "python" / "src"
FIXTURES = ROOT / "fixtures" / "live-2026-11-22"
sys.path.insert(0, str(SOURCE))

from cbys import (
    Ambiguous, BadRequest, Client, FixtureMissing, HTTPError, MixedUnitError,
    NetworkError, NotFound, Timeout, best_per_unit, compare_rates, filter_program,
    format_rate, freshness, group_by_unit,
)
from cbys.cli import main


def read_fixture(file):
    return json.loads((FIXTURES / file).read_bytes())


class FixtureTests(unittest.TestCase):
    def setUp(self):
        self.client = Client(fixtures_dir=FIXTURES)
        network = patch("cbys.client._open", side_effect=AssertionError("fixtures used HTTP"))
        network.start()
        self.addCleanup(network.stop)

    def test_search_normalizes_manifest_key(self):
        result = self.client.search("  HoMe DePoT ")
        self.assertEqual(result.data.query, "home depot")
        self.assertEqual(result.data.count, 2)
        self.assertIsNone(result.data_as_of)

    def test_resolve_ambiguous_and_missing(self):
        for query, slugs in [
            ("american", {"american-tourister", "american-blinds"}),
            ("macys", {"macys-com", "macy-s-us"}),
        ]:
            with self.subTest(query=query), self.assertRaises(Ambiguous) as caught:
                self.client.resolve_store(query)
            self.assertTrue(slugs <= {row.slug for row in caught.exception.candidates})
            self.assertTrue(all(row.kind == "merchant" for row in caught.exception.candidates))
        with self.assertRaises(NotFound) as caught:
            self.client.resolve_store("zzqxnotastore")
        self.assertEqual(caught.exception.suggestions, ())

    def test_fixtures_precedence_and_missing_key(self):
        with patch.dict(os.environ, {"CBYS_FIXTURES_DIR": str(FIXTURES)}):
            self.assertEqual(Client().get_store("nike").data.merchant.name, "Nike")
            with TemporaryDirectory() as missing:
                with self.assertRaisesRegex(FixtureMissing, "manifest.json"):
                    Client(fixtures_dir=missing).get_store("nike")
        with self.assertRaisesRegex(FixtureMissing, "/api/v1/search.json.*not in fixtures"):
            self.client.search("no fixture captured for this")

    def test_errors_from_fixtures(self):
        with self.assertRaisesRegex(BadRequest, "at least 2 characters") as caught:
            self.client.search(" a ")
        self.assertEqual(caught.exception.status, 400)
        for method in (self.client.get_store, self.client.get_portal):
            with self.assertRaises(NotFound) as caught:
                method("does-not-exist-zzq")
            self.assertEqual(caught.exception.status, 404)

    def test_store_and_rate_models_keep_confirmations_and_links(self):
        result = self.client.get_store("nike")
        raw = read_fixture("merchants/nike.json")
        self.assertEqual(result.raw, raw)
        for key in ("data_as_of", "source", "attribution", "disclosure"):
            self.assertEqual(getattr(result, key), raw[key])
        self.assertEqual(result.data.merchant.page_url, raw["data"]["merchant"]["page_url"])
        row, original = result.data.rates[0], raw["data"]["rates"][0]
        for key, value in original.items():
            self.assertEqual(getattr(row, key), value)
        with self.assertRaises(FrozenInstanceError):
            row.is_stale = True

    def test_directory_portal_and_highs_models(self):
        directory = self.client.list_portals()
        self.assertEqual(directory.data.count, len(directory.data.portals))
        self.assertLessEqual(directory.data.active_count, directory.data.count)
        self.assertTrue(directory.data.portals[0].page_url)
        for portal_id in ("rakuten", "delta-skymiles"):
            portal = self.client.get_portal(portal_id)
            self.assertEqual(portal.data.portal.portal_id, portal_id)
            self.assertTrue(portal.data.top_rates[0].page_url)
        highs = self.client.get_highs()
        self.assertEqual(highs.data.count, len(highs.data.highs))
        self.assertTrue(highs.data.highs[0].page_url)
        self.assertIsNone(freshness(highs.data.highs[0]).is_stale)
        self.assertIsNone(freshness(highs.data.highs[0]).last_confirmed_at)

    def test_square_bonus_units_and_macys_ceilings(self):
        square = self.client.get_store("square").data.rates
        self.assertEqual({row.rate_kind for row in square}, {"one_time_bonus"})
        self.assertEqual(set(group_by_unit(square)), {"flat_cash", "flat_points", "flat_miles"})
        self.assertTrue(all("one-time bonus" in format_rate(row) for row in square))
        macys = self.client.get_store("macys-com").data.rates
        up_to = [row for row in macys if row.is_up_to]
        self.assertGreater(len(up_to), 1)
        self.assertTrue(all(format_rate(row).startswith("up to ") for row in up_to))

    def test_delta_and_unit_safe_ordering(self):
        rates = self.client.get_store("nike").data.rates
        delta, = filter_program(rates, " DELTA ")
        self.assertEqual(delta.program, "Delta SkyMiles")
        self.assertEqual(delta.rate_unit, "miles_per_dollar")
        cash = filter_program(rates, "cash")[0]
        same = replace(cash, is_up_to=False)
        ceiling = replace(same, is_up_to=True)
        stale = replace(
            same, rate_value=same.rate_value + 100, is_stale=True,
            last_confirmed_at="2026-10-01T00:00:00Z",
            extra={"_synthetic_note": "Higher stale value should come after fresh rows"},
        )
        self.assertEqual(freshness(stale).last_confirmed_at, "2026-10-01T00:00:00Z")
        self.assertIn("[STALE]", format_rate(stale))
        self.assertLess(compare_rates(same, ceiling), 0)
        self.assertLess(compare_rates(ceiling, stale), 0)
        self.assertLess(compare_rates(replace(ceiling, rate_value=10_000), same), 0)
        self.assertEqual(best_per_unit([stale, ceiling, delta, same]), {
            same.rate_unit: same, delta.rate_unit: delta,
        })
        with self.assertRaises(MixedUnitError):
            compare_rates(delta, cash)
        wrong_kind = replace(cash, rate_kind="one_time_bonus")
        with self.assertRaises(MixedUnitError):
            compare_rates(cash, wrong_kind)
        with self.assertRaises(MixedUnitError):
            best_per_unit([cash, wrong_kind])


class FakeResponse(BytesIO):
    def __init__(self, payload, status=200):
        super().__init__(json.dumps(payload).encode())
        self.status = status
        self.headers = Message()


def http_error(status, body, **headers):
    message = Message()
    for key, value in headers.items():
        message[key.replace("_", "-")] = value
    return UrllibHTTPError(
        "https://example.test/api/v1/search.json", status, "HTTP error",
        message, BytesIO(json.dumps(body).encode()),
    )


def search_payload(*rows):
    payload = read_fixture("search/zzqxnotastore.json")
    payload["data"]["results"] = list(rows)
    payload["data"]["count"] = len(rows)
    return payload


def merchant(slug, name, domain=None, *, suggestion=False):
    return {
        "kind": "merchant", "slug": slug, "name": name, "domain": domain,
        "page_url": f"https://example.test/m/{slug}", "did_you_mean": suggestion,
    }


class HTTPTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        os.environ.pop("CBYS_FIXTURES_DIR", None)
        self.client = Client(base_url="https://example.test/", timeout=3, user_agent="cbys-test")

    def test_retries_429_503_and_honors_retry_after(self):
        with (
            patch("cbys.client._open", side_effect=[
                http_error(429, {"error": "slow down"}, Retry_After="7"),
                http_error(503, {"error": "try again"}),
                FakeResponse(search_payload()),
            ]) as transport,
            patch("cbys.client.time.sleep") as sleep,
        ):
            self.assertEqual(self.client.search("A & B").data.count, 0)
        self.assertEqual(sleep.call_args_list, [call(7.0), call(3.0)])
        for sent in transport.call_args_list:
            request, = sent.args
            self.assertEqual(sent.kwargs["timeout"], 3)
            self.assertEqual(request.get_method(), "GET")
            self.assertEqual(request.full_url, "https://example.test/api/v1/search.json?q=A+%26+B")
            self.assertEqual(request.get_header("User-agent"), "cbys-test")

    def test_retry_after_http_date(self):
        now = datetime.now(timezone.utc).replace(microsecond=0)
        date = format_datetime(now + timedelta(seconds=30), usegmt=True)
        with (
            patch("cbys.client._open", side_effect=[
                http_error(503, {}, Retry_After=date), FakeResponse(search_payload()),
            ]),
            patch("cbys.client.datetime") as clock,
            patch("cbys.client.time.sleep") as sleep,
        ):
            clock.now.return_value = now
            self.client.search("zzqxnotastore")
            sleep.assert_called_once_with(30.0)

    def test_retry_network_and_response_read(self):
        failed_read = FakeResponse({})
        with (
            patch.object(failed_read, "read", side_effect=IncompleteRead(b"half", 4)),
            patch("cbys.client._open", side_effect=[
                URLError("disconnected"), failed_read, FakeResponse(search_payload()),
            ]) as transport,
            patch("cbys.client.time.sleep") as sleep,
        ):
            self.assertEqual(self.client.search("zzqxnotastore").data.count, 0)
        self.assertEqual(transport.call_count, 3)
        self.assertEqual(sleep.call_args_list, [call(1.5), call(3.0)])

    def test_timeout_exhaustion_and_cli_network_exit(self):
        with (
            patch("cbys.client._open", side_effect=URLError(TimeoutError())) as transport,
            patch("cbys.client.time.sleep"),
        ):
            with self.assertRaises(Timeout):
                self.client.search("nike")
            self.assertEqual(transport.call_count, 3)
            with patch("sys.stderr", new_callable=StringIO) as stderr:
                self.assertEqual(main(["search", "nike"]), 2)
            self.assertIn("timed out", stderr.getvalue())
            self.assertIn("Data from CheckBeforeYouShop", stderr.getvalue())
            self.assertIn("Some portal links may earn us a referral bonus", stderr.getvalue())

    def test_nonretryable_http_errors_and_network_exhaustion(self):
        for status, cls in [(400, BadRequest), (404, NotFound), (403, HTTPError)]:
            with self.subTest(status=status), (
                patch("cbys.client._open", side_effect=http_error(status, {"error": "details"}))
            ) as transport:
                with self.assertRaisesRegex(cls, "details") as caught:
                    self.client.search("nike")
                self.assertEqual(caught.exception.body, {"error": "details"})
                self.assertEqual(caught.exception.status, status)
                self.assertEqual(transport.call_count, 1)
        with (
            patch("cbys.client._open", side_effect=URLError("disconnected")) as transport,
            patch("cbys.client.time.sleep"),
        ):
            with self.assertRaisesRegex(NetworkError, "disconnected"):
                self.client.search("nike")
            self.assertEqual(transport.call_count, 3)

    def test_redirect_handler_rejects_outbound_click(self):
        from cbys.client import _NoRedirects
        from urllib.request import Request
        request = Request("https://example.test/api/v1/search.json?q=nike")
        self.assertIsNone(_NoRedirects().redirect_request(
            request, BytesIO(), 302, "Found", Message(), "https://example.test/go/portal",
        ))

    def test_resolution_precedence_and_no_single_fuzzy_pick(self):
        rows = (
            merchant("same", "Other"),
            merchant("name-match", "Same"),
            merchant("domain-match", "Another", "same"),
        )
        exact_detail_missing = http_error(404, {"error": "merchant not found"})
        with patch("cbys.client._open", side_effect=[
            exact_detail_missing, FakeResponse(search_payload(*rows)),
            http_error(404, {}), FakeResponse(search_payload(*rows[1:])),
            http_error(404, {}), FakeResponse(search_payload(rows[2])),
            FakeResponse(search_payload(merchant("other", "Other", suggestion=True))),
        ]):
            self.assertEqual(self.client.resolve_store("Same").slug, "same")
            self.assertEqual(self.client.resolve_store("Same").slug, "name-match")
            self.assertEqual(self.client.resolve_store("Same").slug, "domain-match")
            with self.assertRaises(NotFound) as caught:
                self.client.resolve_store("another store")
            self.assertEqual([row.slug for row in caught.exception.suggestions], ["other"])

    def test_keeps_extra_fields_at_every_store_level(self):
        payload = copy.deepcopy(read_fixture("merchants/nike.json"))
        payload["raw"] = {"wire": True}
        payload["data"]["nested_extension"] = {"version": 2}
        payload["data"]["merchant"]["additional_id"] = 7
        payload["data"]["rates"][0]["extra"] = "API extension named extra"
        payload["data"]["verdict"]["extended_caveat"] = "example"
        with patch("cbys.client._open", return_value=FakeResponse(payload)):
            response = self.client.get_store("nike")
        self.assertEqual(response.raw, payload)
        self.assertEqual(response.extra["raw"], {"wire": True})
        self.assertEqual(response.data.extra["nested_extension"], {"version": 2})
        self.assertEqual(response.data.merchant.extra["additional_id"], 7)
        self.assertEqual(response.data.rates[0].extra["extra"], "API extension named extra")
        self.assertEqual(response.data.verdict.extra["extended_caveat"], "example")


class CLITests(unittest.TestCase):
    def cli(self, *args, env_fixture=True):
        env = dict(os.environ, PYTHONPATH=str(SOURCE))
        env.pop("CBYS_FIXTURES_DIR", None)
        if env_fixture:
            env["CBYS_FIXTURES_DIR"] = str(FIXTURES)
        result = subprocess.run(
            [sys.executable, "-m", "cbys", *args], cwd=ROOT, env=env,
            capture_output=True, text=True, timeout=10,
        )
        return result

    def assert_attribution(self, output, page):
        attribution, disclosure = output.splitlines()[-2:]
        self.assertIn("Data from CheckBeforeYouShop", attribution)
        self.assertTrue(attribution.endswith(page))
        self.assertIn("Some portal links may earn us a referral bonus", disclosure)

    def test_store_headings_and_attribution(self):
        result = self.cli("store", "square")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Recorded fixture data", result.stdout)
        for label in ("cash", "points", "airline miles"):
            self.assertIn(f"One-time bonus - {label}\n", result.stdout)
        self.assertNotIn("best overall", result.stdout.lower())
        self.assert_attribution(result.stdout, "/m/square")

    def test_delta_and_cash_filters(self):
        result = self.cli("store", "Nike", "--program", "delta", "--unit", "miles_per_dollar")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Airline miles per $", result.stdout)
        self.assertIn("Delta SkyMiles", result.stdout)
        delta, = filter_program(Client(fixtures_dir=FIXTURES).get_store("nike").data.rates, "delta")
        self.assertIn(f"confirmed {delta.last_confirmed_at}", result.stdout)
        self.assertNotIn("Cash back (%)", result.stdout)
        result = self.cli("store", "nike", "--program", "cash", "--hide-stale")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Cash back (%)", result.stdout)

    def test_show_and_hide_stale(self):
        source = read_fixture("merchants/nike.json")
        row = dict(source["data"]["rates"][0])
        stale_row = dict(
            row, is_stale=True, rate_value=100, rate_display="100 pts/$",
            portal_name="Synthetic stale portal", last_confirmed_at="2026-10-01T00:00:00Z",
            _synthetic_note="Higher stale rate should sort last and respect --hide-stale",
        )
        source["data"]["rates"] = [stale_row, row]
        source["data"]["best_rates"] = []
        with TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "nike.json").write_text(json.dumps(source), encoding="utf-8")
            manifest = {"requests": {
                "/api/v1/merchants/nike.json": {"file": "nike.json", "status": 200},
            }}
            (path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            result = self.cli("--fixtures", directory, "store", "nike", "--include-stale")
            self.assertEqual(result.returncode, 0, result.stderr)
            lines = [line for line in result.stdout.splitlines() if line.startswith("- ")]
            self.assertIn(row["portal_name"], lines[0])
            self.assertIn("Synthetic stale portal", lines[-1])
            self.assertIn("[STALE]", lines[-1])
            self.assertIn(stale_row["last_confirmed_at"], lines[-1])
            hidden = self.cli("store", "nike", "--fixtures", directory, "--hide-stale")
            self.assertEqual(hidden.returncode, 0, hidden.stderr)
            self.assertNotIn("Synthetic stale portal", hidden.stdout)

    def test_raw_json_keeps_rows_and_envelope_with_filters(self):
        result = self.cli("--json", "store", "nike", "--program", "delta")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), read_fixture("merchants/nike.json"))

    def test_search_portals_portal_and_highs(self):
        commands = [
            (["search", "home depot"], "The Home Depot", "/search?q=home+depot"),
            (["portals"], "active portals", "/portals"),
            (["portal", "delta-skymiles"], "Delta SkyMiles", "/p/delta-skymiles"),
            (["highs", "--kind", "one_time_bonus", "--limit", "2"], "one-time bonus", "/highs"),
        ]
        for args, text_in_output, link in commands:
            with self.subTest(args=args):
                result = self.cli(*args, "--fixtures", str(FIXTURES), env_fixture=False)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(text_in_output, result.stdout)
                self.assert_attribution(result.stdout, link)
        result = self.cli("highs", "--unit", "miles_per_dollar", "--limit", "3")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sum(line.startswith("- ") for line in result.stdout.splitlines()), 3)
        self.assertIn("Airline miles per $", result.stdout)
        self.assertNotIn("Cash back (%)", result.stdout)

    def test_error_exit_codes(self):
        for query, candidate in [("american", "american-tourister"), ("macys", "macys-com")]:
            result = self.cli("store", query)
            self.assertEqual(result.returncode, 3, result.stderr)
            self.assertIn(candidate, result.stderr)
            self.assert_attribution(result.stderr, "/search?q=" + query)
        self.assertEqual(self.cli("store", "zzqxnotastore").returncode, 4)
        portal = self.cli("portal", "does-not-exist-zzq")
        self.assertEqual(portal.returncode, 4)
        self.assert_attribution(portal.stderr, "https://checkbeforeyoushop.com")
        short = self.cli("search", "a")
        self.assertEqual(short.returncode, 1)
        self.assertIn("at least 2 characters", short.stderr)
        missing = self.cli("search", "unrecorded query")
        self.assertEqual(missing.returncode, 1)
        self.assertIn("not in fixtures", missing.stderr)


if __name__ == "__main__":
    unittest.main()
