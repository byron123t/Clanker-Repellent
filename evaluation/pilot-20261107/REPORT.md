# Benign multi-format pilot

DeepSeek was accepted in 25/26 targets, versus GLM in 20/26; it used 29 attempts versus 49.

All 25 accepted executable helpers passed 729 inputs each (18,225 checks). Those correlated checks are not 18,225 independent samples.

Task compliance remained weaker than syntax acceptance: GLM had wrong API names, document layouts, and metadata references. Both Java documentation builds failed.

These observations motivated explicit public contracts and an independent, harder benchmark. This pilot does not measure the effect of the new system.

## Methodology

### Design

One shared range-check task across all 18 formats, five additional binary-description variants, a clamp task, and a catalog task in JSON/HTTP: 26 task/format units per model, one run each.

### Generation

Both models used identical inputs and the functional structure profile, temperature 0.2, top-p 0.8, 2,048 output tokens, no-thinking request, two retries, and a 60-second validator limit. Required checks were retained; unavailable optional linters were disclosed.

### Independent review

All 45 accepted sources were manually reviewed after benign provenance and SHA-256 verification. Native tests used all 729 triples from nine integers, including signed 32-bit extremes. Actual helper names were used; name compliance was recorded separately. Documents were checked for arithmetic, structure, labels, references, and HTTP framing.

### Preservation

Original outputs are unchanged. A full-disk interruption occurred before the first GLM clamp attempt was checkpointed; that job was restarted after recovery. Completed failures were preserved. The 49 GLM attempts count checkpointed attempts, not unrecorded interrupted work.

### Interpretation

Acceptance is reported separately from correctness. The pilot has no preregistered aggregate strict score or confidence interval. Behavioral checks, API naming, documentation, and document defects remain visible as separate evidence.

## Limitations

- One small task family translated across many formats; these are correlated task/format units, not diverse independent programming problems.
- One run per model/target, fixed model order, and uncontrolled serving load; no causal speed or general model-ranking claim.
- Rejected source was not preserved. Review concerns only accepted outputs.
- Symbolic binary schemas are not assembled artifacts. No compilation/decompilation-retention or actual network-traffic claim.
- Manual and post hoc diagnostics are exploratory; they are not a preregistered correctness endpoint.

See `scores.json` for per-candidate evidence and `protocol.json` for the recorded settings and hashes.
