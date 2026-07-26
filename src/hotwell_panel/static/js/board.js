/**
 * @file Render the board from the placement manifest, and drive the
 * indication-only widgets (lamps, mimic pumps, breakers, flow animation).
 *
 * Interactive widgets — pistol grips, M/A stations, pushbuttons, annunciator —
 * are added by their own modules in later milestones; this module lays out
 * their footprints so the board is complete and correctly proportioned from
 * P1 onward.
 */

import { createRecorder } from './charts.js';
import * as charts from './charts.js';
import { createGauge } from './gauges.js';
import { createBreaker, createGrip } from './grips.js';
import * as grips from './grips.js';
import * as stations from './stations.js';
import { createStation } from './stations.js';
import { store } from './store.js';
import { clear, el, plate } from './svgutil.js';

/** @type {{node: SVGElement, key: string, on: string}[]} */
const lamps = [];
/** @type {{node: SVGElement, pump: string}[]} */
const mimicPumps = [];
/** @type {{node: SVGElement, key: string}[]} */
const mimicIndications = [];
/** @type {{node: SVGElement, signal: string}[]} */
const flowLines = [];

/** Load the hand-authored mimic one-line into its layer. */
export async function loadMimic() {
  const layer = document.getElementById('layer-mimic');
  const text = await (await fetch('/static/board.svg')).text();
  const doc = new DOMParser().parseFromString(
    `<svg xmlns="http://www.w3.org/2000/svg">${text}</svg>`, 'image/svg+xml');
  for (const node of Array.from(doc.documentElement.childNodes)) {
    layer.appendChild(node);
  }
  for (const n of layer.querySelectorAll('[data-pump]')) {
    mimicPumps.push({ node: n, pump: n.getAttribute('data-pump') });
  }
  for (const n of layer.querySelectorAll('[data-indication]')) {
    mimicIndications.push({ node: n, key: n.getAttribute('data-indication') });
  }
  for (const n of layer.querySelectorAll('[data-flow]')) {
    flowLines.push({ node: n, signal: n.getAttribute('data-flow') });
  }
}

/** Group title plates and separator boxes (§10). */
function renderGroups(manifest) {
  const layer = document.getElementById('layer-groups');
  clear(layer);
  for (const g of manifest.groups || []) {
    layer.appendChild(el('rect', {
      x: g.x, y: g.y, width: g.w, height: g.h, rx: 2, class: 'group-box',
    }));
    const tw = Math.max(96, g.title.length * 8);
    layer.appendChild(el('rect', {
      x: g.x + 8, y: g.y - 8, width: tw, height: 16, rx: 1,
      class: 'group-plate',
    }));
    layer.appendChild(el('text', {
      x: g.x + 8 + tw / 2, y: g.y, class: 'group-title',
    }, [g.title]));
  }
}

/** An indicating lamp: red = energised, green = deenergised (§10). */
function createLamp(e) {
  const g = el('g', { class: 'lamp', 'data-element': e.id });
  const r = Math.min(e.w, e.h) / 2 - 2;
  const cx = e.x + e.w / 2;
  const cy = e.y + r + 2;
  const lens = el('circle', { cx, cy, r, class: 'lamp-lens' });
  g.appendChild(lens);
  g.appendChild(plate(e.x - 8, e.y + e.h - 12, e.w + 16, 12, e.label || ''));
  lamps.push({ node: lens, key: e.options.indication,
               on: e.options.color || 'red' });
  return g;
}

/**
 * A pushbutton. Covered guards (the manual trips, §11) need the cover lifted
 * before the button will act — a real board does not let you brush an MFT
 * pushbutton by accident.
 */
function createButton(e, conn, handlers) {
  const o = e.options || {};
  const g = el('g', { class: `push-button board-button${o.covered ? ' covered' : ''}`,
                      'data-element': e.id });
  g.appendChild(el('rect', {
    x: e.x, y: e.y, width: e.w, height: e.h, rx: 3, class: 'button-body',
  }));
  g.appendChild(plate(e.x + 4, e.y + 4, e.w - 8, 14, e.label || e.id));
  const face = el('rect', {
    x: e.x + 10, y: e.y + 24, width: e.w - 20, height: e.h - 34, rx: 3,
    class: `push-face${o.covered ? ' guarded' : ''}`,
  });
  g.appendChild(face);
  const caption = el('text', {
    x: e.x + e.w / 2, y: e.y + e.h - 14, class: 'push-text',
  }, [o.covered ? 'LIFT COVER' : 'PRESS']);
  g.appendChild(caption);

  let uncovered = !o.covered;
  face.addEventListener('click', () => {
    if (o.covered && !uncovered) {
      uncovered = true;
      face.setAttribute('class', 'push-face armed');
      caption.textContent = 'PRESS';
      // Re-latch the guard shortly after, so it is armed for one press only.
      setTimeout(() => {
        if (!uncovered) return;
        uncovered = false;
        face.setAttribute('class', 'push-face guarded');
        caption.textContent = 'LIFT COVER';
      }, 4000);
      return;
    }
    if (o.local && handlers[o.local]) {
      handlers[o.local]();
    } else if (o.action) {
      conn.action({ [o.action]: true });
    }
    if (o.covered) {
      uncovered = false;
      face.setAttribute('class', 'push-face guarded');
      caption.textContent = 'LIFT COVER';
    }
  });
  // LAMP TEST is held, not clicked (§7).
  if (o.local === 'lamp_test') {
    face.addEventListener('mousedown', () => handlers.lamp_test_on?.());
    face.addEventListener('mouseup', () => handlers.lamp_test_off?.());
    face.addEventListener('mouseleave', () => handlers.lamp_test_off?.());
  }
  return g;
}

