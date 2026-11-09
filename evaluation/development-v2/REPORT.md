# Development · task-contract evaluation

State: **complete**. 48/48 planned observations.

| Model | System | Accepted | Verified | False acceptances | Attempts |
| --- | --- | ---: | ---: | ---: | ---: |
| glm | baseline | 9/12 | 2/12 | 7 | 22 |
| glm | contract | 8/12 | 6/12 | 2 | 22 |
| glm | filter-only | 3/12 | 2/12 | 1 | 22 |
| deepseek | baseline | 10/12 | 10/12 | 0 | 16 |
| deepseek | contract | 12/12 | 12/12 | 0 | 13 |
| deepseek | filter-only | 10/12 | 10/12 | 0 | 16 |

glm: paired change +33.3 percentage points (95% task-bootstrap interval +8.3 to +58.3; 12 tasks).

deepseek: paired change +16.7 percentage points (95% task-bootstrap interval +0.0 to +41.7; 12 tasks).

## Observed inference cost

| Model | System | Prompt tokens | Completion tokens | Inference seconds | Token-limit stops |
| --- | --- | ---: | ---: | ---: | ---: |
| glm | baseline | 16745 | 17391 | 310.66754 | 3 |
| glm | contract | 17532 | 20726 | 362.7795700000001 | 4 |
| deepseek | baseline | 11103 | 2623 | 549.4407800000001 | 0 |
| deepseek | contract | 9257 | 2309 | 591.731 | 0 |

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

### Offline reproduction archive

Download includes both frozen engines, public tasks, private grading fixtures, raw explicitly benign request/response traces, manifests, exact accepted sources, and checksums. The offline driver regrades in a temporary copy without inference or altering original evidence. The original acceptance decision is preserved; native/data and filter-only outcomes are recomputed.

### Development revision · exploratory

Aggregate totals and table shape did not guarantee correct item arithmetic. The GLM JSON output used 430 where the requested calculation gives 434; the HTML output used 51 where it gives 55. The selected revision preserves supplied inputs and checks bounded integer equations. It was selected before any held-out output was collected. The original development engine and primary outcomes remain unchanged.

### Native grading incident

One interim re-scoring invocation abruptly failed on unchanged DeepSeek LLVM minimum bytes with empty stderr. The same source passed earlier and in 12 immediate repetitions of all 323 cases. A full final re-score and separate archive reproduction agree on every outcome. No inference was repeated. The held-out grader now treats child termination and timeouts as infrastructure interruptions, not wrong answers.

### Observed inference cost · descriptive addendum

Provider-reported token totals and inference seconds include all attempts. Hardware and server load were uncontrolled; timing is not a causal model-speed comparison. Filter-only reuses baseline inference.

### Offline verification

Recomputed native/document grades and filter-only decisions from saved model outputs. Acceptance is the original manifest decision, not a new generation. All 48 outcomes agreed exactly on macOS-14.5-arm64-arm-64bit with Python 3.9.15.

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
  "scores_sha256": "83e156a824d0972ae13d2e0099913ad4251c9d578016647fe63ac521bf98e312",
  "reproduction_sha256": "a49bbdadba6fe69f833e6f7b2b94ba7849b41a14d14e4b4066ef7531cb6b6723",
  "figure_sha256": {
    "figure.pdf": "ba3f9ab5dcf82e1a626c3e47a05696fb003d2ea98750b96c054010554144fc02",
    "figure.svg": "aa68505bd86ae056aeef9c6fde5fdec36c268db51e0b21ea444c9869b8171062",
    "figure.png": "f2d1e4505c28bff9565b67031d5ac92d9dc6fe3cfc38398cf0351e43ce98c753"
  },
  "offline_verification": {
    "benign": true,
    "reproduced": true,
    "observations": 48,
    "protocol_sha256": "138196360521a88fd805f8125241ea639f951e44536f71d0a0dbb79464da62cc",
    "exact_outcome_agreement": true,
    "original_evidence_preserved": true,
    "repeated_inference": false,
    "scope": "Recomputed native/document grades and filter-only decisions from saved model outputs. Acceptance is the original manifest decision, not a new generation.",
    "environment": {
      "python": "3.9.15",
      "platform": "macOS-14.5-arm64-arm-64bit"
    }
  }
}
```

Reproduce with the frozen runner and source snapshots. `scores.json` contains every completed observation; `protocol.json` pins the design and SHA-256 hashes.

## Development findings

All 48 planned development candidates are recorded. These exploratory outcomes are excluded from held-out estimates.

GLM verified success: 2/12 baseline, 6/12 task contracts (+33.3 pp; 95% paired task interval +8.3 to +58.3). Accepted-but-incorrect outputs fell from 7 to 2.

DeepSeek verified success: 10/12 baseline, 12/12 task contracts (+16.7 pp; 95% paired task interval 0.0 to +41.7). The interval includes no improvement; the 12/12 result does not establish universal correctness.

The two remaining GLM contract false acceptances were nested JSON and HTML arithmetic. A post hoc revision rejects both unchanged outputs while all 36 correct reference controls pass. That revision is evaluated prospectively in heldout-v1.

All 48 independent grades and filter-only decisions reproduced exactly from the exported archive, without new inference.
