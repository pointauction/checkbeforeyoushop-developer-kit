"""Pool case attempts across explicitly supplied graded run directories."""

import argparse
import json
from collections import defaultdict
from pathlib import Path

from grader import HERE, rates, summary


def aggregate(folders, output):
    if not folders or len({f.resolve() for f in folders}) != len(folders):
        raise ValueError("supply distinct graded run directories")
    rows = []
    for folder in folders:
        report = json.loads((folder / "grades.json").read_text())
        if report["schema_version"] != 1:
            raise ValueError(f"unsupported report in {folder}")
        rows.extend(report["cases"])
    result = summary(rows)
    for field in ["model", "runner"]:
        groups = defaultdict(list)
        for r in rows:
            groups[r[field] or "(unassigned)"].append(r)
        result["by_" + field] = {
            name: rates(group) for name, group in sorted(groups.items())
        }
    result["distinct_cases"] = len({r["id"] for r in rows})
    output.mkdir(parents=True, exist_ok=True)
    (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    overall = result["overall"]
    md = [
        "# Shopping portal eval results",
        "",
        f"{overall['passed']} of {overall['total']} case attempts passed deterministic checks across {result['distinct_cases']} distinct prompts.",
        f"Attempts with a detected cross-unit error: {result['unit_conflation_errors']}.",
        "",
    ]
    for field in ["model", "tag", "runner"]:
        md.extend(
            [
                "## By " + field,
                "",
                "| " + field.title() + " | Pass | Attempts | Pass rate |",
                "| --- | ---: | ---: | ---: |",
            ]
        )
        for name, counts in result["by_" + field].items():
            label = name.replace("|", "\\|").replace("\n", " ")
            md.append(
                f"| {label} | {counts['passed']} | {counts['total']} | {counts['pass_rate']:.1%} |"
            )
        md.append("")
    (output / "summary.md").write_text("\n".join(md) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dirs", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, default=HERE / "results")
    args = parser.parse_args()
    print(aggregate(args.run_dirs, args.out)["overall"])
