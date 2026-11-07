# Steam Plant Control Panel — Phase 2 Implementation Plan

## 0. Context and objective

Phase 1 delivered `hotwell`: a deterministic headless steam-plant simulation with stable
observation, action, scenario, and protection-table contracts. **`hotwell` lives in its
own repository** (it may be published to PyPI later); this phase builds `hotwell-panel`,
a **separate sibling repository** that consumes `hotwell` strictly as an installed
dependency. Check both repos out side by side and read `../hotwell/HANDOFF.md` before
starting — its "Notes for the panel phase" section feeds this plan directly. **Phase 2
builds the human-playable browser control panel.** No AI
agent, no LLM calls — the assistant arrives in phase 3; this phase reserves its screen
region only.

The product: a single-user, localhost web app presenting a 1970s-era US power-plant
control board — annunciator array, mimic diagram with analog gauges and pistol-grip
switches, manual/auto controller stations, chart recorders, a sequence-of-events log,
and an instructor station for scenario control. A player must be able to run the
condensate-pump casualty from the panel and either save the plant or watch the cascade
the handoff documents (DA drain → FP suction trip → safety valves → low-low drum level
→ MFT → dead bus).

**Definition of done:** acceptance tests in §12 pass, the human-playable checklist in
§12.7 is demonstrated, and `HANDOFF.md` is updated per §14.

## 1. Locked design decisions

- **One Python process.** FastAPI serves static assets and a WebSocket; the simulator
  runs in-process in an asyncio task. No separate workers, no message broker.
- **Frontend: Svelte 5 + TypeScript + Vite, plain SPA — no SvelteKit.** Chosen for
  fine-grained compiled reactivity (the right shape for one 20 Hz telemetry stream
  fanning out to many small SVG elements — no virtual-DOM diff per frame) and for
  stack alignment with Alan's target work. No routing, no SSR; FastAPI stays the only
  server. Force runes mode in `svelte.config`/compiler options so legacy syntax fails
  loudly.
- **Write Svelte 5 idioms, not Svelte 4.** `$state`/`$derived`/`$effect`/`$props`,
  snippets rather than slots, `onclick` rather than `on:click`, reusable reactive
  logic in `.svelte.ts` modules. Assistant-generated Svelte skews toward Svelte 4
  patterns (`export let`, `$:`, writable stores) from training-data vintage — that is
  the expected failure mode; `svelte-check` is in the test gate to catch it, and
  current Svelte docs win over habit whenever in doubt.
- **The panel is a thin animation/input layer.** Everything derivable from contracts is
  generated server-side in Python (gauge faces, annunciator legend, unit conversion
  tables, layout validation) and shipped to the client as SVG/JSON. The Svelte client
  animates needles, runs the annunciator flasher, and sends actions — it contains as
  little domain knowledge as possible.
- **Sim time is authoritative; actions are stamped to sim ticks.** Operator actions are
  queued and applied at the next tick boundary exactly as scenario `action` events are.
  Every session therefore reduces to a scenario file and is **replayable bit-identically
  headlessly** (§3.4). This is the bridge to phase-4 human-vs-agent comparisons; treat
  it as a contract.
- **Fixed dt = 0.05 s always.** Speed control multiplies steps per wall tick, never
  changes dt. Pause stops stepping, never the server.
- **Display units are US customary, period-correct** (psig, inHg vacuum, °F, inches of
  water, klb/hr, RPM, Hz, MW), implemented entirely in the panel layer. The `hotwell`
  SI contract is untouched.
- **Panel default fidelity: `drum.model: astrom_bell` + three-element feedwater** (per
  phase-1 D18). Two-state drum and single-element control remain instructor-selectable —
  single-element + AB is a legitimate degraded-mode training configuration, not a bug.
- **This repository never edits `hotwell`.** The small core changes the panel needs
  (§11) are a precursor task executed in the `hotwell` repo first and released as
  `hotwell` 0.2.0. Anything else the panel wants from the core goes in `HANDOFF.md` as
  a proposal for a future core release, not an edit.
