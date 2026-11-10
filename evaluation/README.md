# Recorded benign evaluations

These are measured, explicitly benign study exports. Open **Research** in the dashboard:

```sh
repel dashboard --store .repel-deploy-store --experiments evaluation --port 0 --open
```

| Study | Status | Evidence |
| --- | --- | --- |
| [Controlled fault audit](fault-audit-v1/REPORT.md) | Complete and independently reproduced | 84 authored sources, 168 paired validator decisions, 84 additional ablation validations |
| [GLM / DeepSeek pilot](pilot-20261107/REPORT.md) | Complete historical model run | 52 candidates, 45 accepted examples, 18,225 native behavior checks |
| [Development comparison](development-v2/REPORT.md) | Complete; offline grades reproduced | 48 real model candidates, 39 accepted, 30 independently verified |
| [Held-out comparison](heldout-v1/REPORT.md) | Complete; all 288 outcomes reproduced, including in a clean environment | 214 accepted, 173 verified; 28,160 private numeric checks |

The completed held-out comparison uses 24 authored tasks × three repeats × two models × two
systems. The primary result is verified output per planned candidate:

| Model | Baseline | Task contracts | Paired change, 95% task-bootstrap interval |
| --- | ---: | ---: | --- |
| GLM | 16/72 | 25/72 | +12.5 pp, 0.0 to +26.4 |
| DeepSeek | 64/72 | 68/72 | +5.6 pp, 0.0 to +12.5 |

Both intervals include no improvement. Related-family intervals are −1.6 to +30.4 pp for
GLM and 0.0 to +11.5 pp for DeepSeek. Accepted outputs failing the registered checks decrease
from 32 to 6 for GLM and from 3 to 0 for DeepSeek. This is a narrow authored benchmark,
not evidence of universal correctness or a general model ranking.

The [reviewed examples](heldout-v1/EXAMPLES.md), [figure](heldout-v1/figure.pdf), and
[reproduction archive](heldout-v1/reproduction.zip) expose exact sources, uncertainty,
serving metadata, and regrading instructions. Manual review also records remaining quality
issues, including an unused LLVM instruction; verified behavior does not guarantee polished code.

The authored audit reduced false acceptance from **47/48 to 18/48**, a **60.4 percentage-point**
reduction (95% paired task-bootstrap interval **50.0–70.8**). Correct-control false rejections
fell from **3/36 to 0/36**. These deliberately constructed faults do not estimate natural model
error frequency. The [figure](fault-audit-v1/figure.pdf), [reproduction archive](fault-audit-v1/reproduction.zip),
and per-study reports explain the scope, remaining failures, and methodology.

The development comparison raised verified success from **2/12 to 6/12 for GLM** and from
**10/12 to 12/12 for DeepSeek**. Paired changes were +33.3 pp (95% task-bootstrap interval
+8.3 to +58.3) and +16.7 pp (0.0 to +41.7), respectively. These are exploratory development
results; DeepSeek's interval includes no improvement, and 12/12 is not proof of all-input
correctness. The [development report](development-v2/REPORT.md) documents the JSON/HTML arithmetic
gaps, the subsequent validator revision, and a transient native-grader incident.

The held-out comparison is frozen as `heldout-v1`: **288/288 completed observations**. It uses the revised arithmetic checks,
matched public information and attempt budgets, independent grading, and both task-unit and
related-family uncertainty intervals. Its results remain separate from development.

Later Python fixes reject definition-time annotation failures and distinguish docstrings from
operations. They do not alter the frozen primary outcomes. A separate post hoc diagnostic
revalidates 12 saved terminal Python policy rejections: 10 pass updated validation, of which
nine pass the independent checks and one fails. All 12 diagnostic outcomes reproduce exactly.
This is not a fresh generation run or an estimate of changed retry behavior.

Each `report.json` supplies the dashboard view, `scores.json` preserves observations, and
`protocol.json` records the study's design/hashes. `candidates/` contains only the checksum-verified
benign sources exported for that study. Model candidates are unchanged accepted generation artifacts; audit
candidates are authored controls/faults, including rejected examples. Their origins are labeled
separately. Reports are portable; raw operational snippet directories are not needed.

Model studies grade the CLI pipeline's output after normal extraction and formatting, rather
than the provider's entire response. The CLI extracts fenced source; for HTTP it normalizes CRLF
headers and computes Content-Length from the final UTF-8 body. The measured object is the accepted
artifact. New model-study archives preserve raw provider responses separately, so these steps
remain inspectable. HTTP framing success is a pipeline result, not a claim that the model
calculated exact byte lengths itself. See [format handling](../docs/generation-formats.md).

The completed local studies are in `.repel-workspaces/benign-eval-v2/development-v2` and
`.repel-workspaces/benign-eval-v2/heldout-v1`. Offline reproduction needs no inference endpoint.
Use a new frozen directory for further generation experiments. See the
[benchmark guide](../benchmarks/benign-v2/README.md) for the protocol and publication steps.
