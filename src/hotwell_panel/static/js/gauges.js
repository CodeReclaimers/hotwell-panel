/**
 * @file Analog gauges: instantiate the server-generated faces, animate needles.
 *
 * The face — ticks, numerals, alarm/trip marks — is generated in Python from
 * the observation spec and the protection table and arrives in `hello`. This
 * module only places it and moves the needle, so setpoints on the glass can
 * never drift from the protection table (§5.2).
 *
 * Needle motion uses first-order smoothing with tau = 150 ms: analog feel
 * without lying about the data (§6.2). The underlying 20 Hz values are what the
 * simulator sensed, including the +/-0.05 MW droop dither the phase-1 handoff
 * notes — that shows through, which is the point.
 */

import { el, parseFragment, plate } from './svgutil.js';
import { store } from './store.js';

const TAU_MS = 150;
const SWEEP = 270;
const START = 135;
const FACE_R = 50;      // face units, matching facegen.py

/** @type {Map<string, {node: SVGElement, needle: SVGElement, readout: SVGElement,
 *                      instrument: string, shown: number}>} */
const gauges = new Map();

/**
 * Put every generated face into <defs> once.
 * @param {Object<string,string>} faces instrument -> SVG <g> markup
 */
export function installFaces(faces) {
  const defs = document.getElementById('face-defs');
  for (const markup of Object.values(faces)) {
    for (const node of parseFragment(markup)) defs.appendChild(node);
  }
}

/** Needle angle in degrees for a display fraction, matching facegen. */
function angleFor(instrument, si) {
  const d = store.units[instrument];
  if (!d) return START;
  const v = si * d.scale + d.offset;
  const frac = d.hi === d.lo ? 0 : (v - d.lo) / (d.hi - d.lo);
  return START + SWEEP * Math.min(Math.max(frac, 0), 1);
}

/**
 * Build one gauge from a manifest element.
 * @param {Object} e manifest element with kind 'gauge'
 * @returns {SVGElement}
 */
export function createGauge(e) {
  const size = e.size || 88;
  const scale = size / (FACE_R * 2);
  const cx = e.x + size / 2;
  const cy = e.y + size / 2;
  const d = store.units[e.instrument] || {};

  const g = el('g', { class: 'gauge', 'data-instrument': e.instrument,
                      'data-element': e.id });
  g.appendChild(el('circle', { cx, cy, r: size / 2 + 3, class: 'gauge-bezel' }));

  const inner = el('g', {
    transform: `translate(${cx} ${cy}) scale(${scale.toFixed(4)})`,
  });
  inner.appendChild(el('use', { href: `#face-${e.instrument}` }));

  // Needle: a slim wedge with a red tail, rotated about the hub.
  const needle = el('g', { class: 'needle-group',
                           transform: `rotate(${START})` });
  needle.appendChild(el('path', {
    class: 'needle', d: `M -2.2 0 L 0 -${FACE_R - 8} L 2.2 0 Z`,
  }));
  needle.appendChild(el('path', {
    class: 'needle-tail', d: 'M -2.2 0 L 0 13 L 2.2 0 Z',
  }));
  needle.appendChild(el('circle', { cx: 0, cy: 0, r: 3.2, class: 'needle-hub' }));
  inner.appendChild(needle);

  // Small digital readout under the hub: a period board had a scale you read,
  // but an exact value makes the sim inspectable without squinting.
  const readout = el('text', { x: 0, y: 26, class: 'gauge-digital' }, ['—']);
  inner.appendChild(readout);
  g.appendChild(inner);

  const label = e.label || (d.label ?? e.instrument);
  g.appendChild(plate(cx - size / 2, e.y + size + 4, size, 13, label));

  gauges.set(e.id, { node: g, needle, readout, instrument: e.instrument,
                     shown: NaN });
  return g;
}

/**
 * Advance every needle toward its latest sensed value.
 * @param {number} dtMs wall milliseconds since the previous animation frame
 */
export function animate(dtMs) {
  const alpha = 1 - Math.exp(-dtMs / TAU_MS);
  for (const gg of gauges.values()) {
    const si = store.siValue(gg.instrument);
    if (si === undefined) continue;
    const target = angleFor(gg.instrument, si);
    // First frame snaps: a needle sweeping up from zero on connect would
    // misrepresent the plant as having just started.
    gg.shown = Number.isNaN(gg.shown) ? target
                                      : gg.shown + (target - gg.shown) * alpha;
    gg.needle.setAttribute('transform', `rotate(${gg.shown.toFixed(2)})`);
    const text = store.formatted(gg.instrument);
    if (gg.readout.textContent !== text) gg.readout.textContent = text;
  }
}

/** Drop all gauge state (used when a new scenario re-sends hello). */
export function reset() { gauges.clear(); }

/** @returns {number} how many gauges are installed (tests/diagnostics). */
export function count() { return gauges.size; }
