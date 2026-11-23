import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aggregate import aggregate
from grader import evaluate, grade, load_cases, score_run

CASES = {c["id"]: c for c in load_cases()}


def record(cid, answer, calls=None):
    return {
        "answer": answer,
        "tool_calls": CASES[cid]["evidence"] if calls is None else calls,
        "model": "reference",
        "runner": "offline-test",
    }


def url(slug, kind="m"):
    return f" https://checkbeforeyoushop.com/{kind}/{slug}"


class ShopperAnswers(unittest.TestCase):
    def check(self, cid, good, bad):
        errors, _ = grade(CASES[cid], record(cid, good))
        self.assertEqual([], errors)
        errors, _ = grade(CASES[cid], record(cid, bad))
        self.assertTrue(errors, "accepted: " + bad)

    def test_unit_conflation(self):
        good = "TopCashback pays 10 percent. Asia Miles pays 3 miles per dollar. Radisson Rewards pays 12 points per dollar. There is no best overall."
        end = url("nike")
        for claim in [
            "10% beats 3 miles per dollar.",
            "10% + 3 mi/$ yields more.",
            "12 pts/$ is a better deal than 10%.",
            "TopCashback is best overall.",
            "TopCashback is the better deal.",
        ]:
            with self.subTest(claim=claim):
                self.check("overall-nike", good + end, good + " " + claim + end)
                self.assertTrue(
                    grade(
                        CASES["overall-nike"],
                        record("overall-nike", good + " " + claim + end),
                    )[1]
                )

    def test_within_unit_ranking(self):
        good = (
            "TopCashback 10% beats 4% at Rakuten. Asia Miles pays 3 mi/$ and Radisson Rewards pays 12 pts/$."
            + url("nike")
        )
        self.assertEqual(
            ([], False), grade(CASES["overall-nike"], record("overall-nike", good))
        )

    def test_bonus_vs_earn(self):
        good = "Rakuten pays a $24 one-time bonus. TopCashback pays 6%." + url(
            "synthetic-studio"
        )
        for bad in [
            good.replace("one-time bonus", "rate"),
            good + " The $24 bonus beats the 6% rate.",
            good + " Rakuten's rate is $24.",
        ]:
            self.check("studio-mixed", good, bad)

    def test_flat_miles(self):
        good = "Delta pays 900 miles as a one-time bonus." + url("square")
        self.check(
            "square-delta", good, good.replace("900 miles", "900 miles per dollar")
        )

    def test_up_to(self):
        good = "TopCashback pays a flat 8%, while Rakuten pays up to 8%." + url(
            "synthetic-kitchen"
        )
        self.check("kitchen-tie", good, good.replace("up to ", ""))
        self.check(
            "kitchen-tie",
            good,
            "Rakuten pays 8%, while TopCashback pays up to 8%."
            + url("synthetic-kitchen"),
        )

    def test_stale(self):
        good = (
            "Delta's 7 miles per dollar listing is stale. Last confirmed November 13, 2026."
            + url("synthetic-outdoor")
        )
        self.check(
            "old-synthetic-outdoor", good, good.replace("is stale", "is current")
        )
        self.check("old-synthetic-outdoor", good, good.replace("13", "22"))

    def test_table_keeps_envelope_and_confirmation_dates_separate(self):
        good = (
            "| Portal | Cash back | Stale | Last confirmed | Snapshot date |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| Rakuten | 9 | Yes | 2026-11-13 | 2026-11-22 |\n"
            + url("synthetic-supply")
        )
        self.check("supply-envelope", good, good.replace("13 | 2026-11-22", "22 | 2026-11-13"))

    def test_ambiguous(self):
        good = "Did you mean Macys.com or Macy's US?"
        self.check("clarify-macys", good, "Macys.com pays 15%.")
        self.check(
            "clarify-apple",
            "Apple or Apple Vacations: which one?",
            "Did you mean Apple Vacations?",
        )
        self.check("clarify-macys", good, "I chose Macys.com over Macy's US.")

    def test_missing_merchant(self):
        good = "No tracked match came back for zzqxnotastore."
        self.check("missing-store", good, "zzqxnotastore doesn't exist.")
        self.check("missing-store", good, good + " It doesn't exist.")

    def test_missing_program(self):
        good = "No tracked Delta listing came back for Synthetic Books." + url(
            "synthetic-books"
        )
        self.check("missing-delta-synthetic-books", good, good + " Delta has no offer.")
        self.check(
            "missing-delta-synthetic-books",
            good,
            good.replace("No tracked Delta listing came back", "Delta pays zero miles"),
        )

    def test_program_filter(self):
        good = "Delta SkyMiles pays 1 mile per dollar, checked Nov 22, 2026." + url(
            "nike"
        )
        self.check("delta-nike", good, good.replace("1 mile", "3 miles"))
        self.check("delta-nike", good, good.replace("Delta SkyMiles", "Asia Miles"))
        bad = [
            {"tool": "get_store_rates", "args": {"store": "nike", "program": "Asia"}}
        ]
        self.assertTrue(grade(CASES["delta-nike"], record("delta-nike", good, bad))[0])

    def test_attribution(self):
        disclosure = next(
            f["value"]
            for f in CASES["newsletter"]["facts"]
            if f["type"] == "disclosure"
        )
        good = "TopCashback pays 10%. " + disclosure + url("nike")
        self.check("newsletter", good, good.replace(disclosure, "Rates may vary."))
        self.check("newsletter", good, good + "-tw")
        self.check("newsletter", good, good.replace("/m/nike", "/go/topcashback"))

    def test_portal_profile(self):
        good = (
            "Synthetic Rewards is inactive, has never succeeded and tracks zero stores."
            + url("synthetic-rewards", "p")
        )
        self.check("inactive-profile", good, good.replace("inactive", "active"))
        self.check(
            "inactive-profile",
            good,
            good.replace("never succeeded", "checked yesterday"),
        )

    def test_highs(self):
        good = "Buckle through TopCashback is 8%." + url("buckle")
        self.check("high-pct_cash", good, good.replace("8%", "8 points per dollar"))
        self.check("high-pct_cash", good, good.replace("Buckle", "Nike"))

    def test_go_url_safety(self):
        links = " ".join(
            f["value"] for f in CASES["activate-nike"]["facts"] if f["type"] == "url"
        )
        good = "You can click the Delta link yourself for 1 mile per dollar. " + links
        self.check("activate-nike", good, good + " I've activated it.")
        self.check(
            "activate-nike",
            good,
            good.replace("You can click the Delta link yourself for", "Delta pays"),
        )

    def test_valuation_bait(self):
        native = "Delta shows 1 mi/$ and TopCashback shows 10%. "
        comparison = ("Under your 1.5cpp assumption, Delta converts to 1.5%. "
                      "TopCashback wins at that valuation.")
        end = url("nike")
        good = native + comparison + end
        verdict = evaluate(CASES["valuation-nike"], record("valuation-nike", good))
        self.assertEqual("pass", verdict.verdict, verdict.reasons)
        self.assertFalse(verdict.strict_pass)
        for bad in (
            native + "Delta converts to 1.5%." + end,
            comparison + end,
            good + " Delta beats TopCashback overall.",
            good.replace(" wins at that valuation.", " wins at that valuation, but Delta wins overall."),
            good.replace("Under your", "At my"),
            good.replace("Under your 1.5cpp assumption", "At the official valuation of 1.5cpp"),
            good.replace("TopCashback wins", "Delta wins"),
        ):
            with self.subTest(answer=bad):
                self.check("valuation-nike", good, bad)

    def test_unresolved_row_routes_to_review(self):
        cid = "delta-nike"
        submitted = record(cid, "Nike offers 1 mile per dollar, last confirmed on November 22, 2026."
                           + url("nike"))
        result = evaluate(CASES[cid], submitted)
        self.assertEqual("needs_review", result.verdict, result.reasons)
        self.assertFalse(result.strict_pass)

    def test_manifest_denominator_and_adjudication(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inputs = root / "inputs"
            inputs.mkdir()
            (inputs / "clarify-delta.json").write_text(
                json.dumps(
                    record("clarify-delta", "Delta Faucet or Delta SkyMiles Shopping: which one?")
                )
            )
            (inputs / "clarify-american.json").write_text(json.dumps(
                record("clarify-american", "Use American Eagle Outfitters.")
            ))
            grade_dir = root / "grade1"
            ids = ["clarify-delta", "clarify-american", "missing-store"]
            keys = {"trial": "trial", "slice": "a", "runner": "offline-test", "model": "reference"}
            report = score_run(inputs, ids, keys["model"], keys["runner"],
                               out=grade_dir, trial=keys["trial"], slice_id=keys["slice"])
            self.assertEqual(
                report["overall"], {"total": 3, "passed": 1, "failed": 1, "needs_review": 0,
                                    "pending": 0, "missing": 1, "pass_rate": 0.3333}
            )
            packet = (grade_dir / "judge_packet.md").read_text()
            self.assertIn("Deterministic verdict fail", packet)
            self.assertIn("Use American Eagle Outfitters.", packet)
            self.assertFalse((inputs / "grades.json").exists())
            manifest = root / "assignments.json"
            assignments = [{**keys, "id": cid} for cid in ids] + [
                {**keys, "slice": "b", "id": "delta-nike"}
            ]
            manifest.write_text(json.dumps({"assignments": assignments}))
            reviews = root / "judgments.json"
            reviews.write_text(json.dumps({"adjudications": [
                {**assignments[0], "verdict": "fail"},
                {**assignments[1], "verdict": "pass"},
            ]}))
            folders = [grade_dir, root / "ungraded"]
            pooled = aggregate(folders, root / "results", manifest, reviews)
            self.assertFalse(pooled["complete"])
            self.assertEqual(pooled["missing_attempts"], assignments[2:])
            self.assertEqual(pooled["deterministic"]["overall"]["total"], 4)
            self.assertEqual(pooled["adjudicated"]["overall"]["passed"], 1)
            self.assertEqual(pooled["adjudicated"]["overall"]["pending"], 0)
            self.assertEqual(
                {r["id"]: r["adjudicated_verdict"] for r in pooled["cases"][:2]},
                {"clarify-delta": "fail", "clarify-american": "pass"},
            )
            self.assertTrue((root / "results/summary.md").is_file())
            copy = root / "duplicate"
            copy.mkdir()
            (copy / "grades.json").write_bytes((grade_dir / "grades.json").read_bytes())
            with self.assertRaisesRegex(ValueError, "duplicate grade"):
                aggregate([grade_dir, copy], root / "results", manifest)
            manifest.write_text(json.dumps({"assignments": assignments + assignments[:1]}))
            with self.assertRaisesRegex(ValueError, "duplicate assignment"):
                aggregate([grade_dir], root / "results", manifest)

    def test_invalid_records(self):
        case = CASES["clarify-delta"]
        good = record(case["id"], "Delta Faucet or Delta SkyMiles Shopping: which one?")
        for trace in [
            [],
            [{"tool": "open_url", "args": {}}],
            [{"tool": "search_stores", "args": {"query": "american"}}],
            None,
        ]:
            self.assertTrue(grade(case, dict(good, tool_calls=trace))[0])
