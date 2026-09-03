# Comment-delivery vs native-carrier code payloads

**Dimension:** `comments_vs_code`

## Setup
- Conditions: see `config.json`.
- Guardrails: qwen3, nemo, codex, leaked-claude (endpoint templates in `eval/configs/guardrails/`).
- Run: `python eval/dimensions/comments_vs_code/run.py` (dry-run) or `--live` with endpoints set.
- Aggregate: `python eval/aggregate.py eval/results/comments_vs_code/*.jsonl`.

## Findings
_Pending reachable guardrail endpoints._ Record full-refusal rate + Wilson 95% CI
per guardrail here, then interpret against the research questions in `RESEARCH.md`.
