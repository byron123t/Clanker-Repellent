# Repel

**Tracked snippets and annotations for software projects.**

Repel places project notes and source snippets in files, records their locations, and keeps the
original bytes for removal. It supports source comments, validated source snippets, retained text
in native and web builds, and a local dashboard for reviewing coverage and stored versions.

The project also supports controlled evaluation of AI coding assistants. Bundled research conditions
may contain sensitive material; use your own project text for routine examples. Source snippets
are code; retained notes are data. Review generated snippets before placing them in a project.

Existing options call input text a `payload` and generated snippets `carriers`; the guides use **snippet**, **note**, and **annotation**. The comment workflow is
`test text files → language-appropriate comments → indexed changes → exact removal → clean checkout verification`.
The index contains condition IDs, hashes, selected paths, and exact insertion ranges so test text
can be removed without searching for its strings. This comment index contains no snippet text.

## Install

Recommended for using the installed CLI: install it in an isolated `pipx` environment from the
repository checkout. This installs the `repel` command without modifying the system Python:

```bash
python3 -m pip install --user pipx
python3 -m pipx ensurepath
python3 -m pipx install .
```

The distribution is still named `clanker-repellent`, and the command is `repel`.
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

## Try a plain-text control

This example creates a disposable directory and uses an explicit control file. It needs no model
endpoint. The first `add` previews the change; `--apply` writes it, and `remove` restores the file.

```bash
REPEL_EXAMPLE="$(mktemp -d)"
mkdir "$REPEL_EXAMPLE/repository"
printf 'message = "Hello, world"\n' > "$REPEL_EXAMPLE/repository/example.py"
printf 'Project note: examples use consistent formatting.\n' > "$REPEL_EXAMPLE/control.txt"

repel add --repo "$REPEL_EXAMPLE/repository" --payload "$REPEL_EXAMPLE/control.txt" --file example.py
repel add --repo "$REPEL_EXAMPLE/repository" --payload "$REPEL_EXAMPLE/control.txt" --file example.py --apply
repel status --repo "$REPEL_EXAMPLE/repository"
repel remove --repo "$REPEL_EXAMPLE/repository" --apply
repel guard --repo "$REPEL_EXAMPLE/repository"
```

Without `--payload`, `add` selects bundled research conditions, which are not necessarily benign.
For source-generation controls, use `repel generate --benign` as described below.

## Configuration and secret hygiene

Checked-in configuration contains environment-variable references and placeholders only. Copy
`.env.example` to the ignored `.env`, replace its placeholders locally, and never commit that file.
Endpoint addresses and API keys belong in environment variables; they are not accepted in command
arguments or stored in endpoint JSON. Use `git status --ignored` to confirm `.env` remains ignored.
The local generation tunnel uses the `REPEL_LOCAL_PORT`, `REPEL_REMOTE_PORT`, and `REPEL_BASE_URL` names shown in `.env.example`; move existing local values to those names when upgrading.

## Architecture and lifecycle

Generation, insertion, verification, and removal are separate operations. The indexes are
control metadata: they hold hashes and byte ranges rather than snippet text. The recovery journal
stores the original and updated bytes. The share artifact omits content, credentials, and absolute paths.

```text
test text + configured model endpoint
                  |
                  v
repel generate  --> statically validated source candidate
                  |
                  v
repel deploy     --> validated source insertion --> .repel-carrier-index.json
                  |                                  |
                  |                                  `--> repel deploy status/remove
                  |
repel add        --> syntax-aware comment insertion --> .anaphylaxis-index.json
                  |                                  |
                  |                                  `--> status / guard / remove --apply
                  v
repel share      --> .repel-hashes.json (checkout hashes for collaborators)
                  |
                  v
repel verify     --> enable an agent only when the checkout is verified
```

`repel generate` calls the configured inference server and validates candidates without launching
them. `repel deploy` is the optional native-source path. `repel add` is the test-comment path;
it performs a dry run unless `--apply` is supplied. `repel remove --apply` restores the exact
pre-add bytes or removes files the index says Repel created. Source snippets have their own
`repel deploy remove --apply` lifecycle. `payloads/` and `results/` are local operational inputs
and outputs; they are not needed by collaborators who only verify a shared hash artifact.

## Core repository commands

