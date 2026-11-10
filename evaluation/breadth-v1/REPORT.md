# Benign breadth evaluation

glm: 18/63 candidates passed every registered check; 41 passed CLI acceptance.

deepseek: 37/63 candidates passed every registered check; 50 passed CLI acceptance.

33/33 selected consumer integrations passed. This measures compatibility of specific interfaces, separately from semantic correctness.

Post hoc authored controls: 56/63 verified through the original pipeline; 63/63 through the updated pipeline, with exact source preservation.

Separate extraction audit: 10 changed complete first responses; 0 verified before versus 6 with escapes preserved. No inference or revised retry trajectory.

Separate authored placement check: 2/3 stripped executables retained the note; 3/3 source trees and snapshotted executables restored exactly. zlib's note was recovered from its linked shared library in a separate diagnostic.

| Model | Accepted | Verified | Accepted but not verified | Attempts |
| --- | --- | --- | --- | --- |
| glm | 41/63 | 18/63 | 23 | 88 |
| deepseek | 50/63 | 37/63 | 13 | 78 |

## Frozen breadth design

63 task-format units × two live model endpoints × one replicate = 126 generations. Eleven source languages share three behavioral families; eight document formats share three transformation tasks; six binary descriptions check typed metadata graphs. Tasks, private expected values, engine and runner hashes were frozen before inference.

## Equal attempt budget

Both models use 8,192 output tokens, temperature 0.2, top_p 0.8, no-thinking requested, and at most two attempts. One serial queue per model, queues concurrent. Retries receive only CLI acceptance diagnostics. Completed failures are retained; infrastructure interruptions are separate. Requested seeds are recorded but backend determinism is not independently verified.

## Behavior, semantics, and acceptance

Accepted helpers are compiled or interpreted by native toolchains in restricted subprocesses. Ceiling division, increasing contiguous runs, and bounded ASCII decimal parsing include empty, invalid, boundary, Unicode, embedded-NUL and deterministic randomized inputs. Documents must preserve exact inputs and compute correct temperature, invoice, and schedule results. Private expected outputs never enter model requests. Generic CLI acceptance does not imply these task-specific checks passed.

## Reference controls and containment

All 63 authored correct controls passed direct validation and independent grading before freezing. Those controls did not exercise extraction; the later full-pipeline audit is reported separately. Native processes deny network, home reads except the Python runtime, and writes outside temporary work directories, with CPU, file-size and wall-time limits. Three denial probes passed.

## Pinned repository interfaces

Clean cJSON, zlib and curl releases are built from exact commits. cJSON consumes every accepted JSON candidate; zlib round-trips every accepted YAML/TOML/XML/CSV/INI candidate; curl consumes every accepted HTTP response over an authored loopback server. Selection includes semantically failing accepted files. Upstream tests and consumer results are recorded separately. Tracked source hashes are verified unchanged.

## Reproduction

Every accepted candidate was regraded from unchanged bytes without model inference, with exact per-case agreement. The downloadable archive includes frozen runner, engine, tasks, private oracles, requests/responses, manifests, source files, toolchain versions and SHA-256 inventory. Rebuilding the upstream projects requires their public pinned revisions; native reproduction currently requires macOS and the listed toolchains.

## Source preservation correction · post hoc

The frozen primary engine could turn literal source escape sequences into control characters. Its completed outcomes remain unchanged. The updated CLI preserves literal source by default. A paired audit screens all first responses, excludes token-limit or unextractable responses, and revalidates only responses whose extracted source differs. Frozen validators and graders are identical across the two arms. Both accepted and failing audited sources are archived.

## Full-pipeline authored controls · post hoc

All 63 identical authored controls were also passed through original and updated generation pipelines using a fixed local response provider, with zero inference requests. Every accepted source was independently regraded; the updated pipeline passed 6,182 native behavior assertions and all document/metadata checks. This supplements the original pre-freeze direct-validator controls, which had not exercised extraction.

## Placement and restoration · auxiliary authored check

A known benign note was placed in six explicit source files across separate pinned cJSON, zlib and curl clones, with real records in the central journal. Release rebuilds and declared upstream tests passed. One executable per project was symbol-stripped, checked for note recovery, smoke-tested, and restored exactly with every tracked source file. cJSON and curl retained the note in their executable; minigzip links a shared zlib library, where a separate local-symbol-stripping check recovered it. The executable-only failure is retained. This is an authored lifecycle check, separate from model generation and from the clean primary/audit reproduction.

## Repository sizes

