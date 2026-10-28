# Journal frontend contract

All endpoints are same-origin GET requests. Read `token` from the URL fragment, store it in
session storage, remove the fragment with `history.replaceState`, and send
`Authorization: Bearer TOKEN`. Assets at `/`, `/app.js`, `/style.css`, and `/favicon.svg` are
public; journal APIs require the token. The server is read-only and returns no CORS grants.

| Endpoint | Returns |
| --- | --- |
| `/api/summary` | Store label, deployment summaries, record/response counts, integrity errors |
| `/api/deployments/{id}` | Complete metadata for one deployment |
| `/api/deployments/{id}/preview?file=0&step=0&version=insertion` | Explicit insertion preview |
| `/api/deployments/{id}/preview?file=0&version=before` | Explicit original-file preview |
| `/api/deployments/{id}/preview?file=0&version=after` | Explicit final-file preview |
| Same paths ending `/download` | Exact bytes with an attachment filename |
| `/api/responses` | `{ "responses": [...] }`, metadata only |
| `/api/responses/{id}/preview?version=before` | Original entity-body preview |
| `/api/responses/{id}/download?version=before` | Exact original entity body |

Response preview/download also accepts `version=after`. IDs are 32 lowercase hexadecimal
characters. `file` is the file's `number`, not an index in a filtered/sorted UI. `step` is the
edit's `step`. Invalid authentication returns 401, missing records/versions 404, writes 405,
invalid/corrupt content 422, and an unavailable journal 503. Error bodies contain `error`.

## Metadata

`fixtures/journal.json` is a complete, readable schema example. The summary contains:

- `store`, `demo`, optional `template`, `total_deployments`, `response_count`, `limit`, `errors`.
- `deployments`: newest journal records first. The live API currently limits this to 200.
- Each summary: `id`, `repository`, `repository_name`, `index`, `state`, `mode`, `benign`,
  `created_at`, `updated_at`, `selection`, `types`, and `metrics`.

Detail adds `eligible_paths`, `files`, and `examples` (inspect/status/restore command strings).
Use a repository's latest record for an overview; only latest records in `applied` state
belong in totals labeled current/applied. The API's state is a journal state, not a live
checkout/build check. `prepared`, `removing`, and `restored` are also possible.

`metrics` includes `eligible_files`, `placed_files`, `selected_files`, `coverage_percent`,
`placements`, `inserted_bytes`, `after_bytes`, `density_percent`, `artifacts`, and `scope`.
Coverage = placed files / recorded compatible files in that deployment's target scope.
Unknown denominators produce `null`. Explicit file scopes are not full-repository coverage.
Density = surviving inserted bytes / final bytes of placed files. Build snapshots are excluded.

Each file has `number`, `path`, `kind`, `role` (`placement` or `artifact`), `pending`,
`before_bytes`, `after_bytes`, `before_sha256`, `after_sha256`, `payload_ids`, `edits`,
`spans`, `placements`, and `inserted_bytes`. A missing original/final version can have a null hash.

`edits` records an insertion's `step`, pre-step byte `offset`, `inserted_bytes`,
`removed_bytes`, insertion `sha256`, and `location_percent` in the pre-step image.
`spans` records surviving final-image intervals: `start`, `end`, `step`, `start_percent`,
and `width_percent`. Later edits may split or delete a span. Use spans for final byte tracks;
use edits for insertion history. Neither array represents source line numbers.

Response metadata includes `id`, `request.method`, `request.path`, `status`, `content_type`,
`created_at`, `before_sha256`, and `after_sha256`. Private response headers are not exposed.
The archive does not record the total request population, so traffic coverage is unknown.

## Content

Previews return `text`, `encoding` (`utf-8` or `base64`), full `bytes`, `preview_bytes`,
`truncated`, `sha256`, and `filename`. The limit is 65,536 bytes. A copied truncated preview
is not a complete file. Download routes return all original bytes as `application/octet-stream`.
The server verifies object hashes before returning bytes. Render preview strings as text,
never executable markup. The fixture object store is base64-encoded data keyed by SHA-256.

## Assets and policy

Runtime assets are local. The server CSP permits same-origin scripts and connections,
same-origin and data images, and same-origin/inline styles; it blocks inline JavaScript,
external scripts, framing, and a changed document base URL. Use DOM text nodes for untrusted
names and snippet text. The current production asset allowlist has four files. Extend that
explicitly when integrating a candidate that requires more files.

The fixture API is a simulation of this interface, not a recovery engine. Its data is visibly
marked `template: true`. It does not open any SQLite journal or read any parent/sibling folder.
