# Held-out · task-contract evaluation

State: **incomplete**. 72/288 planned observations.

| Model | System | Accepted | Verified | False acceptances | Attempts |
| --- | --- | ---: | ---: | ---: | ---: |
| glm | baseline | 20/31 | 6/31 | 14 | 61 |
| glm | contract | 14/30 | 11/30 | 3 | 66 |
| glm | filter-only | 7/31 | 6/31 | 1 | 61 |
| deepseek | baseline | 5/5 | 5/5 | 0 | 5 |
| deepseek | contract | 6/6 | 6/6 | 0 | 6 |
| deepseek | filter-only | 5/5 | 5/5 | 0 | 5 |

## Observed inference cost

| Model | System | Prompt tokens | Completion tokens | Inference seconds | Token-limit stops |
| --- | --- | ---: | ---: | ---: | ---: |
| glm | baseline | 73449 | 71986 | 1249.7904899999996 | 10 |
| glm | contract | 82661 | 56453 | 976.5347899999999 | 8 |
| deepseek | baseline | 4814 | 1024 | 809.935 | 0 |
| deepseek | contract | 7062 | 1508 | 1193.02897 | 0 |

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
  "scores_sha256": "111f8b40d1251c7f9529ed1516d052075f1cd730a8fa68f3753dfa314b8fe21f"
}
```

Reproduce with the frozen runner and source snapshots. `scores.json` contains every completed observation; `protocol.json` pins the design and SHA-256 hashes.
