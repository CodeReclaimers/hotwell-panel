# HANDOFF — hotwell-panel phase 2

## Status summary

**P0–P3 code complete, client migrated to Svelte 5 (2026-08-29); the §12.7
human-playable gate is NOT signed off** — it requires a person at a browser and
cannot be self-certified. See "§12.7 checklist" below for exactly what is
automated and what is still open.

Built against **`hotwell` 0.3.0** (station-service pump loads, `../hotwell`
commit `9464eb2`; previously 0.2.0 `c88af5d`). The panel consumes it as an
installed dependency and never edits it — 0.3.0 was executed as its own task
in the core repo at Alan's direction (2026-08-29) after panel play showed
pump starts not moving the MW meter. Panel-side effect: the two-state
casualty-table pins were re-measured (every event within 0.3 s, sequence and
first-out unchanged); display anchors and the §5.1 table are untouched by
design. FP-2 start now reads ~+0.3 MW on the GEN OUTPUT meter; a condensate
pump start is +0.02 MW — real but below the meter's 0.1 MW resolution (the
ammeter is the visible cue). 0.2.0 session logs no longer replay to their
recorded hashes (physics change).

| Milestone | State | Evidence |
|---|---|---|
| §11 precursor — hotwell 0.2.0 | complete | 55 passed in the core repo; wheel-install check |
| P0 — server + replay spine | complete | replay hash bit-identical, incl. same-tick collision |
| P1 — the board lights up | complete | 17 gauges, 19 windows, live needles |
| P2 — operate it | complete | full ISA sequence, grips, stations, manual trips |
| P3 — diagnose it | complete | recorders with historian backfill, instructor station |
| Svelte migration (updated §1) | complete | same browser suite green against the Svelte client; §12.5 client gate clean |
| P4 — polish | **not started** (explicit go-ahead only, §13) | — |

Suite: **95 passed**, ruff clean, `svelte-check` 0/0, vitest 29 passed. The 16
Chromium tests run against the **built** client served by `server.py` and skip
cleanly when playwright or `client/dist` is absent.

## How to run

```bash
uv venv .venv
uv pip install -e ../hotwell
uv pip install -e '.[dev]'
cd client && npm install && npm run build && cd ..
make check          # pytest + ruff + svelte-check + vitest (the §12 gate)
.venv/bin/python -m hotwell_panel --scenario builtin:cp1_trip_unrecovered
```

Dev mode is two processes (`make dev`): uvicorn on :8000 plus `vite dev` on
:5173 with HMR, proxying `/ws`. Production is the single Python process above;
it refuses to start without `client/dist`.

## Svelte migration (2026-08-29)

PLAN-panel.md §1 was revised to lock **Svelte 5 + TypeScript + Vite (runes
mode, plain SPA)** in place of the original vanilla-JS decision the P0–P3 build
followed. The client was ported wholesale (`client/`), the server now mounts
`client/dist`, and `static/` is deleted. Contracts, protocol, replay, and all
server code except the static-serving block are untouched. Details, decisions,
and per-phase verification: `.plan-checkpoint.md` and `progress-20260829.md`.

- **One behavioral addition** (required by §4): the client now *refuses to run*
  on a `protocol_version` mismatch (full-screen refusal, no reconnect). The
  vanilla client only logged it.
- **One test-contract change** (required by §5.2): faces are `{@html}`-injected
  inside `Gauge`, so the smoke test now asserts 23 faces in `hello.gauge_faces`
  and 17 placed faces in the DOM, replacing the old `#face-defs > g == 23`.
- Browser tests were otherwise kept verbatim; `window.panel` and the DOM
  contract (`data-element`/`data-alarm`/`data-instrument`, class names,
  instructor ids, swappable `conn.handlers`) are preserved deliberately.
