# Benign generation evaluation

This directory contains a deterministic task corpus, independent outcomes, a frozen experiment
runner, paired task-bootstrap analysis, and a separate authored fault audit. All inputs and
outputs in these studies are explicitly benign. Operational snippet directories are not used.

## Evidence available now

| Study | Observations | What it measures |
| --- | ---: | --- |
| [November 7 pilot](../../evaluation/pilot-20261107/REPORT.md) | 52 real model candidates, 45 accepted | GLM/DeepSeek acceptance and exploratory quality diagnostics across 18 formats |
| [Controlled fault audit](../../evaluation/fault-audit-v1/REPORT.md) | 84 fixed sources, two systems; 84 additional ablation validations | False acceptance and false rejection, independently confirmed; no model generation |
| [Development comparison](../../evaluation/development-v2/REPORT.md) | 48 actual model candidates, 39 accepted, 30 independently verified | Exploratory generation improvement and concrete failure diagnosis; all independent grades reproduced offline |
| [Held-out comparison](../../evaluation/heldout-v1/REPORT.md) | 288/288 candidates complete; 214 accepted, 173 verified | Frozen 24-task, three-repeat comparison; all outcomes reproduced from the archive, including in a clean environment |

The audit reduces acceptance of authored faults from **47/48 to 18/48**: 60.4 percentage
points, with a paired task-bootstrap 95% interval of **50.0–70.8 points** over 12 task clusters.
Correct-control false rejections fall from **3/36 to 0/36**. The post hoc ablation separates
the accumulator fix from semantic filtering. Faults were deliberately constructed, so this is
not an estimate of real model-error prevalence or evidence of improved model generation.
The complete primary and ablation outcomes reproduced exactly in isolated copies. A standalone
[figure (PDF)](../../evaluation/fault-audit-v1/figure.pdf) is also available as
[SVG](../../evaluation/fault-audit-v1/figure.svg) and [PNG](../../evaluation/fault-audit-v1/figure.png).

The new model experiment resumed on November 9 with both inference tunnels open. Its
[development report](../../evaluation/development-v2/REPORT.md) contains measured observations;
planned counts are not results. Development has 12 tasks × 2 models × 2 arms = 48 candidates.
The held-out design has 24 tasks × 3 replicates × 2 models × 2 arms = 288 candidates. Three authored
complexity levels cover arithmetic/boundaries, composition/structured records, and loops/nested
calculations. There are seven formats: Python, SQL, LLVM, JSON, HTTP, binary descriptions, HTML.
The original model-discovery interruption and every completed outcome are preserved in the
frozen `development-v2` directory. New arithmetic checks address observed GLM JSON/HTML
calculation errors; they do not retroactively change that development experiment's engine.

Development verified success was GLM 2/12 → 6/12 and DeepSeek 10/12 → 12/12. The paired changes
were +33.3 pp (95% interval +8.3 to +58.3) and +16.7 pp (0.0 to +41.7). These exploratory
results motivated the selected intervention; they are not pooled with held-out observations.
The new `heldout-v1` study freezes all 288 planned cells before collection. Its protocol SHA-256
is `08ddd60dfbd4277c81b04ffaa7cd30ba0ffdbd76da9e9237c3410ee68eb634c1`.

GLM's completed held-out grid gives **16/72 → 25/72** verified candidates (+12.5 pp;
95% task-bootstrap interval 0.0 to +26.4 pp; related-family interval −1.6 to +30.4 pp).
Accepted-but-incorrect candidates fall from **32 to 6**, while acceptance falls from 48 to 31.
DeepSeek gives **64/72 → 68/72** verified candidates (+5.6 pp; task interval 0.0 to +12.5 pp;
related-family interval 0.0 to +11.5 pp). Its accepted outputs failing the registered checks
fall from three to zero. Both primary intervals include no improvement. These results are
reported separately from development and concern this authored task mix and serving setup.
All 288 independent grades and filter-only decisions reproduced exactly offline, including
in the clean environment with no project or inference SDK installed. The archive includes
the full request/response evidence, toolchain/dependency versions, and server self-reports.
[Five reviewed examples](../../evaluation/heldout-v1/EXAMPLES.md) illustrate substantive code
and structured documents, while also documenting remaining code-polish limitations.

