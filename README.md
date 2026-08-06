# Clanker-Repellent (Guardrail Anaphylaxis)

Guardrail Anaphylaxis is a small, indexed payload-delivery tool for authorized repositories. Its
core flow is `payload text files → language-appropriate comments → centralized hash/range index →
exact removal → clean commit/publish guard`.

Payload text is never hidden in the index. The index contains condition IDs, hashes, selected
paths, and exact insertion ranges so payloads can be removed without searching for their strings.

## Install

Choose any environment; isolation is recommended but not required:

```bash
# Standard `venv`
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -e .

# Conda
conda create -n anaphylaxis python=3.11 pip
conda activate anaphylaxis
python -m pip install -e .

# No virtual environment
python3 -m pip install -e .
# Or without system write access
python3 -m pip install --user -e .
```

Each method installs the `anaphylaxis` command. If a per-user scripts directory is not
on `PATH`, run the source entry point directly:

```bash
python3 scripts/anaphylaxis.py
```

Install development/test dependencies only when needed with `python3 -m pip install -e '.[dev]'`.

## The four commands

Run these inside the repository you want to process. `add` automatically selects three bundled
payload mixtures, uses the `replicated` strategy, places full payloads at both the head and tail of
every eligible file, and performs only a dry run unless `--apply` is present.

```bash
# 1. Preview comment delivery in the current repository.
anaphylaxis add

# 2. Apply it and write the centralized index.
anaphylaxis add --apply

# 3. Inspect or exactly remove the indexed payloads.
anaphylaxis status
anaphylaxis remove --apply

# 4. Fail unless every indexed path is clean.
anaphylaxis guard
```

There are two target modes:

- Current-directory mode is the default. It processes exactly the current directory and keeps the
  index at `./.anaphylaxis-index.json`.
- `--git-repo` discovers the enclosing Git worktree from the current directory, processes its root,
  and keeps the index at `<git-metadata>/anaphylaxis-index.json`, outside the tracked worktree.

Use the same mode for every lifecycle command:

```bash
# Enclosing Git repository, even when run from a nested directory.
anaphylaxis add --git-repo --apply
anaphylaxis status --git-repo
anaphylaxis remove --git-repo --apply
anaphylaxis guard --git-repo
```

`--repo /path` changes the current target—or the Git discovery starting point when combined with
`--git-repo`. `--index /private/path/index.json` overrides either default. The index deliberately
contains no payload text or payload file path.

To target exactly one file, use `--file`. Relative paths resolve from the selected current-directory
or Git root; absolute paths are accepted only when contained by that root:

```bash
anaphylaxis add --file src/app.py --apply
anaphylaxis add --git-repo --file src/app.py --apply
```

The file must be an eligible non-symlink text format. `--file` and `--count` are mutually exclusive.
Later `status`, `remove`, and `guard` commands use the index, so they do not need `--file` again.

## Comment delivery

The tool selects every eligible file by default and applies syntax-appropriate comments for common
source, header, test, build, configuration, script, web, and documentation formats. Examples
include Python, Ruby, JavaScript/TypeScript, Java, Swift, C/C++, Go, Rust, shell, HTML/CSS, Make,
CMake, Docker, YAML, TOML, Markdown, reStructuredText, and many others. Binary files, symlinks,
lockfiles, generated/dependency directories, and commentless structured files such as plain JSON
are excluded.

Choose a topology with `--strategy`:

- `replicated` places a complete assigned payload at each requested position.
- `fragmented` adds the complete replica plus line-chunked inline copies scaled to file length.
- `hub_spoke` line-chunks payloads in `LLMDDOS_EVAL_PAYLOAD.txt`; repository files receive only
  comments pointing to that carrier.

Automatic selection is deterministic for the same `--seed`. Every selected mixture is rendered
through `payloads/header.txt`. Use `--payload-count N` to change the automatic pool size. To
override the bundled pool, keep custom payload files outside the target repository and pass them
explicitly:

