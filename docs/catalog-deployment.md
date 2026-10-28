# Typed payloads, random deployment, and exact recovery

The new catalog scaffold is `payloads/catalog-v1/`. It is an independent namespace;
existing payload collections are never automatically read or migrated. Initialize its
local index with `repel catalog init`, or create a separate catalog with
`repel catalog init --catalog /path/to/new-catalog`. An initialized catalog cannot be
overwritten. The checked-in descriptor also supports initialization on a fresh checkout.

## Catalog structure and types

```text
payloads/catalog-v1/
  catalog.json                             layout/schema version
  catalog.sqlite3                          transactional ID/type/tag index
  entries/source/<language>/<id>.json       source metadata
  entries/document/<document-type>/<id>.json document metadata
  entries/data/plain/<id>.json              generic text metadata
  objects/sha256/<prefix>/<sha256>          immutable UTF-8 content
```

The index, entries, and objects are private local data ignored by Git. Metadata records
include the ID, kind, language or document type, tags, encoding, content hash and byte
length, benign flag, validation, and optional generation provenance. IDs are immutable:
re-registering the same ID/content/metadata is idempotent; changes require a new ID.
Metadata and content hashes are checked on selection/read. Symlinked entries and objects
are rejected. Source registration performs static validation without executing the source.

```sh
repel catalog add --id project-note --kind data --file /tmp/note.txt --tag release --benign
repel catalog add --id python-note --kind source --language python \
  --file /tmp/control.py --tag release --benign
repel catalog add --id readme-note --kind document --document-type markdown \
  --file /tmp/note.txt --tag release --benign
repel catalog list --tag release --benign
```

Kinds are `source`, `document`, and `data`. Source languages are the existing generation
languages. Document types are `plain`, `markdown`, `html`, and `rst`. Tags are lowercase
slugs; multiple `--tag` filters require all tags. `list` prints metadata, not content.

Generation can consume a catalog entry and register accepted candidates automatically:

```sh
repel generate --catalog payloads/catalog-v1 --payload-id project-note \
  --language python --benign --output-dir /tmp/control-run \
  --register-prefix release-note --tag release
# Alternatively, import an existing benign run:
repel catalog import-run --run-dir /tmp/control-run --prefix release-note --tag release --benign
```

Only passed candidates are registered. `--benign` requires benign inputs/runs and applies
the existing conservative content checks. A catalog payload ID and a direct `--payload`
input are mutually exclusive. Generated IDs use `<prefix>-<language>`.

## Seeded random deployment

```sh
repel deploy add --repo ./app --catalog payloads/catalog-v1 \
  --kind source --language python --tag release --benign \
  --random --seed 42 --count 8
# Add --apply after reviewing the plan.
```

`--count` selects compatible files. `--random` samples them and chooses a compatible
payload per file, reproducibly with `--seed` (default 0). Source mode also tries shuffled
physical statement boundaries, retaining only placements whose complete host parses.
It preserves shebangs, encoding cookies, Python docstrings/future imports, indentation,
tabs, UTF-8 BOMs, and LF/CRLF style. Ruby/shell heredocs and Java declarations use safe
head/tail alternatives. Explicit `--positions head,mid,tail` or `--positions random`
overrides the default placement policy. Syntax validation does not prove semantic equivalence.

For compiled/web/document data, use retained deployment:

```sh
repel deploy add --repo ./app --catalog payloads/catalog-v1 --retain --benign \
  --tag release --random --seed 42 --count 8 --payload-count 1 --apply
```

Source entries match their language, document entries match their document type, and
generic `data` entries match all supported targets. An incompatible explicit `--file`
fails; discovery skips incompatible files. Retained mode defaults to one compatible record
per file with `--random`, otherwise all compatible records. Repeated `--file` restricts the
target set. It uses safe retained-data locations rather than arbitrary binary offsets.
Markdown, reStructuredText, and plain-text documents get escaped JSON data blocks with
the host's newline style. See [retained representations](retained-data.md) for C/C++, JS/TS,
HTML, and WASM. Retained mode requires a normal build and artifact verification afterwards.

## Central recovery journal

New deployments use a schema-2 `.repel-carrier-index.json` pointer and a private
`.repel-deploy-store/` containing a SQLite journal and content-addressed byte objects.
`--store /private/shared-store` allows multiple repositories to share one store. The journal
binds each deployment to its repository and index path. Legacy schema-1 indexes still use
their original `.preimage/` removal workflow.

Before modifying any target, Repel persists:

- Original and planned final file bytes and their SHA-256 hashes.
- Original permissions, relative path, payload selection, and carrier information.
- Ordered byte edits: offset in the image **before that step**, removed and inserted lengths,
  and hashes referencing the exact removed/inserted bytes.
- A transaction state: prepared, applied, removing, or restored.

