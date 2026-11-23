# Trial 01 (2026-11-22, baseline MCP server build 75bab7d)

- `answers/<runner>/`: each runner's prompts, assigned ids, answer files and the harness's own call log (independent of the self-reported `tool_calls`; they matched 102/102).
- `grades-v2/`: the hardened deterministic grader's output per runner and `trial-01-summary/`.
- `judges/`: the anonymised packet both blind judges scored, their verdicts (`judge-a` GPT-6.2 Sol xhigh, `judge-b` GPT-6.2 Astra xhigh) and `answer-key-mapping.json`, which maps each anonymous `answer_id` back to runner, model and case. The judges never saw the mapping.

Runners: 4x GPT-6.2 Sol and 4x GPT-6.2 Astra at high reasoning effort, identical slices, tools only through the offline MCP server.
