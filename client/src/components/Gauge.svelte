<script lang="ts">
  /**
   * Analog gauge: the server-generated face, an animated needle, a small
   * digital readout.
   *
   * The face — ticks, numerals, alarm/trip marks — is generated in Python from
   * the observation spec and the protection table, arrives in `hello`, and is
   * injected here as opaque markup via `{@html}` (§5.2): faces are data, not
   * components, so setpoints on the glass can never drift from the protection
   * table.
   *
   * Needle motion is the shared τ = 150 ms low-pass pool (§6.2). The first
   * sample snaps — a needle sweeping up from zero on connect would
   * misrepresent the plant as having just started.
   */
  import { store } from '../lib/frame.svelte';
  import { registerGauge } from '../lib/registry';
  import { needles } from '../lib/smoothing.svelte';
  import type { ManifestElement } from '../types';
  import Plate from './Plate.svelte';

  let { element }: { element: ManifestElement } = $props();

  const SWEEP = 270;
  const START = 135;
  const FACE_R = 50; // face units, matching facegen.py

  const size = $derived(element.size || 88);
  const scale = $derived(size / (FACE_R * 2));
  const cx = $derived(element.x + size / 2);
  const cy = $derived(element.y + size / 2);

  const face = $derived(store.hello?.gauge_faces[element.instrument] ?? '');
  const label = $derived(
    element.label || store.units[element.instrument]?.label || element.instrument);

  /** Needle angle in degrees for a display fraction, matching facegen. */
  function angleFor(si: number): number {
    const d = store.units[element.instrument];
    if (!d) return START;
    const v = si * d.scale + d.offset;
    const frac = d.hi === d.lo ? 0 : (v - d.lo) / (d.hi - d.lo);
    return START + SWEEP * Math.min(Math.max(frac, 0), 1);
  }

  const lp = needles.create();
  $effect(() => {
    const si = store.siValue(element.instrument);
    if (si !== undefined) lp.setTarget(angleFor(si));
  });
  $effect(() => {
    const unregister = registerGauge();
    return () => {
      needles.drop(lp);
      unregister();
    };
  });

  const needleDeg = $derived(Number.isNaN(lp.shown) ? START : lp.shown);
</script>

<g class="gauge" data-instrument={element.instrument} data-element={element.id}>
  <circle {cx} {cy} r={size / 2 + 3} class="gauge-bezel" />
  <g transform={`translate(${cx} ${cy}) scale(${scale.toFixed(4)})`}>
    {@html face}
    <!-- Needle: a slim wedge with a red tail, rotated about the hub. -->
    <g class="needle-group" transform={`rotate(${needleDeg.toFixed(2)})`}>
      <path class="needle" d={`M -2.2 0 L 0 -${FACE_R - 8} L 2.2 0 Z`} />
      <path class="needle-tail" d="M -2.2 0 L 0 13 L 2.2 0 Z" />
      <circle cx="0" cy="0" r="3.2" class="needle-hub" />
    </g>
    <!-- A period board had a scale you read, but an exact value makes the sim
         inspectable without squinting. -->
    <text x="0" y="26" class="gauge-digital">{store.formatted(element.instrument)}</text>
  </g>
  <Plate x={cx - size / 2} y={element.y + size + 4} w={size} h={13} text={label} />
</g>
