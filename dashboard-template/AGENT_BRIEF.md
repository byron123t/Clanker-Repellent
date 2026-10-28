# Design task: make this dashboard substantially better

Build an excellent interface for understanding where documentation snippets were embedded
across source files, native builds, websites, and WASM modules. The user wants a substantial
improvement in visual quality and useful visualization. You have freedom to replace the
layout, visual language, interactions, charts, and frontend code in `web/`.

The audience is a developer inspecting a reversible deployment journal. The central tasks are:

1. Understand repository coverage and the scope behind each percentage.
2. Locate individual placements and inspect their exact byte positions.
3. Retrieve a snippet, the original file, or the post-deployment file.
4. Compare current deployments with restored history and pending build snapshots.
5. Browse archived responses and download their exact original bodies.

## Working environment

Run `python3 serve.py --open`. This folder contains everything needed. Read `API_CONTRACT.md`
and inspect the synthetic fixtures to understand the data. The fixture server is standard
Python; there is no build pipeline to learn. Framework changes are allowed if their setup
and built output remain self-contained and the integration steps are documented.

## Design expectations

- Establish a clear hierarchy, readable typography, strong contrast, and intentional spacing.
- Make charts useful for choosing and inspecting real records. Values must come from the API.
- Make dense and sparse repositories both understandable. Test the large inventory and the
  unknown-denominator record; unknown coverage is not zero or 100 percent.
- Preserve fluid desktop and mobile layouts. File paths and binary previews can be long.
- Provide keyboard focus states, meaningful labels, reduced-motion support, and understandable
  loading, empty, error, and selected states.
- Keep sample data visibly identified. Metadata checks are not a claim of live build health.

## Behaviors to preserve

- Same-origin GET API with the Bearer token obtained from the URL fragment.
- Repository/deployment selection and file search.
- Coverage calculated from the recorded eligible file set; restored placements remain historical.
- Content fetched only on explicit preview/download actions and displayed as inert text.
- Exact-byte downloads, truncated-preview labels, binary/base64 labels, and copy controls.
- HTTP archive navigation and original-body retrieval.
- No restore/deploy commands executed by the UI. Command examples may be copied.

## Deliverable

Leave a runnable candidate in this directory. Include desktop and mobile screenshots, tests
you ran, design decisions that materially improve the workflow, and any unresolved issues.
Document how to build and integrate additional assets if the four-file layout changes.
The user will compare your version and can try it against their real journal with `--assets`.
