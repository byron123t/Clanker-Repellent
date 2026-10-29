# Frontend interface guide

The preview server replays fixed synthetic responses. The existing `web/app.js` is a
working client; preserve its request format while changing the interface. All requests
are same-origin GETs with `Authorization: Bearer TOKEN`. The token comes from the URL
fragment printed by `preview.py`; the client saves it in session storage.

## Views and data

| View | Request | Relevant data |
| --- | --- | --- |
| Overview | `/api/summary` | `deployments` contains project/record summaries; `response_count` counts saved responses |
| Record detail | `/api/deployments/{id}` | `metrics`, `eligible_paths`, and `files` describe the selected record |
| File preview | `/api/deployments/{id}/preview?file=N&step=0&version=VERSION` | Stored text, encoding, size, and checksum |
| File download | Same URL with `/download` | Full saved bytes |
| Response list | `/api/responses` | `responses` contains saved request labels, statuses, and content types |
| Response preview/download | `/api/responses/{id}/preview?version=before` or `/download?version=before` | Saved response body |

`VERSION` is `insertion` for a snippet, `before` for the original file, or `after` for the
updated file. `N` is the file's `number`, not its row position after sorting. The supplied
samples have one edit per changed file, so `step` is 0. Include these parameters explicitly.
Response previews also support `version=after`.

## Summaries and charts

Each summary has `id`, `repository`, `repository_name`, `state`, `types`, and `metrics`.
Records are ordered newest first. Use the latest record per project in the overview;
only those with `state: applied` contribute to current placement/byte totals. `restored`
is historical, and `prepared` is pending. These are recorded states, not live health checks.

| Metric | Display meaning |
| --- | --- |
| `coverage_percent` | Files with recorded snippets divided by files in the recorded compatible scope |
| `placed_files`, `eligible_files` | Numerator and denominator for file coverage |
| `placements` | Number of recorded snippets |
| `inserted_bytes` | Added bytes present in the updated files |
| `density_percent` | Added bytes as a percentage of updated file size |
| `artifacts` | Number of saved snapshots |
| `scope` | Description of the recorded file selection |

A null denominator/percentage is unknown. Coverage of a selected subset is not whole-project
coverage. Show the scope alongside the percentage. There is no total-request count from which
to calculate response-traffic coverage.

## File selection and previews

`eligible_paths` supplies the inventory for the coverage map. Each `files` row has `number`,
`path`, `kind`, sizes, version hashes, `placements`, `spans`, and `edits`. `spans` provides
`start_percent` and `width_percent` for tracks in the updated file. `edits` supplies the
step/offset and snippet size for inspection. These positions are bytes, not source lines.

An inventory file without a stored file row has no preview. A row with `role: artifact`
is a snapshot; it has file versions but no snippet. `pending` identifies an unfinished
snapshot. `examples` is empty in this handoff; the existing client handles that optional area.

Previews return `text`, `encoding`, `bytes`, `preview_bytes`, `truncated`, `sha256`, and
`filename`. Render `text` using text nodes. `encoding: base64` identifies a binary preview.
If truncated, label the preview and offer the full download. Fetch content after a user
chooses to preview/download it, rather than while loading overview metadata.

## Available examples

The sample projects cover a large inventory, sparse coverage, several file types, historical
records, pending snapshots, and an unknown denominator. The response list includes text
and binary samples. All paths and contents are fictional and supplied as fixed data.

Run `preview.py --scenario empty` for no records or `--scenario error` for unavailable data.
The server returns JSON errors with an `error` string. Keep the last known source label on
temporary failures and never fabricate chart values to fill an error state.
