<script lang="ts">
  /**
   * Breaker: indication always, plus a handle when the manifest says it is
   * controllable. The generator output breaker is indication-only — it opens
   * on a turbine trip and is not an operator control (D10). The lens IS the
   * control switch — a separate pushbutton did not fit the 64 px footprint
   * without running over the engraved plate.
   */
  import { store } from '../lib/frame.svelte';
  import type { Connection } from '../lib/ws';
  import type { ManifestElement } from '../types';
  import Plate from './Plate.svelte';

  let { element, conn }: { element: ManifestElement; conn: Connection } = $props();

  const o = $derived(element.options);
  const cx = $derived(element.x + element.w / 2);
  const closed = $derived(store.frame ? store.indication(o.indication ?? '') : null);
  const lensClass = $derived.by(() => {
    const state = closed === null ? '' : closed ? ' closed' : ' open';
    return `breaker-lens${state}${o.controllable ? ' controllable' : ''}`;
  });

  function toggleBreaker(): void {
    if (!o.controllable || !o.action) return;
    conn.action({ [o.action]: !store.indication(o.indication ?? '') });
  }
</script>

<g class="breaker" data-element={element.id}>
  <Plate x={element.x} y={element.y + element.h - 14} w={element.w} h={14}
         text={element.label || ''} />
  {#if o.controllable}
    <rect x={cx - 18} y={element.y + 8} width="36" height="24" rx="2"
          class={lensClass} onclick={toggleBreaker} role="switch"
          aria-checked={closed === true} aria-label={element.label}
          tabindex="0"
          onkeydown={(ev) => {
            if (ev.key === 'Enter' || ev.key === ' ') { toggleBreaker(); ev.preventDefault(); }
          }} />
  {:else}
    <rect x={cx - 18} y={element.y + 8} width="36" height="24" rx="2"
          class={lensClass} />
  {/if}
  <text x={cx} y={element.y + 44} class="breaker-state">
    {closed === null ? '—' : closed ? 'CLOSED' : 'OPEN'}
  </text>
</g>
