# Portable dashboard design template

Move or copy **this entire directory** anywhere. It runs independently of Repel, the original
repository, its virtual environment, and its central journal. Python 3.9+ is the only runtime
requirement. No installation, network access, or Node build step is needed.

```sh
cd /wherever/you/put/dashboard-template
python3 serve.py --open
```

The server chooses an available loopback port and prints an authenticated URL. Open that
URL, including `#token=…`. Stop with Ctrl-C. You can also run the server by its absolute path
from any working directory.

## Hand this to another agent

Point the agent at [AGENT_BRIEF.md](AGENT_BRIEF.md). It has the design task, API requirements,
acceptance checks, and handoff expectations. The agent can replace everything in `web/`.

```text
dashboard-template/
  AGENT_BRIEF.md       Ready-to-use design task
  API_CONTRACT.md      Endpoints, data shapes, and metric meanings
  serve.py            Independent read-only fixture API + asset server
  web/                Editable HTML, CSS, JavaScript, and favicon
  fixtures/           Synthetic metadata and benign content objects
  build_fixtures.py   Rebuild the fixtures without reading any repository
  tests/              Standard-library server/fixture checks
  reference/          Desktop and mobile screenshots of this starting point
```

The included UI is a working starting point with an interactive file atlas, byte tracks,
repository navigation, original/snippet previews, and downloads. It is deliberately a copy:
editing it does not change the main dashboard.

## Useful states

```sh
python3 serve.py --scenario populated --open
python3 serve.py --scenario empty --open
python3 serve.py --scenario error --open
python3 serve.py --check
python3 -m unittest discover -s tests -v
node --check web/app.js
```

Populated fixtures include seven repositories, several file types, head/middle/tail
insertions, a binary snapshot, a pending artifact, restored history, an unknown coverage
denominator, a 280-file inventory, and three archived responses. They contain synthetic
examples, not copied project files, credentials, journal snapshots, or operational payloads.
The UI labels this mode **Isolated template · sample data**. `error` simulates an unavailable
journal; `empty` returns an empty one.

`python3 build_fixtures.py` regenerates deterministic data in `fixtures/`. The server validates
object hashes at startup and before returning content. Restart after changing fixture data;
frontend edits appear on browser refresh.

Optional browser regression checks use Playwright (Node is only needed for these checks):

```sh
npm install
npx playwright install chromium
REPEL_DASHBOARD_URL='http://127.0.0.1:PORT/#token=TOKEN' npm run test:browser
```

Use the URL printed by this template's server. Set `REPEL_CHROME` to use an existing Chrome
executable. The screenshots in `reference/` are a baseline for the next design iteration.

## Try a candidate against a real journal

This optional step uses the main Repel installation. It is not needed for independent design.
Run from the main repository, pointing `--assets` at the moved template's `web/` directory:

```sh
python3 scripts/repel.py dashboard --store /path/to/.repel-deploy-store \
  --assets /wherever/dashboard-template/web --port 0 --open
```

That serves the candidate frontend with the real, read-only journal API without replacing
the production frontend. There is no need to put a live journal or session token in this
template. The token printed by `serve.py` authenticates only the local fixture server.

## Bring the design back

Copy the finished `web/index.html`, `web/app.js`, `web/style.css`, and `web/favicon.svg` into
the main repository's `dashboard/repel_dashboard_ui/`. Preserve its `__init__.py`. Run the
dashboard browser checks and Python dashboard tests there. If you introduce additional
assets or a framework, document the build and extend the production asset allowlist/package
data accordingly. Keep all runtime assets local and compatible with the CSP in the contract.
