/**
 * @file Instructor station: a collapsible bottom drawer (§9).
 *
 * Deliberately plain HTML with modern flat styling, not SVG benchboard — it is
 * out-of-fiction, and looking like part of the 1970s board would be a lie
 * about what the player is touching (§9, §10).
 *
 * The casualty-insertion forms are generated from the injectable event types
 * the protocol advertises, and their instrument/pump pickers are generated
 * from the observation spec, so a core release that adds an instrument shows
 * up here without an edit.
 */

import * as audio from './audio.js';
import { store } from './store.js';

const PUMPS = ['cp1', 'cp2', 'fp1', 'fp2'];
const SPEEDS = [1, 2, 5];

let conn = null;
let root = null;

function h(tag, attrs = {}, children = []) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') n.className = v;
    else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, String(v));
  }
  for (const c of children) {
    n.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
  }
  return n;
}

function field(label, control) {
  return h('label', { class: 'ins-field' }, [h('span', {}, [label]), control]);
}

function select(id, options, value) {
  const s = h('select', { id });
  for (const [v, text] of options) {
    const o = h('option', { value: v }, [text]);
    if (v === value) o.selected = true;
    s.appendChild(o);
  }
  return s;
}

function num(id, value, step = '0.1') {
  return h('input', { id, type: 'number', value: String(value), step });
}

/** Build the drawer. Called once, then refreshed from frames. */
export function render(connection) {
  conn = connection;
  root = document.getElementById('instructor');
  root.innerHTML = '';

  const toggle = h('button', {
    class: 'ins-toggle',
    onclick: () => root.classList.toggle('open'),
  }, ['INSTRUCTOR STATION']);
  root.appendChild(toggle);

  const body = h('div', { class: 'ins-body' });

  // --- scenario + time control -------------------------------------------
  const scenarios = (store.hello.scenarios || []).map((s) => [
    s.ref, `${s.name} (${s.source}${s.self_playing ? ', self-playing' : ''})`,
  ]);
  const scenSel = select('ins-scenario', scenarios,
                         store.hello.scenario ? store.hello.status.scenario_ref : '');
  const drumSel = select('ins-drum', [
    ['astrom_bell', 'Åström–Bell (default)'], ['two_state', 'two-state'],
  ], (store.hello.fidelity || {}).drum_model);
  const elemSel = select('ins-element', [
    ['3', 'three-element (default)'], ['1', 'single-element (degraded)'],
  ], (store.hello.fidelity || {}).three_element ? '3' : '1');

  body.appendChild(h('div', { class: 'ins-group' }, [
    h('h3', {}, ['SCENARIO']),
    field('scenario', scenSel),
    field('drum model', drumSel),
    field('level control', elemSel),
    h('div', { class: 'ins-note' },
      ['fidelity applies on the next LOAD — it constructs the simulator']),
    h('div', { class: 'ins-row' }, [
      h('button', { id: 'ins-load', onclick: () => conn.instructor('load_scenario', {
        ref: scenSel.value,
        fidelity: { drum_model: drumSel.value,
                    three_element: elemSel.value === '3' },
      }) }, ['LOAD']),
      h('button', { id: 'ins-reset',
                    onclick: () => conn.instructor('reset') }, ['RESET']),
    ]),
  ]));

  const speedSel = select('ins-speed', SPEEDS.map((s) => [String(s), `${s}x`]),
                          '1');
  body.appendChild(h('div', { class: 'ins-group' }, [
    h('h3', {}, ['TIME']),
    h('div', { class: 'ins-row' }, [
      h('button', { id: 'ins-run', class: 'primary',
                    onclick: () => conn.instructor('run') }, ['RUN']),
      h('button', { id: 'ins-freeze',
                    onclick: () => conn.instructor('pause') }, ['FREEZE']),
    ]),
    field('speed', speedSel),
    h('div', { class: 'ins-note' },
      ['speed multiplies steps per wall tick; dt is always 0.05 s']),
  ]));
  speedSel.addEventListener('change',
    () => conn.instructor('speed', { speed: Number(speedSel.value) }));

  body.appendChild(casualtyPanel());
  body.appendChild(diagnosticsPanel());
  root.appendChild(body);
}

