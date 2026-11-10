# Benign breadth study

This extension preserves all earlier studies. It measures the current generator across
63 task-format units and two live local models, with one replicate and at most two attempts.
The unit count is **not** a count of independent algorithms: seven families are reused.
No population confidence intervals or causal improvement claim are planned.

- 11 programming languages × 3 families: ceiling division, longest increasing contiguous
  run, and bounded ASCII decimal parsing (including malformed, Unicode and embedded-NUL inputs).
- 8 document formats × 3 families: temperature records, integer invoice calculations,
  and interval scheduling records. YAML, TOML, XML, CSV and INI are newly supported targets.
- Six logical binary metadata graphs: ELF, PE, Mach-O, JVM, CLR and Wasm.
- Clean pinned cJSON, zlib and curl builds, with declared upstream tests and specific
  consumer-interface checks for every compatible accepted candidate. No source insertion.

Levels 1–3 are authored complexity labels, not a validated difficulty scale. Helpers are
native computations; document fixtures contain computed reference values, not executable
business logic. Binary descriptions are symbolic schemas, not loadable binaries.

`build_suite.py` writes only authored benign task definitions and expected values. All 63
correct controls and the execution containment probes must pass before `prepare` freezes
the engine, runner, tasks, oracles, environment and repository manifest. The grader never
feeds back into generation. API transport interruptions stop a queue; saved responses are
replayed only against identical request hashes. Completed failures are never regenerated.

Native evaluation requires macOS `sandbox-exec` plus the toolchains captured in
`environment.json`. Child processes have a stripped environment, network denied, home reads
denied except the Python runtime, writes restricted to their temporary directory, CPU and
file-size limits, and a wall deadline. The harness is for explicitly benign sources, not a
general-purpose untrusted-code execution service. Compilers run separately from runtime
containment. Go changes only its package declaration to attach the authored test driver.

Repository integration is deliberately scoped: cJSON parses and serializes JSON; zlib
compresses and restores exact document bytes; curl consumes exact fixture responses from a
loopback server. It does not measure arbitrary whole-codebase insertion, removal, or
decompilation. Tracked upstream source hashes must stay unchanged. Source size counts physical
lines, including comments and blank lines, in the source extensions listed in `integration.py`.

```sh
PYTHONPATH=src .venv/bin/python benchmarks/benign-v3/check_controls.py .repel-workspaces/benign-eval-v3/fresh-controls
PYTHONPATH=src .venv/bin/python benchmarks/benign-v3/experiment.py prepare .repel-workspaces/benign-eval-v3/breadth-v1
.venv/bin/python .repel-workspaces/benign-eval-v3/breadth-v1/runner/experiment.py run .repel-workspaces/benign-eval-v3/breadth-v1
```

Run `runner/experiment.py regrade STUDY_ROOT` for offline behavior/semantic reproduction.
Verify `ARTIFACTS.json` before reproducing from a downloaded archive. Reproduction never
contacts inference endpoints. Native toolchain/platform differences can change results.
The dashboard export requires a complete grid, successful offline reproduction, exact
source hashes and completed repository integration evidence.

Later preparation gates bind the complete control-pipeline proof to the engine, grader, tasks
and oracle hashes, and reject stale proofs. This strengthening followed discovery of the
source-escape bug; it does not rewrite the already frozen `breadth-v1` protocol or outcomes.
The frozen study used direct validation/native controls; the later full-pipeline check also
exercises extraction, source preservation, manifest writes and native behavior.

For an exported archive, use its `provenance.reproduction_sha256` from `report.json`:

```sh
.venv/bin/python benchmarks/benign-v3/reproduce.py evaluation/breadth-v1/reproduction.zip /tmp/repel-breadth-reproduction --sha256 PUBLISHED_SHA256
```

Extraction verifies the published archive hash, exact member inventory, every member hash,
path safety and size bounds before writing anything. Reproduction uses the frozen grader and
never calls a model. The separate `audit_extraction.py` compares original versus literal-preserving
extraction on changed, complete first responses only, with no revised model requests or retries.
