# Benign breadth study

This extension preserves all earlier studies. It measures the frozen generator across
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

The published archive includes `publication/audit_controls.py` and
`publication/audit_extraction.py`. From an extracted archive, reproduce the separate audits
into new directories:

```sh
python EXTRACTED/publication/audit_controls.py EXTRACTED EXTRACTED/supplement/updated-engine /tmp/breadth-controls --compare EXTRACTED/supplement/control-audit/report.json
python EXTRACTED/publication/audit_extraction.py EXTRACTED /tmp/breadth-extraction --compare EXTRACTED/supplement/extraction-audit/report.json
```

The controls audit runs identical authored responses through two archived engines in separate
processes and recomputes every accepted native/document grade. It does not contact a model.
The extraction audit holds the frozen validators and grader constant and changes only how
literal source escapes are preserved. Both are post hoc mechanism checks, separate from the
primary 126 observations. The updated snapshot is identified by its complete Python-source hash.

`finish.py STUDY_ROOT EXPORT --clean-python CLEAN_PYTHON --wait` waits for the registered
model runner, then performs consumer integration, offline regrading, publication, fresh
checksum-gated archive extraction, and exact reproduction of primary grades and both audits.
It never starts or retries inference. Interrupted queues stop publication. Clean reproduction
uses a separate Python environment on the same host and native toolchains; it is not an
independent team's replication. `progress.py STUDY_ROOT EXPORT --watch` exposes completed
observations while clearly marking the incomplete grid and withholding final artifacts.

An additional authored lifecycle check uses `retention_check.py` in fresh local clones of
the pinned projects. It places one benign note in six explicit C files, rebuilds and runs the
declared upstream tests, strips one executable per project, verifies recovery, and restores
all tracked sources plus the three snapshotted executables byte-for-byte using the central
journal. The zlib executable links a shared library: its executable-only failure remains in
the report, alongside a separate `strip -x` library diagnostic. This check is auxiliary,
does not measure decompiler output or full-repository coverage, and is not part of the clean
primary-grade/control-audit reproduction. Its script, note, metadata and build logs are archived.

`smoke_contracts.py OUTPUT --endpoint http://127.0.0.1:18474/v1` runs the five new public
invoice contracts against a local endpoint. Use `18473` for DeepSeek. These are small auxiliary
example checks with independent exact parsing, not a causal comparison or part of the frozen
primary grid. All generation uses `benign=True`; only those artifacts are inspected.