- **`hotwell-panel` is its own package (Python + node).** Python runtime deps:
  `hotwell>=0.2,<0.3`, `fastapi`, `uvicorn[standard]`; dev extra `[dev]`: `pytest`,
  `ruff`, `playwright` (one smoke test). Node dev deps, version-pinned in
  `package.json`: `svelte` 5.x, `@sveltejs/vite-plugin-svelte`, `vite`, `typescript`,
  `svelte-check`, `vitest`. Nothing else on either side. Dev setup (document in
  README): `uv pip install -e ../hotwell`, `uv pip install -e '.[dev]'`,
  `npm install`; then run `uvicorn` and `vite dev` side by side (a two-line
  `make dev` is fine). Production is single-process: `vite build`, then
  `python -m hotwell_panel` serves the built client.

## 2. Architecture and repository layout

Separate repository, expected checked out beside `hotwell`. The panel consumes
`hotwell` only through its public API; `hotwell` keeps zero web dependencies.

```
hotwell-panel/
  pyproject.toml        # package hotwell_panel; depends on hotwell>=0.2,<0.3
  package.json          # svelte 5, vite, typescript, svelte-check, vitest (pinned)
  vite.config.ts        # svelte plugin; dev proxy /ws -> :8000 with ws upgrade
  tsconfig.json
  README.md             # incl. the two-repo dev setup from §1
  HANDOFF.md
  manifest.yaml         # instrument/control placement (§6.1)
  scenarios/            # panel-authored scenarios (hotwell built-ins load via §11 API)
  sessions/             # exported session logs (gitignored)
  client/
    index.html
    src/
      main.ts
      App.svelte
      types.ts          # hand-mirrored protocol.py types + protocol_version guard
      board.svg         # hand-authored mimic board template with placement slots
      panel.css
      lib/              # ws.ts, audio.ts, and .svelte.ts stores: frame, events,
                        #   annunciator (ISA state machine), smoothing (needle low-pass)
      components/       # Gauge, Lamp, PistolGrip, Breaker, MAStation, Annunciator,
                        #   ChartRecorder, SoeLog, Instructor, AdvisorBezel (.svelte)
  src/hotwell_panel/
    __main__.py         # python -m hotwell_panel [--scenario s] [--port 8000]
    server.py           # FastAPI app, WebSocket endpoint, mounts client/dist in prod
    session.py          # SimSession: owns Simulator, RT loop, action queue,
                        #   session log, speed/pause, scenario lifecycle
    protocol.py         # message dataclasses + JSON (de)serialization, versioned
    displayunits.py     # SI -> display conversions, per-instrument (table in §5)
    facegen.py          # generates gauge-face SVG defs from ObservationSpec +
                        #   the protection table (ranges, ticks, red zones)
    manifest.py         # loads/validates panel manifest against contracts (§6.1)
  scripts/
    session_to_scenario.py  # session log -> scenario YAML (replay bridge)
  tests/                # pytest: protocol, replay-determinism, manifest, facegen, units
                        # vitest lives under client/ (annunciator machine, smoothing,
                        #   types guard)
```

Dev mode runs two processes: `uvicorn` on :8000 and `vite dev` proxying `/ws` (with
WebSocket upgrade enabled) — hot module reload against the live sim. Production mode is
one process: `vite build` emits `client/dist/`, which `server.py` mounts;
`python -m hotwell_panel` fails with a clear message if `dist/` is missing.