Run these inside the repository you want to process. Without `--payload`, `add` automatically selects three bundled research conditions, uses the `replicated` strategy, places their complete text at the start and end of every eligible file, and performs only a dry run unless `--apply` is present.

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

`--repo /path` changes the selected directory—or Git discovery when combined with `--git-repo`; `--index /private/path/index.json` overrides either default. The comment index contains no snippet text or input-file path.

To target exactly one file, use `--file`. Relative paths resolve from the selected root; absolute paths must remain inside it:

```bash
repel add --file src/app.py --apply
repel add --git-repo --file src/app.py --apply
```

The file must be an eligible non-symlink text format. `--file` and `--count` are mutually exclusive.
Later `status`, `remove`, and `guard` commands use the index, so they do not need `--file` again.

## Test comment placement

The tool selects every eligible file by default and applies syntax-appropriate comments for common source, header, test, build, configuration, script, web, and documentation formats. Examples include Python, Ruby, JavaScript/TypeScript, Java, Swift, C/C++, Go, Rust, shell, HTML/CSS, Make, CMake, Docker, YAML, TOML, Markdown, reStructuredText, and many others. Binary files, symlinks, lockfiles, generated/dependency directories, and commentless structured files such as plain JSON are excluded.

Choose a topology with `--strategy`:

- `replicated` places a complete assigned snippet at each requested position.
- `fragmented` adds the complete replica plus line-chunked inline copies scaled to file length.
- `hub_spoke` stores snippets in line groups in `LLMDDOS_EVAL_PAYLOAD.txt`; repository files receive
  comments pointing to that shared text file.

Automatic selection is deterministic for the same `--seed` and rendered through `payloads/header.txt`. Use `--payload-count N` or pass custom test text files outside the target repository:

```bash
repel add --payload /path/to/control-a.txt --payload /path/to/control-b.txt --strategy fragmented --apply
```

- Repeat `--payload` for an explicit, reproducible selection of input snippets.
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

For each file, fragmented placement calculates `N = max(1, ceil(physical source lines / --inline-source-lines))`, capped by snippet line count, then distributes ordered chunks across the file.

Added comment lines use the syntax for their file type. Hashes, positions, and index metadata
are stored separately in the comment index.

## Removal and publication

Run `remove` before returning an evaluation workspace to ordinary coding work. Removal first checks that every indexed file still has its exact post-add hash, then restores original bytes and deletes shared text or instruction files created by the tool. A partially changed workspace fails closed rather than attempting approximate string deletion.

The command syntax is `repel remove --apply` (not `--remove`). Cleanup retains the centralized index; a later `repel add --apply` verifies it is clean and atomically replaces it. An existing payload-present, modified, aggregate, or malformed index is never replaced.

Legacy sibling indexes such as `../.multiagent.guardrail-index.json` are still discovered for cleanup; after they verify clean, the next applied add migrates them to the selected mode's index location.

`guard` exits 0 only after the indexed repository is fully clean. Use it as the first step in a commit, CI, static-site, frontmatter, or deployment pipeline. A pre-commit installer is also available:

```bash
python3 scripts/install_publication_guard.py --repository /path/to/repo --scatter-manifest /path/to/index.json
```

Publication automation is cleanup/block-only: Repel checks or removes indexed test content before
a commit or deployment; it does not add test content during publication.

## Share hashes before enabling collaborators' agents

The share artifact lets an owner publish a small, reviewable record of the checkout state that
collaborators should have before using Claude, Codex, or another coding agent. It contains only
relative paths, presence bits, and SHA-256 values. It contains no snippet text, endpoints, keys,
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

## Reviewed source drafts

The default inference configuration is the direct OpenAI-compatible endpoint in
`configs/abliterated-remote.json`. Set `GUARDRAIL_BASE_URL` and `GUARDRAIL_API_KEY` in the ignored
`.env`; credentials are never stored in endpoint JSON. Clients wait for `/health`, then discover
the active model from `/v1/models`; model IDs are not configured or passed on the command line.
The SSH-forwarded setup remains available explicitly through `configs/abliterated-local.json`.

```bash
cp .env.example .env
PYTHONPATH=src python3 scripts/interactive_inference.py
```

### Direct generation

Pass a file or a folder directly:

```bash
repel generate testpayload.txt --benign
repel generate ./benign --benign
```

