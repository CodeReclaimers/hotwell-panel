# hotwell-panel

A 1970s-era US power-plant control board for the [`hotwell`](../hotwell) steam
plant simulation core: annunciator array, mimic diagram with analog gauges and
pistol-grip switches, manual/auto controller stations, chart recorders, a
sequence-of-events log, and an instructor station.

Single user, localhost, one Python process. Vanilla JavaScript ES modules and
SVG in the browser — no build step, no node toolchain, no framework.

`hotwell` is consumed strictly as an installed dependency; this repository never
edits it.

## Dev setup (two repos, checked out side by side)

```bash
uv venv .venv
uv pip install -e ../hotwell          # the core, as a dependency
uv pip install -e '.[dev]'
```

```bash
.venv/bin/python -m pytest            # all tests
.venv/bin/python -m ruff check .      # lint
.venv/bin/python -m hotwell_panel --list-scenarios
.venv/bin/python -m hotwell_panel --scenario builtin:cp1_trip_unrecovered
```

Then open <http://127.0.0.1:8000>.

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
  static/                   index.html, panel.css, js/, board.svg
scripts/session_to_scenario.py
```
