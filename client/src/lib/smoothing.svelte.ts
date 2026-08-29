/**
 * Needle smoothing (§6.2): first-order low-pass with τ = 150 ms — analog feel
 * without lying about the data. The underlying 20 Hz values are what the sim
 * sensed, including the ±0.05 MW droop dither; that shows through, which is
 * the point. No interpolation beyond the smoothing.
 *
 * The time constant is the spec; the mechanism (a shared rAF pool driving
 * per-gauge low-passes) is the implementer's choice the plan allows. Runs on
 * the wall clock so needles settle while the sim is paused (§3.2).
 */

export const TAU_MS = 150;
/** rAF gap clamp: after a tab-switch stall, don't teleport the dynamics. */
export const MAX_FRAME_MS = 250;

export class LowPass {
  shown = $state(NaN);
  private target = NaN;

  /**
   * Aim at a new value. The first sample snaps: a needle sweeping up from
   * zero on connect would misrepresent the plant as having just started.
   */
  setTarget(v: number): void {
    this.target = v;
    if (Number.isNaN(this.shown)) this.shown = v;
  }

  /** One smoothing step with precomputed blend factor alpha ∈ (0, 1]. */
  advance(alpha: number): void {
    if (Number.isNaN(this.target) || Number.isNaN(this.shown)) return;
    this.shown += (this.target - this.shown) * alpha;
  }
}

export class SmoothingPool {
  private items = new Set<LowPass>();
  private rafId: number | null = null;
  private lastAt = 0;

  create(): LowPass {
    const lp = new LowPass();
    this.items.add(lp);
    return lp;
  }

  drop(lp: LowPass): void {
    this.items.delete(lp);
  }

  /** Advance every low-pass by dtMs of wall time (clamped). Pure; testable. */
  advance(dtMs: number): void {
    const alpha = 1 - Math.exp(-Math.min(dtMs, MAX_FRAME_MS) / TAU_MS);
    for (const lp of this.items) lp.advance(alpha);
  }

  /** Start the shared requestAnimationFrame loop (idempotent). */
  start(): void {
    if (this.rafId !== null) return;
    this.lastAt = performance.now();
    const tick = (now: number) => {
      this.advance(now - this.lastAt);
      this.lastAt = now;
      this.rafId = requestAnimationFrame(tick);
    };
    this.rafId = requestAnimationFrame(tick);
  }

  stop(): void {
    if (this.rafId !== null) cancelAnimationFrame(this.rafId);
    this.rafId = null;
  }

  size(): number {
    return this.items.size;
  }
}

/** The one pool every gauge needle registers with. */
export const needles = new SmoothingPool();