/** Casualty insertion, one form per injectable event type (§9). */
function casualtyPanel() {
  const pumpOpts = PUMPS.map((p) => [p, p.toUpperCase()]);
  const instrOpts = (store.hello.obs_spec || [])
    .map((s) => [s.name, s.name]);

  const tripPump = select('ins-trip-pump', pumpOpts, 'cp1');
  const inhibitPump = select('ins-inhibit-pump', pumpOpts, 'cp2');
  const faultInstr = select('ins-fault-instr', instrOpts, 'drum_level');
  const faultKind = select('ins-fault-kind',
                           [['bias', 'bias'], ['stuck', 'stuck']], 'bias');
  const faultBias = num('ins-fault-bias', -0.1, '0.01');
  const loadTarget = select('ins-load-target',
                            [['nonvital', 'NON-VITAL'], ['vital', 'VITAL']],
                            'nonvital');
  const loadDelta = num('ins-load-delta', 6.0, '0.5');
  const airFrac = num('ins-air', 0.02, '0.01');

  return h('div', { class: 'ins-group wide' }, [
    h('h3', {}, ['CASUALTY INSERTION']),
    h('div', { class: 'ins-row' }, [
      tripPump,
      h('button', { id: 'ins-trip-btn', class: 'danger', onclick: () => conn.instructor(
        'inject_event', { event: 'trip_pump',
                          params: { target: tripPump.value,
                                    reason: 'instructor' } }) }, ['TRIP PUMP']),
    ]),
    h('div', { class: 'ins-row' }, [
      inhibitPump,
      h('button', { id: 'ins-inhibit-btn', onclick: () => conn.instructor(
        'inject_event', { event: 'inhibit_start',
                          params: { target: inhibitPump.value } }) },
        ['INHIBIT START']),
    ]),
    h('div', { class: 'ins-row' }, [
      faultInstr, faultKind, faultBias,
      h('button', { id: 'ins-fault-btn', onclick: () => conn.instructor(
        'inject_event', { event: 'sensor_fault',
                          params: { target: faultInstr.value,
                                    kind: faultKind.value,
                                    bias: Number(faultBias.value) } }) },
        ['SENSOR FAULT']),
    ]),
    h('div', { class: 'ins-row' }, [
      loadTarget, loadDelta,
      // §9 asks for a MW delta; hotwell's set_load takes absolute watts. The
      // server converts (SimSession._resolve_set_load) so the units live in
      // one tested place.
      h('button', { id: 'ins-load-btn', onclick: () => conn.instructor(
        'inject_event', { event: 'set_load',
                          params: { target: loadTarget.value,
                                    delta_mw: Number(loadDelta.value) } }) },
        ['LOAD STEP MW']),
    ]),
    h('div', { class: 'ins-row' }, [
      airFrac,
      h('button', { id: 'ins-air-btn', onclick: () => conn.instructor(
        'inject_event', { event: 'set_air_ingress',
                          params: { value: Number(airFrac.value) } }) },
        ['AIR INGRESS']),
    ]),
  ]);
}

function diagnosticsPanel() {
  const mute = h('button', {
    id: 'ins-mute',
    onclick: () => {
      audio.setMuted(!audio.isMuted());
      mute.textContent = audio.isMuted() ? 'HORN MUTED' : 'MUTE HORN';
      mute.classList.toggle('active', audio.isMuted());
    },
  }, ['MUTE HORN']);
  return h('div', { class: 'ins-group' }, [
    h('h3', {}, ['DIAGNOSTICS']),
    h('div', { class: 'ins-readout', id: 'ins-audit' }, ['—']),
    h('div', { class: 'ins-readout', id: 'ins-seed' }, ['—']),
    h('div', { class: 'ins-row' }, [
      mute,
      h('button', { id: 'ins-export-btn',
                    onclick: () => conn.instructor('export_session') },
        ['EXPORT SESSION']),
    ]),
    h('div', { class: 'ins-note', id: 'ins-export' }, ['']),
  ]);
}

/** Refresh the live readouts from a frame. */
export function onFrame() {
  const f = store.frame;
  if (!f || !root) return;
  const a = f.audit || {};
  const audit = document.getElementById('ins-audit');
  if (audit) {
    audit.textContent =
      `mass drift ${(a.mass_drift_frac * 100).toFixed(6)} % | `
      + `energy residual ${(a.energy_residual_frac * 100).toFixed(4)} % | `
      + `relief ${a.relief_kg.toFixed(1)} kg`;
  }
  const seed = document.getElementById('ins-seed');
  if (seed) {
    const st = f.status || {};
    const loads = (f.loops || {}).loads_mw || {};
    seed.textContent =
      `seed ${st.seed} | tick ${st.tick} | ${st.state}`
      + ` | missed deadlines ${st.missed_deadlines}`
      + ` | loads V ${(loads.vital ?? 0).toFixed(1)} / NV `
      + `${(loads.nonvital ?? 0).toFixed(1)} MW`;
  }
}

/** @param {Object} msg a `session_exported` message */
export function onExported(msg) {
  const n = document.getElementById('ins-export');
  if (n) n.textContent = `wrote ${msg.path} — hash ${msg.hash.slice(0, 16)}…`;
}
