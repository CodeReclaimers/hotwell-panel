/**
 * The annunciator horn (§7): a two-tone square-ish buzz on WebAudio, plus a
 * short switch click (§15 limits sound design to exactly these two).
 *
 * Browsers refuse to start audio without a user gesture, so everything stays
 * behind one unlock on the first pointerdown anywhere; until then the horn is
 * silently skipped rather than throwing.
 */

const F_LOW = 320;
const F_HIGH = 470;
const ALTERNATE_MS = 260;

let ctx: AudioContext | null = null;
let gain: GainNode | null = null;
let osc: OscillatorNode | null = null;
let toggle: ReturnType<typeof setInterval> | null = null;
let sounding = false;
let muted = false;

/** Arm audio on the first user gesture (browser autoplay policy). */
export function unlock(): void {
  if (ctx) return;
  const Ctor = window.AudioContext
    ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!Ctor) return;
  ctx = new Ctor();
  gain = ctx.createGain();
  gain.gain.value = 0;
  gain.connect(ctx.destination);
  // Square wave through a gentle low-pass: buzzy, not a videogame beep.
  const filter = ctx.createBiquadFilter();
  filter.type = 'lowpass';
  filter.frequency.value = 1800;
  filter.connect(gain);
  osc = ctx.createOscillator();
  osc.type = 'square';
  osc.frequency.value = F_LOW;
  osc.connect(filter);
  osc.start();
  if (sounding) applyGain();
}

function applyGain(): void {
  if (!gain || !ctx) return;
  const target = sounding && !muted ? 0.06 : 0.0;
  gain.gain.setTargetAtTime(target, ctx.currentTime, 0.01);
}

/** Start the horn. Idempotent — a second new alarm does not stack it. */
export function start(): void {
  if (sounding) return;
  sounding = true;
  applyGain();
  if (toggle === null) {
    let high = false;
    toggle = setInterval(() => {
      if (!osc || !ctx) return;
      high = !high;
      osc.frequency.setValueAtTime(high ? F_HIGH : F_LOW, ctx.currentTime);
    }, ALTERNATE_MS);
  }
}

/** SILENCE: stop the horn. Flashing continues — that is the ISA sequence. */
export function silence(): void {
  sounding = false;
  applyGain();
  if (toggle !== null) {
    clearInterval(toggle);
    toggle = null;
  }
}

/** Instructor-station mute, for demo rooms (§9). */
export function setMuted(on: boolean): void {
  muted = Boolean(on);
  applyGain();
}

export function isMuted(): boolean {
  return muted;
}

export function isSounding(): boolean {
  return sounding;
}

/** A short switch click, so the board has some tactile feedback. */
export function click(): void {
  if (!ctx || muted) return;
  const o = ctx.createOscillator();
  const g = ctx.createGain();
  o.type = 'square';
  o.frequency.value = 1400;
  g.gain.setValueAtTime(0.05, ctx.currentTime);
  g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.04);
  o.connect(g);
  g.connect(ctx.destination);
  o.start();
  o.stop(ctx.currentTime + 0.05);
}
