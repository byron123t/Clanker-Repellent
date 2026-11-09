# Development · task-contract evaluation

State: **incomplete**. 0/48 planned observations.

| Model | System | Accepted | Verified | False acceptances | Attempts |
| --- | --- | ---: | ---: | ---: | ---: |
| glm | baseline | 0/0 | 0/0 | 0 | 0 |
| glm | contract | 0/0 | 0/0 | 0 | 0 |
| glm | filter-only | 0/0 | 0/0 | 0 | 0 |
| deepseek | baseline | 0/0 | 0/0 | 0 | 0 |
| deepseek | contract | 0/0 | 0/0 | 0 | 0 |
| deepseek | filter-only | 0/0 | 0/0 | 0 | 0 |

## Methodology

### Question

Does task-aware acceptance and retry feedback improve verified benign generation over parser/compiler/structure checks? The intervention includes the accumulator-dependency fix.

### Design

12 development task/format units; 1 replicates, two models, two generation arms. Randomized block and arm order; equal token/attempt budgets. Filter-only is a post hoc re-scoring ablation, not a generation arm.

### Independent outcomes

Acceptance and correctness are separate. Each numeric program must pass three public and 320 private cases. Documents must match independently computed records, fields, references, ordering, and framing. The model worker never loads the private oracle file as prompt data.

### Uncertainty

95% paired task-bootstrap intervals use 10,000 draws. Tasks are resampled with all replicates and both arms retained; individual test inputs are not independent observations. Intervals appear only for complete paired data. Boundary intervals can degenerate and do not prove universal correctness.

### Reproduction

Engine, corpus, private fixture, and runner snapshots are pinned by SHA-256. Seeds are requested, not assumed to guarantee server determinism. Completed failures are preserved. Infrastructure interruptions are disclosed, not counted as model failures.

## Limitations

- Synthetic, narrow integer/data tasks across seven formats; not a general software-engineering benchmark.
- Authored complexity levels are not calibrated difficulty measurements.
- The generator and grader share parsing/eligibility dependencies, although primary native results and reference outcomes are separate.
- Symbolic binary metadata does not demonstrate compilation/decompilation survival; HTTP fixtures are never replayed.
- Model training/fine-tuning provenance and serving hardware/load are not controlled. No contamination-free or causal speed claim.
- Development results are exploratory and excluded from held-out inference.

## Provenance

```json
{
  "protocol_sha256": "138196360521a88fd805f8125241ea639f951e44536f71d0a0dbb79464da62cc",
  "baseline_commit": "65d5cb357140d2c76808f254c7d2a4b6d95f3f31",
  "models": {
    "glm": {
      "endpoint": "http://127.0.0.1:18474/v1",
      "id": "glm-4.7-flash-abliterated"
    },
    "deepseek": {
      "endpoint": "http://127.0.0.1:18473/v1",
      "id": "deepseek-v4-flash-abliterated"
    }
  },
  "snapshot_files": 134,
  "study_directory": "development-v2",
  "scores_sha256": "9ab2b9b4723db42247fb1a0c1ddd19046138b1682fa4a5face29b84a12d36cb4"
}
```

Reproduce with the frozen runner and source snapshots. `scores.json` contains every completed observation; `protocol.json` pins the design and SHA-256 hashes.
