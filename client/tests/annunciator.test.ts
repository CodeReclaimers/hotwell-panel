/**
 * §12.5: the annunciator ISA state machine, including the first-out and
 * ringback paths. Pure state — the DOM/CSS flash timing is not under test
 * here (the Playwright suite covers the rendered board).
 */
import { beforeEach, describe, expect, it } from 'vitest';

import {
  AnnunciatorMachine, DARK, FAST, SLOW, STEADY, groupClasses, windowClasses,
} from '../src/lib/annunciator.svelte';
import type { AnnunciatorWindowSpec } from '../src/types';

function spec(id: string, isTrip = false): AnnunciatorWindowSpec {
  return {
    id, legend: [id.slice(0, 12)], signal: 's', op: '<', setpoint: 0,
    reseat: null, delay: 0, latching: false, actions: [], is_trip: isTrip,
    target: '',
  };
}

let m: AnnunciatorMachine;

beforeEach(() => {
  m = new AnnunciatorMachine();
  m.install([spec('DRUM_LVL_LO'), spec('DA_LO'), spec('DRUM_LVL_LOLO', true)]);
});

describe('install', () => {
  it('builds one dark window per protection-table condition', () => {
    expect(m.count()).toBe(3);
    for (const w of Object.values(m.windows)) expect(w.state).toBe(DARK);
    expect(m.flashing()).toEqual([]);
  });
});

describe('the ISA sequence', () => {
  it('new alarm fast-flashes and joins flashing()', () => {
    m.onAlarm('DRUM_LVL_LO', 'active');
    expect(m.windows['DRUM_LVL_LO'].state).toBe(FAST);
    expect(m.flashing()).toEqual(['DRUM_LVL_LO']);
    const cls = groupClasses(m.windows['DRUM_LVL_LO'], m.lampTest);
    console.log(`  active group classes: ${cls}`);
    expect(cls).toContain('lit');
    expect(cls).toContain('flash-fast');
  });

  it('ACK takes the window steady and out of flashing()', () => {
    m.onAlarm('DRUM_LVL_LO', 'active');
    m.onAlarm('DRUM_LVL_LO', 'acknowledged');
    expect(m.windows['DRUM_LVL_LO'].state).toBe(STEADY);
    expect(m.flashing()).toEqual([]);
    const cls = groupClasses(m.windows['DRUM_LVL_LO'], m.lampTest);
    expect(cls).toContain('lit');
    expect(cls).not.toContain('flash-fast');
    expect(cls).not.toContain('flash-slow');
  });

  it('ringback: cleared while acknowledged slow-flashes until RESET', () => {
    m.onAlarm('DRUM_LVL_LO', 'active');
    m.onAlarm('DRUM_LVL_LO', 'acknowledged');
    m.onAlarm('DRUM_LVL_LO', 'clear');
    expect(m.windows['DRUM_LVL_LO'].state).toBe(SLOW);
    expect(groupClasses(m.windows['DRUM_LVL_LO'], false)).toContain('flash-slow');
    m.reset();
    expect(m.windows['DRUM_LVL_LO'].state).toBe(DARK);
  });

  it('cleared while still fast-flashing also rings back (vanilla semantics)', () => {
    m.onAlarm('DRUM_LVL_LO', 'active');
    m.onAlarm('DRUM_LVL_LO', 'clear');
    expect(m.windows['DRUM_LVL_LO'].state).toBe(SLOW);
  });

  it('clear on a dark window stays dark', () => {
    m.onAlarm('DRUM_LVL_LO', 'clear');
    expect(m.windows['DRUM_LVL_LO'].state).toBe(DARK);
  });

  it('re-activation during ringback starts the sequence over', () => {
    m.onAlarm('DRUM_LVL_LO', 'active');
    m.onAlarm('DRUM_LVL_LO', 'acknowledged');
    m.onAlarm('DRUM_LVL_LO', 'clear');
    m.onAlarm('DRUM_LVL_LO', 'active');
    expect(m.windows['DRUM_LVL_LO'].state).toBe(FAST);
    expect(m.flashing()).toEqual(['DRUM_LVL_LO']);
  });

  it('RESET leaves fast and steady windows alone', () => {
    m.onAlarm('DRUM_LVL_LO', 'active');
    m.onAlarm('DA_LO', 'active');
    m.onAlarm('DA_LO', 'acknowledged');
    m.reset();
    expect(m.windows['DRUM_LVL_LO'].state).toBe(FAST);
    expect(m.windows['DA_LO'].state).toBe(STEADY);
  });

  it('ignores transitions for ids with no window', () => {
    expect(() => m.onAlarm('CP1_TRIP:overload', 'active')).not.toThrow();
    expect(m.flashing()).toEqual([]);
  });
});

describe('first-out (§7)', () => {
  it('tags a windowed initiator and reports success', () => {
    m.onAlarm('DRUM_LVL_LOLO', 'active');
    expect(m.setFirstOut('DRUM_LVL_LOLO')).toBe(true);
    const cls = groupClasses(m.windows['DRUM_LVL_LOLO'], false);
    console.log(`  first-out classes: ${cls}`);
    expect(cls).toContain('first-out');
  });

  it('returns false for a free-form label with no window', () => {
    expect(m.setFirstOut('CP1_TRIP:overload')).toBe(false);
  });

  it('RESET clears the tag', () => {
    m.setFirstOut('DRUM_LVL_LOLO');
    m.reset();
    expect(m.windows['DRUM_LVL_LOLO'].firstOut).toBe(false);
  });
});

describe('lamp test', () => {
  it('lights every window while held, restores on release', () => {
    m.setLampTest(true);
    for (const w of Object.values(m.windows)) {
      expect(groupClasses(w, m.lampTest)).toContain('lit');
      expect(windowClasses(w, m.lampTest)).toContain('lit');
    }
    m.setLampTest(false);
    expect(groupClasses(m.windows['DA_LO'], m.lampTest)).not.toContain('lit');
  });
});

describe('window rect classes', () => {
  it('trip-class windows carry the trip class, lit or dark', () => {
    expect(windowClasses(m.windows['DRUM_LVL_LOLO'], false)).toBe('ann-window trip');
    m.onAlarm('DRUM_LVL_LOLO', 'active');
    expect(windowClasses(m.windows['DRUM_LVL_LOLO'], false)).toBe('ann-window lit trip');
  });
});

describe('seedFromFrame (mid-casualty connect)', () => {
  it('adopts active/acknowledged wholesale, keeps ringback, darkens the rest', () => {
    m.onAlarm('DRUM_LVL_LOLO', 'active');
    m.onAlarm('DRUM_LVL_LOLO', 'acknowledged');
    m.onAlarm('DRUM_LVL_LOLO', 'clear'); // -> SLOW, absent from frame.alarms
    m.onAlarm('DA_LO', 'active'); // will be darkened: not in the frame
    m.seedFromFrame({ DRUM_LVL_LO: 'active' });
    expect(m.windows['DRUM_LVL_LO'].state).toBe(FAST);
    expect(m.windows['DRUM_LVL_LOLO'].state).toBe(SLOW);
    expect(m.windows['DA_LO'].state).toBe(DARK);
  });
});
