# Retained text in executables and web builds

`repel deploy add --retain` stores UTF-8 project notes, documentation, or source snippets as data.
It preserves their text without executing it. It does not need
a model endpoint: use `--payload` for your own text, or `--run-dir` for accepted generated
snippets. Every selected file receives every input record. Use repeated `--file` arguments
to choose entry points when copying the text into every translation unit or web module
would add too much size.

Comments and unused source declarations usually disappear during compilation. Retained mode
uses build-specific representations instead:

| Target | Representation | When to apply |
| --- | --- | --- |
| C/C++ `.c`, `.cc`, `.cpp`, `.cxx` | UTF-8 string data and a retained accessor | Before compiling/linking |
| JS/TS, including JSX/TSX and module extensions | Non-enumerable `globalThis["repel:<content-sha256>"]` string | Before bundling, or on the final JS bundle |
| HTML | `<script type="application/json" data-repel-notes="v1">` data block | Source HTML or the exported page |
| Markdown, reStructuredText, plain text | Escaped JSON records in document data blocks | Source documents |
| Uncompressed `.wasm` | `repel.notes.v1` custom section | After linking and WASM optimization |

Native snippets use Clang/GCC `used`, plus `retain` on ELF, or an exported accessor on MSVC.
ELF builds require a compiler and linker supporting `retain` (Clang 13+/GCC 11+ and a
compatible linker). Unsupported ELF compilers fail compilation rather than silently dropping
the data. See [Clang's retention attributes](https://clang.llvm.org/docs/AttributeReference.html#retain).
This works on translation units actually included by the linker: an otherwise unused object
in a static archive still needs to be linked. Build flags, bundler `sideEffects` declarations,
and custom optimizers can affect retention, so always verify the final artifact.

## Native executable example

Keep the input text outside the selected targets. The first command previews metadata;
`--apply` writes changes and backups. `--benign` applies the existing conservative content
checks and requires a benign run when used with `--run-dir`.

```sh
repel deploy add --repo ./app --retain --benign --payload ./project-note.txt --file src/main.c
repel deploy add --repo ./app --retain --benign --payload ./project-note.txt --file src/main.c --apply
# Run your normal release build, including stripping/LTO if normally enabled.
repel deploy verify --repo ./app --artifact build/app
```

Existing ELF, Mach-O, or PE executables are verified, not patched: rebuild them from the
modified C/C++ sources. The text is in the binary's retained data, so `strings` and binary
analysis tools can recover it even without debug symbols. The accessor also provides a code
reference to the data. No format guarantees that a decompiler will display it as source
comments, or that deliberate stripping/repacking will preserve it. Stored notes remain text;
they do not control how someone uses the software.

## Websites and WebGL games

For a JavaScript game such as the horror-game example, target its HTML shell and loaded entry
module, then run the normal build:

```sh
repel deploy add --repo ./game --retain --benign --payload ./project-note.txt \
  --file index.html --file src/main.js --apply
repel deploy verify --repo ./game --artifact dist/index.html --artifact dist/assets/main.js
```

For Godot, Unity, or Emscripten web exports, target the actual exported HTML and WASM files.
Run this after WASM optimization and before compression, integrity hashes, service-worker
precache manifests, or packaging. A later export overwrites these files, so reapply to a
fresh export and verify it again.

```sh
repel deploy add --repo ./web-export --retain --benign --payload ./project-note.txt \
  --file game.html --file game.wasm --apply
repel deploy verify --repo ./web-export --artifact game.html --artifact game.wasm
```

Automatic discovery excludes dependencies, `build/`, `dist/`, `target/`, backups, and
operational `payloads/` and `results/` directories, plus TypeScript declaration files.
Select an export directory as `--repo`,
or explicitly name built files with `--file`. Symlinked targets are rejected. Compressed
`.wasm.gz`, `.br`, Unity `.unityweb`, Godot `.pck`, and signed/encrypted native packages are
not insertion targets; embed in the unpacked HTML/WASM or native source before packaging.

JavaScript values are retrievable through their `globalThis` keys. HTML data is JSON and
needs no executable inline script. Given a compiled WebAssembly `module`, retrieve records
with `WebAssembly.Module.customSections(module, "repel.notes.v1")` and decode the bytes as
UTF-8. [Custom sections are ignored by WASM execution](https://webassembly.github.io/spec/core/binary/modules.html#custom-section);
optimizers or text-format conversions may remove them. Reapply after such transformations.

## Verification and removal

```sh
repel deploy status --repo ./app
repel deploy verify --repo ./app --artifact build/app
repel deploy remove --repo ./app --apply
```

`verify` checks that **every** expected record is recoverable from **each** artifact. It
checks the full text's length and SHA-256, not just the presence of a marker. It reads raw
native/WASM bytes and statically decodes JS/JSON string literals, including common minifier
escapes; it never executes the target. `.gz` artifacts are decompressed for verification.
Other compression/encryption must be unpacked first. It returns exit code 0 on success,
3 for missing/corrupted records, and 2 for invalid input or an unreadable artifact.
Verification confirms data recovery, not runtime reachability or decompiler presentation.

Retained deployments use `.repel-carrier-index.json` and the private `.repel-deploy-store/`,
just like source placement. The retained index and command output contain hashes, sizes,
paths, and storage formats, not the embedded text. Previewing changes writes nothing; an
applied deployment refuses an existing index. Removal preflights the current file hashes
and backup hashes before restoring exact bytes and permissions. It refuses intervening edits.
To restore already-built executables or bundles exactly, use the
[`--snapshot` and `deploy seal` workflow](catalog-deployment.md) before/after building;
otherwise rebuild those separately. The comment workflow's `repel guard`/`share` commands continue to
use their own comment placement index; they do not verify retained deployments.
