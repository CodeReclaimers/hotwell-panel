/**
 * @file Client-side state: the last hello, the latest frame, and the unit
 * conversion the server shipped.
 *
 * The panel holds as little domain knowledge as possible (§1). Everything here
 * is either verbatim from the server or a mechanical application of the
 * affine display table.
 */

export const store = {
  /** @type {Object|null} */ hello: null,
  /** @type {Object|null} */ frame: null,
  /** @type {Object<string,Object>} */ units: {},
  /** @type {Object<string,Object>} */ windows: {},   // alarm id -> window spec
  /** @type {Object<string,Object>} */ elements: {},  // manifest id -> element
  connected: false,

  /** @param {Object} hello */
  setHello(hello) {
    this.hello = hello;
    this.units = hello.display_units || {};
    this.windows = {};
    for (const w of hello.annunciator || []) this.windows[w.id] = w;
    this.elements = {};
    for (const e of (hello.manifest && hello.manifest.elements) || []) {
      this.elements[e.id] = e;
    }
  },

  /** @param {Object} frame */
  setFrame(frame) { this.frame = frame; },

  /**
   * SI value for an instrument, following a derived signal's `source`.
   * @param {string} name
   * @returns {number|undefined}
   */
  siValue(name) {
    if (!this.frame) return undefined;
    const d = this.units[name];
    const key = (d && d.source) ? d.source : name;
    return this.frame.values[key];
  },

  /**
   * Display value: the server's affine conversion, applied mechanically.
   * @param {string} name
   * @returns {number|undefined}
   */
  displayValue(name) {
    const si = this.siValue(name);
    const d = this.units[name];
    if (si === undefined || !d) return undefined;
    return si * d.scale + d.offset;
  },

  /** Display value formatted at the instrument's resolution, with units. */
  formatted(name) {
    const v = this.displayValue(name);
    const d = this.units[name];
    if (v === undefined || !d) return '—';
    return `${v.toFixed(d.decimals)}`;
  },

  /** @returns {boolean} */
  indication(key) {
    return Boolean(this.frame && this.frame.indications[key]);
  },
};
