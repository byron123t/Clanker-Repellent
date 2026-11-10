# Structured generation formats

`repel generate --format TARGET` selects the same registry as `--language`. Saved configuration
continues to use `generation.languages`, and manifest compatibility fields such as `language`
remain unchanged. New targets go through the normal bounded retries, benign checks, checkpoints,
hashing, and optional catalog registration.

Add `--benign --contract FILE` for task-specific names, example outcomes, field values,
array relationships, status/headers, or table requirements. Contracts are supported for
Python, SQL, LLVM, JSON, HTTP, binary descriptions, HTML, YAML, TOML, XML, CSV, and INI;
see [task contracts](task-contracts.md).
The normal generic format checks below remain required.

| Target | Accepted output | Required validation |
| --- | --- | --- |
| `yaml` | `generated.yaml`, a populated mapping | Safe scalar types, unique string keys, finite numbers, bounded tree; no tags, anchors, aliases, merges, or multiple documents |
| `toml` | `generated.toml`, configuration tables | TOML parser, finite numbers and bounded ordinary values; quote dates as strings |
| `xml` | `generated.xml`, semantic XML | Well-formed tree with populated descendants; bounded depth/items; no DTD, declared entities, processing instructions, or external resolution |
| `csv` | `generated.csv`, a rectangular table | Unique nonempty header with at least two columns, consistent row widths, standard quoting, populated data |
| `ini` | `generated.ini`, named configuration sections | Strict case-sensitive keys, literal values, no duplicate sections/keys, no DEFAULT inheritance or interpolation |
| `json` | `generated.json`, a populated object | Strict JSON, unique keys at every depth, finite numbers, valid Unicode, bounded nesting |
| `http` | `generated.http`, one HTTP/1.1 response with a JSON object body | Status/header grammar, no duplicate headers or transfer/content encoding, exact UTF-8 body length |
| `binary-info` | `generated.binary.json`, a logical binary/VM description | Versioned schema, architecture compatibility, unique sections/symbols, typed cross-references |
| `llvm` | `generated.ll`, human-readable LLVM IR | Restricted integer profile plus Clang object compilation; no execution |

These document formats are documents in both `--structure` modes. Their metadata
records `structured-documents-v1`, with counts rather than source keys or values. LLVM uses the
existing functional/data profiles. Ordinary programming-language targets keep their current rules.

For example, using your configured model:

```sh
repel generate ./benign --benign --format yaml,toml,xml,csv,ini
```

The five new targets use the normal generation checkpoints, retries, hashes and catalog import.
They validate document syntax and populated structure; they do not claim that arbitrary values
satisfy the user's intended calculation. Add `--contract` for exact fields, input preservation,
and bounded arithmetic; the [task-contract guide](task-contracts.md) defines the logical views
used by CSV, INI and XML. Independent semantic evaluation is also provided in the
[breadth benchmark](../benchmarks/benign-v3/README.md).
The CLI preserves accepted bytes, including CSV quoting, XML escapes and literal INI percent signs.

