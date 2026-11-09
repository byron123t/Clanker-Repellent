# Benign generation evaluation v2

This protocol defines the experiment before collecting held-out model outputs. Development
results may inform changes; the held-out engine/task snapshots must remain frozen during
collection and analysis. Completion and findings are reported from recorded data, never from
the planned sample size.

The study tests whether explicit task contracts and semantic retry feedback improve useful
benign generation beyond parser/compiler/structure acceptance. The intervention also includes
a Python accumulator-dependency bug fix found with a development control. It is a system
comparison, not an isolated causal estimate of one prompt sentence.

The baseline is commit `65d5cb357140d2c76808f254c7d2a4b6d95f3f31`. The enhanced arm uses the
version-1 contract implementation. Each study copies both engines, the runner, task corpus,
and private grading fixtures into its own directory and records their SHA-256 hashes.

There are 12 development tasks and 24 held-out task/format units. The held-out suite has
eight units per complexity level: elementary boundary/shape requirements, compositional
arithmetic and structured records, and loops or multi-stage/nested calculations. Formats are
Python (six units), SQLite, LLVM IR, JSON, HTTP, symbolic binary metadata, and HTML (three
units each for the latter six). Levels are authored categories, not calibrated difficulty
measurements. This is a narrow, synthetic integration benchmark, not general software engineering.

Both GLM and DeepSeek receive the same natural-language task and public contract information.
Baseline contracts are embedded as reference data in the user task. The enhanced arm supplies
the contract as a structured field and makes its checks required for acceptance/retry. Public
examples appear in both arms. Private tests, reference implementations, and expected documents
are stored separately in `oracles.json`; the model worker never loads that file as prompt data.

The planned held-out run has three replicates per task, two models, and two generation arms:
288 candidates, each with at most three attempts. Development uses one replicate (48 candidates).
Both arms use 4,096 output tokens, temperature 0.2, top-p 0.8, no-thinking requests, a 60-second
validator budget, and all required parsers/compilers. Optional standalone linters are disabled
equally. A seed is requested for each attempt; server compliance/determinism is not assumed.
Task/replicate blocks are shuffled deterministically; arm order is counterbalanced by seeded
randomization within blocks. Each model has one sequential queue, with the two queues allowed
to run concurrently. Hardware and server load are not controlled enough for causal speed claims.

The primary outcome is **verified success per planned completed candidate**: generation is
accepted, its requested API/fields/instruction restrictions match, and every independent public
and hidden behavior or document check passes. Validation acceptance, first-attempt acceptance,
attempt count, false acceptance (accepted but not verified), and each failure category are
reported separately. A filter-only ablation re-scores baseline outputs with the public contract
without generating replacements. This ablation can improve accepted-output precision by rejection;
it is not an end-to-end repair run and must not be described as one.

Each numeric unit has three public examples and 320 private test inputs. Private inputs exclude
public examples and combine deterministic boundary combinations with seeded samples from the
documented domains. Primary grading checks both sets. Python uses native subprocess results after
AST, step-budget, and integer-size eligibility checks; those eligibility results are not used as
the expected answers. LLVM is compiled and called natively only after its no-memory/no-call
profile and task instruction restrictions are checked. SQL runs only a self-contained SELECT in
an in-memory database with an authorizer and per-query instruction budget. Native subprocesses
have CPU, wall-time, file-size, and descriptor limits. Address-space limits are not supported by
this macOS host and are not claimed; Python value/work bounds provide additional eligibility
checks. These are complementary graders with shared parsing/eligibility dependencies, not wholly
independent formal proofs.

JSON/HTTP expected calculations and preserved inputs are checked against independent authored
documents. HTTP framing is checked with Python's HTTP parser and exact body bytes. HTML tables
are compared with independently computed cells, labels, and order. Binary schema records are
checked for exact requested sections/symbols and references. These are symbolic records, not
assembled or decompiled binaries. No deployment, replayed traffic, or third-party repository
changes are part of this experiment.

All 36 authored controls must pass required validation and independent grading before collection.
The current controls exercise 6,080 private numeric cases plus document cases. Negative mutations
are reported as an authored validator-sensitivity experiment, separately from model generations.
Development and held-out model samples are never pooled in the primary analysis.

Confidence intervals use a paired bootstrap resampling entire task units, preserving all
replicates and both arms within each sampled task. Report model-specific differences and 95%
intervals, with stratified descriptive results by level and format. Individual test inputs and
repeated generations are not treated as independent task samples. Do not infer a broad model
ranking, general code safety, or compilation/decompilation retention from this narrow suite.
Do not tune on held-out outputs or selectively reroll failed candidates. Exploratory breakdowns
are labeled as such; no favorable subset replaces the registered primary outcome.

The worker verifies model identity on discovery and every response. It stores each request and
response as explicitly benign trace data, plus generation manifests and final records. Completed
failures remain in the denominator. Infrastructure interruptions stop that model queue and are
reported as missing/incomplete, not as model errors. Exact replay of saved requests can recover
an interrupted job; a request mismatch stops recovery instead of silently changing the protocol.

Methodological motivation: [EvalPlus](https://arxiv.org/abs/2305.01210) shows why stronger tests can
expose errors missed by small test suites. [LiveCodeBench](https://arxiv.org/abs/2403.07974) motivates
explicit attention to contamination and evaluation scope. This newly authored synthetic suite
does not establish contamination freedom: its algorithms are familiar, and model training data
and fine-tuning histories are unknown. These papers inform the methodology; this is not a run of
their benchmarks or a comparable leaderboard score.

Reproduction starts with `build_suite.py`, the authored controls via `grade.py`, and
`experiment.py prepare`, `run`, then `score`. A new development revision gets a fresh study
directory. Held-out collection begins only after selecting and freezing the intervention.
