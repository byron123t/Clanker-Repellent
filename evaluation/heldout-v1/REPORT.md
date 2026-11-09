# Held-out · task-contract evaluation

State: **incomplete**. 167/288 planned observations.

| Model | System | Accepted | Verified | False acceptances | Attempts |
| --- | --- | ---: | ---: | ---: | ---: |
| glm | baseline | 48/72 | 16/72 | 32 | 132 |
| glm | contract | 31/72 | 25/72 | 6 | 171 |
| glm | filter-only | 18/72 | 16/72 | 2 | 132 |
| deepseek | baseline | 11/12 | 10/12 | 1 | 14 |
| deepseek | contract | 10/11 | 10/11 | 0 | 13 |
| deepseek | filter-only | 10/12 | 10/12 | 0 | 14 |

glm: paired change +12.5 percentage points (95% task-bootstrap interval +0.0 to +26.4; 24 tasks).
Related-family sensitivity: -1.6 to +30.4 pp (19 family clusters).

## Observed inference cost

| Model | System | Prompt tokens | Completion tokens | Inference seconds | Token-limit stops |
| --- | --- | ---: | ---: | ---: | ---: |
| glm | baseline | 158457 | 142355 | 2428.8040800000003 | 20 |
| glm | contract | 203631 | 163896 | 2827.91708 | 24 |
| deepseek | baseline | 15564 | 3518 | 2752.22227 | 0 |
| deepseek | contract | 14152 | 3115 | 2450.1744200000003 | 0 |

## Methodology

### Question

Does task-aware acceptance and retry feedback improve verified benign generation over parser/compiler/structure checks? The intervention includes the accumulator-dependency fix.

### Design

24 heldout task/format units; 3 replicates, two models, two generation arms. Randomized block and arm order; equal token/attempt budgets. Filter-only is a post hoc re-scoring ablation, not a generation arm.

### Independent outcomes

Acceptance and correctness are separate. Each numeric program must pass three public and 320 private cases. Documents must match independently computed records, fields, references, ordering, and framing. The model worker never loads the private oracle file as prompt data.

### Uncertainty

95% paired task-bootstrap intervals use 10,000 draws. Tasks are resampled with all replicates and both arms retained; individual test inputs are not independent observations. Intervals appear only for complete paired data. Boundary intervals can degenerate and do not prove universal correctness.

### Related-task sensitivity

Some authored task instances share calculation families across formats. An additional 10,000-draw paired bootstrap resamples entire named families, retaining all member tasks, arms, and replicates, and weights the rate by the sampled candidate count. Its interval is reported separately from the registered task-unit interval.

### Resource accounting

Provider-reported prompt/completion tokens and inference latency include all attempts, including failed and truncated responses. Missing usage remains unknown. Filter-only reuses the baseline cost and adds no inference. Latencies describe this run, not an intrinsic model speed comparison; server load and hardware are uncontrolled.

### Reproduction

Engine, corpus, private fixture, and runner snapshots are pinned by SHA-256. Seeds are requested, not assumed to guarantee server determinism. Completed failures are preserved. Infrastructure interruptions are disclosed, not counted as model failures.

## Limitations

- Synthetic, narrow integer/data tasks across seven formats; not a general software-engineering benchmark.
- Authored complexity levels are not calibrated difficulty measurements.
- Held-out means new task instances, not wholly unseen algorithm families. JSON/HTTP calculations and HTML tables share templates; related-family intervals are a sensitivity analysis, not evidence of generalization to arbitrary software.
- The generator and grader share parsing/eligibility dependencies, although primary native results and reference outcomes are separate.
- Symbolic binary metadata does not demonstrate compilation/decompilation survival; HTTP fixtures are never replayed.
- Model training/fine-tuning provenance and serving hardware/load are not controlled. No contamination-free or causal speed claim.
- Inference is conditional on 24 authored task units; format/level slices are descriptive and exploratory.

## Provenance

```json
{
  "protocol_sha256": "08ddd60dfbd4277c81b04ffaa7cd30ba0ffdbd76da9e9237c3410ee68eb634c1",
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
  "snapshot_files": 143,
  "study_directory": "heldout-v1",
  "scores_sha256": "2246048372616f1278ba40dedb3458f3a9d4d96b6560ee342d9ccd44f7ea4bce"
}
```

Reproduce with the frozen runner and source snapshots. `scores.json` contains every completed observation; `protocol.json` pins the design and SHA-256 hashes.
