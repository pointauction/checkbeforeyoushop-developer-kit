"""Corpus invariants and optional MCP harness integration across every prompt."""

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build_fixtures import HERE, LIVE, SYNTHETIC, build, read
from evidence import replay
from grader import load_cases


class FixtureContract(unittest.TestCase):
    def test_merged_manifest(self):
        merged = build()
        live = read(LIVE / "manifest.json")["requests"]
        synthetic = read(SYNTHETIC / "manifest.json")["requests"]
        entries = read(merged / "manifest.json")["requests"]
        self.assertEqual(entries.keys(), live.keys() | synthetic.keys())
        for key, entry in entries.items():
            folder, original = (
                (SYNTHETIC, synthetic[key]) if key in synthetic else (LIVE, live[key])
            )
            self.assertEqual(entry["status"], original["status"])
            expected = read(folder / original["file"])
            self.assertEqual(read(merged / entry["file"]), expected)
            if folder == SYNTHETIC:
                self.assertTrue(expected["_synthetic_note"])

    def test_generated_facts(self):
        from make_cases import CASES, compile_cases

        CASES.clear()
        self.assertEqual(compile_cases(), load_cases())

    @unittest.skipUnless(
        os.environ.get("CBYS_EVAL_HARNESS")
        or (HERE.parent / "mcp-server/dist/index.js").is_file(),
        "built MCP harness required",
    )
    def test_all_cases_through_stdio(self):
        harness = os.environ.get(
            "CBYS_EVAL_HARNESS", str(HERE.parent / "mcp-server/scripts/call-tool.mjs")
        )
        env = dict(os.environ, CBYS_FIXTURES_DIR=str(build()))
        cache = {}

        def invoke_raw(call):
            key = (call["tool"], json.dumps(call["args"], sort_keys=True))
            if key not in cache:
                proc = subprocess.run(
                    ["node", harness, *key],
                    env=env,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=45,
                )
                cache[key] = json.loads(proc.stdout)
            return cache[key]

        def invoke(call):
            response = invoke_raw(call)
            if call == {"tool": "search_stores", "args": {"query": "zzqxnotastore"}}:
                self.assertTrue(response["isError"])
                self.assertIn("no tracked", response["text"].lower())
                self.assertIn("zzqxnotastore", response["text"])
                return {}
            self.assertFalse(response["isError"], response["text"])
            data = response["structuredContent"]
            self.assertTrue(data["fixture_mode"])
            return data

        for case in load_cases():
            with self.subTest(case=case["id"]):
                outputs = [invoke(call) for call in case["evidence"]]
                data = outputs[0]
                for f in case["facts"]:
                    if f["type"] == "row":
                        groups = data.get(
                            "rates_by_unit", data.get("highs_by_unit", {})
                        )
                        candidates = groups[f["rate_unit"]]["rows"]
                        if "highs" in case["tags"]:
                            candidates = candidates[:1]
                        self.assertTrue(
                            any(
                                all(row[k] == v for k, v in f.items() if k != "type")
                                for row in candidates
                            ),
                            f,
                        )
                    if f["type"] in ("url", "disclosure"):
                        self.assertIn(f["value"], json.dumps(outputs))
                    if f["type"] == "directory_counts":
                        self.assertEqual(
                            (data["count"], data["active_count"]),
                            (f["registered"], f["active"]),
                        )
                if "missing_program" in case["tags"]:
                    self.assertFalse(
                        any(
                            "delta" in r["program"].lower()
                            for g in data["rates_by_unit"].values()
                            for r in g["rows"]
                        )
                    )
                if case["id"] == "inactive-profile":
                    self.assertEqual(data["portal"]["data_status"], "never_succeeded")


        # Check fixture replay against the same calls that challenged the grader,
        # including failed lookups and the prefilter program-miss response.
        probes = read(Path(__file__).parent / "data/review_probes.json")
        reviewed_calls = {
            json.dumps(call, sort_keys=True)
            for probe in probes for call in probe["record"]["tool_calls"]
        }
        for encoded in sorted(reviewed_calls):
            call = json.loads(encoded)
            with self.subTest(call=call):
                actual = invoke_raw(call)
                replayed = replay(call)
                self.assertEqual(actual["isError"], bool(replayed.error or replayed.no_match))
                if actual["isError"]:
                    continue
                data = actual["structuredContent"]
                for key in ("count", "active_count", "program_match", "store", "data_as_of"):
                    if key in replayed.data:
                        self.assertEqual(data[key], replayed.data[key])
                groups = data.get("rates_by_unit", data.get("highs_by_unit", {}))
                actual_rows = [row for group in groups.values() for row in group["rows"]]
                fields = ("portal_id", "rate_unit", "rate_value")
                self.assertCountEqual(
                    [tuple(r[k] for k in fields) for r in actual_rows],
                    [tuple(r[k] for k in fields) for r in replayed.rows],
                )
