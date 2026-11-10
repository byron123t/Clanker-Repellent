# Task contracts for benign generation

Use a task contract when a valid parser/compiler result is not enough: helper names,
parameter order, example results, document fields, or table labels must also match.

```sh
repel generate examples/benign-contracts/clamp.txt --benign --contract examples/benign-contracts/clamp.contract.json
```

The contract infers the format. Add `--endpoint http://127.0.0.1:18473/v1` for an already
open DeepSeek tunnel, or port `18474` for GLM. `--seed 42` requests a server sampling seed;
the CLI records it but cannot guarantee that a server honors it. Use a new output directory
when changing the model, contract, or seed. Successful candidates are hash-checked on resume.

The same contract is sent to the model and checked locally. A failed check feeds a bounded
diagnostic into the normal retry loop. Contracts require `--benign`, exactly one matching
format, and version 1. They add to the normal parser/compiler/structure checks. A folder
invocation applies its supplied contract to every `.txt` input; it does not automatically
discover different companion contracts.

## Integer helpers

```json
{
  "schema_version": 1,
  "language": "python",
  "function": {"name": "clamp", "parameters": ["value", "lower", "upper"]},
  "examples": [
    {"inputs": [5, 10, 0], "expected": 5},
    {"inputs": [-2, 0, 10], "expected": 0},
    {"inputs": [15, 0, 10], "expected": 10}
  ]
}
```

Python contracts use a bounded interpreter, without `eval`, `exec`, imports, or invoking
the generated function. Supported constructs are scalar integer/Boolean locals, comparisons,
`+ - * // %`, Boolean expressions, conditionals, `while`, `break`/`continue`, flat tuple
assignment, and `abs`/`min`/`max`. There are limits on source size, AST nodes, steps, and values.
Unsupported constructs fail the contract rather than being silently treated as correct.
Optional annotations may use `int`, `bool`, or quoted text. Unresolved names and computations
in annotations are rejected because they can fail when Python defines the helper, even when
its body passes every example. Python scope/control-flow rules are checked by compilation
without executing the function.

SQL uses the same `function`/`examples` fields. The function name is the result alias and
parameters are named `:parameters`. SQL predicates expect integer `0`/`1`. Unlike the default
prepare-only SQL validator, a SQL task contract **evaluates** its pure SELECT examples in a
private in-memory database, with a read-only authorizer and a fresh instruction budget per
example. It cannot read tables or external databases.

LLVM adds `parameter_types` and `return_type` to `function`, plus an `llvm.instructions`
allowlist. The bounded interpreter supports `icmp`, `select`, `add`, `sub`, `mul`, `and`,
`or`, `xor`, and `ret`; it handles signed comparisons and fixed-width wraparound. Contracts
require one straight-line helper with scalar integer types. `i1` examples use Booleans.
The normal Clang compilation check still runs. Generation never loads the resulting native code.

## Documents and tables

JSON, HTTP, `binary-info`, YAML, TOML, CSV, INI, and XML use a `document` object with:

- `shape`: `type`, `required`, `properties`, `additional_properties`, `items`, `min_items`,
  `max_items`, and `enum`. This is a bounded Repel schema, **not full JSON Schema**.
- `equals`: exact type-sensitive values at JSON pointers, such as `{"path":"/currency","value":"credits"}`.
- `relations`: `count`, `sum`, or `unique` over an array. `left` and `right` are JSON pointers;
  `field` optionally selects a member of each array entry for sums or uniqueness checks.
- `equations`: integer calculations over JSON pointers. For example,
  `{"left":"/amount","expression":{"op":"mul","args":[{"path":"/quantity"},{"path":"/unit_price"}]}}`.
  Expressions nest binary `add`, `sub`, `mul`, `floordiv`, `mod`, `min`, and `max` operations;
  leaves are integer constants or `{"path":"/field"}` references. Division floors toward
  negative infinity. Division by zero, missing values, and non-integer values fail the check.
  There is no executable expression language or callback. Rules are limited to 128 equations,
  depth 12, 8,192 evaluation steps, and magnitude at most 2^127 for every value/intermediate.

Use `equals` to preserve supplied inputs and `equations` to check derived fields. A sum check
alone cannot detect a consistently wrong item amount and total. Equations express the requested
calculation without supplying a precomputed answer to the generator.

Configuration and markup contracts use these logical views. These are check representations;
the generated file remains in its requested native format.

| Format | Pointer root | Numeric equations |
| --- | --- | --- |
| YAML / TOML | The parsed mapping and native scalar types | Integer values, as for JSON |
| INI | Section name → case-sensitive key → literal string | Canonical decimal integer strings |
| CSV | `columns`: ordered header strings; `records`: row objects keyed by column name, with string values | Canonical decimal integer strings |
| XML | Root node with `tag`, `attributes`, `text`, `tail`, and `children`; child nodes use the same shape | Canonical decimal integer text |

XML `text` and `tail` trim surrounding formatting whitespace for checks; internal whitespace is
retained. Saved XML bytes are unchanged. Namespaced element/attribute names use
`{namespace}local` notation. XML parsing rejects DTDs, declared entities, and processing
instructions before constructing the check tree. For CSV/INI/XML, `equals` remains type-sensitive
and therefore expects strings for textual values. Only `equations` interprets numeric strings;
`sum` and `count` relations retain their ordinary native-number requirements. Use array shape
bounds and explicit equations when working with textual tables.

```sh
repel generate examples/benign-contracts/invoice.txt --benign --contract examples/benign-contracts/invoice.csv.contract.json
```

Equivalent authored invoice contracts are provided for YAML, TOML, INI and XML. They preserve
inputs and constrain calculated amounts without giving the final amounts as examples.

An HTTP contract can require a status and headers through
`"http":{"status":200,"headers":{"X-Example-Id":"catalog"}}`. Existing exact-byte
framing checks remain required. No response is sent over the network.

HTML uses `html.required_ids` and `html.table` with `columns`, `row_count`, and optional
exact `rows`. Column order, dimensions, IDs, and ARIA references are checked. The table also
accepts `equals` and `equations`: pointers address data rows and columns, excluding the header
(for example `/0/2`). Equations require canonical decimal integer text in referenced cells;
units, decimal points, and leading zeros are rejected. Preserve input cells with `equals`, then
check computed cells with `equations`. Dimensions alone cannot verify arithmetic.

Unknown keywords, incompatible fields, malformed types, duplicate parameter names, excessive
nesting, and oversized contracts are rejected before inference. Contracts are limited to
128 KiB and code contracts to 128 public examples. Type checks distinguish Booleans from integers.

## What passing means

Passing establishes the specified checks, not all-input correctness. A helper can memorize
public examples; a document can preserve totals while changing an input; a table can have the
right dimensions but wrong calculations. Encode required input fields and values explicitly,
and use independent tests for evaluation. The [controlled fault study](../evaluation/fault-audit-v1/REPORT.md)
includes these failures instead of hiding them. The [evaluation protocol](../benchmarks/benign-v2/PROTOCOL.md)
keeps private grading separate from generation acceptance.

Examples for all twelve supported contract formats are in
[`examples/benign-contracts/`](../examples/benign-contracts/README.md). They are authored task
specifications, not model outputs.
