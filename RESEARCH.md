# Research notes and local inference

GuardrailAnaphylaxis studies artifact-induced LLM over-refusal: whether safety-related text inside
an otherwise benign artifact makes a model refuse the benign task. A full refusal is task denial;
a scoped refusal that ignores only embedded unsafe text is successful handling; provider failures
are infrastructure errors, not trigger success.

## Main observations

- The initial 144-inference gateway study found no task denial from the fixed markers tested.
- A later raw-ingestion calibration produced refusal signals in 12/24 GPT-4o-mini responses, but
  the effect did not transfer to the newer comparison model.
- The realistic tool-using smoke verified payload exposure in 24 trials and observed no
  refusal-caused task failures for its current conditions.
- Local abliterated GLM/Qwen runs are behavioral smoke tests because their tool transports differ.

These results do not establish a universal trigger or privacy mechanism. Confirmation requires
held-out tasks and model families, repeats, blinded labels, paired uncertainty estimates, and safe
contrast controls.

## Local endpoints

`configs/abliterated-local.json` contains `${VARIABLE}` references only. Copy `.env.example` to the
ignored `.env` and set the SSH target, loopback-forward ports, and base URLs. Process environment
values override `.env`; missing references fail explicitly. Plain HTTP is allowed only on an
explicit loopback port declared in the SSH forwards.

```bash
PYTHONPATH=src python3 scripts/interactive_inference.py
```

The client supports routed models, managed/reused SSH forwards, streaming, multiline paste,
per-model histories, `/model`, `/think`, `/no_think`, `/compact`, `/context`, and `/new`. The Qwen
routes use prompt-JSON tool compatibility; GLM uses native tools. The default maximum output and
context controls are documented by `--help` and `/settings`.

The abliterated endpoints are not automatic payload generators. Candidate drafting is manual and
reviewed; repository addition is a separate explicit `anaphylaxis add --apply` action.
The system does not optimize, mutate, or publish evasive variants automatically.

## Measurement and logging

Inference event logs are append-only JSONL metadata. They record request hashes, structure,
delivery/exposure, provider state, usage, latency, refusal signals, and scorer outcomes without
copying credentials. Results are now entirely ignored by Git and must be reviewed before separate
publication.

The primary research metric is conditional attributable block rate: marked responses that fully
refuse among pairs where both clean and matched-benign controls complete the task. This avoids
calling ordinary model failure a payload effect.

## Ethics boundary

Allowed work is bounded, sequential testing in owned or explicitly authorized environments with
synthetic artifacts and non-operational controls. Out of scope are stealth/universal deployment,
adaptive trigger search, hidden encoding, third-party targeting, resource exhaustion, and
actionable chemical, biological, nuclear, cyber, violence, or self-harm procedures.

Prompt instructions are not access control. A model receives content before it can refuse, and
another model can remove or ignore the text. Use authentication, authorization, and encryption for
real confidentiality. Unexpected model output must be reviewed before publication.

## Closest prior work

- Safeguard is a Double-edged Sword (artifact-triggered false-positive safeguards)
- Indirect prompt injection and BIPIA (untrusted external instructions)
- AgentDojo (joint task utility and agent security)
- Instruction Hierarchy and Spotlighting (provenance and privilege separation)
- XSTest, OR-Bench, and SORRY-Bench (over-refusal measurement)
- PoisonedRAG (retrieval-delivered adversarial context)