Source insertion offsets are converted from Unicode positions to byte offsets. Replaying
the recorded operations must produce the exact planned postimage. For an external build or
compression transform, a replacement range records the changed byte region; it does not
claim to identify individual instructions in machine code.

The store uses process locks, synchronous SQLite transactions, fsynced objects, and atomic
file replacement. It keeps recovery data after successful cleanup. Removal verifies every
target and backup before writing, refuses unrelated edits/corrupt objects, and can resume
an interrupted apply/removal. These are integrity checks, not signatures or protection
against someone who can rewrite both the journal and its objects.

```sh
repel deploy status --repo ./app
repel deploy inspect --repo ./app                    # paths, offsets, sizes, hashes
repel deploy inspect --repo ./app --include-text     # explicit access to insertion strings
repel deploy remove --repo ./app --apply
# After an interrupted operation, or a lost index pointer:
repel deploy recover --repo ./app --apply
# Supply --store again if recovering a lost pointer to a shared store.
```

Binary insertion strings use base64 in `inspect --include-text`. A preview does not modify
targets. Do not delete the journal/object store until restoration is no longer needed.
Restoration covers file bytes and permission bits; it does not recreate timestamps, extended
attributes, hardlink relationships, or an entire build environment.

## Executables, saved HTTP responses, and packet captures

Exact restoration of a built artifact requires saving its **original bytes before the
build**. Hashes alone cannot reconstruct an old executable or compressed response.

```sh
repel deploy add --repo ./app --retain --benign --payload /tmp/note.txt \
  --file src/main.c --snapshot build/app --apply
# Build, strip, sign, compress, or package as usual.
repel deploy seal --repo ./app
repel deploy verify --repo ./app --artifact build/app
repel deploy remove --repo ./app --apply
```

`seal` records the final bytes only for explicitly snapshotted artifacts; it refuses changes
to deployed source or previously sealed artifacts. Removal restores the saved source and
executable bytes. If an output did not exist before the snapshot, removal deletes that new
output. Pending snapshots must be sealed before ordinary removal. A prepared transaction
interrupted before the build can be recovered while its snapshots remain unchanged.

Use standalone snapshots for an external transform of responses, scripts, executables,
`.pcap`/`.pcapng`, or any other regular file:

```sh
repel deploy snapshot --repo ./session --artifact capture.pcap --artifact response.http --apply
# Perform the authorized local transformation.
repel deploy seal --repo ./session
repel deploy remove --repo ./session --apply
```

The snapshot path does not parse, inject into, or replay network packets. It preserves
their saved bytes. An existing executable is restored from its snapshot; arbitrary compiled
payloads cannot be removed reliably without an original artifact or a reproducible rebuild.

## Live HTTP responses

`repel traffic proxy` is a local fixed-upstream HTTP adapter for an application you control.
It defaults to pass-through; `--apply` enables insertion at startup. The middleware can also
wrap an existing WSGI app through `RetainedResponseMiddleware` in the Python package.

```sh
repel traffic proxy --upstream http://127.0.0.1:8000 --port 8081 \
  --catalog payloads/catalog-v1 --tag release --benign \
  --archive /private/tmp/repel-traffic --apply
# In another shell:
repel traffic disable --archive /private/tmp/repel-traffic
repel traffic enable --archive /private/tmp/repel-traffic
repel traffic list --archive /private/tmp/repel-traffic
repel traffic restore --archive /private/tmp/repel-traffic \
  --request-id REQUEST_ID --output /private/tmp/restored-response
```

Supported live bodies are UTF-8 HTML, JavaScript, and uncompressed or gzip-encoded WASM.
Type matching follows the catalog; `data` entries match all three. `--random --seed N`
chooses a stable record per request path. The buffer limit defaults to 2 MB of both encoded
and decoded data. Unsupported encodings, oversized bodies, HEAD/range responses, non-200
responses, and `Cache-Control: no-transform` pass through unchanged. This development proxy
uses the standard WSGI server; it is not a production gateway, WebSocket proxy, or TLS
interception tool.

Before sending a modified response, the adapter archives the exact original entity-body
bytes (including the original gzip stream), response status/headers, postimage, and byte edits.
It updates Content-Length, removes stale entity validators/digests, and sets `no-store`.
If recording fails, it sends the original response. Disabling insertion affects subsequent
responses. Restoring a record creates `body.bin` and `response.json` in a new output directory.
Archives can contain application data and headers; keep them private.

This preserves the HTTP representation seen by the adapter, **not** TCP segmentation,
TLS ciphertext, original header wire formatting, or traffic already delivered to clients.
Existing cached responses cannot be recalled. Use saved packet snapshots for byte-exact
capture restoration. Protocol references: [WSGI](https://peps.python.org/pep-3333/) and
[HTTP message transformations](https://www.rfc-editor.org/rfc/rfc9110.html#section-7.7).
