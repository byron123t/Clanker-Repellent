# Dashboard design workspace

This folder is an isolated, movable design project. Start with `AGENT_BRIEF.md` and
`API_CONTRACT.md`. Run `python3 serve.py --open`; no parent repository is required.

Edit `web/` freely to implement the design. Fixtures are synthetic and benign. Preserve
their label so sample data is distinguishable from a live journal. Keep previews inert and
request them only after a user action. Runtime assets should work without external services.

Verify desktop and mobile layouts, keyboard interactions, populated/empty/error states,
and preview/download behavior. Run `python3 -m unittest discover -s tests` and
`node --check web/app.js`. Include screenshots and exact run instructions in your handoff.
