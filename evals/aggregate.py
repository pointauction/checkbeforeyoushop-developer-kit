"""Reconcile grade reports and optional adjudications with coordinator assignments."""

import argparse
import json
from pathlib import Path

from grader import HERE, load_cases, rates, summary

KEYS = ("trial", "slice", "id", "runner", "model")
GRADE_VERDICTS = {"pass", "fail", "needs_review", "missing"}


def index(records, source):
    entries = {}
    for record in records:
        key = tuple(record[k] for k in KEYS)
        if any(not isinstance(value, str) or not value.strip() for value in key):
            raise ValueError(f"{source} needs a nonempty {', '.join(KEYS)} for every entry")
        if key in entries:
            raise ValueError(f"duplicate {source} entry {key}")
        entries[key] = record
    return entries


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def breakdown(rows, field):
    return {
        "overall": rates(rows, field),
        **{
            "by_" + group: {
                key: rates([r for r in rows if key in values(r)], field)
                for key in sorted({k for r in rows for k in values(r)})
            }
            for group, values in (
                ("model", lambda r: [r["model"]]),
                ("runner", lambda r: [r["runner"]]),
                ("tag", lambda r: r["tags"]),
            )
        },
    }


def aggregate(folders, output, manifest, adjudications=None):
    assignments = index(read(manifest)["assignments"], "assignment")
    if not assignments:
        raise ValueError("assignment manifest is empty")
    corpus = {c["id"]: c["tags"] for c in load_cases()}
    unknown = {record["id"] for record in assignments.values()} - corpus.keys()
    if unknown:
        raise ValueError(f"unknown assigned case IDs {sorted(unknown)}")
    if len({folder.resolve() for folder in folders}) != len(folders):
        raise ValueError("duplicate grade directory")
    grades = []
    for folder in folders:
        path = folder / "grades.json"
        try:
            report = read(path)
        except FileNotFoundError:
            # The manifest still accounts for a wholly ungraded slice.
            continue
        if report["schema_version"] != 2:
            raise ValueError(f"unsupported report in {folder}")
        grades.extend(report["cases"])
    graded = index(grades, "grade")
    judged = index(read(adjudications)["adjudications"], "adjudication") if adjudications else {}
    if unassigned := graded.keys() - assignments.keys():
        raise ValueError(f"unassigned grade entries {sorted(unassigned)}")
    if unsubmitted := {k for k in judged if k not in graded or graded[k]["verdict"] == "missing"}:
        raise ValueError(f"adjudications without a submitted answer {sorted(unsubmitted)}")
    if any(r["verdict"] not in GRADE_VERDICTS for r in graded.values()):
        raise ValueError("unrecognized deterministic verdict")
    if any(r["verdict"] not in ("pass", "fail") for r in judged.values()):
        raise ValueError("adjudication verdicts must be pass or fail")
    if any(type(r.get("unit_conflation_error", False)) is not bool for r in judged.values()):
        raise ValueError("adjudicated unit_conflation_error must be boolean")

    rows = []
    for key, assignment in assignments.items():
        row = graded.get(key, {
            **assignment,
            "verdict": "missing",
            "strict_pass": False,
            "unit_conflation_error": False,
            "reasons": ["no grade for assigned attempt"],
        })
        row = {**row, "tags": corpus[assignment["id"]]}
        adjudication = judged.get(key)
        row["adjudicated_verdict"] = (
            adjudication["verdict"] if adjudication else
            "missing" if row["verdict"] == "missing" else "pending"
        )
        if adjudication:
            row["adjudication"] = adjudication
        rows.append(row)
    deterministic = {**summary(rows), **breakdown(rows, "verdict")}
    adjudicated = breakdown(rows, "adjudicated_verdict")
    reviewed_units = [r["unit_conflation_error"] for r in judged.values() if "unit_conflation_error" in r]
    adjudicated["unit_conflation_errors"] = sum(reviewed_units)
    adjudicated["unit_conflation_reviewed"] = len(reviewed_units)
    missing = [dict(zip(KEYS, key)) for key, row in zip(assignments, rows)
               if row["verdict"] == "missing"]
    result = {
        "schema_version": 2,
        "complete": not missing,
        "distinct_cases": len({r["id"] for r in rows}),
        "missing_attempts": missing,
        "deterministic": deterministic,
        "adjudicated": adjudicated,
        "cases": rows,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    md = ["# Shopping portal eval results", ""]
    for name, totals in (("Deterministic", deterministic), ("Adjudicated", adjudicated)):
        overall = totals["overall"]
        md.extend([
            f"## {name}", "",
            f"{overall['passed']} pass, {overall['failed']} fail, {overall['needs_review']} need review, "
            f"{overall['pending']} pending, {overall['missing']} missing across {overall['total']} assignments.",
            "",
        ])
        for field in ("model", "tag", "runner"):
            md.extend([
                f"### By {field}", "",
                f"| {field.title()} | Pass | Fail | Review | Pending | Missing | Assigned |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            ])
            for key, c in totals["by_" + field].items():
                label = key.replace("|", "\\|").replace("\n", " ")
                md.append(f"| {label} | {c['passed']} | {c['failed']} | {c['needs_review']} | "
                          f"{c['pending']} | {c['missing']} | {c['total']} |")
            md.append("")
    (output / "summary.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dirs", nargs="*", type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--adjudications", type=Path)
    parser.add_argument("--out", type=Path, default=HERE / "results")
    args = parser.parse_args()
    report = aggregate(args.run_dirs, args.out, args.manifest, args.adjudications)
    print(json.dumps({key: report[key]["overall"] for key in ("deterministic", "adjudicated")}, indent=2))
