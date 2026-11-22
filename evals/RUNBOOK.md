# Shopping portal answer eval

The corpus has 42 shopper questions against the November 22, 2026 snapshot and six fictional merchant or portal profiles. Prepare the assignments before starting the answering agents. Keep the scoring corpus, gold facts, other answers and tests out of their context.

## Prepare the corpus and assignments

Run these commands from the kit root with Python 3.10 or newer. The grader, compiler and aggregator use the standard library. The local MCP server needs its own dependencies and built entry point in `mcp-server/dist`. Use its project build instructions before the offline run.

```sh
python3 evals/build_fixtures.py
export CBYS_FIXTURES_DIR="$PWD/evals/fixtures-merged"
node mcp-server/scripts/call-tool.mjs get_store_rates '{"store":"synthetic-outdoor","program":"Delta"}'
python3 evals/make_cases.py
python3 -m unittest discover -s evals/tests -v
```

The smoke call should report fixture mode. Synthetic directory data adds one inactive portal to the captured list, leaving the active count unchanged. Manifest keys select the synthetic response when the two inputs share a key. The compiler refreshes the merged corpus and derives its answers from those manifests. The integration test exercises every case through MCP when the built server is present. Set `CBYS_EVAL_HARNESS` to the absolute path to another checkout's built server's `scripts/call-tool.mjs` to use it instead.

For six disjoint assignments, run the following once as the coordinator. Use seven or eight in place of six if desired. Start a new run directory for each trial. Give each answering agent only its prompts, its output directory, the harness command and the runner instructions below.

```sh
python3 - <<'PY'
import json
from pathlib import Path
root = Path("evals/runs/trial-01")
cases = [json.loads(line) for line in Path("evals/cases.jsonl").read_text().splitlines()]
slots = 6
for i in range(slots):
    batch = cases[i::slots]
    folder = root / f"slice-{i+1}"
    folder.mkdir(parents=True, exist_ok=False)
    (folder / "ids.txt").write_text("".join(c["id"] + "\n" for c in batch))
    (folder / "prompts.jsonl").write_text("".join(
        json.dumps({k: c[k] for k in ("id", "prompt")}) + "\n" for c in batch))
PY
```

## Runner instructions to pass to the answering agent

Answer each assigned prompt as you would answer a shopper. Use only the local tool harness with the coordinator's absolute `CBYS_FIXTURES_DIR` exported. Every call uses this form:

```sh
node mcp-server/scripts/call-tool.mjs <tool> '<JSON arguments>'
```

The five tools are `search_stores(query)`, `get_store_rates(store, program?, unit?, include_stale?)`, `list_portals(category?)`, `get_portal(portal)`, and `get_highs(unit?, kind?, limit?)`. Read the structured result, including any tool error. Use exact merchant slugs, e.g. `the-home-depot`, for known identities. Fixture search supports recorded queries only. A “not in fixtures” error is a coverage limitation and cannot establish a merchant or program is absent. Record failed calls and retry a supported lookup when available. Never switch to a live service or open an outbound URL. Do not inspect source, manifests, fixture files, gold answers, grader output or another agent's answers.

Keep each quoted payout with its portal and unit. Cite the CBYS item page when reporting its data. Preserve the disclosure when re-serving rates. For each prompt, write one UTF-8 JSON object to `<run_dir>/<case_id>.json`. Keep the actual tool names and arguments in call order, including retries. Use the actual model ID and runner or harness identity assigned by the coordinator. The tool trace is self-reported. An independent coordinator can capture the harness invocations to audit it.

Answer-file JSON schema:

```json
{
  "type": "object",
  "required": ["answer", "tool_calls", "model", "runner"],
  "properties": {
    "answer": {"type": "string", "minLength": 1},
    "model": {"type": "string", "minLength": 1},
    "runner": {"type": "string", "minLength": 1},
    "tool_calls": {
      "type": "array", "minItems": 1,
      "items": {
        "type": "object", "required": ["tool", "args"],
        "properties": {
          "tool": {"enum": ["search_stores", "get_store_rates", "list_portals", "get_portal", "get_highs"]},
          "args": {"type": "object"}
        }
      }
    }
  }
}
```

## Grade and aggregate

Run this once per slice, substituting the assigned model and runner labels. Those flags assign missing submissions to their intended denominator. Without `--ids`, every case in the corpus counts, including missing files. Grading writes scores even when a model fails cases. Inspect the JSON for a CI pass threshold.

```sh
slice=evals/runs/trial-01/slice-1
python3 evals/grader.py "$slice" --ids "$slice/ids.txt" --model MODEL_ID --runner RUNNER_ID
```

Each run directory receives `grades.json` with pass/fail, case reasons, tag totals and overall counts. `judge_packet.md` carries the prompt, answer, constraints, facts and trace for every answer that cleared deterministic checks. A reviewer should read those answers for unsupported factual claims, program or date mix-ups, incorrect tie explanations and indirect rankings. Inspect failed cases and their original answers for valid phrasing the text matcher missed. Keep adjudications separate so the deterministic scores stay reproducible.

After grading all slices:

```sh
python3 evals/aggregate.py evals/runs/trial-01/slice-*
```

Read `evals/results/summary.json` or `summary.md` for pass counts, denominators and rates by model, tag and runner. Pass explicit graded directories from a single trial to measure coverage. Pooling repeated prompts across trials counts each attempt. Tags overlap. The cross-unit error count measures attempts with a detected prohibited comparison or conversion, once per attempt. An incorrect numeric answer can fail its case without increasing that count. Different agents on different slices see different questions, so their pass rates alone cannot establish a model ranking.

## Valuation and interpretation

For a shopper supplying 1.5 cents per mile, give the native Delta and cashback listings. An answer may repeat 1.5 cpp as the shopper's stated assumption. Under the developer kit contract, doing the conversion, reporting an equivalent cashback percentage, adding across units, or naming a winner across those units fails, even with a personal-valuation label. A comparison between percentages within the same earn kind is valid. Fixed bonuses need their one-time label. A flat percentage beats an equal “up to” percentage in the same unit and kind.

A deterministic pass covers the encoded facts and recognizable claim patterns. Reviewers decide implied claims, scope of negation, paragraph/table associations, and novel phrasings. Historical rates and fictional listings are for this offline evaluation only.