## Reproduce the completed audit

The [reproduction archive](../../evaluation/fault-audit-v1/reproduction.zip) contains the exact
engine trees, runner, authored source variants, task contracts, independent oracles, protocol,
raw results, and ablation addendum. The recorded audit used macOS, Python, Clang, html5lib, and
Pygments. Its frozen native LLVM grader uses macOS dynamic-library linking. Use the repository's
Python dependencies; no inference endpoint is needed.

```sh
mkdir /tmp/repel-audit-reproduction
unzip evaluation/fault-audit-v1/reproduction.zip -d /tmp/repel-audit-reproduction
cd /tmp/repel-audit-reproduction
python runner/reproduce.py .
```

The reproduction driver verifies hashes, creates separate temporary copies for primary and
ablation reruns, and compares decisions/grades with the recorded evidence. It leaves original
files unchanged; timings and temporary compiler paths are not expected to match. It stops on missing required
toolchains. The audit's native eligibility checks and resource limits are described in
[PROTOCOL.md](PROTOCOL.md). Original reports should be preserved; use the extracted copy for reruns.

To rebuild the figures, install the optional `requirements.txt` here and run
`python benchmarks/benign-v2/plot.py evaluation/fault-audit-v1`. The figure reads measured
report values, uses the recorded task-bootstrap intervals, and does not recompute or replace
the statistical results. The archive includes this plotting script and its optional dependency pin.

## Run the model comparison

First open both Messi tunnels and verify `/v1/models` on ports 18473 and 18474. The runner
requires the expected model IDs, not merely an HTTP response. It stops on infrastructure
failures and preserves completed outcomes, including failures. There is one serial queue per
model; the model queues may run concurrently.

The original baseline source must be available at
`.repel-workspaces/benign-eval-v2/baseline/src`. To reconstruct it from repository history:

```sh
mkdir -p .repel-workspaces/benign-eval-v2/baseline
git archive 65d5cb357140d2c76808f254c7d2a4b6d95f3f31 src | tar -x -C .repel-workspaces/benign-eval-v2/baseline
python benchmarks/benign-v2/experiment.py prepare .repel-workspaces/benign-eval-v2/development-new --split development --repeats 1
python benchmarks/benign-v2/experiment.py run .repel-workspaces/benign-eval-v2/development-new
python benchmarks/benign-v2/experiment.py score .repel-workspaces/benign-eval-v2/development-new
python benchmarks/benign-v2/analyze.py .repel-workspaces/benign-eval-v2/development-new evaluation/development-new
```

Use the project's Python environment. Scoring imports the frozen engine itself. Before an
independent model study, run all authored controls with `PYTHONPATH=src python benchmarks/benign-v2/grade.py /tmp/controls.json`.
The 36 controls passed validation and independent grading, including 6,080 private numeric cases.

After development is complete, freeze a **new** directory with `--split heldout --repeats 3`.
Do not tune on held-out outputs or reroll completed failed candidates. The protocol, both engines,
runner, analysis, tasks, and private fixtures are hashed before collection. Baseline and enhanced
arms receive the same public task information; only the enhanced system enforces the public
contract during acceptance/retry. Primary grading uses private cases and independent native/data
outcomes. A complete paired dataset is required for confidence intervals.

`build_suite.py` deterministically rebuilds the authored fixtures. Never regenerate files inside
a frozen study. `faults.py` authors the fixed fault/control corpus; `ablate.py` adds the explicitly
post hoc mechanism check. `publish_pilot.py` only exports the existing benign pilot after checking
its manifests and candidate hashes. `publish_audit.py` exports the completed audit without
reclassifying outcomes or modifying original sources.

## Dashboard

```sh
repel dashboard --store .repel-deploy-store --experiments evaluation --port 0 --open
```

