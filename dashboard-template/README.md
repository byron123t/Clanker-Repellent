# File-change viewer design template

This is a **read-only visualization of synthetic file-change records**. Use it to design
charts, file navigation, previews, and download interactions. All example projects, file
versions, snippets, and response bodies are generated locally by `build_fixtures.py`.

The API uses the same record structure as Repel's annotation journal, so a finished design
can be connected to that journal later. The standalone server serves its own sample files;
project modification and restoration belong to the separate Repel application.

## Run anywhere

Move or copy **this entire directory** to your preferred location. Python 3.9+ is the only
runtime requirement. The server works without the original repository, its virtual
environment, a journal database, Node, or an internet connection.

```sh
cd /wherever/you/put/dashboard-template
python3 serve.py --open
```

The server prints a local URL with a session token and chooses an available loopback port.
Open that complete URL. Stop with Ctrl-C. An absolute path to `serve.py` also works from
another working directory. Frontend changes appear on browser refresh.

## Design handoff

Give your agent [AGENT_BRIEF.md](AGENT_BRIEF.md). The task is frontend design using the
included sample API. It covers coverage charts, byte-position tracks, search, file-version
previews, accessibility, and responsive layouts.

```text
dashboard-template/
  AGENT_BRIEF.md       Frontend task and acceptance criteria
  API_CONTRACT.md      Read-only endpoints and field definitions
  INTEGRATION.md       Optional connection to the main application
  serve.py            Local sample API and static asset server
  web/                Editable HTML, CSS, JavaScript, and favicon
  fixtures/README.md  Sample provenance and design scenarios
  fixtures/           Generated record metadata and content objects
  build_fixtures.py   Reproducible sample-data generator
  tests/              API and browser checks
  reference/          Desktop and mobile reference screenshots
```

The UI identifies the dataset as **Synthetic sample data** on every view. Its numbers
come from the fixture API. The seven example projects cover different file types, sparse
and dense coverage, historical records, pending snapshots, an unknown coverage denominator,
and a 280-file inventory. Three response samples exercise text and binary previews.
See [the fixture guide](fixtures/README.md) for details.

## Check the design

```sh
python3 serve.py --scenario populated --open
python3 serve.py --scenario empty --open
python3 serve.py --scenario error --open
python3 serve.py --check
python3 -m unittest discover -s tests -v
node --check web/app.js
```

`empty` returns no records; `error` simulates an unavailable data source. These states help
test explanatory messages and layout. `--check` validates asset availability and content
hashes. Previews and downloads read saved fixture objects; requests to change data return 405.

Optional browser checks use Playwright:

```sh
npm install
npx playwright install chromium
REPEL_DASHBOARD_URL='http://127.0.0.1:PORT/#token=TOKEN' npm run test:browser
```

Use the URL printed by `serve.py`. Set `REPEL_CHROME` to use an existing Chrome executable.
The reference screenshots show the included starting design; refresh them for your candidate.

Run `python3 build_fixtures.py` to regenerate the samples, then restart the server. The
fixture guide explains which files are generated. Optional connection to real records and
instructions for returning the design are in [INTEGRATION.md](INTEGRATION.md).
