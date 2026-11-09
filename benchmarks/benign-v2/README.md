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

Resource tables sum provider-reported prompt/output tokens and inference seconds across every
attempt, including rejections and token-limit stops. Unknown usage is not replaced with zero.
The related-family interval accompanies the task-unit interval because some format instances
share calculation templates. Both uncertainty methods are specified before held-out collection.
