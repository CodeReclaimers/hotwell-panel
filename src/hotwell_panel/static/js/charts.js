/**
 * @file Strip-chart recorders styled as paper recorders (§8.1).
 *
 * Three pens each, assignable to any instrument from a margin dropdown. On
 * load and on reassignment the trace backfills from the historian via
 * `chart_query`; after that, frames append live.
 *
 * Time runs left to right with "now" at the right edge. A paper recorder feeds
 * its chart vertically under fixed pens, but at 648x216 px the horizontal axis
 * gives ten times the time resolution, and reading a trend is the point.
 *
 * Span selector 2 / 10 / 30 min maps onto the historian's retention tiers: it
 * keeps 20 Hz for the trailing 10 minutes and 1 Hz beyond, so a 30-minute span
 * is genuinely coarser at its left end. That is the data, not a rendering
 * artefact.
 */

import { store } from './store.js';
import { el, plate } from './svgutil.js';

const SPANS = [2, 10, 30];              // minutes
const PEN_CLASSES = ['chart-pen-1', 'chart-pen-2', 'chart-pen-3'];
const MAX_POINTS = 900;

/** @type {Object[]} */
const recorders = [];
let connection = null;

/**
 * @param {Object} e manifest element, kind 'chart'
 * @param {import('./ws.js').Connection} conn
 */
export function createRecorder(e, conn) {
  connection = conn;
  const o = e.options || {};
  const margin = { l: 46, r: 10, t: 20, b: 16 };
  const plotX = e.x + margin.l;
  const plotY = e.y + margin.t;
  const plotW = e.w - margin.l - margin.r;
  const plotH = e.h - margin.t - margin.b;

  const g = el('g', { class: 'recorder', 'data-element': e.id });
  g.appendChild(el('rect', {
    x: e.x, y: e.y, width: e.w, height: e.h, rx: 2, class: 'chart-paper',
  }));
  g.appendChild(plate(e.x, e.y - 16, 120, 14, e.label || 'RECORDER'));

  // Chart grid: period recorders use a printed rule, not a screen grid.
  const grid = el('g', { class: 'chart-grid-group' });
  for (let i = 0; i <= 10; i += 1) {
    const gx = plotX + (plotW * i) / 10;
    grid.appendChild(el('line', {
      x1: gx, y1: plotY, x2: gx, y2: plotY + plotH,
      class: `chart-grid${i % 5 === 0 ? ' major' : ''}`,
    }));
  }
  for (let i = 0; i <= 4; i += 1) {
    const gy = plotY + (plotH * i) / 4;
    grid.appendChild(el('line', {
      x1: plotX, y1: gy, x2: plotX + plotW, y2: gy,
      class: `chart-grid${i % 4 === 0 ? ' major' : ''}`,
    }));
  }
  g.appendChild(grid);

  const rec = {
    el: e, plotX, plotY, plotW, plotH,
    span: (o.span_min || 10) * 60,
    pens: (o.pens || []).slice(0, 3).map((name, i) => ({
      name, cls: PEN_CLASSES[i], t: [], v: [],
      path: el('path', { class: `chart-pen ${PEN_CLASSES[i]}`, d: '' }),
      label: null, select: null,
    })),
    requests: new Map(),
  };

  for (const pen of rec.pens) g.appendChild(pen.path);

  // Pen legend + assignment dropdowns down the left margin.
  rec.pens.forEach((pen, i) => {
    const ly = plotY + 12 + i * 13;
    g.appendChild(el('line', {
      x1: e.x + 6, y1: ly - 3, x2: e.x + 18, y2: ly - 3,
      class: `chart-pen ${pen.cls}`,
    }));
    pen.label = el('text', { x: e.x + 21, y: ly, class: 'chart-pen-label' },
                   [pen.name]);
    pen.label.addEventListener('click', () => cyclePen(rec, i));
    g.appendChild(pen.label);
  });

  // Span selector along the bottom margin.
  SPANS.forEach((mins, i) => {
    const bx = e.x + e.w - 100 + i * 32;
    const b = el('g', { class: 'span-btn', 'data-span': String(mins) });
    b.appendChild(el('rect', { x: bx, y: e.y + e.h - 14, width: 28, height: 12,
                               rx: 2, class: 'span-face' }));
    b.appendChild(el('text', { x: bx + 14, y: e.y + e.h - 5,
                               class: 'span-text' }, [`${mins}M`]));
    b.addEventListener('click', () => { rec.span = mins * 60; backfill(rec); });
    g.appendChild(b);
  });

  rec.axis = el('g', { class: 'chart-axis' });
  g.appendChild(rec.axis);
  recorders.push(rec);
  return g;
}

