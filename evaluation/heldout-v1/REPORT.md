# Held-out · task-contract evaluation

State: **complete**. 288/288 planned observations.

| Model | System | Accepted | Verified | False acceptances | Attempts |
| --- | --- | ---: | ---: | ---: | ---: |
| glm | baseline | 48/72 | 16/72 | 32 | 132 |
| glm | contract | 31/72 | 25/72 | 6 | 171 |
| glm | filter-only | 18/72 | 16/72 | 2 | 132 |
| deepseek | baseline | 67/72 | 64/72 | 3 | 86 |
| deepseek | contract | 68/72 | 68/72 | 0 | 81 |
| deepseek | filter-only | 64/72 | 64/72 | 0 | 86 |

glm: paired change +12.5 percentage points (95% task-bootstrap interval +0.0 to +26.4; 24 tasks).
Related-family sensitivity: -1.6 to +30.4 pp (19 family clusters).

deepseek: paired change +5.6 percentage points (95% task-bootstrap interval +0.0 to +12.5; 24 tasks).
Related-family sensitivity: +0.0 to +11.5 pp (19 family clusters).

## Observed inference cost

| Model | System | Prompt tokens | Completion tokens | Inference seconds | Token-limit stops |
| --- | --- | ---: | ---: | ---: | ---: |
| glm | baseline | 158457 | 142355 | 2428.8040800000003 | 20 |
| glm | contract | 203631 | 163896 | 2827.91708 | 24 |
| deepseek | baseline | 88436 | 20728 | 5165.517910000003 | 0 |
| deepseek | contract | 81714 | 19872 | 4652.432239999998 | 0 |

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

### Offline reproduction archive

