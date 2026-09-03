# Static payload files vs repel-generated source

**Dimension:** `static_vs_generative`

## Setup
- Conditions: see `config.json`.
- Guardrails: qwen3, nemo, codex, leaked-claude (endpoint templates in `eval/configs/guardrails/`).
- Run: `python eval/dimensions/static_vs_generative/run.py` (dry-run) or `--live` with endpoints set.
- Aggregate: `python eval/aggregate.py eval/results/static_vs_generative/*.jsonl`.

## Findings
_Pending reachable guardrail endpoints._ Record full-refusal rate + Wilson 95% CI
per guardrail here, then interpret against the research questions in `RESEARCH.md`.