| Repository | Tracked files | Source lines | Commit |
| --- | --- | --- | --- |
| cjson | 229 | 23143 | c859b25da02955fef659d658b8f324b5cde87be3 |
| zlib | 257 | 42250 | 51b7f2abdade71cd9bb0e7a373ef2610ec6f9daf |
| curl | 3996 | 316202 | 7eb8c048470ed2cc14dca75be9c1cdae7ac8498b |

Source lines count physical lines in the registered C/C++/Python/Perl/shell/CMake extensions; comments and blank lines are included.

## Limitations

- Authored corpus, one generation per model/task-format, shared families and parsers; descriptive capability coverage only.
- Static markup/data fixtures do not compute at runtime. Binary descriptions are logical schemas, not real executable serialization or decompilation evidence.
- Codebase integration measures specific interfaces, not arbitrary whole-repository insertion or all platform/build configurations.
- No baseline arm: this extension measures current-system breadth and does not estimate improvement over the earlier study. Studies are not pooled.
- No confidence intervals are shown: one replicate and seven reused task families do not support treating 63 units or thousands of assertions as independent population samples.
- Successful native examples are bounded tests, not all-input correctness or a proof of purity. No memory address-space limit is enforced on macOS.
- Integration covers three C projects and selected consumer interfaces. It does not establish arbitrary placement/restoration, all build configurations, Windows/Linux behavior, or decompilation retention.
- Primary outcomes describe the frozen CLI, including its escape-handling defect. They are not estimates of the updated CLI or of model quality independent of extraction.
- The extraction audit is a post hoc mechanism check on changed complete first responses. It does not estimate full generation success after different retry feedback. Authored controls do not estimate naturally occurring model errors.
- The auxiliary placement check uses one authored note and six explicitly chosen source files. It does not measure whole-repository coverage or preservation in a decompiler’s reconstructed source. Executable-only verification can miss notes located in shipped shared libraries.


## Post hoc source-preservation audits

| Authored pipeline | Accepted | Verified | Source preserved |
| --- | ---: | ---: | ---: |
| before | 56/63 | 56/63 | 56/63 |
| updated | 63/63 | 63/63 | 63/63 |

Extraction audit: 126 first responses screened; 9 excluded for token limits, 1 unextractable, 106 unchanged, and 10 changed. Only the changed complete responses enter the following paired table.

| Model | Task | Before: accepted / verified | Preserved: accepted / verified |
| --- | --- | --- | --- |
| glm | javascript-parse_decimal | False / False | True / False |
| glm | ruby-parse_decimal | False / False | False / False |
| deepseek | c-parse_decimal | False / False | True / True |
| deepseek | cpp-parse_decimal | False / False | True / False |
| deepseek | go-parse_decimal | False / False | False / False |
| deepseek | java-parse_decimal | False / False | True / True |
| deepseek | javascript-parse_decimal | False / False | True / True |
| deepseek | typescript-parse_decimal | False / False | True / True |
| deepseek | python-parse_decimal | False / False | True / True |
| deepseek | rust-parse_decimal | False / False | True / True |

No model requests or completed primary outcomes were changed. Sources and reproduction scripts are in the archive.

## Auxiliary placement and exact restoration

| Project | Source files | Stripped executable note | Tracked source restored | Executable bytes restored |
| --- | ---: | --- | --- | --- |
| cjson | 1 | True | True | True |
| zlib | 3 | False | True | True |
| curl | 2 | True | True | True |

The missing zlib executable note was recovered from its separately stripped linked library. Both observations are retained; library stripping removes local symbols (`strip -x`). The journal contains three restored deployments.


## Clean archive reproduction

The published archive was extracted into a fresh directory only after its inventory and every member hash passed. All 91 accepted primary grades, the paired source-extraction audit, and the 126 authored pipeline evaluations reproduced exactly in a separate Python environment, using the same host/native toolchains and zero inference requests. This is local reproducibility, not replication by an independent team.

Published archive SHA-256: `f02070ea1a6e319f90ee86616945ddb69dcf174dea3dc4f6b65b0c08f4d2a1fb`


## Qualitative review

Five unchanged benign examples were manually inspected after scoring: Lua parsing, Rust increasing runs, XML intervals, CSV escaping, and JVM metadata. The Rust helper passes its behavior checks but contains an unnecessary boolean conversion chain and an unmeasured performance comment. Data/markup fixtures are static reference values, and symbolic binary metadata is not executable code. These notes do not alter primary grades; the exported example index links the review.

See [review notes](REVIEW.md) and the [example index](EXAMPLES.md).
