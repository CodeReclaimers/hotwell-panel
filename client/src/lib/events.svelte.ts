/**
 * Sequence-of-events state (§8.2) and the FIRST OUT plate value.
 *
 * Every line is a server-rendered `event.text` — the client is not formatting
 * domain text. The FIRST OUT plate exists because the initiating event of the
 * canonical casualty is `CP1_TRIP:overload`, a free-form label with no
 * protection-table id and therefore no annunciator window; without a dedicated
 * display the panel would show the cascade but not what started it.
 */

import type { EventMsg } from '../types';

export const MAX_LINES = 400;

export interface SoeLine {
  t: number;
  text: string;
  kind: string;
  trip: boolean;
}

export type SoeFilter = 'all' | 'alarms' | 'actions';

/** MMM:SS.s — the SOE/plate timestamp format. */
export function fmtT(t: number): string {
  const m = Math.floor(t / 60);
  return `${String(m).padStart(3, '0')}:${(t - m * 60).toFixed(1).padStart(4, '0')}`;
}

export class SoeStore {
  // Replaced wholesale per push (≤ 400 entries): reference-level reactivity,
  // same reasoning as the frame store.
  lines = $state.raw<SoeLine[]>([]);
  filter = $state<SoeFilter>('all');
  firstOut = $state.raw<{ t: number; id: string } | null>(null);

  push(ev: EventMsg): void {
    const line: SoeLine = {
      t: ev.t,
      text: ev.text || `${ev.kind} ${ev.id}`,
      kind: ev.kind,
      trip: Boolean(ev.is_trip),
    };
    const next = [...this.lines, line];
    if (next.length > MAX_LINES) next.shift();
    this.lines = next;
    if (ev.kind === 'first_out' && ev.first_out) {
      this.firstOut = { t: ev.t, id: ev.id };
    }
  }

  /** Clear the plate and the log (new scenario / reset). */
  reset(): void {
    this.lines = [];
    this.firstOut = null;
  }

  /** Lines passing the current filter toggle. */
  visible(): SoeLine[] {
    if (this.filter === 'alarms') {
      return this.lines.filter((l) =>
        l.kind === 'alarm' || l.kind === 'first_out' || l.kind === 'plant_dead');
    }
    if (this.filter === 'actions') {
      return this.lines.filter((l) => l.kind === 'action');
    }
    return this.lines;
  }

  count(): number {
    return this.lines.length;
  }
}

export const soe = new SoeStore();
