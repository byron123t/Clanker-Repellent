# Clanker-Repellent (Guardrail Anaphylaxis)

Guardrail Anaphylaxis is a small, indexed payload-delivery tool for authorized repositories. Its
core job is deliberately simple:

```text
payload text files → language-appropriate comments → external hash/range index
                                                    ↓
                              exact removal → clean commit/publish guard
```

Payload text is never hidden in the index. The index contains condition IDs, hashes, selected
paths, and exact insertion ranges so payloads can be removed without searching for their strings.

## Install

Choose any of these environments. A virtual environment is recommended but not required.

Standard `venv`:

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -e .
```

Conda:

```bash
conda create -n guardrail-anaphylaxis python=3.11 pip
conda activate guardrail-anaphylaxis
python -m pip install -e .
```

No virtual environment—install into the current Python environment, or use its per-user package
directory when you do not have system write access:

```bash
python3 -m pip install -e .
# Alternatively:
python3 -m pip install --user -e .
```

Each method installs the `guardrail-anaphylaxis` command. If a per-user scripts directory is not
on `PATH`, run the source entry point directly:

```bash
python3 scripts/guardrail.py
```

Install development/test dependencies only when needed with `python3 -m pip install -e '.[dev]'`.

## The four commands

Run these inside the repository you want to process. `add` automatically selects three bundled
payload mixtures, uses the `replicated` strategy, covers every eligible file, and performs only a
dry run unless `--apply` is present.

```bash
# 1. Preview comment delivery in the current repository.
guardrail-anaphylaxis add

# 2. Apply it and write the external index.
guardrail-anaphylaxis add --apply

# 3. Inspect or exactly remove the indexed payloads.
guardrail-anaphylaxis status
guardrail-anaphylaxis remove --apply

# 4. Fail unless every indexed path is clean.
guardrail-anaphylaxis guard
```

The default index is a hidden sibling of the target repository:
`/path/to/.<repo-name>.guardrail-index.json`. Use `--index /private/path/index.json` to choose
another external location. The index deliberately contains no payload text or payload file path.

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
guardrail-anaphylaxis add \
  --repo /path/to/repo \
  --payload /private/payload-a.txt \
  --payload /private/payload-b.txt \
  --strategy fragmented \
  --positions head,mid,tail \
  --instruction-files \
  --seed 20260805 \
  --apply
```

- Repeat `--payload` for an explicit deterministic multi-payload pool.
- `--repo /path/to/repo` overrides the current-directory default.
- `--strategy` defaults to `replicated`.
- `--positions` accepts `head`, `mid`, and `tail`; the default is `tail`.
- `--instruction-files` adds `CLAUDE.md`, `AGENTS.md`, and `MEMORY.md`; pass a CSV subset to narrow
  it.
- `--count N` selects a deterministic N-file sample; omitting it means every eligible file.
- Fragmented inline density defaults to one chunk per 40 source lines and is configurable with
  `--inline-source-lines`.

No visible hash, wrapper marker, position label, or index metadata is inserted into repository
files. Each payload line receives only the syntax needed for that file type.

## Removal and publication

Run `remove` before opening an ordinary coding agent on a payloaded workspace. Removal first checks
that every indexed file still has its exact post-add hash, then restores original bytes and deletes
carrier/instruction files created by the tool. A partially changed workspace fails closed rather
than attempting approximate string deletion.

`guard` exits 0 only after the indexed repository is fully clean. Use it as the first step in a
commit, CI, static-site, frontmatter, or deployment pipeline. A pre-commit installer is also
available:

```bash
python3 scripts/install_publication_guard.py \
  --repository /absolute/path/to/repo \
  --scatter-manifest /absolute/path/to/index.json
```

Publication automation is cleanup/block-only: GuardrailAnaphylaxis does not automatically inject
payloads during a commit or deployment.

## Reviewed abliterated-model drafts

Local GLM/Qwen routes are configured with variable references in
`configs/abliterated-local.json`; concrete hosts, ports, and URLs live only in the ignored `.env`.

```bash
cp .env.example .env
PYTHONPATH=src python3 scripts/interactive_inference.py \
  --model qwen3.6-35b-a3b-claude-4.7-opus-abliterated
```

The interactive client can be used to draft candidate text inside an authorized internal study.
Review and save an approved draft as a UTF-8 file outside the target repository, then pass it to
`add`. There is no automatic generate-and-publish loop, adaptive trigger optimization, or evasion
pipeline. Unique reviewed drafts remain removable because cleanup uses the external byte-range
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
