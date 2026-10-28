# Read-only file-change API

The standalone server returns **synthetic file-change records** and saved example content.
It reads `fixtures/journal.json` and `fixtures/objects.json`. The same response structure is
used by Repel's real journal viewer; fields describe records, not actions performed by this
API. The template's `template: true` flag identifies its dataset as synthetic.

## Requests and authentication

All endpoints use same-origin GET requests. Read `token` from the URL fragment, store it in
session storage, remove the fragment with `history.replaceState`, and send
`Authorization: Bearer TOKEN`. Static assets at `/`, `/app.js`, `/style.css`, and `/favicon.svg`
are public. Data endpoints require the token. Other HTTP methods return 405.

| Endpoint | Saved data returned |
| --- | --- |
| `/api/summary` | Dataset label, record summaries, counts, and integrity errors |
| `/api/deployments/{id}` | Complete metadata for one file-change record |
| `/api/deployments/{id}/preview?file=0&step=0&version=insertion` | Snippet added by a recorded edit |
| `/api/deployments/{id}/preview?file=0&version=before` | Original file version |
| `/api/deployments/{id}/preview?file=0&version=after` | Updated file version |
| Same paths ending `/download` | Full saved bytes as an attachment |
| `/api/responses` | `{ "responses": [...] }`, containing response metadata |
| `/api/responses/{id}/preview?version=before` | Original response body |
| `/api/responses/{id}/download?version=before` | Full original response body |

Response preview/download also accepts `version=after`. IDs are 32 lowercase hexadecimal
characters. `file` is the file's `number`, independent of its position in a filtered UI;
`step` is the edit's `step`. Invalid authentication returns 401, missing records/versions
404, invalid queries or corrupt content 422, and an unavailable data source 503.
Error responses contain an `error` string.

## Record fields

`fixtures/journal.json` is a complete schema example. The summary includes `store`, `demo`,
optional `template`, `total_deployments`, `response_count`, `limit`, `errors`, and `deployments`.
The real journal API returns its newest 200 records first. The fixture list has a fixed order
for reproducible layouts.

| Field | Meaning |
| --- | --- |
| `deployments` | File-change records grouped by the operation that originally produced them |
| `id` | Record identifier |
| `repository`, `repository_name` | Project path and display name; template paths are fictional |
| `index` | Recorded path to the operation's index; a label, not a file the viewer opens |
| `state` | Recorded lifecycle state: `applied`, `restored`, `prepared`, or `removing` |
| `mode` | How the underlying record was made, such as source placement, retained text, or a snapshot |
| `benign` | Whether the producer marked the content benign; the sample generator sets this to true for its authored examples |
| `created_at`, `updated_at` | Saved timestamps; fixed example times in this template |
| `selection` | Recorded file-selection settings: `random`, `seed`, and `count` |
| `types` | File/representation categories used for labels and filters |
| `eligible_paths` | Recorded file inventory used for coverage |
| `examples` | Optional mapping of `inspect`, `status`, and `restore` to copyable command strings; `{}` in the template |

A detailed record adds `eligible_paths`, `files`, and `examples`. Use the latest record per
project for overview totals. Only latest records in `applied` state contribute to totals
labeled current/applied. These states describe saved history, not a live filesystem check.
The `restored` samples demonstrate history display; selecting them performs no restoration.

## Coverage and file changes

`metrics` contains `eligible_files`, `placed_files`, `selected_files`, `coverage_percent`,
`placements`, `inserted_bytes`, `after_bytes`, `density_percent`, `artifacts`, and `scope`.

- File coverage is files with recorded snippets divided by compatible files in the saved scope.
- An unknown denominator is `null`. An explicitly selected subset is not a whole-project measure.
- Density is added bytes still present after the recorded edits divided by updated file bytes.
- Saved build snapshots are excluded from snippet-coverage and density calculations.

| File field | Meaning |
| --- | --- |
| `number`, `path`, `kind` | API lookup number, relative display path, and format/category |
| `role` | `placement` for a file with snippets, or `artifact` for a saved snapshot |
| `pending` | Whether the final snapshot has yet to be recorded |
| `before_bytes`, `after_bytes` | Original and updated sizes |
| `before_sha256`, `after_sha256` | Content-object references; a missing version can have a null hash |
| `payload_ids` | IDs of the snippets associated with this file-change record |
| `edits` | Ordered changes, with offsets relative to the file before each change |
| `spans` | Added byte ranges still present in the updated version |
| `placements`, `inserted_bytes` | Recorded snippet count and added-byte total |

Each edit has `step`, `offset`, `inserted_bytes`, `removed_bytes`, `sha256` (its added content),
and `location_percent` in the version before that edit. Each span has `start`, `end`, `step`,
`start_percent`, and `width_percent`. Draw updated-file tracks from spans; use edits to show
change history. These values are byte offsets, not source line numbers.

The `version` query selects stored content: `insertion` is the snippet for one edit, `before`
is the original version, and `after` is the updated version. Field names and route values are
part of the shared API schema.

## Response samples and previews

Response metadata has `id`, `request.method`, `request.path`, `status`, `content_type`,
`created_at`, `before_sha256`, and `after_sha256`. Template request paths and bodies are
generated examples. Private response headers are absent. There is no total-request count,
so the data cannot support a percentage of all traffic.

Previews return `text`, `encoding` (`utf-8` or `base64`), full `bytes`, `preview_bytes`,
`truncated`, `sha256`, and `filename`. Preview size is limited to 65,536 bytes. Downloads
return the complete saved object as `application/octet-stream`. The server checks content
hashes before returning bytes. Base64 represents binary data in JSON; it is not encryption.

Render previews as text nodes. A text preview is content to display, including when it
contains HTML or JavaScript. Label binary and truncated views, and keep downloads available
for the complete byte sequence.

## Browser assets

All runtime assets are local. The Content Security Policy allows same-origin scripts and
connections, same-origin/data images, and same-origin/inline styles. Inline JavaScript,
external scripts, framing, and changed document base URLs are blocked. Preserve those
protections and the authenticated, read-only API when redesigning the frontend.

The asset server currently serves four files. A design with more assets needs an explicit
route/package update when integrated; see `INTEGRATION.md`. The standalone server reads only
its own fixture and asset files.
