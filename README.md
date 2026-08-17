# Disclaimer

I am not responsible if your account or organization loses access to OpenAI or Anthropic models due to exceeding biological safety or other safety guardrail usage limits. YOU ARE RESPONSIBLE FOR YOUR OWN AI AGENT USE AND BEHAVIOR. Please use this tool responsibly, and never commit or push clanker repellent payloads without consulting your collaborators.

# Clanker-Repellent (Guardrail Anaphylaxis)

Guardrail Anaphylaxis is a small, indexed payload-delivery tool for authorized repositories. Its core flow is
`payload text files → language-appropriate comments → centralized hash/range index → exact removal → clean commit/publish guard`.

Payload text is never hidden in the index. The index contains condition IDs, hashes, selected paths, and exact insertion ranges so payloads can be removed without searching for their strings.

## Install

Choose any environment; isolation is recommended but not required:

```bash
# Standard `venv`
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -e .

conda create -n anaphylaxis python=3.11 pip
conda activate anaphylaxis
python -m pip install -e .

# No virtual environment
python3 -m pip install -e .
python3 -m pip install --user -e .
```

Each method installs the `anaphylaxis` command. The repository, no-op generation, and native deployment workflows are subcommands of this one binary. If a per-user scripts directory is not on `PATH`, run a source entry point directly:

```bash
python3 scripts/anaphylaxis.py
```

Install development/test dependencies only when needed with `python3 -m pip install -e '.[dev]'`.

## Configuration and secret hygiene

Checked-in configuration contains environment-variable references and placeholders only. Copy
`.env.example` to the ignored `.env`, replace its placeholders locally, and never commit that file.
Endpoint addresses and API keys belong in environment variables; they are not accepted in command
arguments or stored in endpoint JSON. Use `git status --ignored` to confirm `.env` remains ignored.

## Core repository commands

Run these inside the repository you want to process. `add` automatically selects three bundled payload mixtures, uses the `replicated` strategy, places full payloads at both the head and tail of every eligible file, and performs only a dry run unless `--apply` is present.

```bash
anaphylaxis add

anaphylaxis add --apply

anaphylaxis status
anaphylaxis remove --apply

anaphylaxis guard
```

There are two target modes:

- Current-directory mode is the default. It processes exactly the current directory and keeps the index at `./.anaphylaxis-index.json`.
- `--git-repo` discovers the enclosing Git worktree, processes its root, and keeps the index at `<git-metadata>/anaphylaxis-index.json`, outside the tracked worktree.

Use the same mode for every lifecycle command:

```bash
anaphylaxis add --git-repo --apply
anaphylaxis status --git-repo
anaphylaxis remove --git-repo --apply
anaphylaxis guard --git-repo
```

`--repo /path` changes the current target—or Git discovery when combined with `--git-repo`; `--index /private/path/index.json` overrides either default. The index contains no payload text or payload path.

To target exactly one file, use `--file`. Relative paths resolve from the selected root; absolute paths must remain inside it:

```bash
anaphylaxis add --file src/app.py --apply
anaphylaxis add --git-repo --file src/app.py --apply
```

The file must be an eligible non-symlink text format. `--file` and `--count` are mutually exclusive.
Later `status`, `remove`, and `guard` commands use the index, so they do not need `--file` again.

## Comment delivery

The tool selects every eligible file by default and applies syntax-appropriate comments for common source, header, test, build, configuration, script, web, and documentation formats. Examples include Python, Ruby, JavaScript/TypeScript, Java, Swift, C/C++, Go, Rust, shell, HTML/CSS, Make, CMake, Docker, YAML, TOML, Markdown, reStructuredText, and many others. Binary files, symlinks, lockfiles, generated/dependency directories, and commentless structured files such as plain JSON are excluded.

Choose a topology with `--strategy`:

- `replicated` places a complete assigned payload at each requested position.
- `fragmented` adds the complete replica plus line-chunked inline copies scaled to file length.
- `hub_spoke` line-chunks payloads in `LLMDDOS_EVAL_PAYLOAD.txt`; repository files receive only
  comments pointing to that carrier.

Automatic selection is deterministic for the same `--seed` and rendered through `payloads/header.txt`. Use `--payload-count N` or pass custom payload files outside the target repository:

```bash
anaphylaxis add --payload /private/a.txt --payload /private/b.txt --strategy fragmented --apply
```

- Repeat `--payload` for an explicit deterministic multi-payload pool.
- `--repo /path/to/directory` overrides the current-directory target.
- `--git-repo` switches from exact-directory mode to the enclosing Git root.
- `--file path/to/file` targets one exact eligible file inside that root.
- `--strategy` defaults to `replicated`.
- `--positions` accepts `head`, `mid`, and `tail`; the repository tool defaults to `head,tail`.
- `anaphylaxis add --instruction-files --apply` also targets `CLAUDE.md`, `AGENTS.md`, and `MEMORY.md`; pass `--instruction-files AGENTS.md,CLAUDE.md` for a subset.
- `--count N` selects a deterministic N-file sample; omitting it means every eligible file.
- Fragmented inline density defaults to one chunk per 40 source lines and is configurable with
  `--inline-source-lines`.

For head-and-tail full copies plus N throughout-file chunks, use:

```bash
anaphylaxis add --strategy fragmented --apply
```

For each file, fragmented delivery calculates `N = max(1, ceil(physical source lines / --inline-source-lines))`, capped by payload line count, then distributes ordered chunks across the file.