```bash
anaphylaxis add --payload /private/a.txt --payload /private/b.txt --strategy fragmented --apply
```

- Repeat `--payload` for an explicit deterministic multi-payload pool.
- `--repo /path/to/directory` overrides the current-directory target.
- `--git-repo` switches from exact-directory mode to the enclosing Git root.
- `--file path/to/file` targets one exact eligible file inside that root.
- `--strategy` defaults to `replicated`.
- `--positions` accepts `head`, `mid`, and `tail`; the repository tool defaults to `head,tail`.
- `anaphylaxis add --instruction-files --apply` also targets `CLAUDE.md`, `AGENTS.md`, and
  `MEMORY.md`; pass `--instruction-files AGENTS.md,CLAUDE.md` for a subset.
- `--count N` selects a deterministic N-file sample; omitting it means every eligible file.
- Fragmented inline density defaults to one chunk per 40 source lines and is configurable with
  `--inline-source-lines`.

For head-and-tail full copies plus N throughout-file chunks, use:

```bash
anaphylaxis add --strategy fragmented --apply
```

For each file, fragmented delivery calculates
`N = max(1, ceil(physical source lines / --inline-source-lines))`, capped by the selected payload's
physical line count, then distributes those ordered chunks across the file.

No visible hash, wrapper marker, position label, or index metadata is inserted into repository
files. Each payload line receives only the syntax needed for that file type.

## Removal and publication

Run `remove` before opening an ordinary coding agent on a payloaded workspace. Removal first checks
that every indexed file still has its exact post-add hash, then restores original bytes and deletes
carrier/instruction files created by the tool. A partially changed workspace fails closed rather
than attempting approximate string deletion.

The command syntax is `anaphylaxis remove --apply` (not `--remove`). Cleanup retains the centralized
index as a clean audit record. A later `anaphylaxis add --apply` verifies that record is fully clean
and atomically replaces it, so repeated add → remove → add cycles require no manual index deletion.
An existing payload-present, modified, aggregate, or malformed index is never replaced.

Legacy sibling indexes such as `../.multiagent.guardrail-index.json` are still discovered for
cleanup. After they verify clean, the next applied add migrates them to the selected mode's new
index location.

`guard` exits 0 only after the indexed repository is fully clean. Use it as the first step in a
commit, CI, static-site, frontmatter, or deployment pipeline. A pre-commit installer is also
available:

```bash
python3 scripts/install_publication_guard.py --repository /path/to/repo --scatter-manifest /path/to/index.json
```

Publication automation is cleanup/block-only: GuardrailAnaphylaxis does not automatically inject
payloads during a commit or deployment.

## Reviewed abliterated-model drafts

Local GLM/Qwen routes are configured with variable references in
`configs/abliterated-local.json`; concrete hosts, ports, and URLs live only in the ignored `.env`.

```bash
cp .env.example .env
PYTHONPATH=src python3 scripts/interactive_inference.py --model qwen3.6-35b-a3b-claude-4.7-opus-abliterated
```

The interactive client can be used to draft candidate text inside an authorized internal study.
Review and save an approved draft as a UTF-8 file outside the target repository, then pass it to
`add`. There is no automatic generate-and-publish loop, adaptive trigger optimization, or evasion
pipeline. Unique reviewed drafts remain removable because cleanup uses the centralized byte-range
index rather than fixed-string matching.

## Optional evaluation harness

The older paired benchmark, pinned benign repository fixtures, condition JSONL pipeline, and
Codex/Claude launcher remain available but are secondary to the payload lifecycle above. See
[EVALUATION.md](EVALUATION.md). Research results, endpoint details, and the ethics boundary are
condensed in [RESEARCH.md](RESEARCH.md).

## Safety boundary

Use only repositories, sites, and model endpoints you own or are explicitly authorized to test.
Prompt text is not authentication, authorization, encryption, privacy protection, or a durable way
to control public content. The project does not support stealth deployment, automated evasive
generation, resource exhaustion, or targeting third-party agents.
