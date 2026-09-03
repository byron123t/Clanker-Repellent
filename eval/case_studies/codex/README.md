# Case study: codex on a payloaded repository

Illustrative end-to-end example: prepare a payloaded checkout with `repel add`,
open codex on it, and record whether the agent completed the benign task,
over-refused (guardrail anaphylaxis), or ignored the payload (scoped refusal).

## Steps
1. `repel add --apply` in a disposable authorized workspace.
2. Run the agent on a benign task from `data/repository_tasks.json`.
3. Capture transcript + outcome under `eval/results/case_studies/codex/`.
4. `repel remove --apply` to restore the workspace.

## Notes
_Add the concrete transcript excerpt and outcome classification here._
