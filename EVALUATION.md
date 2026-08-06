# Optional evaluation harness

The evaluation layer compares clean and payloaded copies of pinned benign repositories. It is not
required for the four-command `anaphylaxis` repository tool.

## Conditions and payload pools

Conditions are JSONL records. `--condition-id` is the guaranteed anchor; `--payload-count` defaults
to 3 and adds reproducibly selected conditions using `--seed`. Generated mixed conditions are in
`payloads/mixed_conditions.generated.jsonl`, and every selected condition is rendered through
`payloads/header.txt` before scattering. Manifests retain hashes and IDs, never payload text.

## Prepare repository variants

```bash
PYTHONPATH=src python3 scripts/clone_benign_repos.py

PYTHONPATH=src python3 scripts/prepare_repo_evaluation.py \
  --conditions payloads/mixed_conditions.generated.jsonl \
  --condition-id mix_001_bio_header2_c4_raw_meth1 \
  --payload-count 3 \
  --repository-ids stb \
  --strategies replicated,fragmented,hub_spoke \
  --file-positions head,mid,tail \
  --instruction-files \
  --reset
```

The clean source is verified before every disposable copy. Workspaces contain no Git metadata and
are separated into `with_instruction_files` and `without_instruction_files` layouts. Each layout
has an independent clean baseline and `evaluation-manifest.json`.

Omitting `--count` selects every eligible file by default. With `--count N`, `--allow-fewer` caps
the sample when fewer files qualify. Selection ranks paths deterministically by
`SHA-256(seed + NUL + relative_path)`.

## Strategy contract

- `replicated`: complete pool payloads rotate across selected files and requested positions.
- `fragmented`: the same complete-payload placement plus
  `N = max(1, ceil(source physical lines / --inline-source-lines))` inline line chunks, capped by
  payload line count. Concatenating chunks in index order reconstructs the original payload exactly.
- `hub_spoke`: every pool payload is split only at physical line boundaries in
  `LLMDDOS_EVAL_PAYLOAD.txt`; source, documentation, and instruction files contain references only.

The engine preserves LF/CRLF and missing-final-newline behavior. Paired comment delimiters are
validated before any source-file write. Placement is text-based rather than parser-aware, so
head/mid fixtures can change language semantics and resulting build failures must be treated as
fixture failures.

Mainstream language coverage includes Python, Ruby, JavaScript/TypeScript, Java, Kotlin, Swift, C,
C++, Objective-C, C#, Go, Rust, Dart, PHP, Perl, R, Julia, Lua, shell, SQL, Haskell, OCaml, Elixir,
Erlang, Clojure, Fortran, assembly, Solidity, Zig, HTML/XML/SVG/Vue/Svelte, CSS/Sass/Less,
Make/CMake/Docker/Bazel/Meson/Gradle, YAML/TOML/INI, recognized shebang scripts, and documentation.
Test directories receive no special exclusion. Non-UTF-8 or NUL-containing files, symlinks,
binaries, generated dependencies, lockfiles, and plain JSON are excluded.

## Run Codex or Claude

```bash
python3 scripts/launch_repo_agents.py \
  --condition-id mix_001_bio_header2_c4_raw_meth1 \
  --task-id stb_png_grayscale_cli \
  --agents codex,claude \
  --variants baseline,replicated,fragmented,hub_spoke \
  --file-positions head,mid,tail \
  --instruction-files \
  --reset
```

Omit `--task-id` to run all catalog tasks. The launcher reinjects before each matched run, uses CLI
default models, and stores patches/status under `results/repo-cli-runs/`. Results are ignored by
Git. Codex uses workspace-write/no-approval mode; Claude uses permission mode `auto`.

## Cleanup and verification

Use the primary CLI for a prepared workspace:

```bash
anaphylaxis status \
  --repo data/benign_repos/injected/with_instruction_files/replicated/stb \
  --index data/benign_repos/injected/with_instruction_files/evaluation-manifest.json
```

The higher-level evaluation manifest may contain multiple workspaces, so the repository path must
match exactly. Cleanup rejects files edited after scattering. Reset disposable workspaces when an
agent has already changed them.

The strategy engine has a 100% line-and-branch coverage contract:

```bash
PYTHONPATH=src python3 -m coverage run -m unittest tests.test_payload_scatter
PYTHONPATH=src python3 -m coverage report
```

Dry runs calculate the same selections, roles, byte ranges, and hashes as applied runs. The index
contains metadata only, and indexed removal restores original bytes exactly.