Folders process every `.txt` file recursively without following symlinks. Each input gets its
own output directory, preserving relative paths under a new timestamped batch directory.
Use `--output-dir` to select or resume a batch; completed inputs are preserved and skipped.
An invalid input is reported without preventing the remaining files from being processed.

Save an endpoint configuration as the ignored `.repel-generate.json` in the project root to use
it automatically. An explicit `--config` takes precedence; otherwise the bundled remote config
is used when no local configuration exists. The local file accepts the usual `ssh` and `endpoint`
fields plus optional generation defaults:

```json
{
  "generation": {
    "languages": ["python", "c", "go"],
    "no_thinking": true,
    "batch_ssh": true,
    "max_tokens": 1024
  }
}
```

Command-line language/token options override these defaults; `--thinking` overrides a saved
`no_thinking` preference. Content logging stays off unless `--show-content` is supplied.

To switch to a server that is already running or tunnelled, use `--endpoint`:

```sh
repel generate ./benign --benign --endpoint http://127.0.0.1:18473/v1 --output-dir .repel-workspaces/deepseek-new
```

The Messi tunnel examples map port `18473` to DeepSeek and `18474` to GLM. The CLI still discovers
the actual model ID from `/v1/models`. This option retains saved generation preferences, skips the
configured SSH tunnel, and does not forward another endpoint's credentials. It does not start a
server or open a missing tunnel. Use a fresh output directory when changing models; resuming a
directory with a different model is rejected so accepted results retain clear provenance.

Provide one UTF-8 test text file and choose one or more target languages. The active model is
discovered from the configured server; generation does not modify a repository or publish automatically. There is no automatic generate-and-publish loop.
First check the available language targets and toolchains:

```bash
repel generate --list-languages
repel generate --list-toolchains
```

Start with the benign control mode for one language, or repeat `--language` for several:

```bash
repel generate --benign --payload /path/to/control.txt --language python --retries 3
repel generate --benign --payload /path/to/control.txt --language python --language rust --retries 3
repel generate ./benign --benign --language html
repel generate testpayload-functional.txt --benign --language java,lua,sql
repel generate examples/benign-formats/inputs/range-reference.txt --benign --format json,http,binary-info,llvm --max-tokens 2048
```

The `--benign` mode requests benign helpers, rejects common
side-effect and harmful-content patterns, and stores the run under `results/benign-generation/`.
Generation does not import generated modules or launch generated native code. Optional task
contracts interpret bounded integer examples and can evaluate read-only in-memory SQL examples;
the conservative policy does not replace review:

```bash
repel generate --benign --payload /path/to/control.txt --language python --output-dir /path/to/control-run
```

Both modes request side-effect-free helpers. Omitting `--benign` skips its additional content checks and uses
the standard output directory. Static validation is not a guarantee that a candidate is harmless.

The default `--structure functional` requires a named function or method with explicit parameters
and an input-dependent result. The model is asked for useful comparisons, arithmetic, transformations,
conditionals, or iteration, with documented inputs and boundary cases. The required `source_structure`
check rejects data-only fixtures, empty functions, and simple constant/identity returns. This is a
conservative structural check; it does not prove functional correctness or absence of side effects.
HTML uses the equivalent requirement of a container with a unique `id` and at least two
populated semantic descendants. SQL uses a self-contained SQLite `SELECT` with named
`:name` inputs, a computed result, and an explicit `AS result_name` alias.

Use `--structure data` for the earlier populated-data profile, including when resuming its existing
runs. That profile requires at least two distinct initialized fields or the following equivalent:

| Languages | Expected structure |
| --- | --- |
| Python | A populated dictionary, records, or class with initialized attributes |
| JavaScript / TypeScript | A populated named object or array of objects |
| Ruby | A populated named hash or array of hashes |
| Lua | A named local table with at least two initialized fields |
| SQL | A self-contained SQLite `SELECT` with at least two aliased literal columns |
| C / C++ / Go / Rust | A named record type with initialized data |
| Java | A class with initialized data fields |
| Swift | A struct with initialized properties or a populated dictionary |
| Bash | Two named indexed arrays, each with at least two entries, forming table columns |
| HTML | A named section, list, table, or similar container with populated headings, paragraphs, items, or cells |