`SimSession` is the only owner of the `Simulator`. WebSocket handlers never touch the
sim directly; they enqueue messages and subscribe to broadcasts. Multiple browser
connections may observe; all may act (it's a localhost tool — no auth, no roles).

## 3. Real-time loop, time control, session log

### 3.1 Loop

Asyncio task at 20 Hz wall clock with drift-corrected scheduling (absolute next-tick
times, not accumulated sleeps). Per wall tick: drain the action queue → apply at tick
boundary → `sim.step()` × `speed` → broadcast one `frame` + any `event`s. If the wall
deadline is missed (slow machine), log it and continue — sim determinism is unaffected
because dt never changes.

### 3.2 Speed and pause

`speed ∈ {1, 2, 5}` (steps per wall tick). Pause freezes stepping; UI flashers keep
running on wall clock. Frames are only sent when the sim steps (plus one immediately on
state-changing instructor commands), so a paused panel is static except UI animation.

### 3.3 Scenario lifecycle

States: `no_scenario → loaded(frozen at t=0) → running ⇄ paused → ended(plant_dead |
max_t | operator_reset)`. Loading a scenario constructs a fresh `Simulator` (reset =
reload; no snapshot/restore machinery). The scenario picker merges two sources:
`hotwell`'s built-in canonical scenarios (via the 0.2.0 package-data accessor, §11) and
this repo's local `scenarios/` directory, labeled by origin.
Scenarios authored for panel play should contain casualty events but no scripted
recovery `action` events; the canonical `cp1_trip_recovered` stays a headless test
artifact (loading it in the panel is allowed and simply plays itself — see §13 P4
attract mode).

### 3.4 Session log and replay (contract-grade)

Every applied action (operator or scenario) is recorded as `(tick, source, command,
result)`. On demand or at session end the server writes
`sessions/<timestamp>_<scenario>.session.yaml`: scenario reference, seed, fidelity
config, action log, end state, and the state-history hash `hotwell` already computes.
`scripts/session_to_scenario.py` converts a session file to a plain scenario YAML.
**Acceptance test:** a session driven through the live server, converted and replayed
headlessly, reproduces the identical state-history hash.

## 4. WebSocket protocol

One endpoint (`/ws`), JSON text messages, `protocol_version: 1` in the hello. Schemas
live in `protocol.py` dataclasses; document every field there, not in prose.

Server → client:

- `hello` — protocol version, scenario info, fidelity config, ObservationSpec digest,
  display-unit table, annunciator legend (id → window position, text), gauge-face SVG
  bundle, manifest.
- `frame` — `t`, sensed values (SI floats; client converts for display), indications,
  alarm states, sim status (`running|paused|ended`, speed), and the audit pair
  (mass/energy closure — instructor display).
- `event` — alarm transitions (id, `clear→active` etc., first_out flag), trips,
  pump-mode changes, SV lift/reseat, plant_dead. Drives horn, SOE log, and annunciator
  flash edges so the client never diffs frames.
- `action_result` — echo of a submitted action with accepted/rejected + reason
  (rejections surface verbatim on the panel per phase-1 handoff).
- `chart_data` — response to `chart_query` (historian passthrough).

Client → server:

- `action` — one command dict, exactly `hotwell.actions` schema.
- `instructor` — `load_scenario | run | pause | speed | reset | inject_event |
  export_session`. `inject_event` accepts the scenario event types (`trip_pump`,
  `inhibit_start`, `sensor_fault`, `set_load`, `set_air_ingress`) for live casualty
  insertion.
- `chart_query` — signals, t0, t1, max_points (historian `query` passthrough).

Frames are ~2–4 KB at 20 Hz on localhost; do not optimize. No binary framing, no
compression, no batching. The client mirrors these schemas by hand in
`client/src/types.ts` and refuses to run on a `protocol_version` mismatch;
dataclass→TypeScript codegen is a noted future nicety, not part of this phase.

## 5. Display units and instrument faces

### 5.1 Conversion table (panel layer only; SI beneath)

| Signal group | Display unit | Anchors (from achieved design point) |
|---|---|---|
| Drum/chest/DA pressure | psig | 8.0 MPa → 1146 psig; SV 8.6 MPa → 1233 psig; DA 0.15 MPa → 7.1 psig |
| Condenser pressure | inHg vacuum | 7 kPa abs → 27.9 inHg vac (higher = better; gauge reads vacuum) |
| Drum/hotwell/DA level | inches (drum: relative to NWL) | LOLO −300 mm → −11.8 in; drum gauge ±15 in |
| Flows | klb/hr | 76.9 kg/s → 611 klb/hr; feed 87.1 kg/s → 691 klb/hr |
| Shaft speed | RPM (2-pole, 60 Hz ⇒ 3600 nominal) | overspeed trip 110% → 3960 RPM |
| Frequency | Hz | meter face 50–70 Hz — **must** span the 66 Hz overspeed equivalent (phase-1 handoff note); do not "improve" this to 55–65 |
| Electrical | MW, 0–75 | |
| Temperatures | °F | Tsat(8 MPa) 295 °C → 563 °F |
| Valve/firing | % | |
| Pump motor current | % rated amps, 0–125% | |

`displayunits.py` owns conversions and formatting (sig figs per instrument resolution);
Python tests pin the anchor rows above. The client receives the table in `hello` and
applies it mechanically.

### 5.2 Generated gauge faces

`facegen.py` renders each instrument's face as an SVG def: 270° sweep, major/minor
ticks from display range and resolution, engraved label, units legend, and colored
arcs/lines for alarm and trip setpoints **read from the installed `hotwell`'s
protection table (§11 accessor)** (alarm =
amber tick, trip = red arc, SV lift = red line). Setpoints thereby appear on gauge
faces without duplication — the protection table is already the single source of truth.
Faces regenerate at server start; a golden-file test pins a couple of rendered faces to
catch accidental drift. The client treats each face as an opaque def injected via
`{@html}` inside its `Gauge` component — faces are data, not components.

## 6. Panel layout and widget inventory

Layout regions (single page, target 1600×900+, degrade gracefully to 1280):

- **Top strip, full width: annunciator array** (§7).
- **Left ~58%: mimic board** — the flow path hotwell → CP-1/2 → DA → FP-1/2 → FRV →
  drum → throttle → turbine-generator → condenser → hotwell, drawn as a period one-line
  with gauges at their tap points, pump symbols with run/trip lights and pistol-grip
  switches, valve position indicators, generator breaker and non-vital load breaker,
  the four controller stations (§6.3), and covered manual-trip pushbuttons (§11).
- **Right ~42%, stacked:** chart recorders (§8.1), SOE log (§8.2), and a dark CRT bezel
  labeled `ADVISOR — OFFLINE` reserving the phase-3 assistant region (non-functional;
  a single static placeholder line of phosphor-green text is fine).
- **Bottom drawer, collapsible: instructor station** (§9) — deliberately styled as the
  out-of-fiction training console.

### 6.1 Placement manifest

`manifest.yaml` maps every placed element: `{id, kind: gauge|lamp|grip|station|
breaker|annunciator|chart|button, instrument_or_action_ref, x, y, size, options}`.
`manifest.py` validates at server start: every referenced instrument exists in
ObservationSpec; every referenced action key exists in ACTION_SCHEMA; every alarm id in
protection.yaml has an annunciator window; **coverage check** — every instrument in the
spec is either placed or explicitly listed under `unplaced:` with a reason. A pytest
runs the same validation. This keeps the drawing honest as contracts evolve. The client
renders the board as one `<svg>` root — `board.svg` inlined — with an `{#each}` over
manifest entries instantiating `Gauge`/`Lamp`/`PistolGrip`/etc. components as
positioned `<g>` groups.

### 6.2 Widget behavior notes

- **Gauges**: needle driven by sensed value with client-side first-order smoothing,
  τ ≈ 150 ms — analog feel without lying about the data (the underlying 20 Hz values
  are what the sim sensed, including the ±0.05 MW droop dither the phase-1 handoff
  notes; let it show). Implement with `svelte/motion` (`Tween`/`Spring`) or a small
  low-pass in a shared `.svelte.ts` store — the time constant is the spec, the
  mechanism is the implementer's choice. No interpolation beyond smoothing.
- **Pistol grips** (pump start/stop): three-position spring-return-to-center,
  START/NORM/STOP, drawn rotated; click-and-hold left/right or keyboard. Emits
  `cpN.start`/`cpN.stop` on release. Green (running) / red (stopped) lamps above each
  grip, amber for tripped — lamp state from `indications`, which phase 1 guarantees
  honest. (Sense flipped 2026-08-30 to Alan's operator convention; see §10.)
- **Breakers**: generator output breaker indication (closed/open — opens on turbine
  trip per D10) and a controllable non-vital load breaker (`loads.nonvital.connect`).
- **Flow-path animation**: subtle marching dashes on lines with nonzero flow; direction
  from sign. Keep understated (opacity ~0.35, slow), it is a reading aid not a toy.

### 6.3 Controller stations (M/A stations)

Four, one per loop (drum level, drum pressure, DA level) plus the governor station:

- Loop stations: AUTO/MAN pushbuttons with lamps (`loop.<id>.mode`), output meter
  (0–100% actuator command), and in MAN, RAISE/LOWER pushbuttons stepping the manual
  command (`<actuator>.manual_cmd`) at a fixed slew per held tick — a human turning a
  knob, not typing a float. Setpoint display; setpoint changes are out of scope this
  phase (fixed setpoints, as in the core).
- Governor station: RAISE/LOWER load reference (`governor.load_ref_mw`, ±0.25 MW per
  step, held-repeat), MW and frequency meters adjacent, droop placard "5% DROOP".
- Station for drum level additionally shows the 1E/3E element mode as a legend lamp
  (from fidelity config) — the D18 story made visible.

## 7. Annunciator

ISA-18.1-style sequence, implemented client-side as a pure state machine in
`lib/annunciator.svelte.ts`, driven by `event` messages and unit-tested with vitest
(§12.5):

- New alarm → window **fast-flashes** + horn sounds. `SILENCE` button stops the horn,
  flashing continues. `ACK` → steady lit (and sends `alarm.ack` for each flashing id —
  the core tracks acknowledged state). Condition clears while acked → slow-flash
  ("ringback" simplified: slow-flash until `RESET`), then off. `LAMP TEST` lights every
  window while held.
- **First-out**: the initiating window of a trip sequence carries a distinct pattern
  (fast flash with inverted colors) and a small corner tag, driven by the `first_out`
  flag on events — the phase-1 first-out record surfacing exactly where a 1970s panel
  put it.
- Window grid sized for all protection.yaml ids **plus ~30% engraved blank spares**
  (period-correct, and room to grow). Legend text comes from a `label` field to be
  added to protection.yaml entries (§11).
- Horn: WebAudio, two-tone square-ish buzz, mute toggle on the instructor station
  (demo rooms). All audio behind one user-gesture unlock (browser autoplay rules).

## 8. Right pane

### 8.1 Chart recorders

Two vertical strip-chart widgets styled as paper recorders (grid, pen colors, slow
scroll), each 3 pens, default assignments: recorder 1 — drum level, feed flow, steam
flow (the shrink/swell showcase); recorder 2 — frequency, MW, drum pressure. Pen
assignment selectable from any instrument (dropdown on the recorder margin). History
backfills via `chart_query` on load/reassignment; live appends from frames. Time span
selector 2/10/30 min mapped onto the historian's 20 Hz/1 Hz retention tiers.

### 8.2 Sequence-of-events log

Line-printer-styled scrolling log of `event` messages with sim timestamps: alarms
(with state transitions), trips with first-out marking, pump mode changes, SV
lift/reseat, operator/instructor actions with results (rejections printed verbatim —
"CP1 START REJECTED: ALREADY RUNNING"). Filter toggles: alarms / actions / all.
Export button → text file. This is the panel twin of the phase-1 timeline strip.

## 9. Instructor station

Collapsible drawer, visually distinct (modern flat styling — it is out-of-fiction):
scenario picker + LOAD, RUN/FREEZE, speed selector, RESET, casualty insertion buttons
generated from the injectable event types with small parameter forms (pump picker for
`trip_pump`/`inhibit_start`; instrument picker + stuck/bias value for `sensor_fault`;
MW delta for `set_load`; fraction for `set_air_ingress`), fidelity selectors (drum
model, 1E/3E — apply on next LOAD, since they construct the sim), audit readout
(mass/energy closure from frames), horn mute, EXPORT SESSION, and seed display.

## 10. Aesthetic direction

Embedded spec — follow it rather than inventing a look per widget:

- **Board**: two-tone gray-green benchboard (`#6b7f77` field, `#4d5c55` frame),
  subtle brushed texture at most; flat, matte, functional. No glossy skeuomorphism,
  no drop shadows beyond a hint of bezel relief.
- **Gauge faces**: ivory `#f2edd8`, black markings, red/amber setpoint arcs per §5.2;
  black bezels. Needles matte black with a red tail.
- **Labels**: engraved-lamacoid style — white text on black plates (or reversed for
  warnings), uppercase, a condensed grotesque font stack (e.g. "Oswald", fallback
  `Arial Narrow, sans-serif`), letter-spacing 0.05em. Every device gets a plate; that
  is half the period feel.
- **Annunciator windows**: translucent white when dark, amber backlight for alarms,
  red for trip-class windows; engraved two-line legends.
- **Indicating lamps**: red = stopped pump / closed valve, green = running / open,
  amber = tripped/abnormal — Alan's operator convention (flipped 2026-08-30 from
  the original red=running spec). Breakers read green = closed / black (dark
  lens) = open. Single-state event lamps (SV OPEN, MFT, TURB TRIP) stay
  red-when-lit: they are abnormal-event indications, not position pairs.
- **SOE log / advisor bezel**: the two CRT/printer surfaces may go phosphor green on
  near-black; they are the only "terminal" styling on the page.
- **Layout discipline**: align to a 8 px grid; group by system (condensate, feed,
  boiler, turbine-electric) with thin engraved separator lines and group title plates,
  mirroring the mimic's left-to-right flow.

## 11. Precursor: `hotwell` 0.2.0 (separate task, executed in the `hotwell` repo first)

This section is a self-contained mini-handoff for a session in the `hotwell` repo. The
panel repo pins the released result and never edits the core.

1. **Manual trip actions**: `trips.manual_mft` and `trips.manual_turbine` — operator
   pushbuttons behind covered guards on the panel (every real board has them; an
   operator who sees the casualty coming may trip deliberately). Semantics identical to
   the corresponding protective action, first-out records `MANUAL`. Unit tests + a
   protection-table note.
2. **Annunciator labels**: optional `label:` (two lines ≤ 12 chars each) per
   protection-table entry, defaulting to the id. Pure data addition.
3. **Package-data migration** (required by the repo split, and by any future PyPI
   release regardless of the panel): move `configs/baseline.yaml`,
   `data/protection.yaml`, and the canonical `scenarios/*.yaml` into `src/hotwell/`
   package data, exposed through `importlib.resources`-backed accessors (e.g.
   `hotwell.data.baseline_config()`, `hotwell.data.protection_table()`,
   `hotwell.data.builtin_scenarios()`), with every loader still accepting an explicit
   user-supplied path override. Add a test that installs/imports `hotwell` and runs a
   canonical scenario **from a temp working directory with no repo checkout present**.
4. Version 0.2.0, changelog entry, `HANDOFF.md` note. Nothing else changes; wants
   discovered during panel work are proposals in the panel's `HANDOFF.md`.

## 12. Testing and acceptance

1. **Protocol tests** (pytest, FastAPI test client + WS): hello contents, frame
   cadence vs sim ticks, action round-trip with accepted and rejected commands,
   instructor commands, chart_query passthrough, pause/speed semantics (N sim steps at
   5× ≡ 5N at 1× for identical action tick-stamps).
2. **Replay determinism** (the flagship): drive a scripted casualty + recovery through
   the live server API, export session, convert via `session_to_scenario.py`, replay
   headlessly → identical state-history hash.
3. **Manifest validation** as pytest (§6.1) including full-coverage check. Because it
   runs against the *installed* `hotwell`'s live contracts, this doubles as the
   cross-repo compatibility gate — a core release that moves a contract fails here
   first.
4. **Facegen golden files** for two representative faces (goldens intentionally track
   the installed core's protection table; regenerate deliberately on a core rev);
   **displayunits anchors** from §5.1 pinned.
5. **Client gate**: `svelte-check` (TypeScript + template diagnostics, runes mode)
   clean, and vitest unit tests covering the annunciator ISA state machine (including
   first-out and ringback paths), the needle smoothing store, and the `types.ts`
   protocol-version guard. Runs in the same gate as pytest and ruff.
6. **Playwright smoke** (dev-optional, one test, run against the built client served
   by `server.py`): page loads, hello received, a needle
   element's transform changes across frames, a grip click yields an `action_result`,
   annunciator window lights on an injected `trip_pump`. Skipped cleanly when
   playwright isn't installed.
7. **Human-playable checklist** (manual gate, recorded as checked boxes in
   `HANDOFF.md`): (a) load the unrecovered casualty scenario, do nothing, and observe
   the exact annunciator/SOE sequence from the phase-1 handoff table with correct
   first-out; (b) reload, recover by pistol-gripping CP-2 within the window — no trip,
   levels return; (c) practice recognizing the cascade with the horn on — silence, ack,
   reset flow all behave; (d) drum-level shrink/swell visibly leads flow changes on
   recorder 1 with the AB drum; (e) manual turbine trip drops the bus dead; (f) a
   rejected action prints its reason in the SOE log; (g) 30 minutes of continuous run
   with no wall-clock drift complaints logged and no browser jank at 20 Hz.

## 13. Milestones

- **P0 — server + replay spine.** Precondition: the `hotwell` 0.2.0 precursor (§11) is
  done and installed. `SimSession`, RT loop, protocol, action stamping, session
  log/export, `session_to_scenario.py`. Tests §12.1–.2 green headlessly (no UI yet).
  *Do not start UI until the replay test passes.*
- **P1 — the board lights up.** Vite + Svelte 5 scaffold with the dev proxy verified
  end-to-end (typed hello arriving in a component), board.svg template, manifest +
  validation, facegen, displayunits, gauges animating from live frames,
  lamps/indications. Checklist (g)
  achievable. First visual milestone — screenshot into `HANDOFF.md`.
- **P2 — operate it.** Grips, breakers, M/A + governor stations, manual-trip
  pushbuttons (consuming the 0.2.0 actions from §11), annunciator with full ISA
  sequence + first-out + horn, SOE log. Checklist (a)(b)(c)(e)(f).
- **P3 — diagnose it.** Chart recorders with historian backfill, instructor station
  complete (casualty insertion, fidelity selectors, audit, export). Checklist (d) and
  the full §12.7 pass. **Phase-2 finish line.**
- **P4 — optional polish, explicit go-ahead only.** Attract/demo mode (auto-load
  `cp1_trip_recovered`, letting the scripted recovery play the panel — booth mode for
  EAG), keyboard shortcuts, aesthetic pass, README GIF.

## 14. Working agreements

Same as phase 1 §13: ask-vs-decide with decisions logged in `HANDOFF.md`; no silent
scope growth; ruff clean on the Python side, `svelte-check` clean on the client, typed
public interfaces on both, files ≲ 300 lines; keep
`HANDOFF.md` current with the same section structure plus: the `hotwell` version built
against, screenshot(s) per milestone,
the checked §12.7 checklist, latency/frame-budget observations, and "Notes for the
agent phase" (anything learned about surfacing observations/actions that phase 3's
advisor tools should reuse).

## 15. Explicitly out of scope (phase 2)

The agent, LangGraph, any LLM call, and any content behind the advisor bezel. Auth,
multi-user roles, non-localhost deployment, HTTPS. SvelteKit, server-side rendering,
client routing. Mobile/touch layouts. Setpoint
adjustment on M/A stations. Station-service/blackout-recovery modeling (D10 stands).
Sound design beyond the horn and switch clicks. Randomized-parameter campaigns,
scoring, evaluation harness. Snapshot/restore (reset = reload). Binary or compressed
transport. New physics. Any edit to the `hotwell` repo beyond the §11 precursor task.
