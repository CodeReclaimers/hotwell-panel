/**
 * @file Entry point: wire the socket to the board and run the animation loop.
 *
 * Two clocks, deliberately separate. Sim state arrives on `frame` messages at
 * the simulator's pace; needle smoothing and the annunciator flashers run on
 * requestAnimationFrame and CSS against the wall clock, so they keep animating
 * while the sim is paused (§3.2).
 */

import * as annunciator from './annunciator.js';
import * as audio from './audio.js';
import * as board from './board.js';
import * as gauges from './gauges.js';
import * as soe from './soe.js';
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

/**
 * The annunciator control buttons (§7). SILENCE stops the horn but leaves the
 * windows flashing; ACK sends one `alarm.ack` per flashing window and takes
 * them steady; RESET drops ringing-back windows dark; LAMP TEST is held.
 */
const annHandlers = {
  silence: () => { audio.silence(); audio.click(); },
  ack: () => {
    const ids = annunciator.flashing();
    // Only currently-ACTIVE ids: the core rejects an ack for anything else,
    // and the SOE log would fill with spurious rejections.
    for (const id of ids) conn.action({ 'alarm.ack': id });
    audio.silence();
    audio.click();
  },
  reset: () => { annunciator.reset(); audio.click(); },
  lamp_test: () => {},
  lamp_test_on: () => annunciator.setLampTest(true),
  lamp_test_off: () => annunciator.setLampTest(false),
};

function onHello(msg) {
  const first = store.hello === null;
  store.setHello(msg);
  gauges.reset();
  seeded = false;
  if (first) gauges.installFaces(msg.gauge_faces || {});
  board.renderElements(msg.manifest || {}, conn, annHandlers);
  board.renderRightPane(msg.manifest || {});
  soe.render(msg.manifest || {});
  soe.reset();
  annunciator.render(msg.manifest || {}, msg.annunciator || []);
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
  soe.push(msg);
  if (msg.kind === 'alarm') {
    annunciator.onAlarm(msg.id, msg.state);
    // A new alarm sounds the horn (§7). SILENCE stops it; the window keeps
    // flashing until acknowledged.
    if (msg.state === 'active') audio.start();
  }
  // A first-out label is often NOT a protection-table id (CP1_TRIP:overload,
  // MANUAL_MFT), so it may light no window — the FIRST OUT plate in the SOE
  // pane is the display that always shows it.
  if (msg.kind === 'first_out' && msg.first_out) annunciator.setFirstOut(msg.id);
  if (msg.is_trip) audio.start();
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

// Browsers require a user gesture before audio; arm it on the first click.
window.addEventListener('pointerdown', () => audio.unlock(), { once: true });

board.loadMimic().then(() => {
  conn.connect();
  requestAnimationFrame(tick);
});

// Exposed for the Playwright smoke test and for poking at a live board.
window.panel = { store, conn, gauges, board, annunciator, soe, audio };
