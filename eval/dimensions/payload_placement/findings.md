# Effect of payload location (head/mid/tail)

**Dimension:** `payload_placement`

## Setup
- Conditions: see `config.json`.
- Guardrails: qwen3, nemo, codex, leaked-claude (endpoint templates in `eval/configs/guardrails/`).
- Run: `python eval/dimensions/payload_placement/run.py` (dry-run) or `--live` with endpoints set.
- Aggregate: `python eval/aggregate.py eval/results/payload_placement/*.jsonl`.

## Findings
_Pending reachable guardrail endpoints._ Record full-refusal rate + Wilson 95% CI
per guardrail here, then interpret against the research questions in `RESEARCH.md`.
