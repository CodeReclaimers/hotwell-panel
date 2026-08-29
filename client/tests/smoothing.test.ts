/**
 * §12.5: the needle smoothing store. τ = 150 ms is the spec (§6.2); these
 * tests pin the exponential step response, the first-frame snap, and the
 * tab-switch clamp.
 */
import { describe, expect, it } from 'vitest';

import {
  LowPass, MAX_FRAME_MS, SmoothingPool, TAU_MS,
} from '../src/lib/smoothing.svelte';

describe('LowPass', () => {
  it('snaps on the first sample (no fake sweep-up on connect)', () => {
    const lp = new LowPass();
    expect(Number.isNaN(lp.shown)).toBe(true);
    lp.setTarget(42);
    expect(lp.shown).toBe(42);
  });

  it('advancing with no target yet is a no-op, not a NaN storm', () => {
    const lp = new LowPass();
    lp.advance(0.5);
    expect(Number.isNaN(lp.shown)).toBe(true);
  });
});

describe('SmoothingPool step response', () => {
  it('follows 1 - exp(-t/τ) toward the target', () => {
    const pool = new SmoothingPool();
    const lp = pool.create();
    lp.setTarget(0); // snap to 0
    lp.setTarget(1); // now smooth toward 1
    pool.advance(TAU_MS); // one time constant
    console.log(`  after 1τ: ${lp.shown.toFixed(6)} (expect ${(1 - Math.exp(-1)).toFixed(6)})`);
    expect(lp.shown).toBeCloseTo(1 - Math.exp(-1), 9);
    pool.advance(TAU_MS); // two time constants total
    console.log(`  after 2τ: ${lp.shown.toFixed(6)} (expect ${(1 - Math.exp(-2)).toFixed(6)})`);
    expect(lp.shown).toBeCloseTo(1 - Math.exp(-2), 9);
  });

  it('clamps a stalled animation frame to MAX_FRAME_MS', () => {
    const pool = new SmoothingPool();
    const a = pool.create();
    a.setTarget(0);
    a.setTarget(1);
    pool.advance(10_000); // tab was in the background
    const clamped = 1 - Math.exp(-MAX_FRAME_MS / TAU_MS);
    console.log(`  10 s stall advanced by ${a.shown.toFixed(6)} (clamp ${clamped.toFixed(6)})`);
    expect(a.shown).toBeCloseTo(clamped, 9);
  });

  it('advances every registered needle; dropped ones stop moving', () => {
    const pool = new SmoothingPool();
    const a = pool.create();
    const b = pool.create();
    for (const lp of [a, b]) {
      lp.setTarget(0);
      lp.setTarget(1);
    }
    pool.advance(TAU_MS);
    expect(a.shown).toBeCloseTo(b.shown, 12);
    pool.drop(b);
    const frozen = b.shown;
    pool.advance(TAU_MS);
    expect(a.shown).toBeGreaterThan(frozen);
    expect(b.shown).toBe(frozen);
    expect(pool.size()).toBe(1);
  });
});
