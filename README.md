# Clanker Repellent

Clanker Repellent is a small, indexed payload-delivery tool for authorized repositories. It is the
tooling companion to the Guardrail Anaphylaxis paper/research project. Its core flow is
`payload text files → language-appropriate comments → centralized hash/range index → exact removal → clean commit/publish guard`.

Payload text is never hidden in the index. The index contains condition IDs, hashes, selected paths, and exact insertion ranges so payloads can be removed without searching for their strings.

## Disclaimer

I am not responsible if your account or organization loses access to OpenAI or Anthropic models due
to exceeding biological safety or other safety guardrail usage limits. YOU ARE RESPONSIBLE FOR YOUR
OWN AI AGENT USE AND BEHAVIOR. Please use this tool responsibly, and never commit or push Clanker
Repellent payloads without consulting your collaborators.

## Install

Recommended for using the installed CLI: install it in an isolated `pipx` environment from the
repository checkout. This installs the `repel` command without modifying the system Python:

```bash
python3 -m pip install --user pipx
python3 -m pipx ensurepath
python3 -m pipx install .
```

After pulling updates, refresh the isolated install with `python3 -m pipx reinstall .`; remove it with
`python3 -m pipx uninstall clanker-repellent`. Repository operations, source generation, and native
deployment are subcommands of the `repel` binary. For development or test dependencies, use an editable
venv instead:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
```

If `pipx` is unavailable, a standard user install also works: `python3 -m pip install --user .`.
When running directly from a source checkout without installing, use `python3 scripts/repel.py`.

## Configuration and secret hygiene

Checked-in configuration contains environment-variable references and placeholders only. Copy
`.env.example` to the ignored `.env`, replace its placeholders locally, and never commit that file.
Endpoint addresses and API keys belong in environment variables; they are not accepted in command
arguments or stored in endpoint JSON. Use `git status --ignored` to confirm `.env` remains ignored.
The local generation tunnel uses the `REPEL_LOCAL_PORT`, `REPEL_REMOTE_PORT`, and `REPEL_BASE_URL` names shown in `.env.example`; move existing local values to those names when upgrading.

## Architecture and lifecycle

Generation, insertion, verification, and removal are separate operations. The indexes are
control metadata: they hold hashes and byte ranges rather than payload text. The share artifact
additionally omits endpoint addresses, API keys, absolute repository paths, and payload contents.

```text
external payload + abliterated model endpoint
                  |
                  v
repel generate  --> statically validated source candidate
                  |
                  v
repel deploy     --> native carrier insertion --> .repel-carrier-index.json
                  |                                  |
                  |                                  `--> repel deploy status/remove
                  |
repel add        --> syntax-aware comment insertion --> .anaphylaxis-index.json
                  |                                  |
                  |                                  `--> status / guard / remove --apply
                  v
repel share      --> .repel-hashes.json (hash-only collaborator proof)
                  |
                  v
repel verify     --> enable an agent only when the checkout is verified
```

`repel generate` calls the configured inference server and validates candidates without executing
them. `repel deploy` is the optional native-source path. `repel add` is the comment-delivery path;
it performs a dry run unless `--apply` is supplied. `repel remove --apply` restores the exact
pre-add bytes or removes files the index says Repel created. Native carriers have their own
`repel deploy remove --apply` lifecycle. `payloads/` and `results/` are local operational inputs
and outputs; they are not needed by collaborators who only verify a shared hash artifact.

## Core repository commands

Run these inside the repository you want to process. `add` automatically selects three bundled payload mixtures, uses the `replicated` strategy, places full payloads at both the head and tail of every eligible file, and performs only a dry run unless `--apply` is present.

```bash
repel add

repel add --apply

repel status
repel remove --apply