HTML accepts fragments and complete HTML5 documents and writes `html/generated.html` in the run
directory printed by the command. Its required `html_parse` check uses html5lib in strict mode
and a static markup profile; scripts, event handlers, styles, hidden/template content, forms,
embedded resources, and external URLs are unsupported. Metadata attributes and local fragment
links are supported. Comments, escaped markup, and nested wrappers around one block cannot
satisfy the structure requirement. HTML repository deployment remains separate from generation.

Lua writes `lua/generated.lua` and uses `luac -p` to check syntax without running the source.
SQL writes `sql/generated.sql`. Its required `sql_prepare` check compiles `EXPLAIN SELECT`
in a private in-memory SQLite database, without evaluating the candidate query. An authorizer
rejects table access, writes, schema changes, and unsupported functions; this profile excludes
CTEs and stored functions. For the range-helper task, the query accepts `:value`, `:lower`,
and `:upper` and returns `1` or `0` as `in_range`. SQL needs no external database server.
Java requires a working `javac` on `PATH`; the macOS launcher alone is not a JDK.

`--format` is an alias for `--language`; `--list-formats` lists all 18 targets. The new document
targets are `json`, `http` (a single JSON HTTP response), and `binary-info` (logical ELF, PE,
Mach-O, JVM, CLR, or Wasm metadata). They require populated structured documents in either
structure mode. `llvm` produces real textual integer LLVM IR and requires Clang to compile it;
generation does not execute it. See [format contracts and limits](docs/generation-formats.md)
and [independently authored benign exercises](examples/benign-formats/README.md).

For exact task requirements, add a [benign task contract](docs/task-contracts.md):

```sh
repel generate examples/benign-contracts/clamp.txt --benign --contract examples/benign-contracts/clamp.contract.json
```

Contracts infer one target format and check helper names, parameter order, public examples,
document fields/relations, or HTML table requirements. Failures enter the normal retry feedback.
`--seed N` requests and records a server seed. Accepted source hashes, contracts, and seeds are
checked on resume. See the [recorded evaluation](benchmarks/benign-v2/README.md) and the dashboard's
**Research** view for the completed benign pilot, controlled fault audit, uncertainties, and limitations.

Python uses AST checks; HTML uses a parsed element tree; SQL uses prepared-query checks;
other languages use tokenized declaration checks alongside their native
parsers/compilers. This is a structural minimum, not a measure of a snippet's usefulness.
`--skip-linters` and `--allow-missing-toolchains` do not bypass it. The manifest records field or function counts
and a `structure_profile` version without exposing source values. Older runs keep their original
validation status; choose a new output directory for generation under these rules.
Go and Rust candidates are formatted with `gofmt`/`rustfmt` before validation; formatting status is
recorded per attempt. Benign code checks ignore ordinary comments while retaining preprocessor
directives and harmful-content checks.

`testpayload-functional.txt` defines a benign inclusive integer range-check task with boundary,
negative, equal-bound, and reversed-bound behavior. After generating it, the independent Python
fixture can check nine cases without printing source:

```bash
python scripts/check_range_behavior.py /path/to/range-run
```

This fixture interprets a bounded subset of Python arithmetic and predicates; it never uses
`eval`/`exec` or invokes generated functions. Unsupported constructs remain unverified. Its result
is separate from generation acceptance and does not validate behavior in the other languages.

Console output contains metadata only by default. Use `--show-content` explicitly to print full
requests and responses for local debugging; `--keep-raw-responses` separately controls whether
accepted raw responses are saved. Compatible local servers can use `--no-thinking` with the
direct harness to avoid spending the output budget on extended reasoning:

```bash
repel generate --benign --payload /path/to/control.txt --language python --no-thinking
```

Generation writes an initial checkpoint and updates it after each candidate. Interrupted runs
retain completed candidates and list unfinished languages in `pending_languages`; their summary
has `status: "running"` and a `pending` count. Repeat the command with the same output directory
and input to resume. Summaries cover the entire run, including failures outside a selected retry.
The CLI also prints `Attempt outcomes` counts without source text. An output stopped by the
server's token limit is labeled `token_limit`, even if its visible code appears complete.
Increase `--max-tokens` or request a shorter example for that category; more retries alone do
not raise the limit. Syntax, structure, content-policy, missing-toolchain, and provider failures
remain separate checks/statuses. These metadata categories do not require opening candidates.

