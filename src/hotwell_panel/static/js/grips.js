/**
 * @file Pistol-grip pump switches and breaker handles (§6.2).
 *
 * Three-position, spring-return-to-centre: START / NORM / STOP. Hold the grip
 * over to one side and release; the action fires **on release**, as a real
 * spring-return switch does, and the grip snaps back to NORM. Mouse
 * (click-and-hold left/right of the pivot) or keyboard (focus, hold Left or
 * Right arrow) — §6.2 asks for both.
 *
 * Lamps above each grip read from `indications`, which phase 1 guarantees
 * honest: red = running, green = stopped, amber = tripped. That is the power
 * plant convention, not the traffic-light one (§10).
 */

import { store } from './store.js';
import { el, plate } from './svgutil.js';

const START = 'start';
const NORM = 'norm';
const STOP = 'stop';
const THROW_DEG = 38;

/** @type {{el: Object, lamp: SVGElement, handle: SVGElement, pos: string}[]} */
const grips = [];
/** @type {{el: Object, lamp: SVGElement, label: SVGElement}[]} */
const breakers = [];

/**
 * @param {Object} e manifest element, kind 'grip'
 * @param {import('./ws.js').Connection} conn
 */
export function createGrip(e, conn) {
  // Vertical budget is 80 px: lamp, lever, engraved legend, plate. Each band
  // is placed explicitly rather than by offsets from the box, because they
  // collided when the grip height changed.
  const cx = e.x + e.w / 2;
  const lampY = e.y + 9;
  const pivotY = e.y + 52;

  const g = el('g', { class: 'grip', 'data-element': e.id,
                      'data-pump': e.options.pump });
  g.appendChild(plate(e.x, e.y + e.h - 14, e.w, 14, e.label || ''));

  const lamp = el('circle', { cx, cy: lampY, r: 7, class: 'lamp-lens' });
  g.appendChild(lamp);

  // Engraved STOP / START legend, either side of the pivot boss.
  g.appendChild(el('text', { x: e.x + 6, y: pivotY + 14,
                             class: 'grip-legend' }, ['STOP']));
  g.appendChild(el('text', { x: e.x + e.w - 6, y: pivotY + 14,
                             class: 'grip-legend end' }, ['START']));

  const handle = el('g', { class: 'grip-handle',
                           transform: `rotate(0 ${cx} ${pivotY})` });
  handle.appendChild(el('circle', { cx, cy: pivotY, r: 8, class: 'grip-boss' }));
  // The grip itself: a stubby pistol shape pointing up from the boss.
  handle.appendChild(el('path', {
    class: 'grip-lever',
    d: `M ${cx - 4} ${pivotY} L ${cx - 5} ${pivotY - 16} `
       + `Q ${cx} ${pivotY - 22} ${cx + 5} ${pivotY - 16} `
       + `L ${cx + 4} ${pivotY} Z`,
  }));
  g.appendChild(handle);

  const rec = { el: e, lamp, handle, pos: NORM };
  grips.push(rec);

  const move = (pos) => {
    rec.pos = pos;
    const deg = pos === START ? THROW_DEG : pos === STOP ? -THROW_DEG : 0;
    handle.setAttribute('transform', `rotate(${deg} ${cx} ${pivotY})`);
  };
  const release = () => {
    if (rec.pos === START) conn.action({ [e.options.start_action]: true });
    else if (rec.pos === STOP) conn.action({ [e.options.stop_action]: true });
    move(NORM);
  };

  // A transparent hit area split left/right of the pivot.
  const hit = el('rect', {
    x: e.x, y: e.y + 26, width: e.w, height: 40, class: 'grip-hit',
  });
  hit.addEventListener('mousedown', (ev) => {
    const box = hit.getBoundingClientRect();
    move(ev.clientX < box.left + box.width / 2 ? STOP : START);
  });
  hit.addEventListener('mouseup', release);
  hit.addEventListener('mouseleave', () => { if (rec.pos !== NORM) release(); });
  g.appendChild(hit);

  // §6.2 also asks for keyboard: focus a grip and hold Left (STOP) or Right
  // (START). Same spring-return semantics — the action fires on key release.
  hit.setAttribute('tabindex', '0');
  hit.setAttribute('role', 'button');
  hit.setAttribute('aria-label', `${e.label} pump control switch`);
  hit.addEventListener('keydown', (ev) => {
    if (ev.repeat) return;
    if (ev.key === 'ArrowLeft') { move(STOP); ev.preventDefault(); }
    else if (ev.key === 'ArrowRight') { move(START); ev.preventDefault(); }
  });
  hit.addEventListener('keyup', (ev) => {
    if (ev.key === 'ArrowLeft' || ev.key === 'ArrowRight') {
      release();
      ev.preventDefault();
    }
  });
  hit.addEventListener('blur', () => { if (rec.pos !== NORM) release(); });
  return g;
}

/**
 * Breaker: indication always, plus a handle when the manifest says it is
 * controllable. The generator output breaker is indication-only — it opens on
 * a turbine trip and is not an operator control (D10).
 * @param {Object} e
 * @param {import('./ws.js').Connection} conn
 */
export function createBreaker(e, conn) {
  const cx = e.x + e.w / 2;
  const g = el('g', { class: 'breaker', 'data-element': e.id });
  g.appendChild(plate(e.x, e.y + e.h - 14, e.w, 14, e.label || ''));
  const lamp = el('rect', {
    x: cx - 18, y: e.y + 8, width: 36, height: 24, rx: 2,
    class: 'breaker-lens',
  });
  g.appendChild(lamp);
  const label = el('text', { x: cx, y: e.y + 44, class: 'breaker-state' },
                   ['—']);
  g.appendChild(label);
  breakers.push({ el: e, lamp, label });

  if (e.options.controllable) {
    // The lens IS the control switch — a separate pushbutton did not fit the
    // 64 px footprint without running over the engraved plate.
    lamp.classList.add('controllable');
    lamp.addEventListener('click', () => {
      conn.action({ [e.options.action]: !store.indication(e.options.indication) });
    });
  }
  return g;
}

/** Apply the latest frame to grip lamps and breaker indication. */
export function update() {
  if (!store.frame) return;
  for (const gr of grips) {
    const running = store.indication(gr.el.options.running_indication);
    const tripped = store.indication(gr.el.options.tripped_indication);
    gr.lamp.setAttribute(
      'class', `lamp-lens ${tripped ? 'amber' : running ? 'red' : 'green'}`);
  }
  for (const b of breakers) {
    const closed = store.indication(b.el.options.indication);
    const ctrl = b.el.options.controllable ? ' controllable' : '';
    b.lamp.setAttribute('class',
      `breaker-lens ${closed ? 'closed' : 'open'}${ctrl}`);
    b.label.textContent = closed ? 'CLOSED' : 'OPEN';
  }
}

export function reset() { grips.length = 0; breakers.length = 0; }