Choose **Research**. It displays study-specific denominators, confidence intervals, failure
cases, exact benign source previews, limitations, and downloadable reports/protocols/observations.
The audit and historical model pilot are separate studies with different metrics. No metric is
filled with a placeholder or a planned result.

Completed model studies can be exported with `publish_models.py STUDY OUTPUT`, then plotted
with `plot_models.py OUTPUT`. The publisher uses the frozen analysis and includes a checksum-pinned
offline reproduction archive. Extract it and run `python runner/reproduce_models.py .` to repeat
the independent native/document grades and filter-only decisions in a temporary copy, without
inference. Original acceptance decisions remain those in the saved generation manifests.
The archive includes explicitly benign request/response traces; it never includes operational
snippet directories. Model sampling itself is not claimed to reproduce bit for bit.
After successful offline verification, `finalize_model_report.py OUTPUT` attaches the recorded
grading environment and exact `requirements-regrade.txt` pins to the archive while preserving
all primary outcomes. The archive's `REGRADING_ENVIRONMENT.md` explains the macOS/Clang requirement.
The development archive also records an exact 48-outcome reproduction in a fresh virtual
environment with no installed project or inference SDK. This checks dependency isolation on
the same host; it is not a separate model experiment or an independent replication.
Optional `--clean-verification FILE` and repeatable `--serving-metadata FILE` arguments attach
matching verification evidence and timestamped server self-reports. They cannot change primary
results, and the finalizer verifies existing archive checksums before updating the publication.

Resource tables sum provider-reported prompt/output tokens and inference seconds across every
attempt, including rejections and token-limit stops. Unknown usage is not replaced with zero.
The related-family interval accompanies the task-unit interval because some format instances
share calculation templates. Both uncertainty methods are specified before held-out collection.

## Production changes after the held-out freeze

A separate hand-written regression check found that the bounded Python interpreter ignored
definition-time annotations. A helper with `value: MissingType` could pass its public examples
but fail at definition time. The live validator now rejects unresolved/computed annotations
and compiles its AST without execution to check Python control-flow rules. Ten authored
expressions over 49 integer/Boolean input pairs also agree with native Python values and types.
These are software regression checks, not model observations. Frozen study engines remain
unchanged; the held-out results do not measure this later fix.

Interim rejection diagnostics also motivated an authored documentation check: “half-open
interval” in a Python docstring was misclassified as an `open` operation. The live benign
validator now identifies docstrings with the Python AST and excludes only those spans from
operation matching. It retains the documentation in the accepted artifact and continues
checking actual code and all text for the existing content rules. Tests cover Unicode, CRLF,
code following a docstring on the same line, and end-to-end benign generation. This is a
post-freeze correction, not a revision or reclassification of the registered study outcomes.

The separate post hoc GLM diagnostic screens its complete 144-candidate grid and revalidates
only the final saved Python attempts rejected by the benign operation checks. Four baseline
attempts pass updated validation: three pass every independent check, and one is incorrect.
Two contract-arm attempts clear the operation check but still fail subsequent validation.
All six case outcomes reproduce exactly with the saved engine in the clean environment.
These are validation counterfactuals, not extra generations or an estimate of a new retry
pipeline's yield. The original held-out counts stay unchanged.

After DeepSeek collection completed, the same diagnostic found six additional terminal
policy rejections, three per arm; all six pass updated validation and the independent checks.
The complete twelve-case diagnostic reproduced exactly from the downloaded primary archive
with the saved validator snapshot. Its results, source, and proof are included under
`publication/rejection-audit/` in the final held-out archive and described on the dashboard.

`audit_rejections.py STUDY FRESH_OUTPUT --models glm` creates this diagnostic with a snapshot
of the current validator. After both model grids complete, omit `--models` to include both.
For offline reproduction, run the saved script against the original study/archive with
`--engine ORIGINAL_AUDIT/engine --verify-against ORIGINAL_AUDIT/report.json`, using a fresh
output directory. The matching proof can be attached by passing `--rejection-audit DIR` to
the publication finalizer, with the proof saved as `DIR/reproduction-check.json`.
The finalizer checks both the diagnostic snapshots and their original study evidence.
