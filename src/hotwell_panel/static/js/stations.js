/**
 * @file Manual/auto controller stations and the governor station (§6.3).
 *
 * Loop stations: AUTO / MAN pushbuttons with lamps, a vertical output meter
 * reading the actuator command 0-100%, and — in MAN only — RAISE / LOWER
 * pushbuttons that step the manual command by a fixed slew per held tick. A
 * human turning a knob, not typing a float.
 *
 * Governor station: RAISE / LOWER the load reference in 0.25 MW steps with
 * held-repeat, MW and frequency digital meters adjacent, and a 5% DROOP
 * placard.
 *
 * Mode lamps come from `frame.loops`, read off the live controllers, so the
 * lamp cannot disagree with the plant after a reset or a scenario action.
 */

import { store } from './store.js';
import { el, plate } from './svgutil.js';

const REPEAT_MS = 120;    // held-repeat interval, one step per tick-ish

/** @type {Object[]} */
const stations = [];

function pushButton(x, y, w, h, text, cls, onPress) {
  const g = el('g', { class: `push-button ${cls}`.trim() });
  const face = el('rect', { x, y, width: w, height: h, rx: 2,
                            class: 'push-face' });
  g.appendChild(face);
  g.appendChild(el('text', { x: x + w / 2, y: y + h / 2 + 3,
                             class: 'push-text' }, [text]));
  // Held-repeat: pressing and holding RAISE walks the command, as a real
  // pushbutton station does.
  let timer = null;
  const start = (ev) => {
    ev.preventDefault();
    onPress();
    timer = setInterval(onPress, REPEAT_MS);
    g.classList.add('pressed');
  };
  const stop = () => {
    if (timer) clearInterval(timer);
    timer = null;
    g.classList.remove('pressed');
  };
  g.addEventListener('mousedown', start);
  g.addEventListener('mouseup', stop);
  g.addEventListener('mouseleave', stop);
  return { node: g, face };
}

/**
 * @param {Object} e manifest element, kind 'station'
 * @param {import('./ws.js').Connection} conn
 */
export function createStation(e, conn) {
  const o = e.options;
  const g = el('g', { class: 'station', 'data-element': e.id,
                      'data-loop': o.loop });
  g.appendChild(el('rect', {
    x: e.x, y: e.y, width: e.w, height: e.h, rx: 2, class: 'station-box',
  }));
  g.appendChild(plate(e.x, e.y, e.w, 14, e.label || o.loop));

  const rec = { el: e, loop: o.loop, nodes: {} };

  // --- process variable + setpoint (loop stations only) --------------------
  // The governor has no single PV: it shows MW and frequency meters instead
  // (§6.3), so it would otherwise display two permanently blank fields.
  if (o.loop !== 'governor') {
    rec.pvName = e.instrument;
    rec.nodes.pv = el('text', { x: e.x + 10, y: e.y + 34, class: 'station-pv' },
                      ['—']);
    g.appendChild(rec.nodes.pv);
    rec.nodes.sp = el('text', { x: e.x + 10, y: e.y + 48, class: 'station-sp' },
                      ['SP —']);
    g.appendChild(rec.nodes.sp);
  }

  // --- vertical output meter, 0-100% ---------------------------------------
  const mx = e.x + e.w - 34;
  const my = e.y + 26;
  const mh = 96;
  g.appendChild(el('rect', { x: mx, y: my, width: 16, height: mh,
                             class: 'meter-track' }));
  rec.nodes.meter = el('rect', { x: mx, y: my + mh, width: 16, height: 0,
                                 class: 'meter-fill' });
  g.appendChild(rec.nodes.meter);
  rec.meter = { x: mx, y: my, h: mh };
  g.appendChild(el('text', { x: mx + 8, y: my + mh + 12,
                             class: 'meter-label' }, ['OUT']));
  rec.nodes.out = el('text', { x: mx + 8, y: my - 4, class: 'meter-label' },
                     ['—']);
  g.appendChild(rec.nodes.out);

  if (o.loop === 'governor') {
    buildGovernor(g, e, rec, conn);
  } else {
    buildLoop(g, e, rec, conn);
  }
  stations.push(rec);
  return g;
}

