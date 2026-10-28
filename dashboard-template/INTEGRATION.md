# Optional integration with the Repel journal

The portable template is sufficient for independent frontend design. This guide covers
trying a finished candidate with real records and returning it to the main application.

Repel's separate command-line tools place source snippets or retained notes in software
files and record those changes in a recovery journal. The dashboard reads that journal.
Serving a candidate frontend gives it the viewer's existing read-only API; record labels
such as `applied` and `restored` describe the producing tools' saved operations.

## Preview a candidate with real records

Run from the main Repel repository, using a journal you own:

```sh
python3 scripts/repel.py dashboard --store /path/to/.repel-deploy-store \
  --assets /wherever/dashboard-template/web --port 0 --open
```

This starts a local viewer with the candidate assets. Its printed URL contains a new
session token. The template server's token is separate. The real journal uses the same
schema, and its summary does not set `template: true`; the UI should identify the connected
journal instead of labeling these records synthetic.

Keep private journals and session tokens outside the portable handoff. Previews can contain
project content. Saved metadata does not verify the current state of a repository.

Some real records provide command examples in `examples`. The UI may display and copy them;
it does not run them. The template returns an empty mapping because its projects are fictional.

## Return the design

Copy the candidate's `web/index.html`, `web/app.js`, `web/style.css`, and `web/favicon.svg`
into the main repository's `dashboard/repel_dashboard_ui/`, preserving `__init__.py`.
Run the main dashboard's Python and browser checks. Include any new asset routes, package
files, dependencies, and build steps if the candidate changes the four-file layout.

Keep the API's paths, field meanings, authenticated GET requests, and content-preview
behavior compatible. The included frontend displays dataset provenance for both the
synthetic template and a connected journal; preserve that distinction in the finished design.