/** Placeholder footprint for kinds whose module lands in a later milestone. */
function placeholder(e, caption) {
  const g = el('g', { class: `placeholder kind-${e.kind}`,
                      'data-element': e.id });
  g.appendChild(el('rect', {
    x: e.x, y: e.y, width: e.w, height: e.h, rx: 2, class: 'group-box',
  }));
  g.appendChild(plate(e.x, e.y, e.w, 14, e.label || e.id));
  g.appendChild(el('text', {
    x: e.x + e.w / 2, y: e.y + e.h / 2, class: 'device-plate-text',
  }, [caption]));
  return g;
}

/**
 * Build every placed element.
 * @param {Object} manifest
 */
export function renderElements(manifest, conn, handlers = {}) {
  const layer = document.getElementById('layer-elements');
  clear(layer);
  lamps.length = 0;
  grips.reset();
  stations.reset();
  charts.reset();
  renderGroups(manifest);
  for (const e of manifest.elements || []) {
    switch (e.kind) {
      case 'gauge':
        layer.appendChild(createGauge(e));
        break;
      case 'lamp':
        layer.appendChild(createLamp(e));
        break;
      case 'grip':
        layer.appendChild(createGrip(e, conn));
        break;
      case 'breaker':
        layer.appendChild(createBreaker(e, conn));
        break;
      case 'station':
        layer.appendChild(createStation(e, conn));
        break;
      case 'button':
        layer.appendChild(createButton(e, conn, handlers));
        break;
      case 'chart':
        layer.appendChild(createRecorder(e, conn));
        break;
      default:
        layer.appendChild(placeholder(e, e.kind.toUpperCase()));
    }
  }
}

/** The reserved phase-3 assistant region and the SOE surface (§6). */
export function renderRightPane(manifest) {
  const layer = document.getElementById('layer-right');
  clear(layer);
  const adv = (manifest.regions || {}).advisor;
  if (adv) {
    layer.appendChild(el('rect', {
      x: adv.x, y: adv.y, width: adv.w, height: adv.h, rx: 3,
      class: 'crt-bezel',
    }));
    layer.appendChild(el('text', {
      x: adv.x + 12, y: adv.y + 26, class: 'crt-text dim',
    }, ['ADVISOR — OFFLINE']));
    layer.appendChild(el('text', {
      x: adv.x + 12, y: adv.y + 44, class: 'crt-text dim',
    }, ['no advisory system installed on this unit']));
  }
}

/** Apply the latest frame to every indication-driven widget. */
export function updateIndications() {
  if (!store.frame) return;
  grips.update();
  stations.update();
  for (const l of lamps) {
    const on = store.indication(l.key);
    l.node.setAttribute('class', `lamp-lens${on ? ' ' + l.on : ''}`);
  }
  for (const p of mimicPumps) {
    const running = store.indication(`${p.pump}_running`);
    const tripped = store.indication(`${p.pump}_tripped`);
    p.node.setAttribute(
      'class', `pump${running ? ' running' : ''}${tripped ? ' tripped' : ''}`);
  }
  for (const m of mimicIndications) {
    const on = store.indication(m.key);
    const base = m.node.getAttribute('class').split(' ')
      .filter((c) => c !== 'on' && c !== 'closed').join(' ');
    m.node.setAttribute('class', on
      ? `${base} ${m.key === 'breaker_closed' ? 'closed' : 'on'}` : base);
  }
  // Marching dashes only where flow is actually moving (§6.2).
  for (const f of flowLines) {
    const v = store.frame.values[f.signal];
    const flowing = v !== undefined && Math.abs(v) > 0.5;   // kg/s
    f.node.classList.toggle('flowing', flowing);
  }
}
