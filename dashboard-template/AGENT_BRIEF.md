# Design task: improve the file-change viewer

Design a clear, polished interface for a **read-only visualization of synthetic file-change
records**. This folder supplies a working frontend, a local sample API, and deterministic
fixtures. You can change the layout, typography, colors, charts, and frontend implementation.

The audience is a developer reviewing recorded changes and saved file versions. The task
is to make those records understandable and easy to explore.

## Workflows

1. Compare projects' recorded file coverage and see the denominator behind each percentage.
2. Select a file and locate its recorded snippet ranges on a byte-position track.
3. Preview or download a snippet, an original file version, or an updated version.
4. Distinguish applied records, restored history, and pending snapshots.
5. Browse saved response samples and view text or binary content.

## Working environment

Run `python3 serve.py --open`. Read `API_CONTRACT.md` for endpoints and field meanings and
`fixtures/README.md` for sample provenance and edge cases. The server uses Python's standard
library and reads files inside this directory. No build pipeline is required.

The API schema is shared with the main Repel journal. It describes records produced by
separate software operations; this design task concerns how the viewer presents them.
The template's paths are fictional, and its records have no operating system targets.

Framework changes are welcome if their setup and built output remain portable. Document
any build step and additional assets needed for integration.

## Design expectations

- Use concrete descriptions of the data and controls. Explain technical fields where useful.
- Keep dataset provenance visible throughout navigation. Label loaded sample records
  **Synthetic sample data**, and retain the last known source label on a connection error.
- Establish readable typography, clear hierarchy, restrained chart marks, and useful spacing.
- Derive chart values from API records and make marks support selection or inspection.
- Explain unknown coverage with an unknown state; a missing denominator is not zero.
- Handle both the large inventory and projects with very few recorded changes.
- Support keyboard focus, meaningful accessible labels, and reduced motion.
- Fit mobile and desktop widths, including long file paths and binary previews.
- Distinguish recorded state from a current check of a project's files or build.

## Interface behavior

- Authenticate same-origin GET requests with the token in the server's printed URL.
- Preserve project/record selection, file search, and the recorded coverage scope.
- Load stored content after an explicit preview/download action and render it as text.
- Label truncated previews and base64 encoding; downloads contain the full saved bytes.
- Keep copy and download controls usable across snippet and file-version previews.
- Show optional command examples only when a record provides them. Synthetic records provide
  none. The main application may supply copyable examples through the same schema.

## Deliverable

Leave a runnable candidate in this directory with desktop and mobile screenshots, the
checks you ran, relevant design decisions, and any unresolved issues. Test populated, empty,
and unavailable-data scenarios. Include setup instructions if dependencies change.
The optional connection to the main application is described in `INTEGRATION.md`.
