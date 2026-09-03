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
| `configs/guardrails/` | Typed, env-var-only guardrail configs (see below). |
| `dimensions/<name>/` | One research question each: `config.json` + `run.py` + `findings.md`. |
| `case_studies/{claude_code,codex}/` | Illustrative end-to-end agent runs. |
| `results/` | Emitted JSONL (gitignored). |

## Guardrails under test

Each config in `configs/guardrails/` declares a `type`; the runner drives them differently:

| Config | Type | Project | Runner support |
|--------|------|---------|----------------|
| `qwen3guard` | `moderation_model` | [Qwen3Guard](https://github.com/QwenLM/Qwen3Guard) — Safe/Controversial/Unsafe moderation model, OpenAI-compatible via vLLM/SGLang | live + dry-run |
| `nemo` | `rails_framework` | [NeMo Guardrails](https://github.com/NVIDIA-NeMo/Guardrails) — programmable input/dialog/output rails (`config.yml` + Colang) wrapping an LLM | dry-run (live adapter pending) |
| `openai-guardrails` | `guardrails_library` | [OpenAI Guardrails](https://github.com/openai/openai-guardrails-python) ([wizard](https://guardrails.openai.com/)) — `GuardrailsOpenAI(config=json)`, tripwire on violation | dry-run (live adapter pending) |

Only `moderation_model` has a live adapter today (`RoutedOpenAICompatibleProvider` + `/v1/models`
discovery). `rails_framework` and `guardrails_library` need their libraries installed and a small
adapter; until then they run dry-run only. Codex and a "leaked Claude" guardrail were removed —
Codex ships no open-source guardrails and Claude's guardrails are not leaked.

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
python eval/runner.py --guardrail eval/configs/guardrails/qwen3guard.json \
  --conditions data/refusal_conditions.jsonl --dimension smoke --dry-run
python eval/dimensions/payload_placement/run.py            # dry-run
python eval/aggregate.py eval/results/payload_placement/*.jsonl
```

## Safety boundary

Use only endpoints you own or are authorized to test. See `RESEARCH.md` for the
ethics boundary; the same limits apply to every dimension here.