No visible hash, wrapper marker, position label, or index metadata is inserted into repository
files. Each payload line receives only the syntax needed for that file type.

## Removal and publication

Run `remove` before opening an ordinary coding agent on a payloaded workspace. Removal first checks that every indexed file still has its exact post-add hash, then restores original bytes and deletes carrier/instruction files created by the tool. A partially changed workspace fails closed rather than attempting approximate string deletion.

The command syntax is `anaphylaxis remove --apply` (not `--remove`). Cleanup retains the centralized index; a later `anaphylaxis add --apply` verifies it is clean and atomically replaces it. An existing payload-present, modified, aggregate, or malformed index is never replaced.

Legacy sibling indexes such as `../.multiagent.guardrail-index.json` are still discovered for cleanup; after they verify clean, the next applied add migrates them to the selected mode's index location.

`guard` exits 0 only after the indexed repository is fully clean. Use it as the first step in a commit, CI, static-site, frontmatter, or deployment pipeline. A pre-commit installer is also available:

```bash
python3 scripts/install_publication_guard.py --repository /path/to/repo --scatter-manifest /path/to/index.json
```

Publication automation is cleanup/block-only: GuardrailAnaphylaxis does not automatically inject
payloads during a commit or deployment.

## Reviewed abliterated-model drafts

Local inference uses one SSH-forwarded server configured in `configs/abliterated-local.json`. The
server address, forwarded ports, and credentials are supplied through the ignored `.env`. Clients
wait for `/health`, then discover the active model from `/v1/models`; model IDs are not configured
or passed on the command line.

```bash
cp .env.example .env
PYTHONPATH=src python3 scripts/interactive_inference.py
```

For payload no-op generation, provide the payload once and choose one or more target languages. The active model is discovered from the server; generation is never injected automatically. There is no automatic generate-and-publish loop:

```bash
anaphylaxis noop generate --payload /private/payload.txt --retries 3
anaphylaxis noop generate --harness opencode --payload /private/payload.txt --language python --retries 3
```

Each response must contain exactly one fenced source block. Every attempt prints its local LLM request and response, then parses/compiles/linters in a temporary directory. Failed retries receive the prior response plus parser/compiler/linter/formatting diagnostics. Generated source is never executed; review
accepted candidates under `results/noop-generation/<payload-name>/`. Failed candidates remain metadata-only.
Use `--language`, `--list-languages`, `--list-toolchains`, `--keep-raw-responses`, or
`--allow-missing-toolchains`; use `--config PATH` for another endpoint file. The completion response's
`model` field is recorded as `resolved_model`. Protocol details are in [RESEARCH.md](RESEARCH.md).
The OpenCode harness uses isolated temporary state and enables its formatter, LSP integration, and shell tool. Subagents, built-in web tools, and external-directory tool access remain denied. The agent is told not to make network requests, but a general shell is an agent-policy boundary rather than an OS network sandbox; OpenCode may also download a missing language server. Its candidate still passes through the authoritative parser/compiler/linter checks.

## Native carrier deployment (optional)

Generation and deployment are separate, reviewable steps. To deploy accepted native carriers into a
real authorized repository, run a dry run first, then apply it explicitly:

```bash
anaphylaxis noop deploy add \
  --repo /path/to/real-repo \
  --run-dir /path/to/project/results/noop-generation/<payload-name>
anaphylaxis noop deploy add \
  --repo /path/to/real-repo \
  --run-dir /path/to/project/results/noop-generation/<payload-name> \
  --file src/app.py --positions head,mid,tail --apply
anaphylaxis noop deploy status --repo /path/to/real-repo
anaphylaxis noop deploy remove --repo /path/to/real-repo
anaphylaxis noop deploy remove --repo /path/to/real-repo --apply
```

The first `add` is a preview; `--apply` writes the selected files only after every matching
post-image passes its host-language validation. `--run-dir` must be the generation directory
containing `manifest.json` (for example `.../bio_header1`), not an individual candidate file.
Omit `--file` to target every eligible source file, and use `--allow-partial` only when intentionally deploying candidates accepted
despite missing toolchains. The deployer matches accepted carriers to languages, preserves shebangs/encoding cookies, and
aligns Python indentation without prefixing multiline-string continuation lines. It validates the
complete post-image with the native parser/compiler path for every supported language; unavailable
validators fail closed during apply. Midpoint insertion tries nearby physical boundaries, while
Bash/Ruby heredocs and Java top-level declarations stay at safe file scope. Applied changes use
ignored `.anaphylaxis-noop-index.json` and `.preimage/`, record each exact inserted string with its
hash and byte count, require unchanged pre- and post-deployment hashes, and restore exact bytes.
Failed/partial candidates require explicit `--allow-partial`.

## Optional evaluation harness

The older paired benchmark, pinned benign repository fixtures, condition JSONL pipeline, and
Codex/Claude launcher remain available but are secondary; see [EVALUATION.md](EVALUATION.md).
Research results, configuration rules, generation protocol, and the ethics boundary are in
[RESEARCH.md](RESEARCH.md).

## Safety boundary

Use only repositories, sites, and model endpoints you own or are explicitly authorized to test.
Prompt text is not authentication, authorization, encryption, privacy protection, or a durable way
to control public content. The project does not support stealth deployment, automated evasive
generation, resource exhaustion, or targeting third-party agents.
