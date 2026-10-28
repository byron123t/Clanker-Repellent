# Repel dashboard

The journal frontend lives here. The Python application serves these assets and the
authenticated API together; there is no frontend build step or external asset service.

From the repository root, open the persistent central journal:

```sh
python3 scripts/repel.py dashboard --store .repel-deploy-store --port 0 --open
```

Or run `npm start` from this directory. The CLI prints the authenticated local URL.
Use that URL when reopening the page after restarting the server.

## Layout

- `repel_dashboard_ui/index.html`: workspace, deployment, snippet, and response views.
- `repel_dashboard_ui/style.css`: responsive layout, charts, and visual design.
- `repel_dashboard_ui/app.js`: authenticated journal reads and interactions.
- `tests/browser-smoke.cjs`: browser checks against a running journal.
- `../src/clanker_repellent/dashboard/`: read-only API, integrity checks, and demo support.

`repel_dashboard_ui` is also a Python resource package. The wheel includes its assets;
the source checkout serves the same files directly, so frontend edits appear on refresh.

## Views and metrics

The overview compares the latest journal record for each repository. Placement and byte
totals include only those latest records whose state is `applied`; restored history is
still available in the deployment selector and activity list. Each coverage percentage
uses that deployment's recorded compatible target scope, which can be an explicit subset
of a repository. A missing denominator stays unknown. The overview does not scan live files.

Select a repository card or coverage bar to inspect its file map. The snippet explorer
supports file search, exact byte positions, original-file previews, copying, downloads,
and recovery command examples. `/` focuses the current search field. Content is fetched
only after selecting **Load snippet**, **Load example**, or **View original**.

See [the journal guide](../docs/journal-dashboard.md) for complete metric and integrity
semantics, and [the real-project checks](../docs/real-project-validation.md) for the local
integration workspaces behind the current journal.

## Checks

```sh
npm run check
npm install
npx playwright install chromium
REPEL_DASHBOARD_URL='http://127.0.0.1:PORT/#token=TOKEN' npm run test:browser
```

Set `REPEL_CHROME` to use an existing Chrome executable. Browser tests read metadata from
the selected journal and preview content only from records explicitly marked benign.
The dashboard itself does not need Node or Playwright to run.
