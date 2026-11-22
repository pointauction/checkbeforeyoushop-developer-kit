"""One complete, deliberately plain reference submission for every case."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from grader import grade, load_cases


def reference(case):
    lines = []
    for fact in case["facts"]:
        kind = fact["type"]
        if kind == "row":
            value = fact["rate_display"]
            if fact["is_up_to"]:
                value = "up to " + value
            if case["id"] == "kitchen-tie" and not fact["is_up_to"]:
                value = "a flat " + value
            if fact["rate_kind"] == "one_time_bonus":
                value += " one-time bonus"
            if fact["is_stale"]:
                value += " (stale)"
            lines.append(f"{fact['portal_name']}: {value}.")
        elif kind == "candidates":
            lines.append(
                "Which one: " + " or ".join(x[0] for x in fact["options"][:2]) + "?"
            )
        elif kind == "inactive":
            lines.append("Inactive.")
        elif kind == "never_checked":
            lines.append("No successful check recorded.")
        elif kind == "count":
            lines.append(f"{fact['value']:,} stores.")
        elif kind == "directory_counts":
            lines.append(f"{fact['registered']} registered, {fact['active']} active.")
        elif kind == "hours":
            lines.append(f"Every {fact['value']} hours.")
        else:
            lines.append(fact["value"])
    if case["expected_behavior"] == "report_absent":
        lines.append("No tracked listing returned.")
    if case["expected_behavior"] == "refuse_action":
        lines.append("You can open the link yourself.")
    return {
        "model": "test",
        "runner": "test",
        "tool_calls": case["evidence"],
        "answer": "\n".join(lines),
    }


class CorpusScore(unittest.TestCase):
    def test_all_cases_have_a_passing_reference(self):
        for case in load_cases():
            with self.subTest(case=case["id"]):
                self.assertEqual(grade(case, reference(case)), ([], False))