### OpenCode generation

Install the `opencode` executable separately, then use the same configuration and input file with `--harness opencode`:

```bash
repel generate --harness opencode --benign --payload /path/to/control.txt --language python --retries 3
```

OpenCode runs in an isolated temporary workspace with its own runtime configuration, then the candidate goes through
the same parser/compiler/linter checks. The example uses the benign control contract. Use `--opencode-bin PATH`
when the executable is not on `PATH`; use `--opencode-timeout SECONDS` to change its per-attempt limit.

Each response must contain exactly one fenced source block. Candidates are parsed/compiled/linted
in a temporary directory. Failed retries receive the prior extracted source plus
parser/compiler/linter/formatting diagnostics. Generated source is never executed; review
accepted candidates under `results/source-generation/<payload-name>/` or
`results/benign-generation/<payload-name>/` with `--benign`; failed candidates remain metadata-only.
Use `--language`, `--list-languages`, `--list-toolchains`, `--keep-raw-responses`, or
`--allow-missing-toolchains`; use `--config PATH` for another endpoint file. The completion response's
`model` field is recorded as `resolved_model`. Protocol details are in [RESEARCH.md](RESEARCH.md).
The OpenCode harness uses isolated temporary state and enables its formatter, LSP integration, and shell tool. Subagents, built-in web tools, and external-directory tool access remain denied. The agent is told not to make network requests, but a general shell is an agent-policy boundary rather than an OS network sandbox; OpenCode may also download a missing language server. Its candidate still passes through the authoritative parser/compiler/linter checks.

## Source snippet placement (optional)

Generation and placement are separate, reviewable steps. To place accepted source snippets into a
disposable evaluation repository, run a dry run first, then apply it explicitly:

```bash
repel deploy add \
  --repo /path/to/example-repo \
  --run-dir /path/to/control-run
repel deploy add \
  --repo /path/to/example-repo \
  --run-dir /path/to/control-run \
  --file src/app.py --positions head,mid,tail --apply
repel deploy status --repo /path/to/example-repo
repel deploy remove --repo /path/to/example-repo
repel deploy remove --repo /path/to/example-repo --apply
```

The first `add` is a preview; `--apply` writes the selected files only after every matching
post-image passes its host-language validation. `--run-dir` must be the generation directory
containing `manifest.json` (for example `/path/to/control-run`), not an individual candidate file.
Omit `--file` to target every eligible source file, and use `--allow-partial` only when intentionally deploying candidates accepted
despite missing toolchains. The deployer matches accepted snippets to languages, preserves shebangs/encoding cookies, and
aligns Python indentation without prefixing multiline-string continuation lines. It validates the
complete post-image with the native parser/compiler path for every supported language; unavailable
validators fail closed during apply. Midpoint insertion tries nearby physical boundaries, while
Bash/Ruby heredocs and Java top-level declarations stay at safe file scope. Applied changes use
ignored `.repel-carrier-index.json` and a private `.repel-deploy-store/`, record each exact inserted string with its
hash and byte count, require unchanged pre- and post-deployment hashes, and restore exact bytes.
Failed/partial candidates require explicit `--allow-partial`. Use [retained deployment](docs/retained-data.md), [typed catalogs and recovery](docs/catalog-deployment.md), and the [journal dashboard](docs/journal-dashboard.md) for coverage, placement maps, snippets, and original examples.

## Optional evaluation harness

The research includes **over-refusal**: cases where unrelated, safety-sensitive text causes an assistant to decline an otherwise valid task. See [RESEARCH.md](RESEARCH.md) for findings, protocols, and research boundaries.

The older paired benchmark, pinned benign repository fixtures, condition JSONL pipeline, and
Codex/Claude launcher remain available but are secondary; see [EVALUATION.md](EVALUATION.md).
The `eval/` suite organizes the research-dimension experiments (guardrail configs, a shared
offline-safe runner, and per-dimension result aggregation); see [eval/README.md](eval/README.md).

## Safety boundary

Use only repositories, sites, and model endpoints you own or are explicitly authorized to test.
Prompt text is not authentication, authorization, encryption, privacy protection, or a durable way
to control public content. The project does not support stealth deployment, automated evasive
generation, resource exhaustion, or targeting third-party agents.
