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
import { soe } from './lib/events.svelte';
import { store } from './lib/frame.svelte';
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
    store.setHello(msg);
    annunciator.install(msg.annunciator);
    soe.reset();
    seeded = false;
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
  chart_data: () => {},     // M2: chart recorders
  session_exported: () => {},
  error: (m) => console.error('protocol error:', m.reason),
  info: () => {},
  status: (s) => {
    store.connStatus = s;
    store.connected = s === 'connected';
  },
});

// Browsers require a user gesture before audio; arm it on the first click.
window.addEventListener('pointerdown', () => audio.unlock(), { once: true });

conn.connect();
mount(App, { target: document.getElementById('app')! });

// Exposed for the Playwright suite and for poking at a live board. Widget
// registries (gauges, charts) join in M2.
declare global {
  interface Window {
    panel: Record<string, unknown>;
  }
}
window.panel = { store, conn, annunciator, audio, soe };
