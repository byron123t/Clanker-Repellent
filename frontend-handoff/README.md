# Frontend design handoff

A movable workspace for redesigning a read-only file-change dashboard. The editable app
is in `web/`. Fixed synthetic responses supply charts, lists, previews, and downloads.

## Run

Move this whole folder anywhere, then run:

```sh
python3 preview.py --open
```

Python 3.9+ is sufficient. No installation or internet connection is required to run the
preview. It prints a local URL with a session token; open the complete URL. Stop with Ctrl-C.
You can also run `preview.py` by its absolute path from another directory.

## Delegate

Give the agent this folder and [DESIGN_BRIEF.md](DESIGN_BRIEF.md). The assignment is to
improve `web/index.html`, `web/style.css`, `web/app.js`, and `web/favicon.svg`. Use
[UI_GUIDE.md](UI_GUIDE.md) for the data and interactions the frontend needs.

`preview.py` serves saved responses from `fixtures/responses.json`. Treat those as supplied
preview infrastructure. The folder contains no fixture generator or main-application code.
All seven projects and three response samples are fictional. The UI labels them synthetic.

```text
web/             Editable frontend
DESIGN_BRIEF.md   Task and acceptance criteria
UI_GUIDE.md      Frontend data and interaction guide
preview.py       Local read-only preview server
fixtures/        Fixed sample responses
tests/           Preview and browser checks
reference/       Starting desktop and mobile screenshots
```

## Check

```sh
python3 preview.py --check
python3 preview.py --scenario empty --open
python3 preview.py --scenario error --open
python3 -m unittest discover -s tests -q
node --check web/app.js
```

The default scenario is `populated`. Frontend edits appear on refresh. The other scenarios
exercise empty and unavailable-data views. Node is only needed for JavaScript checks.

Optional browser checks:

```sh
npm install
npx playwright install chromium
REPEL_DASHBOARD_URL='http://127.0.0.1:PORT/#token=TOKEN' npm run test:browser
```

Use the URL from `preview.py`. Set `REPEL_CHROME` to use an existing Chrome executable.

Return the finished `web/` directory, updated screenshots, and a short description of
design decisions and checks. The owner will handle connection to the main application.
