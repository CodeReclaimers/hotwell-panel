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
import { store } from './lib/frame.svelte';
import { Connection } from './lib/ws';
import { protocolMismatch } from './types';
import './panel.css';

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
    console.info('hello: hotwell', msg.hotwell_version,
                 '| protocol', msg.protocol_version,
                 '| obs digest', msg.obs_spec_digest);
  },
  frame: (msg) => store.setFrame(msg),
  event: () => {},          // M1/M2: SOE log, annunciator machine, horn
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

conn.connect();
mount(App, { target: document.getElementById('app')! });

// Exposed for the Playwright suite and for poking at a live board. Widget
// registries (gauges, annunciator, charts, audio) join in M1/M2.
declare global {
  interface Window {
    panel: Record<string, unknown>;
  }
}
window.panel = { store, conn };
