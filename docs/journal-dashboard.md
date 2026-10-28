# Journal dashboard

The dashboard connects directly to a central `.repel-deploy-store/` (or a shared store passed
to `deploy --store`). It reads the SQLite journal and content-addressed objects without
changing deployment state, scanning live repository contents, or executing stored code.

```sh
repel dashboard --store /path/to/central-journal --open
# Default store: ./.repel-deploy-store, default port: 8765.
# Use --port 0 to choose an available port.
```

The CLI prints an authenticated local URL and binds only to `127.0.0.1`. `--open` opens that
URL in your browser. The URL fragment carries a per-session token; the browser removes it
from the address bar and supplies it in authenticated API requests. Journal data has
`Cache-Control: no-store`; there are no external assets, analytics, or CDN dependencies.
Keep the printed URL private. A new server process issues a new token.

Try the complete UI without using an existing payload collection:

```sh
repel dashboard --demo /tmp/repel-dashboard-example --port 0 --open
# The demo directory must be new. To reopen it later:
repel dashboard --store /tmp/repel-dashboard-example/journal --port 0 --open
```

The demo creates real, benign retained deployments, a restored deployment, and archived
HTTP responses. It does not read or migrate existing `payloads/`, `results/`, or operational
artifacts. The new example directory and its journal remain available after the server stops.

## Views

- **Overview:** repository comparisons, searchable repository cards, latest-record totals,
  and deployment/restoration activity. Aggregates use the latest record per repository;
  placement/byte totals include only those latest records marked applied.
- **Deployments:** repository/state/deployment filters, file coverage, recorded insertion count,
  inserted byte totals, a compatible-file map, and head/middle/tail distribution.
- **Snippet explorer:** searchable file paths/types, final-image placement ranges, and an
  inspector for each edit. Select **Load snippet** or **Load example** to read stored content.
  Nothing is fetched automatically from the object store when the overview opens.
- **HTTP archive:** recorded request paths/status/content types and on-demand access to the
  original entity bodies. Private response headers are not included in the overview.

The inspector supports copying text, downloading exact stored bytes, and copying CLI examples
for inspection, status, and restoration. Commands are displayed, not executed. HTML and
JavaScript snippets are displayed as text. Binary previews use base64; downloads preserve
the binary bytes. Previews are limited to 64 KiB and clearly labeled when truncated. The
download provides the full, checksum-verified object.

**Export report** downloads the selected deployment's metadata and computed metrics as JSON;
the report does not include snippet text. The page refreshes journal metadata every 10 seconds
while visible and supports manual refresh. It lists the latest 200 deployments/responses,
up to 200 coverage tiles, and up to 400 matching file rows at a time; larger sets can be
filtered in the file table. The complete deployment remains in the exported report.

## What the percentages mean

Coverage is recorded at deployment time. New source and retained deployments save the
compatible file inventory **before** `--count` sampling, along with selection scope:

```text
File coverage = files with recorded insertions / compatible files in the target scope
```

For `--file`, the denominator is the compatible explicit target set, not the entire repository.
For discovery, it is the compatible source/retained set after normal directory/type exclusions.
Legacy journal entries without an eligible-file denominator display **not recorded**, rather
than an inferred percentage. Snapshot-only records do not claim source coverage.

The coverage map includes unselected compatible files when that inventory was recorded.
Restored deployments keep their historical placement data and are labeled **Restored**.
Applied/prepared records describe their journal plan; this dashboard does not assert that
the current checkout still matches it. Use `repel deploy status`/`verify` for live file checks.

Inserted data is the surviving inserted byte ranges divided by total final bytes of placed
files. External build/packet snapshots are excluded, because a build diff is not a measure
of embedded text. Placement bars map ranges into the final image, including ranges split
or removed by later edits. Head/middle/tail distribution uses the insertion offset in the
image before each edit, with thirds as boundaries; the inspector retains the exact byte offset.

HTTP archives contain transformed responses, not the full request population. The dashboard
reports archive counts and never invents a traffic-coverage denominator.

## Integrity and packaging

Metadata checksums and deployment identity bindings are verified before display. Objects are
verified before preview/download. Damaged records are withheld with a visible error. SQLite
connections use read-only mode; the viewer does not acquire a deployment write lock. A busy
or unavailable journal is reported without overwriting the stored data.

The UI assets ship inside the Python package. After updating an isolated installation, use
`python3 -m pipx reinstall .`, or run directly with `python3 scripts/repel.py dashboard ...`.
Stop the server with Ctrl-C. This is a local inspector, not a remotely hosted multi-user service.

The frontend source and its browser checks live in the top-level [dashboard/](../dashboard/README.md)
directory. Both the checkout and the installed package serve the same resource files.