/** Cycle a pen through the available instruments (§8.1 margin selector). */
function cyclePen(rec, index) {
  const names = Object.keys(store.units).sort();
  if (!names.length) return;
  const pen = rec.pens[index];
  const next = names[(names.indexOf(pen.name) + 1) % names.length];
  pen.name = next;
  pen.label.textContent = next;
  pen.t = [];
  pen.v = [];
  backfill(rec);
}

/** Request history for every pen on a recorder. */
export function backfill(rec) {
  if (!connection || !store.frame) return;
  const now = store.frame.t;
  const t0 = Math.max(0, now - rec.span);
  const signals = rec.pens
    .map((p) => (store.units[p.name] || {}).source || p.name);
  const id = `${rec.el.id}:${Math.round(now * 20)}`;
  rec.requests.set(id, signals);
  connection.chartQuery(id, signals, t0, now + 1, MAX_POINTS);
}

/** Backfill every recorder (called once a first frame has arrived). */
export function backfillAll() {
  for (const rec of recorders) backfill(rec);
}

/** @param {Object} msg a `chart_data` message */
export function onChartData(msg) {
  for (const rec of recorders) {
    const signals = rec.requests.get(msg.request_id);
    if (!signals) continue;
    rec.requests.delete(msg.request_id);
    if (msg.unknown && msg.unknown.length) {
      console.warn('historian has no signal', msg.unknown);
    }
    rec.pens.forEach((pen, i) => {
      const series = msg.series[signals[i]];
      if (!series) return;
      pen.t = msg.t.slice();
      pen.v = series.slice();
    });
    draw(rec);
  }
}

/** Append the current frame to every pen and redraw. */
export function onFrame() {
  const f = store.frame;
  if (!f) return;
  for (const rec of recorders) {
    for (const pen of rec.pens) {
      const si = store.siValue(pen.name);
      if (si === undefined) continue;
      if (pen.t.length && pen.t[pen.t.length - 1] >= f.t) continue;
      pen.t.push(f.t);
      pen.v.push(si);
      // Trim to the visible span plus a little slack.
      const cutoff = f.t - rec.span * 1.05;
      let drop = 0;
      while (drop < pen.t.length && pen.t[drop] < cutoff) drop += 1;
      if (drop > 0) { pen.t.splice(0, drop); pen.v.splice(0, drop); }
    }
    draw(rec);
  }
}

function draw(rec) {
  const f = store.frame;
  if (!f) return;
  const t1 = f.t;
  const t0 = t1 - rec.span;
  for (const pen of rec.pens) {
    const d = store.units[pen.name];
    if (!d || !pen.t.length) { pen.path.setAttribute('d', ''); continue; }
    const lo = d.lo;
    const hi = d.hi;
    let out = '';
    let pending = true;
    for (let i = 0; i < pen.t.length; i += 1) {
      const tv = pen.t[i];
      const raw = pen.v[i];
      if (tv < t0 || raw === null || raw === undefined || Number.isNaN(raw)) {
        pending = true;
        continue;
      }
      const disp = raw * d.scale + d.offset;
      const x = rec.plotX + ((tv - t0) / (t1 - t0)) * rec.plotW;
      const frac = Math.min(Math.max((disp - lo) / (hi - lo), 0), 1);
      const y = rec.plotY + rec.plotH * (1 - frac);
      out += `${pending ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)} `;
      pending = false;
    }
    pen.path.setAttribute('d', out);
  }
  drawAxis(rec, t0, t1);
}

function drawAxis(rec, t0, t1) {
  while (rec.axis.firstChild) rec.axis.removeChild(rec.axis.firstChild);
  const fmt = (t) => {
    const m = Math.floor(Math.max(0, t) / 60);
    return `${m}:${String(Math.floor(Math.max(0, t) - m * 60)).padStart(2, '0')}`;
  };
  for (let i = 0; i <= 2; i += 1) {
    const t = t0 + ((t1 - t0) * i) / 2;
    rec.axis.appendChild(el('text', {
      x: rec.plotX + (rec.plotW * i) / 2,
      y: rec.plotY + rec.plotH + 11,
      class: 'chart-axis-text',
    }, [fmt(t)]));
  }
  // Each pen's scale endpoints, in its own display units.
  rec.pens.forEach((pen, i) => {
    const d = store.units[pen.name];
    if (!d) return;
    rec.axis.appendChild(el('text', {
      x: rec.el.x + rec.el.w - 6, y: rec.plotY + 10 + i * 10,
      class: `chart-scale ${pen.cls}`,
    }, [`${d.lo}–${d.hi} ${d.unit}`]));
  });
}

export function reset() { recorders.length = 0; }
export function count() { return recorders.length; }
