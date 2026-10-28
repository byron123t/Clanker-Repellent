# File-change viewer design workspace

This folder is a standalone frontend project with a read-only sample API. Its records and
content are synthetic. Start with `AGENT_BRIEF.md`, then use `API_CONTRACT.md` and
`fixtures/README.md` for the data model and sample scenarios.

Run `python3 serve.py --open`. Design work belongs in `web/`; the fixture server supplies
local data. Keep the dataset label visible and derive displayed values from the API.
Describe fields and behavior directly. Render previews as text and load content after a
preview or download action. Preserve the server's authentication and browser protections.

Check desktop and mobile layouts, keyboard navigation, populated/empty/error states, and
preview/download behavior. Run `python3 -m unittest discover -s tests` and
`node --check web/app.js`. Include screenshots and run instructions in the handoff.
The optional main-application connection is documented separately in `INTEGRATION.md`.
