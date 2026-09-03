# Open-source model refusal rates

**Dimension:** `oss_refusal_rates`

## Setup
- Conditions: see `config.json`.
- Guardrails: qwen3, nemo, codex, leaked-claude (endpoint templates in `eval/configs/guardrails/`).
- Run: `python eval/dimensions/oss_refusal_rates/run.py` (dry-run) or `--live` with endpoints set.
- Aggregate: `python eval/aggregate.py eval/results/oss_refusal_rates/*.jsonl`.

## Findings
_Pending reachable guardrail endpoints._ Record full-refusal rate + Wilson 95% CI
per guardrail here, then interpret against the research questions in `RESEARCH.md`.