Download includes both frozen engines, public tasks, private grading fixtures, raw explicitly benign request/response traces, manifests, exact accepted sources, and checksums. The offline driver regrades in a temporary copy without inference or altering original evidence. The original acceptance decision is preserved; native/data and filter-only outcomes are recomputed.

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
  "scores_sha256": "3250a7238468c8ec5c5483daa5573423f4e1c730558ed5c26680aa7d0e7e0b96",
  "reproduction_sha256": "9da9d832a1246b60ebf8ce49b9a10f0b258abdfa60efb197d4df87591158611f",
  "figure_sha256": {
    "figure.pdf": "a3d53ea7bb97e4ab618e118c2d03531f475e3f99b8ab97ff23ef5c6f564d8422",
    "figure.svg": "1d073235b63f5320cbb771850c187c03084aef893028370e771a1c560d3bb362",
    "figure.png": "e2602134301a0f788792c6090aa02ea45399dab79484760faadc767870b3fe3e"
  },
  "offline_verification": {
    "benign": true,
    "reproduced": true,
    "observations": 288,
    "protocol_sha256": "08ddd60dfbd4277c81b04ffaa7cd30ba0ffdbd76da9e9237c3410ee68eb634c1",
    "exact_outcome_agreement": true,
    "original_evidence_preserved": true,
    "repeated_inference": false,
    "scope": "Recomputed native/document grades and filter-only decisions from saved model outputs. Acceptance is the original manifest decision, not a new generation.",
    "environment": {
      "python": "3.9.15",
      "platform": "macOS-14.5-arm64-arm-64bit"
    }
  },
  "clean_environment_verification": {
    "benign": true,
    "verification": {
      "benign": true,
      "reproduced": true,
      "observations": 288,
      "protocol_sha256": "08ddd60dfbd4277c81b04ffaa7cd30ba0ffdbd76da9e9237c3410ee68eb634c1",
      "exact_outcome_agreement": true,
      "original_evidence_preserved": true,
      "repeated_inference": false,
      "scope": "Recomputed native/document grades and filter-only decisions from saved model outputs. Acceptance is the original manifest decision, not a new generation.",
      "environment": {
        "python": "3.9.15",
        "platform": "macOS-14.5-arm64-arm-64bit"
      }
    },
    "isolated_interpreter": true,
    "absent_packages": [
      "openai",
      "clanker_repellent"
    ],
    "installed_packages": {
      "webencodings": "0.5.1",
      "Pygments": "2.21.0",
      "pip": "22.0.4",
      "html5lib": "1.1",
      "six": "1.17.0",
      "setuptools": "58.1.0"
    },
    "scope": "Same-host clean virtual environment; no extra model observations."
  },
  "serving_metadata": [
    {
      "benign": true,
      "recorded_at": "2026-11-09T22:21:25.470444+00:00",
      "scope": "Read-only API identity metadata; names do not independently verify model weights.",
      "observations": [
        {
          "port": 18473,
          "server_header": "llama.cpp",
          "models": [
            {
              "id": "deepseek-v4-flash-abliterated",
              "owned_by": "llamacpp",
              "created": 1794262885
            }
          ]
        },
        {
          "port": 18474,
          "server_header": "uvicorn",
          "models": [
            {
              "id": "glm-4.7-flash-abliterated",
              "owned_by": "vllm",
              "root": "huihui-ai/Huihui-GLM-4.7-Flash-abliterated",
              "parent": null,
              "created": 1794262885
            }
          ]
        }
      ]
    },
    {
      "benign": true,
      "recorded_at": "2026-11-09T22:22:08.576617+00:00",
      "scope": "Self-reported static serving metadata, not verified weights.",
      "properties": {
        "model_path": "/models/models--huihui-ai--Huihui-DeepSeek-V4-Flash-abliterated-ds4-GGUF/snapshots/f06f59bce3c36b3282b75c9fe2621c83c9399d10/Huihui-DeepSeek-V4-Flash-BF16-abliterated-ds4-Q2.gguf",
        "model_alias": "deepseek-v4-flash-abliterated",
        "build_info": "b1-44c7b01",
        "total_slots": 1
      },
      "default_metadata": {
        "n_ctx": 8192
      }
    },
    {
      "benign": true,
      "recorded_at": "2026-11-09T23:56:15.831680+00:00",
      "scope": "Server self-reports after collection; no independent weight or hardware verification.",
      "observations": [
        {
          "port": 18473,
          "server_header": "llama.cpp",
          "models": [
            {
              "id": "deepseek-v4-flash-abliterated",
              "owned_by": "llamacpp"
            }
          ],
          "properties": {
            "model_path": "/models/models--huihui-ai--Huihui-DeepSeek-V4-Flash-abliterated-ds4-GGUF/snapshots/f06f59bce3c36b3282b75c9fe2621c83c9399d10/Huihui-DeepSeek-V4-Flash-BF16-abliterated-ds4-Q2.gguf",
            "model_alias": "deepseek-v4-flash-abliterated",
            "build_info": "b1-44c7b01",
            "total_slots": 1
          },
          "default_metadata": {
            "n_ctx": 8192
          }
        },
        {
          "port": 18474,
          "server_header": "uvicorn",
          "models": [
            {
              "id": "glm-4.7-flash-abliterated",
              "owned_by": "vllm",
              "root": "huihui-ai/Huihui-GLM-4.7-Flash-abliterated",
              "parent": null,
              "max_model_len": 32768
            }
          ]
        }
      ]
    }
  ],
  "posthoc_rejection_audit": {
    "benign": true,
    "post_hoc": true,
    "scope": "Only the final saved attempt of completed, rejected Python candidates with a benign_policy_failed status. No new inference or changed retries; primary results remain unchanged.",
    "source_protocol_sha256": "08ddd60dfbd4277c81b04ffaa7cd30ba0ffdbd76da9e9237c3410ee68eb634c1",
    "groups": [
      {
        "model": "glm",
        "arm": "baseline",
        "terminal_rejections": 4,
        "policy_cleared": 4,
        "validation_passed": 4,
        "verified": 3,
        "newly_accepted_incorrect": 1
      },
      {
        "model": "glm",
        "arm": "contract",
        "terminal_rejections": 2,
        "policy_cleared": 2,
        "validation_passed": 0,
        "verified": 0,
        "newly_accepted_incorrect": 0
      },
      {
        "model": "deepseek",
        "arm": "baseline",
        "terminal_rejections": 3,
        "policy_cleared": 3,
        "validation_passed": 3,
        "verified": 3,
        "newly_accepted_incorrect": 0
      },
      {
        "model": "deepseek",
        "arm": "contract",
        "terminal_rejections": 3,
        "policy_cleared": 3,
        "validation_passed": 3,
        "verified": 3,
        "newly_accepted_incorrect": 0
      }
    ],
    "primary_results_changed": false,
    "repeated_inference": false,
    "offline_verification": {
      "benign": true,
      "post_hoc": true,
      "reproduced": true,
      "exact_case_agreement": true,
      "cases": 12,
      "repeated_inference": false,
      "source_protocol_sha256": "08ddd60dfbd4277c81b04ffaa7cd30ba0ffdbd76da9e9237c3410ee68eb634c1",
      "report_sha256": "dab25ff229c5a319a1964614b6ec472d1d2ee03b9e23670a58145c3b0ff446e2",
      "scope": "Offline rerun using the saved engine; no new model observations.",
      "environment": {
        "python": "3.9.15",
        "platform": "macOS-14.5-arm64-arm-64bit",
        "isolated_interpreter": true
      }
    }
  },
  "grading_environment": {
    "benign": true,
    "recorded_at": "2026-11-09T23:59:46.736987+00:00",
    "scope": "Local offline grading/verification host; remote inference hardware and model weights are not independently verified.",
    "python": "3.9.15",
    "platform": "macOS-14.5-arm64-arm-64bit",
    "sqlite": "3.40.0",
    "clang": "Apple clang version 15.0.0 (clang-1500.3.9.4)",
    "python_packages": {
      "html5lib": "1.1",
      "Pygments": "2.21.0",
      "six": "1.17.0",
      "webencodings": "0.5.1"
    }
  }
}
```

Reproduce with the frozen runner and source snapshots. `scores.json` contains every completed observation; `protocol.json` pins the design and SHA-256 hashes.

## Offline outcome reproduction

All 288 independent grades and filter-only decisions reproduced exactly from the downloaded archive, with no repeated inference. Original acceptance decisions remain those recorded in the manifests.

## Regrading environment and artifact definition

The outcome is the accepted CLI artifact after ordinary source extraction and formatting. Fenced source is extracted; HTTP headers are normalized to CRLF and Content-Length is computed from the final UTF-8 body. Exported snippets preserve those accepted bytes. Raw provider responses remain separate in the archive. HTTP framing success is therefore a pipeline result, not proof that the model calculated byte lengths itself.

Offline outcomes were reproduced on macOS-14.5-arm64-arm-64bit, Python 3.9.15, SQLite 3.40.0, Apple clang version 15.0.0 (clang-1500.3.9.4). Python parsing dependencies: html5lib 1.1, Pygments 2.21.0, six 1.17.0, webencodings 0.5.1. The archive includes exact regrading dependency pins. The frozen native LLVM grader uses macOS linking; other platforms have not been validated. Remote serving hardware and weights are not independently verified.

Verification requires the registered bounded task profile as well as every independent check. A failure can be an eligibility violation, excessive work, undefined computation, or a wrong result. Table labels such as false acceptance and accepted-but-incorrect mean accepted outputs that failed these registered checks; they do not imply that every failure is a demonstrated wrong numeric answer or that the source cannot work in another setting.

All 288 saved outcomes also reproduced in a fresh virtual environment using isolated Python, with only the documented parsing dependencies and no installed project or inference SDK. This is a same-host dependency-isolation check, not an independent replication or additional model observations.

The archive contains timestamped, read-only API identity and serving metadata collected during this study. These are server self-reports, not independently verified weight hashes or evidence that configuration remained unchanged for every request. Backend, quantization, hardware, and load differences prevent a model-only speed comparison.

Only the final saved attempt of completed, rejected Python candidates with a benign_policy_failed status. No new inference or changed retries; primary results remain unchanged. glm / baseline: 4 final policy rejections, 4 passing updated validation, 3 independently verified, 1 newly accepted but incorrect. glm / contract: 2 final policy rejections, 0 passing updated validation, 0 independently verified, 0 newly accepted but incorrect. deepseek / baseline: 3 final policy rejections, 3 passing updated validation, 3 independently verified, 0 newly accepted but incorrect. deepseek / contract: 3 final policy rejections, 3 passing updated validation, 3 independently verified, 0 newly accepted but incorrect. The diagnostic reproduced exactly offline. It does not estimate the yield of a fresh generation run or changed earlier retries. Its source snapshot and reproduction evidence are in publication/rejection-audit/ in the archive.

Five verified contract-arm examples were reviewed as illustrations, not a random sample or a new quality-rate estimate. The Python checksum performs substantive computation; HTTP/HTML records contain checked arithmetic. The LLVM example passes native cases but retains an unused instruction and misleading comment. The HTML is a static table, and the JVM example is symbolic metadata. Behavioral verification does not guarantee minimal, idiomatic, or presentation-ready code. See EXAMPLES.md in the repository and reproduction archive for exact source links and notes.
