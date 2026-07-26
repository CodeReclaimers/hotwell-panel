/**
 * @file Small SVG DOM helpers. No framework, so element creation is explicit.
 */

const NS = 'http://www.w3.org/2000/svg';

/**
 * @param {string} tag
 * @param {Object<string,(string|number)>} [attrs]
 * @param {(Node|string)[]} [children]
 * @returns {SVGElement}
 */
export function el(tag, attrs = {}, children = []) {
  const node = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined) continue;
    node.setAttribute(k, String(v));
  }
  for (const c of children) {
    node.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
  }
  return node;
}

/** An engraved lamacoid plate with centred white text (§10). */
export function plate(x, y, w, h, text, cls = '') {
  const g = el('g', { class: `plate ${cls}`.trim() });
  g.appendChild(el('rect', { x, y, width: w, height: h, rx: 1,
                             class: 'device-plate' }));
  g.appendChild(el('text', {
    x: x + w / 2, y: y + h / 2, class: 'device-plate-text',
  }, [text]));
  return g;
}

/** Parse an SVG fragment string into nodes (used for server-rendered faces). */
export function parseFragment(markup) {
  const doc = new DOMParser().parseFromString(
    `<svg xmlns="${NS}">${markup}</svg>`, 'image/svg+xml');
  return Array.from(doc.documentElement.childNodes);
}

export function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}
