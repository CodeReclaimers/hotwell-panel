<script lang="ts">
  /**
   * Manual/auto controller station and the governor station (§6.3).
   *
   * Loop stations: AUTO / MAN pushbuttons with lamps, a vertical output meter
   * reading the actuator command 0–100%, and RAISE / LOWER stepping the manual
   * command at a fixed slew per held tick — a human turning a knob, not typing
   * a float. The core rejects RAISE/LOWER in AUTO and the rejection prints
   * verbatim in the SOE log, which is the honest feedback.
   *
   * Governor: RAISE / LOWER the load reference in 0.25 MW steps with
   * held-repeat, MW and frequency meters adjacent, a 5% DROOP placard.
   *
   * Mode lamps come from `frame.loops`, read off the live controllers, so the
   * lamp cannot disagree with the plant after a reset or a scenario action.
   */
  import { store } from '../lib/frame.svelte';
  import type { Connection } from '../lib/ws';
  import type { LoopState, ManifestElement } from '../types';
  import Plate from './Plate.svelte';
  import StationButton from './StationButton.svelte';

  let { element, conn }: { element: ManifestElement; conn: Connection } = $props();

  const o = $derived(element.options);
  const loop = $derived(o.loop ?? '');
  const isGovernor = $derived(loop === 'governor');
  const bx = $derived(element.x + 10);

  // Vertical output meter, 0-100%.
  const mx = $derived(element.x + element.w - 34);
  const my = $derived(element.y + 26);
  const mh = 96;

  function loopState(): LoopState {
    const v = store.frame?.loops[loop];
    return v && typeof v === 'object' && !Array.isArray(v) ? (v as LoopState) : {};
  }

  const pct = $derived.by(() => {
    if (!store.frame || !o.output_instrument) return 0;
    return store.displayValue(o.output_instrument) ?? 0;
  });
  const fillH = $derived((Math.max(0, Math.min(100, pct)) / 100) * mh);

  const d = $derived(store.units[element.instrument]);
  const pvText = $derived(store.frame
    ? `${store.formatted(element.instrument)} ${d?.unit ?? ''}` : '—');
  const spText = $derived.by(() => {
    const st = loopState();
    if (!store.frame || st.sp === undefined || d?.scale === undefined) return 'SP —';
    const sp = st.sp * d.scale + d.offset;
    return `SP ${sp.toFixed(d.decimals)} ${d.unit}`;
  });
  const manual = $derived(loopState().mode === 'manual');

  const threeElement = $derived(Boolean(store.frame?.loops.three_element));
  const refText = $derived(store.frame
    ? `REF ${(loopState().load_ref_mw ?? 0).toFixed(2)} MW` : 'REF —');

  /** Step the manual command by the slew, clamped to the actuator range. */
  function stepManual(sign: number): void {
    if (!o.manual_action) return;
    const st = loopState();
    const base = st.manual_cmd ?? 0;
    const lo = st.lo ?? 0;
    const hi = st.hi ?? 1;
    const next = Math.min(Math.max(base + sign * (o.slew ?? 0.02), lo), hi);
    conn.action({ [o.manual_action]: Number(next.toFixed(4)) });
  }

  /** Step the governor load reference by ±step_mw, clamped to the block. */
  function stepGovernor(sign: number): void {
    if (!o.raise_action) return;
    const base = loopState().load_ref_mw ?? 0;
    const next = Math.min(Math.max(base + sign * (o.step_mw ?? 0.25), 0), 75);
    conn.action({ [o.raise_action]: Number(next.toFixed(3)) });
  }
</script>

<g class="station" data-element={element.id} data-loop={loop}>
  <rect x={element.x} y={element.y} width={element.w} height={element.h} rx="2"
        class="station-box" />
  <Plate x={element.x} y={element.y} w={element.w} h={14}
         text={element.label || loop} />

  {#if !isGovernor}
    <!-- The governor has no single PV: it shows MW and frequency meters
         instead (§6.3), so it would otherwise display two blank fields. -->
    <text x={element.x + 10} y={element.y + 34} class="station-pv">{pvText}</text>
    <text x={element.x + 10} y={element.y + 48} class="station-sp">{spText}</text>
  {/if}

  <rect x={mx} y={my} width="16" height={mh} class="meter-track" />
  <rect x={mx} y={my + mh - fillH} width="16" height={fillH} class="meter-fill" />
  <text x={mx + 8} y={my + mh + 12} class="meter-label">OUT</text>
  <text x={mx + 8} y={my - 4} class="meter-label">
    {store.frame ? `${pct.toFixed(0)}%` : '—'}
  </text>

  {#if isGovernor}
    <StationButton x={bx} y={element.y + 58} w={54} h={20} text="RAISE"
                   cls="slew" onpress={() => stepGovernor(+1)} />
    <StationButton x={bx + 60} y={element.y + 58} w={54} h={20} text="LOWER"
                   cls="slew" onpress={() => stepGovernor(-1)} />
    <text x={bx} y={element.y + 100} class="station-meter">
      {store.frame ? `${store.formatted('mw_out')} MW` : '— MW'}
    </text>
    <text x={bx} y={element.y + 120} class="station-meter">
      {store.frame ? `${store.formatted('frequency')} HZ` : '— HZ'}
    </text>
    <text x={bx} y={element.y + 136} class="station-sp">{refText}</text>
    <text x={element.x + element.w - 10} y={element.y + element.h - 10}
          class="station-legend droop">5% DROOP</text>
  {:else}
    <StationButton x={bx} y={element.y + 58} w={54} h={20} text="AUTO"
                   cls="mode" lit={store.frame !== null && !manual}
                   onpress={() => o.mode_action && conn.action({ [o.mode_action]: 'auto' })} />
    <StationButton x={bx + 60} y={element.y + 58} w={54} h={20} text="MAN"
                   cls="mode" lit={manual}
                   onpress={() => o.mode_action && conn.action({ [o.mode_action]: 'manual' })} />
    <StationButton x={bx} y={element.y + 84} w={54} h={20} text="RAISE"
                   cls="slew" onpress={() => stepManual(+1)} />
    <StationButton x={bx + 60} y={element.y + 84} w={54} h={20} text="LOWER"
                   cls="slew" onpress={() => stepManual(-1)} />
    {#if o.element_mode_lamp}
      <!-- §6.3: the 1E/3E element mode as a legend lamp — D18 made visible. -->
      <text x={element.x + 10} y={element.y + element.h - 10}
            class={`station-legend${threeElement ? '' : ' degraded'}`}>
        {store.frame ? (threeElement ? '3-ELEMENT' : '1-ELEMENT') : '—'}
      </text>
    {/if}
  {/if}
</g>
