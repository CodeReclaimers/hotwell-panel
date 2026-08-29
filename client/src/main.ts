/**
 * Entry point: the composition root. Builds the Connection, wires its
 * handlers to the stores, mounts the app, and exposes `window.panel` for the
 * Playwright suite and for poking at a live board.
 *
 * Two clocks, deliberately separate (§3.2): sim state arrives on `frame`
 * messages at the simulator's pace; needle smoothing and annunciator flashers
 * run on requestAnimationFrame / CSS against the wall clock, so they keep
 * animating while the sim is paused.
 */

import { mount } from 'svelte';
import App from './App.svelte';
import { annunciator } from './lib/annunciator.svelte';
import * as audio from './lib/audio';
import { dispatchChartData } from './lib/chartdata';
import { soe } from './lib/events.svelte';
import { store } from './lib/frame.svelte';
import { charts, gauges } from './lib/registry';
import { Connection } from './lib/ws';
import { protocolMismatch } from './types';
import './panel.css';

// Events are the primary annunciator driver; a client that connects
// mid-casualty has missed them, so the first frame after each hello seeds
// the array wholesale (§7).
let seeded = false;

const conn = new Connection({
  hello: (msg) => {
    // §4: refuse to run on a protocol_version mismatch. Fatal, no reconnect —
    // a version-skewed pairing must not half-work.
    const refusal = protocolMismatch(msg.protocol_version);
    if (refusal) {
      store.fatal = refusal;
      conn.stop();
      console.error(refusal);
      return;
    }
    // Install machine state BEFORE publishing the hello: the board remounts
    // on `store.hello`, and its first render reads the machine.
    annunciator.install(msg.annunciator);
    soe.reset();
    seeded = false;
    store.setHello(msg);
    console.info('hello: hotwell', msg.hotwell_version,
                 '| protocol', msg.protocol_version,
                 '| obs digest', msg.obs_spec_digest);
  },
  frame: (msg) => {
    store.setFrame(msg);
    if (!seeded) {
      annunciator.seedFromFrame(msg.alarms);
      seeded = true;
    }
  },
  event: (msg) => {
    soe.push(msg);
    if (msg.kind === 'alarm') {
      annunciator.onAlarm(msg.id, msg.state);
      // A new alarm sounds the horn (§7). SILENCE stops it; the window keeps
      // flashing until acknowledged.
      if (msg.state === 'active') audio.start();
    }
    // A first-out label is often NOT a protection-table id (CP1_TRIP:overload,
    // MANUAL_MFT), so it may light no window — the FIRST OUT plate in the SOE
    // pane (fed by soe.push) is the display that always shows it.
    if (msg.kind === 'first_out' && msg.first_out) annunciator.setFirstOut(msg.id);
    if (msg.is_trip) audio.start();
  },
  action_result: (msg) => {
    if (!msg.accepted) console.warn('action rejected:', msg.command, msg.reason);
  },
  chart_data: (m) => dispatchChartData(m),
  session_exported: (m) => { store.sessionExported = m; },
  error: (m) => console.error('protocol error:', m.reason),
  info: () => {},
  status: (s) => {
    store.connStatus = s;
    store.connected = s === 'connected';
  },
});

/**
 * The annunciator control buttons (§7). SILENCE stops the horn but leaves the
 * windows flashing; ACK sends one `alarm.ack` per flashing window and takes
 * them steady; RESET drops ringing-back windows dark; LAMP TEST is held.
 */
const annHandlers = {
  silence: () => {
    audio.silence();
    audio.click();
  },
  ack: () => {
    // Only currently-ACTIVE ids: the core rejects an ack for anything else,
    // and the SOE log would fill with spurious rejections.
    for (const id of annunciator.flashing()) conn.action({ 'alarm.ack': id });
    audio.silence();
    audio.click();
  },
  reset: () => {
    annunciator.reset();
    audio.click();
  },
  lamp_test: () => {},
  lamp_test_on: () => annunciator.setLampTest(true),
  lamp_test_off: () => annunciator.setLampTest(false),
};

// Browsers require a user gesture before audio; arm it on the first click.
window.addEventListener('pointerdown', () => audio.unlock(), { once: true });

conn.connect();
mount(App, {
  target: document.getElementById('app')!,
  props: { conn, handlers: annHandlers },
});

// Exposed for the Playwright suite and for poking at a live board.
declare global {
  interface Window {
    panel: Record<string, unknown>;
  }
}
window.panel = { store, conn, annunciator, audio, soe, gauges, charts };