function buildLoop(g, e, rec, conn) {
  const o = e.options;
  const bx = e.x + 10;
  const auto = pushButton(bx, e.y + 58, 54, 20, 'AUTO', 'mode',
                          () => conn.action({ [o.mode_action]: 'auto' }));
  const man = pushButton(bx + 60, e.y + 58, 54, 20, 'MAN', 'mode',
                         () => conn.action({ [o.mode_action]: 'manual' }));
  g.appendChild(auto.node);
  g.appendChild(man.node);
  rec.autoBtn = auto.face;
  rec.manBtn = man.face;

  const slew = o.slew || 0.02;
  // RAISE/LOWER step the manual command; the core rejects them in AUTO and the
  // rejection prints verbatim in the SOE log, which is the honest feedback.
  const step = (sign) => {
    const st = (store.frame && store.frame.loops[o.loop]) || {};
    const base = st.manual_cmd !== undefined ? st.manual_cmd : 0;
    const lo = st.lo !== undefined ? st.lo : 0;
    const hi = st.hi !== undefined ? st.hi : 1;
    const next = Math.min(Math.max(base + sign * slew, lo), hi);
    conn.action({ [o.manual_action]: Number(next.toFixed(4)) });
  };
  g.appendChild(pushButton(bx, e.y + 84, 54, 20, 'RAISE', 'slew',
                           () => step(+1)).node);
  g.appendChild(pushButton(bx + 60, e.y + 84, 54, 20, 'LOWER', 'slew',
                           () => step(-1)).node);

  if (o.element_mode_lamp) {
    // §6.3: the 1E/3E element mode as a legend lamp — the D18 story made
    // visible on the board.
    rec.nodes.element = el('text', {
      x: e.x + 10, y: e.y + e.h - 10, class: 'station-legend',
    }, ['—']);
    g.appendChild(rec.nodes.element);
  }
}

function buildGovernor(g, e, rec, conn) {
  const o = e.options;
  const bx = e.x + 10;
  const stepMw = o.step_mw || 0.25;
  const step = (sign) => {
    const st = (store.frame && store.frame.loops.governor) || {};
    const base = st.load_ref_mw !== undefined ? st.load_ref_mw : 0;
    const next = Math.min(Math.max(base + sign * stepMw, 0), 75);
    conn.action({ [o.raise_action]: Number(next.toFixed(3)) });
  };
  g.appendChild(pushButton(bx, e.y + 58, 54, 20, 'RAISE', 'slew',
                           () => step(+1)).node);
  g.appendChild(pushButton(bx + 60, e.y + 58, 54, 20, 'LOWER', 'slew',
                           () => step(-1)).node);

  rec.nodes.mw = el('text', { x: bx, y: e.y + 100, class: 'station-meter' },
                    ['— MW']);
  rec.nodes.hz = el('text', { x: bx, y: e.y + 120, class: 'station-meter' },
                    ['— HZ']);
  rec.nodes.ref = el('text', { x: bx, y: e.y + 136, class: 'station-sp' },
                     ['REF —']);
  g.appendChild(rec.nodes.mw);
  g.appendChild(rec.nodes.hz);
  g.appendChild(rec.nodes.ref);
  g.appendChild(el('text', {
    x: e.x + e.w - 10, y: e.y + e.h - 10, class: 'station-legend droop',
  }, ['5% DROOP']));
}

/** Apply the latest frame to every station. */
export function update() {
  const f = store.frame;
  if (!f) return;
  for (const rec of stations) {
    const st = f.loops[rec.loop] || {};
    const o = rec.el.options;

    // output meter: the actuator command as a percentage
    const outInstrument = o.output_instrument;
    const pct = outInstrument !== undefined
      ? (store.displayValue(outInstrument) ?? 0) : 0;
    const h = Math.max(0, Math.min(100, pct)) / 100 * rec.meter.h;
    rec.nodes.meter.setAttribute('y', String(rec.meter.y + rec.meter.h - h));
    rec.nodes.meter.setAttribute('height', String(h));
    rec.nodes.out.textContent = `${pct.toFixed(0)}%`;

    if (rec.loop === 'governor') {
      rec.nodes.mw.textContent = `${store.formatted('mw_out')} MW`;
      rec.nodes.hz.textContent = `${store.formatted('frequency')} HZ`;
      rec.nodes.ref.textContent =
        `REF ${(st.load_ref_mw ?? 0).toFixed(2)} MW`;
      continue;
    }

    const d = store.units[rec.pvName] || {};
    rec.nodes.pv.textContent =
      `${store.formatted(rec.pvName)} ${d.unit || ''}`;
    if (st.sp !== undefined && d.scale !== undefined) {
      const sp = st.sp * d.scale + d.offset;
      rec.nodes.sp.textContent = `SP ${sp.toFixed(d.decimals)} ${d.unit}`;
    }
    const manual = st.mode === 'manual';
    if (rec.autoBtn) {
      rec.autoBtn.setAttribute('class',
        `push-face${manual ? '' : ' lit'}`);
      rec.manBtn.setAttribute('class', `push-face${manual ? ' lit' : ''}`);
    }
    if (rec.nodes.element) {
      rec.nodes.element.textContent =
        f.loops.three_element ? '3-ELEMENT' : '1-ELEMENT';
      rec.nodes.element.setAttribute('class',
        `station-legend${f.loops.three_element ? '' : ' degraded'}`);
    }
  }
}

export function reset() { stations.length = 0; }