YAML uses [PyYAML's safe loader](https://pyyaml.org/wiki/PyYAMLDocumentation), with duplicate-key
and alias/tag rejection before construction. TOML uses [tomllib](https://docs.python.org/3/library/tomllib.html)
on Python 3.11+ and Tomli on older Python. INI uses
[ConfigParser](https://docs.python.org/3/library/configparser.html) with interpolation disabled;
its values remain strings. The shared configuration profile permits strings, booleans, nulls,
bounded integers, finite floats, lists and mappings, subject to each format's grammar. Maximum
depth is 32 and maximum tree size is 10,000 items. XML enforces the same bounds during parsing.
CSV permits at most 10,000 cells, 1,000 columns and 10,000 rows including the header, with the
standard library's field-size limit. All targets retain the generation limit of 2 MB per snippet.

## JSON and HTTP

JSON requires at least two nonempty named, populated root members. Empty/null-only wrappers,
root scalars, duplicate keys, NaN/Infinity, overflow-to-infinity numbers, and unpaired Unicode
surrogates are rejected. False and zero are meaningful values. Maximum depth is 32 and maximum
tree size is 10,000 items. JSON escape sequences are preserved during fenced-block extraction.

HTTP supports a single response, not a capture file or replay engine. Its body is a JSON object.
Accepted statuses are 200, 201, 202, 400, 404, 409, 422, 500, and 503. Content-Type must be
`application/json`, optionally with `charset=utf-8`. Header values are ASCII; body text is UTF-8.
Duplicate/folded headers, transfer/content encodings, credentials, and cookies are outside this profile.

Generation normalizes header newlines to CRLF, computes Content-Length from the final UTF-8 body,
and records whether formatting changed. Validation independently checks that framing. Stored source,
catalog registration, and manifest hashes retain the exact bytes. This is an offline response fixture:
no network request is sent and no existing traffic archive is read or altered.

These checks follow [JSON syntax](https://www.rfc-editor.org/rfc/rfc8259.html) and
[HTTP/1.1 framing](https://www.rfc-editor.org/rfc/rfc9112.html), with the narrower limits above.

## Binary descriptions

This is Repel's own logical schema, not a file-format parser, disassembler, assembler, or universal
executable serializer. It does not assert recovered addresses, offsets, real native symbol tables,
or that a description can be encoded directly into a runnable program.

The exact version-1 root keys are:

```json
{
  "schema_version": 1,
  "format": "ELF",
  "architecture": "x86_64",
  "sections": [
    {"name": ".text", "kind": "code"},
    {"name": ".rodata", "kind": "data"}
  ],
  "symbols": [
    {"name": "in_range", "kind": "function", "section": ".text"},
    {"name": "description", "kind": "object", "section": ".rodata"}
  ],
  "strings": ["Inclusive integer range helper"]
}
```

At least two sections, two symbols, and one descriptive string are required. Section kinds are
`code`, `data`, or `metadata`; symbols are `function` or `object`. Functions reference code sections;
objects reference data/metadata sections. Names must be nonempty and unique within their table.
Additional fields, including raw-machine-code fields, are rejected.

| Format | Architecture values |
| --- | --- |
| ELF | x86, x86_64, aarch64, riscv64 |
| PE | x86, x86_64, aarch64 |
| Mach-O | x86_64, aarch64 |
| JVM | jvm |
| CLR | cil |
| Wasm | wasm32, wasm64 |

For JVM/CLR, sections and symbols are logical descriptions of code and metadata. They are not
literal ELF-style section/symbol tables. Encoding and placement remain separate operations.

## LLVM IR

The functional profile accepts named functions with scalar integer parameters/results (`i1`, `i8`,
`i16`, `i32`, `i64`) and an input-dependent computation. Supported instructions are `add`, `sub`,
`mul`, `and`, `or`, `xor`, `shl`, `lshr`, `ashr`, `icmp`, `select`, `zext`, `sext`, `trunc`, `phi`,
`br`, and `ret`. Instructions and labels occupy separate lines. The data profile accepts at least
two named constant integer globals. Semicolon comments are supported.

Calls, memory operations, pointers, inline assembly, startup entry points, metadata, target
directives, attributes, poison/undef values, and overflow promises (`nsw`, `nuw`, `exact`) are
outside this small profile. Clang checks the real types, SSA uses, and control-flow syntax and
writes a temporary object. Missing Clang is a failed required check unless explicitly recorded
as partial via `--allow-missing-toolchains`.

Compilation and structural dependence do not prove the intended algorithm or all-input correctness.
For example, oversized shifts can still have undefined/poison semantics. Native execution is a
separate review step; the included reference checker executes only hash-pinned, authored controls.
See the [LLVM language reference](https://llvm.org/docs/LangRef.html) for actual instruction semantics.

These new formats can be stored in the typed catalog. Automatic insertion into arbitrary existing
JSON documents, HTTP streams, or binary files is not added by these generation targets.