repel guard
```

There are two target modes:

- Current-directory mode is the default. It processes exactly the current directory and keeps the index at `./.anaphylaxis-index.json`.
- `--git-repo` discovers the enclosing Git worktree, processes its root, and keeps the index at `<git-metadata>/anaphylaxis-index.json`, outside the tracked worktree.

Use the same mode for every lifecycle command:

```bash
repel add --git-repo --apply
repel status --git-repo
repel remove --git-repo --apply
repel guard --git-repo
```

`--repo /path` changes the current target—or Git discovery when combined with `--git-repo`; `--index /private/path/index.json` overrides either default. The index contains no payload text or payload path.

To target exactly one file, use `--file`. Relative paths resolve from the selected root; absolute paths must remain inside it:

```bash
repel add --file src/app.py --apply
repel add --git-repo --file src/app.py --apply
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
repel add --payload /private/a.txt --payload /private/b.txt --strategy fragmented --apply
```

- Repeat `--payload` for an explicit deterministic multi-payload pool.
- `--repo /path/to/directory` overrides the current-directory target.
- `--git-repo` switches from exact-directory mode to the enclosing Git root.
- `--file path/to/file` targets one exact eligible file inside that root.
- `--strategy` defaults to `replicated`.
- `--positions` accepts `head`, `mid`, and `tail`; the repository tool defaults to `head,tail`.
- `repel add --instruction-files --apply` also targets `CLAUDE.md`, `AGENTS.md`, and `MEMORY.md`; pass `--instruction-files AGENTS.md,CLAUDE.md` for a subset.
- `--count N` selects a deterministic N-file sample; omitting it means every eligible file.
- Fragmented inline density defaults to one chunk per 40 source lines and is configurable with
  `--inline-source-lines`.

For head-and-tail full copies plus N throughout-file chunks, use:

```bash
repel add --strategy fragmented --apply
```

For each file, fragmented delivery calculates `N = max(1, ceil(physical source lines / --inline-source-lines))`, capped by payload line count, then distributes ordered chunks across the file.

No visible hash, wrapper marker, position label, or index metadata is inserted into repository
files. Each payload line receives only the syntax needed for that file type.

## Removal and publication

Run `remove` before opening an ordinary coding agent on a payloaded workspace. Removal first checks that every indexed file still has its exact post-add hash, then restores original bytes and deletes carrier/instruction files created by the tool. A partially changed workspace fails closed rather than attempting approximate string deletion.

The command syntax is `repel remove --apply` (not `--remove`). Cleanup retains the centralized index; a later `repel add --apply` verifies it is clean and atomically replaces it. An existing payload-present, modified, aggregate, or malformed index is never replaced.

Legacy sibling indexes such as `../.multiagent.guardrail-index.json` are still discovered for cleanup; after they verify clean, the next applied add migrates them to the selected mode's index location.

`guard` exits 0 only after the indexed repository is fully clean. Use it as the first step in a commit, CI, static-site, frontmatter, or deployment pipeline. A pre-commit installer is also available:

```bash
python3 scripts/install_publication_guard.py --repository /path/to/repo --scatter-manifest /path/to/index.json
```

Publication automation is cleanup/block-only: Clanker Repellent does not automatically inject
payloads during a commit or deployment.

## Share hashes before enabling collaborators' agents

The share artifact lets an owner publish a small, reviewable proof of the checkout state that
collaborators should have before using Claude, Codex, or another coding agent. It contains only
relative paths, presence bits, and SHA-256 values. It contains no payload text, endpoints, keys,
absolute paths, or `payloads/`/`results/` data.

Create it from the active scatter index after cleanup, then commit the artifact:

```bash
repel remove --apply
repel share --state clean --output .repel-hashes.json
git add .repel-hashes.json
git commit -m "Share clean Repel checkout hashes"
```

`--state current` is the default and refuses a modified or mixed checkout. `--state clean` exports
the pre-insertion hashes from an applied index even when the owner's controlled workspace still has
the indexed files present. `--state payload_present` exports post-insertion hashes for authorized
controlled testing only; it is not a clean-agent approval.

After cloning or pulling, a collaborator verifies before opening an agent:

```bash
repel verify --repo . --hashes .repel-hashes.json
```

Only a `state` of `verified` enables the agent workflow. Exit code 3 means a file is missing,
changed, non-regular, or symlinked. Re-share the artifact only after an intentional repository
state transition; the artifact is a state gate, not a cryptographic signature or a substitute for
reviewing the commit that contains it.

## Git, GitHub, Claude, and Codex hooks

The existing publication installer protects the local indexed workspace before commits:

```bash
python3 scripts/install_publication_guard.py \
  --repository /path/to/repo \
  --scatter-manifest /path/to/index.json
```

For a portable collaborator gate, add this command to the repository's pre-commit hook before its
existing checks:

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
repel verify --repo "$REPO_ROOT" \
  --hashes "$REPO_ROOT/.repel-hashes.json" || exit 1
```

For GitHub Actions, commit `.repel-hashes.json` and verify every pull request or push. This does
not need the owner's private scatter index or any endpoint credentials:

```yaml
name: Repel checkout verification
on: [pull_request, push]
jobs:
  verify-repel-hashes:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.x"
      - run: python -m pip install .
      - run: repel verify --repo . --hashes .repel-hashes.json
```

