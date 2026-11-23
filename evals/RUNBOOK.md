# Shopping portal answer eval

The corpus contains 42 shopper questions against the November 22, 2026 snapshot and labeled synthetic listings. The coordinator prepares assignments, stages prompts, grades answers and keeps the answer key private.

## Build and smoke-test the corpus

Use Python 3.10 or newer from the kit root. The scorer, compiler and aggregator use the standard library. The Node harness needs its installed dependencies and built entry point.

```sh
export CBYS_EVAL_HARNESS=/absolute/path/to/mcp-server/scripts/call-tool.mjs
python3 evals/build_fixtures.py
export CBYS_FIXTURES_DIR="$PWD/evals/fixtures-merged"
node "$CBYS_EVAL_HARNESS" get_store_rates '{"store":"synthetic-outdoor","program":"Delta"}'
python3 evals/make_cases.py
python3 -m unittest discover -s evals/tests -v
```

Set `CBYS_EVAL_HARNESS` to the built server's script in the sibling checkout when the eval branch lacks `mcp-server`. The smoke result should report fixture mode and a stale Delta listing at 7 mi/$, confirmed November 13. The merged manifest uses the synthetic response when both layers cover the same request. The integration test exercises the offline harness when its path is configured or it is built in the kit checkout.

## Stage runner prompts and the assignment manifest

Keep the coordinator's checkout, manifests, grades, reference answers and tests in a private directory. Give each runner its own writable directory outside the checkout. Stage only that runner's `prompts.jsonl` there before the run. Keep the harness and merged fixtures in a separate read-only location accessible to the runner, or expose the harness through a coordinator-owned command.

For a blind trial, run each answering agent under a filesystem sandbox or separate identity that can read its prompts and invoke the harness. Limit its mounts or permissions to those paths and its own output directory. The prompt directory layout alone provides convenience. Before launch, verify under the runner identity that a fixture call succeeds and that opening the coordinator's `cases.jsonl` or another runner's submissions is denied. An ordinary same-user shell with access to the checkout cannot provide this isolation.

Set `CBYS_RUNNER_ROOT` to the absolute base for the staged directories, outside the kit checkout. Set `CBYS_TRIAL` to a new trial ID. Replace the illustrative runner/model pairs in this coordinator-only example with the assigned identities. Each pair gets a disjoint slice. For multiple models answering the same slice, repeat the slice IDs in the manifest with their distinct runner/model assignments and use separate runner directories.

```sh
python3 - <<'PY'
import json
import os
from pathlib import Path

trial = os.environ["CBYS_TRIAL"]
private = Path("evals/runs") / trial
staging = Path(os.environ["CBYS_RUNNER_ROOT"]).resolve() / trial
if staging.is_relative_to(Path.cwd().resolve()):
    raise SystemExit("Place runner staging outside the kit checkout.")
private.mkdir(parents=True, exist_ok=False)
cases = [json.loads(line) for line in Path("evals/cases.jsonl").read_text().splitlines()]
slots = [("runner-a", "model-a"), ("runner-b", "model-b")]
assignments = []
for i, (runner, model) in enumerate(slots):
    batch = cases[i::len(slots)]
    slice_id = f"slice-{i + 1}"
    folder = staging / runner
    folder.mkdir(parents=True, exist_ok=False)
    (folder / "prompts.jsonl").write_text("".join(
        json.dumps({k: c[k] for k in ("id", "prompt")}) + "\n" for c in batch
    ), encoding="utf-8")
    (private / f"{runner}.ids").write_text("".join(c["id"] + "\n" for c in batch))
    assignments.extend(
        {"trial": trial, "slice": slice_id, "id": c["id"], "runner": runner, "model": model}
        for c in batch
    )
(private / "assignments.json").write_text(json.dumps({"assignments": assignments}, indent=2))
PY
```

## Instructions for answering agents

