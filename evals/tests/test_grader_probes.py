"""Regression corpus from the independent scorecard review."""

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from grader import evaluate, load_cases


class ReviewProbes(unittest.TestCase):
    def test_expected_verdicts(self):
        cases = {case["id"]: case for case in load_cases()}
        probes = json.loads((HERE / "data/review_probes.json").read_text())
        for number, probe in enumerate(probes, 1):
            case = probe["case"]
            with self.subTest(probe=number, case=case):
                result = evaluate(cases[case], probe["record"])
                expected = "pass" if probe["expected_pass"] else "fail"
                self.assertEqual(result.verdict, expected, result.reasons)
                if number in (21, 22):
                    self.assertFalse(result.strict_pass)
                elif expected == "pass":
                    self.assertTrue(result.strict_pass, result.reasons)
