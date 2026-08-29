/**
 * The annunciator ISA-18.1 sequence as a PURE state machine (§7): no DOM, no
 * socket — driven by `event` messages and unit-tested with vitest. The
 * Annunciator component renders windows from this state; flash timing itself
 * is CSS on the wall clock, so flashing continues while the sim is paused.
 *
 * Sequence (§7, exactly the vanilla client's semantics):
 * new alarm → FAST flash (+ horn, wired in main.ts). SILENCE stops the horn,
 * flashing continues. ACK → STEADY (and main.ts sends one `alarm.ack` per
 * flashing id — the core tracks acknowledged state). Condition clears while
 * lit → SLOW flash ("ringback" simplified: slow-flash until RESET), then off.
 * LAMP TEST lights every window while held. First-out carries inverted colors
 * and a corner tag.
 */

import type { AlarmState, AnnunciatorWindowSpec } from '../types';

export const DARK = 'dark';
export const FAST = 'fast'; // new alarm: fast flash + horn
export const STEADY = 'steady'; // acknowledged, condition still present
export const SLOW = 'slow'; // condition cleared while lit (ringback)

export type WindowState = typeof DARK | typeof FAST | typeof STEADY | typeof SLOW;

export interface WindowRecord {
  spec: AnnunciatorWindowSpec;
  state: WindowState;
  firstOut: boolean;
}

/** Class list for a window's outer group — matches the CSS contract. */
export function groupClasses(w: WindowRecord, lampTest: boolean): string {
  const cls = ['ann-window-group'];
  if (lampTest || w.state !== DARK) cls.push('lit');
  if (w.state === FAST) cls.push('flash-fast');
  if (w.state === SLOW) cls.push('flash-slow');
  if (w.firstOut) cls.push('first-out');
  return cls.join(' ');
}

/** Class list for the window rect itself. */
export function windowClasses(w: WindowRecord, lampTest: boolean): string {
  const lit = lampTest || w.state !== DARK;
  return `ann-window${lit ? ' lit' : ''}${w.spec.is_trip ? ' trip' : ''}`;
}

export class AnnunciatorMachine {
  /** id -> record, in protection-table order (insertion order preserved). */
  windows = $state<Record<string, WindowRecord>>({});
  lampTest = $state(false);

  /** Build the window set from the hello's protection-table list. */
  install(specs: AnnunciatorWindowSpec[]): void {
    const next: Record<string, WindowRecord> = {};
    for (const spec of specs) {
      next[spec.id] = { spec, state: DARK, firstOut: false };
    }
    this.windows = next;
    this.lampTest = false;
  }

  /** Apply an alarm transition from an `event` message. */
  onAlarm(id: string, alarmState: string): void {
    const w = this.windows[id];
    if (!w) return; // not a windowed condition
    if (alarmState === 'active') {
      // Re-activating a window that was ringing back starts the sequence over.
      w.state = FAST;
    } else if (alarmState === 'acknowledged') {
      w.state = STEADY;
    } else if (alarmState === 'clear') {
      // Cleared while lit: slow-flash until RESET (§7 ringback).
      w.state = w.state === DARK ? DARK : SLOW;
    }
  }

  /** Mark the initiating window of a trip sequence (§7 first-out).
   *  Returns false when the label has no window (e.g. CP1_TRIP:overload). */
  setFirstOut(id: string): boolean {
    const w = this.windows[id];
    if (!w) return false;
    w.firstOut = true;
    return true;
  }

  /** RESET: drop every ringing-back window to dark, clear first-out tags. */
  reset(): void {
    for (const w of Object.values(this.windows)) {
      if (w.state === SLOW) w.state = DARK;
      w.firstOut = false;
    }
  }

  /** LAMP TEST lights every window while held (§7). */
  setLampTest(on: boolean): void {
    this.lampTest = Boolean(on);
  }

  /** Ids currently flashing — what an ACK button should acknowledge. */
  flashing(): string[] {
    return Object.entries(this.windows)
      .filter(([, w]) => w.state === FAST)
      .map(([id]) => id);
  }

  /**
   * Adopt frame alarm state wholesale. Events are the primary driver, but a
   * client that connects mid-casualty has missed them, so the first frame
   * after a hello seeds the array.
   */
  seedFromFrame(alarms: Record<string, AlarmState>): void {
    for (const [id, w] of Object.entries(this.windows)) {
      const st = alarms[id];
      w.state = st === 'active' ? FAST
        : st === 'acknowledged' ? STEADY
          : (w.state === SLOW ? SLOW : DARK);
    }
  }

  count(): number {
    return Object.keys(this.windows).length;
  }
}

export const annunciator = new AnnunciatorMachine();