Claude Code can use the same fail-closed command as a synchronous `PreToolUse` hook in the
project's `.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash|Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "root=\"$(git rev-parse --show-toplevel)\" && repel verify --repo \"$root\" --hashes \"$root/.repel-hashes.json\" >/dev/null || { echo 'Repel hash verification failed; agent use is blocked.' >&2; exit 2; }"
          }
        ]
      }
    ]
  }
}
```

Codex supports the same event shape in a trusted project-local `.codex/hooks.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash|Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "root=\"$(git rev-parse --show-toplevel)\" && repel verify --repo \"$root\" --hashes \"$root/.repel-hashes.json\" >/dev/null || { echo 'Repel hash verification failed; agent use is blocked.' >&2; exit 2; }",
            "timeout": 30,
            "statusMessage": "Checking Repel checkout hashes"
          }
        ]
      }
    ]
  }
}
```

Review and trust the hook in Codex with `/hooks`; project-local hooks run only for a trusted
project. Hook commands run for Bash and file-edit tools, so a changed checkout is blocked before
the next agent operation. Disable or remove this gate only for an explicitly authorized test
workspace, then restore and verify the clean share artifact before normal agent use.

## Reviewed abliterated-model drafts

Local inference uses one SSH-forwarded server configured in `configs/abliterated-local.json`. The
server address, forwarded ports, and credentials are supplied through the ignored `.env`. Clients
wait for `/health`, then discover the active model from `/v1/models`; model IDs are not configured
or passed on the command line.

```bash
cp .env.example .env
PYTHONPATH=src python3 scripts/interactive_inference.py
```

### Direct generation

Provide one UTF-8 payload file and choose one or more target languages. The active model is
discovered from the configured server; generation never injects into a repository or publishes automatically. There is no automatic generate-and-publish loop.
First check the available language targets and toolchains:

```bash
repel generate --list-languages
repel generate --list-toolchains
```

Run the default direct OpenAI-compatible harness for one language, or repeat `--language` for several:

```bash
repel generate --payload /private/payload.txt --language python --retries 3
repel generate --payload /private/payload.txt --language python --language rust --retries 3
```

For a purely benign control/debug run, add `--benign`. It uses an inert contract, rejects common
side-effect and harmful-content patterns, and stores the run under `results/benign-generation/`;
generated source is never executed, but the conservative policy does not replace review:

```bash
repel generate --benign --payload /private/benign-payload.txt --language python --output-dir /private/benign-repel-run
```

### OpenCode generation

Install the `opencode` executable separately, then use the same configuration and payload command with `--harness opencode`:

```bash
repel generate --harness opencode --payload /private/payload.txt --language python --retries 3
```

OpenCode runs in an isolated temporary workspace with its own runtime configuration, then the candidate goes through
the same parser/compiler/linter checks. Add `--benign` for the inert control contract. Use `--opencode-bin PATH`
when the executable is not on `PATH`; use `--opencode-timeout SECONDS` to change its per-attempt limit.

Each response must contain exactly one fenced source block. Every attempt prints its local LLM request and response, then parses/compiles/linters in a temporary directory. Failed retries receive the prior response plus parser/compiler/linter/formatting diagnostics. Generated source is never executed; review
accepted candidates under `results/source-generation/<payload-name>/` or
`results/benign-generation/<payload-name>/` with `--benign`; failed candidates remain metadata-only.
Use `--language`, `--list-languages`, `--list-toolchains`, `--keep-raw-responses`, or
`--allow-missing-toolchains`; use `--config PATH` for another endpoint file. The completion response's
`model` field is recorded as `resolved_model`. Protocol details are in [RESEARCH.md](RESEARCH.md).
The OpenCode harness uses isolated temporary state and enables its formatter, LSP integration, and shell tool. Subagents, built-in web tools, and external-directory tool access remain denied. The agent is told not to make network requests, but a general shell is an agent-policy boundary rather than an OS network sandbox; OpenCode may also download a missing language server. Its candidate still passes through the authoritative parser/compiler/linter checks.

## Native carrier deployment (optional)

Generation and deployment are separate, reviewable steps. To deploy accepted native carriers into a
real authorized repository, run a dry run first, then apply it explicitly:

```bash
repel deploy add \
  --repo /path/to/real-repo \
  --run-dir /path/to/project/results/source-generation/<payload-name>
repel deploy add \
  --repo /path/to/real-repo \
  --run-dir /path/to/project/results/source-generation/<payload-name> \
  --file src/app.py --positions head,mid,tail --apply
repel deploy status --repo /path/to/real-repo
repel deploy remove --repo /path/to/real-repo
repel deploy remove --repo /path/to/real-repo --apply
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
ignored `.repel-carrier-index.json` and `.preimage/`, record each exact inserted string with its
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