Answer each assigned prompt as you would answer a shopper. Invoke the offline fixture harness with the coordinator-supplied absolute paths. Keep the recorded tool name and arguments for every attempt, including retries.

```sh
export CBYS_FIXTURES_DIR=/absolute/path/to/runner-visible/fixtures
node /absolute/path/to/mcp-server/scripts/call-tool.mjs get_store_rates '{"store":"nike"}'
```

The tools are `search_stores(query)`, `get_store_rates(store, program?, unit?, include_stale?)`, `list_portals(category?)`, `get_portal(portal)` and `get_highs(unit?, kind?, limit?)`. Use exact merchant slugs for known identities. An explicit no-match result supports an absence scoped to the snapshot. A fixture coverage error requires a supported retry when available. Leave portal navigation and activation to the shopper.

Keep each payout with its portal, native unit, ceiling qualifier, and the row's own date and staleness when applicable. Cite the CBYS item page and carry the disclosure when re-serving rates. Group native payouts by unit and keep flat one-time bonuses separate from earn rates.

When a prompt explicitly asks for a conversion using the shopper's own cents-per-mile assumption, show the native rates and label the calculated cash equivalent and conclusion as conditional on that assumption. For capped payouts, compare advertised ceilings and tell the shopper that their purchase can earn less. The fixture harness describes native-unit comparisons. This evaluation additionally scores the shopper-directed calculation in the two prompts that ask for it.

Write one UTF-8 JSON object per prompt to `<case_id>.json` in your assigned output directory. Use the coordinator's assigned runner label and the actual model ID.

```json
{
  "answer": "Response to the shopper",
  "tool_calls": [{"tool": "get_store_rates", "args": {"store": "nike"}}],
  "model": "model-a",
  "runner": "runner-a"
}
```

## Grade and reconcile attempts

Grade a slice with its coordinator-owned IDs and write output to a private directory.

```sh
private="evals/runs/$CBYS_TRIAL"
python3 evals/grader.py "$CBYS_RUNNER_ROOT/$CBYS_TRIAL/runner-a" \
  --ids "$private/runner-a.ids" --trial "$CBYS_TRIAL" --slice slice-1 \
  --model model-a --runner runner-a --out "$private/grades/runner-a"
```

`grades.json` records `pass`, `fail`, or `needs_review` per submission and `missing` for an absent file. `strict_pass` also rejects rankings made under a valid personal valuation. The scorer replays recorded requests against the frozen manifest to check what those calls could return. Actual tool usage still relies on the runner's trace unless the coordinator captures invocations independently.

`judge_packet.md` includes every attempt, its deterministic reasons and the original answer and calls where readable. Review ambiguous scope, row binding, unsupported extra claims and indirect rankings. The matcher recognizes specific forms of those claims. A deterministic pass covers those checks and fixture-backed evidence. It takes a human judgment to decide open-ended wording or evaluate the answer as a whole.

Aggregate against the assignments created before launch. Missing slices and missing answers stay in the denominator. Duplicated or unassigned grade keys are rejected. A manifest covering multiple trials explicitly pools those trials.

```sh
python3 evals/aggregate.py "$private"/grades/* \
  --manifest "$private/assignments.json" --out "$private/results"
```

Optionally pass `--adjudications "$private/adjudications.json"`. Each adjudication has the same trial, slice, case ID, runner and model as its assignment, with a `pass` or `fail` verdict. Add a reason and, when reviewed, a boolean `unit_conflation_error`.

```json
{
  "adjudications": [
    {
      "trial": "trial-01",
      "slice": "slice-1",
      "id": "delta-nike",
      "runner": "runner-a",
      "model": "model-a",
      "verdict": "pass",
      "reason": "The date follows and refers to the Delta listing.",
      "unit_conflation_error": false
    }
  ]
}
```

`summary.json` and `summary.md` show deterministic and adjudicated results separately. Adjudications can reverse either deterministic decision. Submitted answers awaiting an adjudication count as pending. Different question mixes across runners limit direct comparisons of their scores.
