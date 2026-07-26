/**
 * @file Entry point: wire the socket to the board and run the animation loop.
 *
 * Two clocks, deliberately separate. Sim state arrives on `frame` messages at
 * the simulator's pace; needle smoothing and (later) annunciator flashers run
 * on requestAnimationFrame against the wall clock, so they keep animating while
 * the sim is paused (§3.2).
 */

import * as annunciator from './annunciator.js';
import * as board from './board.js';
import * as gauges from './gauges.js';
import { store } from './store.js';
import { Connection } from './ws.js';

const ui = {
  conn: document.getElementById('conn'),
  scenario: document.getElementById('scenario-name'),
  clock: document.getElementById('sim-clock'),
  state: document.getElementById('sim-state'),
  fidelity: document.getElementById('fidelity'),
  fps: document.getElementById('fps'),
};

let frameCount = 0;
let seeded = false;
let lastFpsAt = performance.now();

/** T + MMM:SS.s, the way a plant clock reads. */
function formatClock(t) {
  const m = Math.floor(t / 60);
  const s = t - m * 60;
  return `T + ${String(m).padStart(3, '0')}:${s.toFixed(1).padStart(4, '0')}`;
}

function onHello(msg) {
  const first = store.hello === null;
  store.setHello(msg);
  gauges.reset();
  seeded = false;
  board.renderElements(msg.manifest || {});
  board.renderRightPane(msg.manifest || {});
  annunciator.render(msg.manifest || {}, msg.annunciator || []);
  if (first) gauges.installFaces(msg.gauge_faces || {});
  ui.scenario.textContent = msg.scenario ? msg.scenario.name : 'NO SCENARIO';
  const f = msg.fidelity || {};
  ui.fidelity.textContent =
    `${(f.drum_model || '?').toUpperCase()} / ${f.three_element ? '3E' : '1E'}`;
  console.info('hello: hotwell', msg.hotwell_version,
               '| protocol', msg.protocol_version,
               '| obs digest', msg.obs_spec_digest);
}

function onFrame(msg) {
  store.setFrame(msg);
  frameCount += 1;
  ui.clock.textContent = formatClock(msg.t);
  const st = msg.status || {};
  ui.state.textContent =
    `${(st.state || '').toUpperCase()}${st.speed > 1 ? ` ${st.speed}X` : ''}`;
  board.updateIndications();
  if (!seeded) { annunciator.seedFromFrame(); seeded = true; }
}

function onEvent(msg) {
  if (msg.kind === 'alarm') annunciator.onAlarm(msg.id, msg.state);
  // A first-out label is often NOT a protection-table id (CP1_TRIP:overload,
  // MANUAL_MFT), so setFirstOut can legitimately find no window. The dedicated
  // first-out display and the SOE log arrive in P2.
  if (msg.kind === 'first_out' && msg.first_out) annunciator.setFirstOut(msg.id);
  console.log(`[${msg.t.toFixed(2)}] ${msg.text || msg.kind}`);
}

function onActionResult(msg) {
  if (!msg.accepted) console.warn('action rejected:', msg.command, msg.reason);
}

const conn = new Connection({
  hello: onHello,
  frame: onFrame,
  event: onEvent,
  action_result: onActionResult,
  chart_data: () => {},
  session_exported: (m) => console.info('session exported:', m.path),
  error: (m) => console.error('protocol error:', m.reason),
  info: () => {},
  status: (s) => {
    store.connected = s === 'connected';
    ui.conn.className = s;
    ui.conn.textContent = s.toUpperCase();
  },
});

let lastAnim = performance.now();
function tick(now) {
  const dt = Math.min(now - lastAnim, 250);   // clamp after a tab-switch stall
  lastAnim = now;
  gauges.animate(dt);
  if (now - lastFpsAt >= 1000) {
    ui.fps.textContent = `${frameCount} FPS`;
    frameCount = 0;
    lastFpsAt = now;
  }
  requestAnimationFrame(tick);
}

board.loadMimic().then(() => {
  conn.connect();
  requestAnimationFrame(tick);
});

// Exposed for the Playwright smoke test and for poking at a live board.
window.panel = { store, conn, gauges, board, annunciator };
