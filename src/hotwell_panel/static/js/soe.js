/**
 * @file Sequence-of-events log (§8.2) and the FIRST OUT plate.
 *
 * Line-printer styling on phosphor green — one of only two "terminal" surfaces
 * on the page (§10). Every line is a server-rendered `event.text`, so the
 * client is not formatting domain text.
 *
 * The FIRST OUT plate exists because the initiating event of the canonical
 * casualty is `CP1_TRIP:overload`, a free-form `record_external_trip` label
 * with no protection-table id and therefore no annunciator window. Without a
 * dedicated display the panel would show the cascade but not what started it —
 * exactly the thing first-out is for.
 */

import { store } from './store.js';
import { clear, el } from './svgutil.js';

const MAX_LINES = 400;
const VISIBLE = 15;
const LINE_H = 11;

/** @type {{t: number, text: string, kind: string, trip: boolean}[]} */
const lines = [];
let filter = 'all';           // all | alarms | actions
let region = null;
let textLayer = null;
let firstOutPlate = null;
let firstOutText = null;

/** Build the log surface and the FIRST OUT plate. */
export function render(manifest) {
  const layer = document.getElementById('layer-right');
  region = (manifest.regions || {}).soe;
  if (!region) return;

  const g = el('g', { class: 'soe' });
  g.appendChild(el('rect', {
    x: region.x, y: region.y, width: region.w, height: region.h, rx: 3,
    class: 'crt-bezel',
  }));
  g.appendChild(el('text', {
    x: region.x + 10, y: region.y + 15, class: 'crt-text dim',
  }, ['SEQUENCE OF EVENTS']));

  // Filter toggles and export, in the header strip.
  const controls = [['ALL', 'all'], ['ALARMS', 'alarms'], ['ACTIONS', 'actions']];
  controls.forEach(([label, key], i) => {
    const bx = region.x + region.w - 250 + i * 60;
    const b = el('g', { class: 'soe-filter', 'data-filter': key });
    b.appendChild(el('rect', { x: bx, y: region.y + 5, width: 54, height: 14,
                               rx: 2, class: 'soe-filter-face' }));
    b.appendChild(el('text', { x: bx + 27, y: region.y + 15,
                               class: 'soe-filter-text' }, [label]));
    b.addEventListener('click', () => { filter = key; paint(); });
    g.appendChild(b);
  });
  const ex = region.x + region.w - 66;
  const exp = el('g', { class: 'soe-filter', 'data-filter': 'export' });
  exp.appendChild(el('rect', { x: ex, y: region.y + 5, width: 56, height: 14,
                               rx: 2, class: 'soe-filter-face' }));
  exp.appendChild(el('text', { x: ex + 28, y: region.y + 15,
                               class: 'soe-filter-text' }, ['EXPORT']));
  exp.addEventListener('click', exportText);
  g.appendChild(exp);

  textLayer = el('g', { class: 'soe-lines' });
  g.appendChild(textLayer);

  // FIRST OUT plate, immediately above the log.
  firstOutPlate = el('g', { class: 'first-out-plate' });
  firstOutPlate.appendChild(el('rect', {
    x: region.x, y: region.y - 26, width: region.w, height: 22, rx: 2,
    class: 'fo-plate',
  }));
  firstOutPlate.appendChild(el('text', {
    x: region.x + 10, y: region.y - 11, class: 'fo-label',
  }, ['FIRST OUT']));
  firstOutText = el('text', {
    x: region.x + 90, y: region.y - 11, class: 'fo-value',
  }, ['— NONE —']);
  firstOutPlate.appendChild(firstOutText);
  g.appendChild(firstOutPlate);

  layer.appendChild(g);
  paint();
}

/** @param {Object} ev an `event` message */
export function push(ev) {
  lines.push({ t: ev.t, text: ev.text || `${ev.kind} ${ev.id}`,
               kind: ev.kind, trip: Boolean(ev.is_trip) });
  if (lines.length > MAX_LINES) lines.shift();
  if (ev.kind === 'first_out' && ev.first_out) setFirstOut(ev);
  paint();
}

function setFirstOut(ev) {
  if (!firstOutText) return;
  firstOutText.textContent = `${fmtT(ev.t)}  ${ev.id}`;
  firstOutPlate.setAttribute('class', 'first-out-plate active');
}

/** Clear the plate and the log (new scenario / reset). */
export function reset() {
  lines.length = 0;
  if (firstOutText) {
    firstOutText.textContent = '— NONE —';
    firstOutPlate.setAttribute('class', 'first-out-plate');
  }
  paint();
}

function fmtT(t) {
  const m = Math.floor(t / 60);
  return `${String(m).padStart(3, '0')}:${(t - m * 60).toFixed(1).padStart(4, '0')}`;
}

function visible() {
  if (filter === 'alarms') {
    return lines.filter((l) => l.kind === 'alarm' || l.kind === 'first_out'
                               || l.kind === 'plant_dead');
  }
  if (filter === 'actions') return lines.filter((l) => l.kind === 'action');
  return lines;
}

function paint() {
  if (!textLayer || !region) return;
  clear(textLayer);
  const rows = visible().slice(-VISIBLE);
  rows.forEach((l, i) => {
    textLayer.appendChild(el('text', {
      x: region.x + 10,
      y: region.y + 30 + i * LINE_H,
      class: `crt-text${l.trip ? ' trip' : ''}`,
    }, [`${fmtT(l.t)}  ${l.text}`]));
  });
  for (const b of document.querySelectorAll('.soe-filter')) {
    b.classList.toggle('active', b.getAttribute('data-filter') === filter);
  }
}

/** Export the whole log (not just the visible window) as a text file. */
function exportText() {
  const scenario = store.hello && store.hello.scenario
    ? store.hello.scenario.name : 'session';
  const body = lines.map((l) => `${fmtT(l.t)}  ${l.text}`).join('\n');
  const blob = new Blob([`SEQUENCE OF EVENTS — ${scenario}\n\n${body}\n`],
                        { type: 'text/plain' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `${scenario}_soe.txt`;
  a.click();
  URL.revokeObjectURL(a.href);
}

/** @returns {number} lines held (tests/diagnostics). */
export function count() { return lines.length; }