- `client/dist` is **not** wheel-packaged (run-from-checkout decision).
- Node dev deps pinned: svelte 5.57.0, vite-plugin-svelte 6.2.4, vite 7.3.6,
  typescript 5.9.3, svelte-check 4.7.6, vitest 4.1.11 (svelte-check 4.x
  excludes TS 7; plugin 7.x needs vite 8 — avoided the brand-new majors).

## Screenshots

| | |
|---|---|
| P1, steady at 60 MW | `docs/img/p1_board.png` |
| P2, board with controls | `docs/img/p2_board_steady.png` |
| P2, mid-casualty | `docs/img/p2_casualty.png` |
| P3, recorders + instructor drawer | `docs/img/p3_board.png` |
| Svelte client, mid-casualty | `docs/img/m2_svelte_board.png` |
| Current board (lamp sense flipped, 2026-08-30) | `docs/img/board_current.png` |

**Lamp convention (flipped 2026-08-30, plan §10 updated):** red = stopped
pump / closed valve, green = running / open, amber = tripped — Alan's
operator experience. Breakers: green = closed, black (dark lens) = open.
All pre-flip screenshots above show the original red=running sense. Event
lamps (SV OPEN, MFT, TURB TRIP) remain red-when-lit: abnormal-event
indications, not position pairs.

The mid-casualty shot is the useful one: eight annunciator windows lit with
trip-class in red, the FIRST OUT plate reading `CP1_TRIP:OVERLOAD`, the SOE log
printing the sequence, and the drum-level gauge at **+14.8 in** — D18's
inverted level response visible on the glass before the plant shrinks.

## §12.7 checklist — the manual gate

(Previously "§12.6": the 2026-08-29 plan revision inserted the client gate as
§12 item 5, shifting the Playwright smoke test to §12.6 and this checklist to
§12.7. Older references in progress logs and commit messages use the old
numbers.)

**This is not signed off.** Items marked *automated* have a test asserting the
observable content; that is not the same as a person having played the panel.
Items marked *open* need Alan at a browser. Per the migration agreement, this
gate is to be performed on the Svelte client now that the port is complete.

- [x] **(a) automated** — unrecovered casualty, no operator action, exact
  annunciator/SOE sequence with correct first-out.
  `tests/test_casualty_sequence.py`. **Read the caveat in §"Plan conflicts"
  below: this reproduces the phase-1 handoff table under `two_state`+1E, and
  characterises a genuinely different cascade under the panel's AB+3E default.**
- [x] **(b) automated, split** — grip CP-2 to START runs the standby pump with
  the correct lamp colour (`test_operate_browser.py`); starting it in time
  actually saves the plant (`test_casualty_sequence.py`, both fidelities).
- [ ] **(c) OPEN** — *practise recognising the cascade with the horn on.* The
  state machine is automated end to end (fast flash + horn → SILENCE leaves it
  flashing → ACK takes it steady and the **core** records `acknowledged` →
  ringback slow-flash → RESET to dark; LAMP TEST lights all 19). **Hearing it,
  and whether the horn is actually useful rather than maddening, is untested.**
  Repro: run the casualty, click anywhere once to arm audio, and let it build.
- [ ] **(d) OPEN, data half automated** — shrink/swell leads flow changes on
  recorder 1. The phenomenon is in the data the recorder plots: **+23.0 mm swell
  peaking at +8.1 s** after the load step while steam flow goes 76.9 → 84.9 kg/s,
  then away to −54 mm (`test_recorder_one_data_contains_the_shrink_swell`).
  Whether it is *legible on the paper at 648×216 px* is a visual judgement.
  Repro: load `builtin:load_step`, run at 5×, watch recorder 1 around t = 300 s.
- [x] **(e) automated** — manual turbine trip drops the bus dead: cover must be
  lifted first (asserted that lifting alone does not trip), then the breaker
  opens and every pump drops.
- [x] **(f) automated** — a rejected action prints its reason verbatim:
  `ACTION cp1.start REJECTED: cp1 is running, not stopped`.
