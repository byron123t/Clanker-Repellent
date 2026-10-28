# Real-project journal checks — 2026-10-28

The local central journal is `.repel-deploy-store/`. The integration workspaces are in
`.repel-workspaces/real-projects-20261028/`. Both directories are ignored by Git and persist
after the dashboard stops. Open this journal from the repository root:

```sh
python3 scripts/repel.py dashboard --store .repel-deploy-store --port 0 --open
```

All placements used `--benign` retention and ordinary documentation notes. No operational
snippet collection or generation result was used. The original curl, horrorgame, and
ballz6Game checkouts were copied before deployment. Additional public projects were fetched
into the isolated workspace. These are actual project files and built artifacts, not the
generated dashboard demo.

## Projects and results

| Project | Recorded target scope | Placement coverage | Validation |
| --- | --- | --- | --- |
| curl | 42 C files in `src/` | 8 / 42 · 19% | Release build, stripped executable, retained note verification, unchanged version output, real local transfers, exact source/executable restoration and redeployment |
| horrorgame | HTML entry and 61 JavaScript files under `src/` | 12 / 62 · 19.4% | Seeded placement, all 12 modified modules pass `node --check`, retained content verified |
| ballz6Game | Six existing WebAssembly modules under `addons/debug_draw_3d/libs/` | 3 / 6 · 50% | All three modified modules compile with `WebAssembly.Module`; original module bytes remain intact and the new custom section contains the note |
| jq 1.8.2 | 21 C files in `src/` | 5 / 21 · 23.8% | Built and stripped, JSON processing check, all nine upstream `make check` groups pass, exact executable restoration and redeployment |
| htmx 2.0.11 | `src/htmx.js` | 1 / 1 · 100% | Minified with the upstream UglifyJS flags; Chrome executes the bundle, completes an AJAX/DOM swap, and exposes the retained note |
| Marked 18.1.2 | 13 TypeScript files in `src/` | 5 / 13 · 38.5% | Upstream esbuild ESM/UMD builds with minification; both retain the note; all 2,160 upstream unit/spec tests pass |

Percentages describe the listed target scopes, not entire repository coverage. Random
selection uses seed 42. The ballz6Game check covers its existing WASM extension modules;
a complete Godot web export was not available. The horrorgame check covers source and
response retention, not a full gameplay regression test.

After the upstream jq tests rebuilt its executable, the verified stripped version was
restored from the journal. The final executable passes retention and JSON processing checks
and matches its recorded hash. All six final deployments match their recorded updated files.

## Real HTTP response archive

The rebuilt curl executable fetched three actual project files through the retention
middleware over loopback: horrorgame's HTML and main JavaScript module, plus a ballz6Game
WASM module. Each transformed response was recorded in the same central journal. Restoring
each archived original entity body reproduced its original SHA-256 exactly. The temporary
HTTP test server was stopped after validation.

The completed journal contains six latest applied deployments, two restored deployment
records, 34 current recorded insertions, and three archived responses. This count is the
state at validation time; the dashboard reads the live journal on subsequent refreshes.

## Provenance and local reports

Public sources were fetched from their upstream projects:

- [jq 1.8.2](https://github.com/jqlang/jq/releases/tag/jq-1.8.2), source archive SHA-256
  `71b8d6e8f5fe81f6c6d0d110e3892251f6ce76ed095abd315e26e6e1193af3af`.
- [htmx](https://github.com/bigskysoftware/htmx), revision
  `fa978b24e75fb03c137bf2cdae4fef0e711cf8a1`.
- [Marked](https://github.com/markedjs/marked), revision
  `ce78bb06863f2bb733b2bc1f6c4590106b0d4dce`.

The workspace retains `provenance.json`, `web-verification.json`, `curl-verification.json`,
`jq-verification.json`, `marked-verification.json`, `htmx-verification.json`,
`htmx-browser-test.json`, and `http-verification.json`, plus build and upstream test logs.
Original build artifacts and source bytes remain in the content-addressed journal.

The dashboard browser check covers real repository counts and coverage, metadata-only
overview loading, search, benign snippet/original-file previews, downloads, archived
responses, authentication, and responsive layout. Its source is in
[`dashboard/tests/browser-smoke.cjs`](../dashboard/tests/browser-smoke.cjs).
