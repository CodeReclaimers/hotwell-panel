# hotwell-panel

A 1970s-era US power-plant control board for the [`hotwell`](https://github.com/CodeReclaimers/hotwell) steam
plant simulation core: annunciator array, mimic diagram with analog gauges and
pistol-grip switches, manual/auto controller stations, chart recorders, a
sequence-of-events log, and an instructor station.

Single user, localhost. The client is **Svelte 5 + TypeScript + Vite** (plain
SPA, runes mode, no SvelteKit); production serving is one Python process with
the built client mounted by FastAPI.

`hotwell` is consumed strictly as an installed dependency; this repository never
edits it.

## Dev setup

```bash
uv venv .venv
uv pip install -e '.[dev]'            # also installs the pinned hotwell tag
cd client && npm install && cd ..     # node dev deps, version-pinned
```

The core comes from the GitHub tag pinned in `pyproject.toml`, installed
non-editable. Do not `pip install -e ../hotwell` into this venv: it silently
re-points the panel at whatever the core checkout has on disk, including
unreleased changes the panel has not been migrated to.

Development runs two processes — uvicorn for the sim/WebSocket and `vite dev`
for the client with HMR (it proxies `/ws` to :8000):

```bash
make dev                              # or run the two halves yourself:
#   .venv/bin/python -m uvicorn --factory hotwell_panel.server:create_app --port 8000
#   cd client && npm run dev          # then open http://127.0.0.1:5173
```

Production is a single process serving the built client:

```bash
cd client && npm run build && cd ..   # emits client/dist/
.venv/bin/python -m hotwell_panel --scenario builtin:cp1_trip_unrecovered
```

Then open <http://127.0.0.1:8000>. `python -m hotwell_panel` refuses to start
if `client/dist/` is missing.

## Test gate

```bash
make check                            # the whole gate, or piecewise:
.venv/bin/python -m pytest            # server + browser tests (browser tests
                                      #   need chromium AND a built client/dist)
.venv/bin/python -m ruff check .      # python lint
cd client && npm run check            # svelte-check (TS + template, runes)
cd client && npm test                 # vitest (annunciator machine, smoothing,
                                      #   protocol-version guard)
```

## Replay

Every session reduces to a scenario file and replays bit-identically headlessly
— the bridge to later human-vs-agent comparison, and a hard contract:

```bash
.venv/bin/python scripts/session_to_scenario.py \
    sessions/<stamp>_<scenario>.session.yaml -o derived.yaml --replay
```

Exit status is non-zero if the replayed state-history hash differs from the one
recorded live, so this is usable as a gate.

## Units

The core is SI throughout. Everything customary — psig, inHg vacuum, inches,
klb/hr, RPM, °F, MW — is a display-layer affine conversion shipped to the
browser in the `hello` message and applied there (`displayunits.py`). The
simulation contract is never re-expressed in customary units.

## Layout

```
manifest.yaml               instrument/control placement, validated against contracts
scenarios/                  panel-authored scenarios (builtins come from hotwell)
sessions/                   exported session logs (gitignored)
src/hotwell_panel/
  server.py                 FastAPI app, WebSocket endpoint, real-time loop
  session.py                SimSession — the only owner of the Simulator
  protocol.py               message schemas, versioned
  events.py                 simulator state changes -> discrete event messages
  sessionlog.py             session log and its reduction to a scenario
  replay.py                 headless replay + hash verification
  displayunits.py           SI -> US customary, affine
  facegen.py                gauge-face SVG generated from the contracts
  manifest.py               manifest loading + validation
  hello.py                  the static-state message
  scenarios.py              builtin + local scenario discovery
client/                     Svelte 5 + TS + Vite SPA
  src/main.ts               composition root: socket -> stores, window.panel
  src/App.svelte            board shell; {#each} over the placement manifest
  src/types.ts              hand-mirrored protocol.py types + version guard
  src/board.svg             hand-authored mimic one-line template
  src/lib/                  ws, stores, annunciator machine, smoothing, audio
  src/components/           Gauge, PistolGrip, Annunciator, ChartRecorder, ...
  tests/                    vitest unit tests
scripts/session_to_scenario.py
```

## License

MIT. See [LICENSE](LICENSE).
