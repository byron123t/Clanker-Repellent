# Recorded benign evaluations

These are measured, explicitly benign study exports. Open **Research** in the dashboard:

```sh
repel dashboard --store .repel-deploy-store --experiments evaluation --port 0 --open
```

| Study | Status | Evidence |
| --- | --- | --- |
| [Controlled fault audit](fault-audit-v1/REPORT.md) | Complete and independently reproduced | 84 authored sources, 168 paired validator decisions, 84 additional ablation validations |
| [GLM / DeepSeek pilot](pilot-20261107/REPORT.md) | Complete historical model run | 52 candidates, 45 accepted examples, 18,225 native behavior checks |
| [New development comparison](development-v2/REPORT.md) | Interrupted at inference discovery | 0/48 observations; both model tunnels unavailable, no new quality result |

The authored audit reduced false acceptance from **47/48 to 18/48**, a **60.4 percentage-point**
reduction (95% paired task-bootstrap interval **50.0–70.8**). Correct-control false rejections
fell from **3/36 to 0/36**. These deliberately constructed faults do not estimate natural model
error frequency. The [figure](fault-audit-v1/figure.pdf), [reproduction archive](fault-audit-v1/reproduction.zip),
and per-study reports explain the scope, remaining failures, and methodology.

Each `report.json` supplies the dashboard view, `scores.json` preserves observations, and
`protocol.json` records the study's design/hashes. `candidates/` contains only the checksum-verified
benign sources exported for that study. Pilot candidates are unchanged model outputs; audit
candidates are authored controls/faults, including rejected examples. Their origins are labeled
separately. Reports are portable; raw operational snippet directories are not needed.

The new experiment's frozen local directory is
`.repel-workspaces/benign-eval-v2/development-v2`. Resume with
`python benchmarks/benign-v2/experiment.py run .repel-workspaces/benign-eval-v2/development-v2`
after reopening ports 18473 and 18474. See the [benchmark guide](../benchmarks/benign-v2/README.md)
for the full development/held-out protocol and publication steps. Planned sample counts are
never presented as completed measurements.