- [ ] **(g) OPEN** — 30 minutes of continuous running, no wall-clock drift
  complaints, no browser jank at 20 Hz. Not attempted: it needs 30 minutes of a
  human watching. The instrumentation is in place — `status.missed_deadlines`
  counts real-time-loop overruns and shows in the instructor drawer; the status
  bar shows received FPS. Longest observed run in testing is ~10 min of sim time
  at 5× with `missed_deadlines: 0` and a steady 20–21 FPS.

## Plan conflicts and gaps found

Recorded rather than resolved unilaterally (§14 ask-vs-decide).

1. **§1 vs §12.7(a) — default fidelity.** §1 locks the panel default to
   `astrom_bell` + three-element. §12.7(a) asks for "the exact annunciator/SOE
   sequence from the phase-1 handoff table" — but that table was measured on
   `two_state` + single-element, phase 1's default. Both cannot describe one run.
   Delivered both, and the default is left as §1 specifies:

   (Re-measured 2026-08-29 under hotwell 0.3.0 station-service loads — every
   entry moved ≤ 0.7 s, ordering unchanged. Source: `pytest
   tests/test_casualty_sequence.py -s`.)

   | | two_state + 1E | AB + 3E (panel default) |
   |---|---|---|
   | DRUM_P_HI | +19.60 s | — (AB storage damps it) |
   | DA_LO | +23.15 | +21.95 |
   | HOTWELL_HI | +57.25 | +57.20 |
   | FP1_SUCTION trip | +92.80 | +77.90 |
   | SAFETY_VALVE | +98.00 | +99.05 |
   | DRUM_LVL_**HI** | — | +89.10 |
   | DRUM_LVL_**HIHI** → turbine trip | — | +100.50 |
   | DRUM_LVL_LO | +112.50 | +202.45 |
   | DRUM_LVL_LOLO → MFT, plant dead | +127.30 | +222.90 |

   The two_state column reproduces the handoff table to within its own rounding.
   The AB column is not a bug: losing feed reduces in-drum condensation, so level
   **rises** first (D18) and the plant trips on high-high level long before
   low-low. Arguably the better training scenario, but it is a different one.
   **Which is the §12.7(a) acceptance target is Alan's call.**

2. **§5.1's 611 klb/hr steam anchor is unreachable on the panel.** `steam_flow`
   quantizes to 0.1 kg/s in the observation contract, so the display is handed
   76.9 and reads **610**; 611 needs the unquantized 76.923, which no panel can
   see. The feed row is unaffected (87.121 → 87.1 → 691). Both pinned in
   `test_displayunits.py`. No constant was tuned to make 611 appear.

3. **§5.1 has no row for NPSH margin.** `fp1/fp2_npsh_margin` are instruments and
   must be placed. Chose **feet** (period-correct for a US plant), face −15 to
   +50 ft.

4. **`Observation.indications` carries no loop modes.** §6.3 wants AUTO/MAN
   lamps. Rather than inferring mode from action echoes — which goes wrong after
   a reset — the server reads `Simulator.control` and ships a `loops` block on
   each frame. Panel-layer enrichment; no core change.

5. **§9's `set_load` is a MW delta; the core's event takes absolute watts.**
   Converted server-side in `SimSession._resolve_set_load`. The session log
   stores the **resolved absolute** value, so replay does not depend on what the
   block happened to be at the time.

## Decisions taken

- **The session log IS the replay scenario.** Built entirely from the log rather
  than from the original scenario plus a diff. `Simulator.step()` applies
  scenario events before submitted actions, so a tick carrying both can reorder
  under a naive merge; because `load_scenario` sorts stably, replaying the log
  in log order reproduces live order exactly, including within a tick.
- **Event times are stamped a half tick early.** Sim time is an accumulated
  float whose drift reaches **−1.089e−9 s at 36000 ticks** (t = 1800 s, the
  canonical `max_t`) — already past the core's 1e-9 event tolerance. Exact
  stamps would fire a late-session action one step late and silently break the
  hash. Half a tick gives 0.025 s of margin either way.
