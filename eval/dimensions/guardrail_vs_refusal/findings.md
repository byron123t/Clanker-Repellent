# Breakdown of guardrail-block vs task-refusal

**Dimension:** `guardrail_vs_refusal`

## Setup
- Conditions: see `config.json`.
- Guardrails: qwen3, nemo, codex, leaked-claude (endpoint templates in `eval/configs/guardrails/`).
- Run: `python eval/dimensions/guardrail_vs_refusal/run.py` (dry-run) or `--live` with endpoints set.
- Aggregate: `python eval/aggregate.py eval/results/guardrail_vs_refusal/*.jsonl`.

## Findings
_Pending reachable guardrail endpoints._ Record full-refusal rate + Wilson 95% CI
per guardrail here, then interpret against the research questions in `RESEARCH.md`.
