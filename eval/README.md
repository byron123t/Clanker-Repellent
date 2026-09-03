# Guardrail Anaphylaxis — evaluation suite

Runnable evaluation harness for the **Guardrail Anaphylaxis** research project (the
paper behind the `clanker-repellent` repo and the `repel` CLI). It measures
whether safety-related text inside an otherwise benign artifact makes a coding
agent over-refuse the benign task.

It reuses the `clanker_repellent` package (inference, verifiers, metrics) — no
inference logic is duplicated here.

## Layout

| Path | Purpose |
|------|---------|
| `runner.py` | Shared runner: guardrail config + condition set → per-trial JSONL (classified via `metrics.classify_response`). Offline-safe with `--dry-run`. |
| `aggregate.py` | Roll result JSONL into full-refusal rate + Wilson 95% CI per group. |
| `configs/guardrails/` | Env-var-only endpoint templates: `qwen3`, `nemo`, `codex`, `leaked-claude`. |
| `dimensions/<name>/` | One research question each: `config.json` + `run.py` + `findings.md`. |
| `case_studies/{claude_code,codex}/` | Illustrative end-to-end agent runs. |
| `results/` | Emitted JSONL (gitignored). |

## Research dimensions

- `guardrail_vs_refusal` — guardrail-block vs task-refusal breakdown.
- `static_vs_generative` — static payload files vs `repel generate` source.
- `payload_placement` — head/mid/tail location effect.
- `comments_vs_code` — comment-delivery vs native-carrier code payloads.
- `oss_refusal_rates` — open-source model refusal rates.

## Status

The abliterated / guardrail endpoints are currently **unreachable**, so every
`run.py` defaults to `--dry-run` (composes and records trials without network).
Pass `--live` after setting a guardrail's `*_BASE_URL` / `*_API_KEY` in the
ignored `.env`. Interpretation of results — the AI-safety-vs-agent-opt-out,
usability-vs-safety-vs-security, and open-source-supply-chain discussion — belongs
in `RESEARCH.md`; this suite produces the numbers those sections cite.

## Quick start (offline)

```bash
python eval/runner.py --guardrail eval/configs/guardrails/qwen3.json \
  --conditions data/refusal_conditions.jsonl --dimension smoke --dry-run
python eval/dimensions/payload_placement/run.py            # dry-run
python eval/aggregate.py eval/results/payload_placement/*.jsonl
```

## Safety boundary

Use only endpoints you own or are authorized to test. See `RESEARCH.md` for the
ethics boundary; the same limits apply to every dimension here.