- **Alarm edges are synthesised by diffing observations.** The core emits a
  `FiredAction` only for non-`alarm` actions and reports a clear as a
  *disappearance*, so most of the cascade would otherwise be invisible.
- **A FIRST OUT plate, separate from the annunciator.** The canonical casualty's
  initiator, `CP1_TRIP:overload`, is a free-form `record_external_trip` label
  with no protection-table id and therefore no window.
- **Conflicting same-key actions defer instead of collapsing.** ACK-ALL sends
  one `alarm.ack` per flashing window; last-wins would acknowledge one.
- **Layout is validated, not eyeballed.** The manifest validator checks bounds,
  the 8 px grid, overlaps (with gauge bezel and label plate included in the
  footprint), annunciator capacity and full instrument coverage. It caught every
  collision in the first two layout passes.
- **Chart time runs horizontally.** A paper recorder feeds vertically, but at
  648×216 px the horizontal axis gives ~10× the time resolution.
- **Instructor station is HTML, not SVG.** It is out-of-fiction (§9); making it
  look like benchboard would misrepresent what the player is touching.

## Notes for the agent phase

- `frame.loops` already exposes per-loop mode, setpoint, output and manual
  command. An advisor recommending "put drum level in manual and open the FRV"
  can check whether that is even currently valid before saying it.
- Rejection reasons come back verbatim from the core and are already rendered as
  operator-facing text in `events.soe_line`. An advisor's proposed action can be
  dry-run against `hotwell.actions.check_schema` for the static half.
- The **first-out record is the causal summary** the advisor should lead with,
  and it is not the annunciator list: labels like `CP1_TRIP:overload` and
  `MANUAL_MFT` never appear as windows.
- `events.EventSynthesizer` is the reusable "what changed" layer. An agent wants
  the same diff the SOE log gets, not raw frames.
- The session log reduces any episode to a scenario file, so an agent run and a
  human run are directly comparable artefacts — that was the point of §3.4.
- **The fidelity switch changes the casualty qualitatively** (see conflict 1). An
  advisor trained or prompted on the two_state cascade will give wrong advice on
  the AB default. `frame.loops.three_element` and `status.fidelity` say which.

## Latency / frame budget

- 20 Hz wall loop, drift-corrected on absolute deadlines. `missed_deadlines`
  stayed at 0 through all browser tests including 5× speed.
- Frames measured 2.5–3.5 KB of JSON; the browser reports a steady 20–21 FPS.
- Steady-state sim cost is well inside budget: the core does 1 h of sim in
  ~21 s wall, i.e. ~170× real time, so 5× speed uses ~3% of the loop.

## Known rough edges

- `energy_residual_frac` in the instructor readout swings to several percent
  during transients. That is expected — the audit's energy closure is a
  steady-state diagnostic (core `audit.py`) — but the readout does not say so.
- The 30-minute chart span mixes the historian's 20 Hz and 1 Hz tiers, so the
  left end of a 30 min trace is visibly coarser. Honest, but unlabelled.

## Proposals for a future `hotwell` release

Not done — §1 forbids editing the core beyond the §11 precursor.

1. **`Simulator.inject_event(ScenarioEvent)`.** The panel currently splices
   injected events into `sim.scenario.events` at `sim._event_idx`, reading a
   private attribute, so that event semantics are never reimplemented in the
   panel. A public method would remove the only private-API dependency.
2. **Loop state in `Observation`.** `indications` has no loop modes; see gap 4.
3. **Alarm transitions as first-class events.** Every consumer will otherwise
   re-implement the observation diff in `events.py`.
4. **A `CP_SUCTION` protection entry.** Already noted as a 0.1.0 rough edge; a
   hotwell-draining casualty has nothing to trip on.
