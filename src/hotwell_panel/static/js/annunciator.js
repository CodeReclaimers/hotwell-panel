/**
 * @file The annunciator array: ISA-18.1 sequence, driven entirely by `event`
 * messages (§7).
 *
 * P1 builds and lights the windows from alarm state. The full acknowledge /
 * ringback / lamp-test sequence and the horn arrive in P2; the state machine
 * below is already shaped for them, so P2 adds behaviour rather than a rewrite.
 *
 * Windows come from the protection table (via `hello`), in table order, with
 * the remaining cells left as engraved blank spares — period-correct, and room
 * to grow (§7).
 */

import { store } from './store.js';
import { clear, el } from './svgutil.js';

/** Window states, in the order a 1970s sequence walks them. */
export const DARK = 'dark';
export const FAST = 'fast';        // new alarm: fast flash + horn
export const STEADY = 'steady';    // acknowledged, condition still present
export const SLOW = 'slow';        // condition cleared while acked (ringback)

/** @type {Map<string, {group: SVGElement, win: SVGElement, spec: Object,
 *                      state: string, firstOut: boolean}>} */
const windows = new Map();
let lampTest = false;

/**
 * Build the array from the manifest grid and the protection-table window list.
 * @param {Object} manifest
 * @param {Object[]} annunciator window specs from `hello`
 */
export function render(manifest, annunciator) {
  const layer = document.getElementById('layer-annunciator');
  clear(layer);
  windows.clear();
  const g = manifest.annunciator;
  if (!g) return;

  const cells = g.cols * g.rows;
  for (let i = 0; i < cells; i += 1) {
    const spec = annunciator[i];
    const col = i % g.cols;
    const row = Math.floor(i / g.cols);
    const x = g.x + col * g.cell_w;
    const y = g.y + row * g.cell_h;
    const wg = el('g', {
      class: 'ann-window-group',
      'data-alarm': spec ? spec.id : '',
    });
    const win = el('rect', {
      x: x + 2, y: y + 2, width: g.cell_w - 4, height: g.cell_h - 4, rx: 1,
      class: `ann-window${spec ? '' : ' spare'}${spec && spec.is_trip ? ' trip' : ''}`,
    });
    wg.appendChild(win);
    if (spec) {
      // Two-line engraved legend, exactly as the protection table declares it.
      const lines = spec.legend;
      const y0 = y + g.cell_h / 2 + (lines.length > 1 ? -3 : 3);
      lines.forEach((line, n) => {
        wg.appendChild(el('text', {
          x: x + g.cell_w / 2, y: y0 + n * 9, class: 'ann-legend',
        }, [line]));
      });
      wg.appendChild(el('text', {
        x: x + g.cell_w - 5, y: y + 9, class: 'ann-fo-tag',
      }, ['']));
      windows.set(spec.id, { group: wg, win, spec, state: DARK,
                             firstOut: false });
    }
    layer.appendChild(wg);
  }
  paint();
}

/**
 * Apply an alarm transition from an `event` message.
 * @param {string} id
 * @param {string} alarmState one of active | acknowledged | clear
 */
export function onAlarm(id, alarmState) {
  const w = windows.get(id);
  if (!w) return;                       // not a windowed condition
  if (alarmState === 'active') {
    // Re-activating a window that was ringing back starts the sequence over.
    w.state = FAST;
  } else if (alarmState === 'acknowledged') {
    w.state = STEADY;
  } else if (alarmState === 'clear') {
    // Cleared while acknowledged: slow-flash until RESET (§7 ringback).
    w.state = w.state === DARK ? DARK : SLOW;
  }
  paint();
}

/** Mark the initiating window of a trip sequence (§7 first-out). */
export function setFirstOut(id) {
  const w = windows.get(id);
  if (!w) return false;                 // e.g. CP1_TRIP:overload has no window
  w.firstOut = true;
  paint();
  return true;
}

/** RESET: drop every ringing-back window to dark. */
export function reset() {
  for (const w of windows.values()) {
    if (w.state === SLOW) w.state = DARK;
    w.firstOut = false;
  }
  paint();
}

/** LAMP TEST lights every window while held (§7). */
export function setLampTest(on) {
  lampTest = Boolean(on);
  paint();
}

/** Ids currently flashing — what an ACK button should acknowledge. */
export function flashing() {
  return [...windows.entries()]
    .filter(([, w]) => w.state === FAST)
    .map(([id]) => id);
}

/** Rebuild classes from state. Flash timing is CSS, on the wall clock. */
function paint() {
  for (const w of windows.values()) {
    const cls = ['ann-window-group'];
    if (lampTest || w.state !== DARK) cls.push('lit');
    if (w.state === FAST) cls.push('flash-fast');
    if (w.state === SLOW) cls.push('flash-slow');
    if (w.firstOut) cls.push('first-out');
    w.group.setAttribute('class', cls.join(' '));
    const lit = lampTest || w.state !== DARK;
    w.win.setAttribute('class',
      `ann-window${lit ? ' lit' : ''}${w.spec.is_trip ? ' trip' : ''}`);
    const tag = w.group.querySelector('.ann-fo-tag');
    if (tag) tag.textContent = w.firstOut ? '1ST' : '';
  }
}

/**
 * Adopt frame alarm state wholesale. Events are the primary driver, but a
 * client that connects mid-casualty has missed them, so the first frame
 * seeds the array.
 */
export function seedFromFrame() {
  if (!store.frame) return;
  for (const [id, w] of windows) {
    const st = store.frame.alarms[id];
    w.state = st === 'active' ? FAST
      : st === 'acknowledged' ? STEADY
      : (w.state === SLOW ? SLOW : DARK);
  }
  paint();
}

/** @returns {number} window count (tests/diagnostics). */
export function count() { return windows.size; }
