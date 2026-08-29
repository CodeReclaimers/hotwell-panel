/**
 * The SOE store: line buffer, filters, FIRST OUT capture, timestamp format.
 * (Not a §12.5-mandated suite; added because the store was ported and pure
 * logic is cheap to pin.)
 */
import { describe, expect, it } from 'vitest';

import { MAX_LINES, SoeStore, fmtT } from '../src/lib/events.svelte';
import type { EventMsg } from '../src/types';

function ev(partial: Partial<EventMsg>): EventMsg {
  return {
    type: 'event', tick: 0, t: 0, kind: 'alarm', id: '', state: '', text: '',
    first_out: false, is_trip: false, detail: {}, ...partial,
  };
}

describe('SoeStore', () => {
  it('falls back to "kind id" when the server sent no text', () => {
    const s = new SoeStore();
    s.push(ev({ kind: 'pump', id: 'cp2', t: 1.0 }));
    expect(s.lines[0].text).toBe('pump cp2');
  });

  it('trims to MAX_LINES, dropping the oldest', () => {
    const s = new SoeStore();
    for (let i = 0; i < MAX_LINES + 5; i += 1) {
      s.push(ev({ text: `line ${i}` }));
    }
    expect(s.count()).toBe(MAX_LINES);
    expect(s.lines[0].text).toBe('line 5');
  });

  it('captures FIRST OUT only from a flagged first_out event', () => {
    const s = new SoeStore();
    s.push(ev({ kind: 'alarm', id: 'DA_LO', first_out: false }));
    expect(s.firstOut).toBeNull();
    s.push(ev({ kind: 'first_out', id: 'CP1_TRIP:overload', first_out: true, t: 12.3 }));
    expect(s.firstOut).toEqual({ t: 12.3, id: 'CP1_TRIP:overload' });
  });

  it('filters: alarms keeps alarm/first_out/plant_dead, actions keeps action', () => {
    const s = new SoeStore();
    s.push(ev({ kind: 'alarm', text: 'a' }));
    s.push(ev({ kind: 'action', text: 'b' }));
    s.push(ev({ kind: 'first_out', text: 'c' }));
    s.push(ev({ kind: 'plant_dead', text: 'd' }));
    s.push(ev({ kind: 'pump', text: 'e' }));
    s.filter = 'alarms';
    expect(s.visible().map((l) => l.text)).toEqual(['a', 'c', 'd']);
    s.filter = 'actions';
    expect(s.visible().map((l) => l.text)).toEqual(['b']);
    s.filter = 'all';
    expect(s.visible()).toHaveLength(5);
  });

  it('reset clears lines and the plate', () => {
    const s = new SoeStore();
    s.push(ev({ kind: 'first_out', id: 'X', first_out: true }));
    s.reset();
    expect(s.count()).toBe(0);
    expect(s.firstOut).toBeNull();
  });
});

describe('fmtT', () => {
  it('renders MMM:SS.s with zero padding', () => {
    expect(fmtT(0)).toBe('000:00.0');
    expect(fmtT(65.5)).toBe('001:05.5');
    expect(fmtT(600)).toBe('010:00.0');
  });
});
