<script lang="ts">
  /** An indicating lamp: red = energised, green = deenergised (§10). */
  import { store } from '../lib/frame.svelte';
  import type { ManifestElement } from '../types';
  import Plate from './Plate.svelte';

  let { element }: { element: ManifestElement } = $props();

  const r = $derived(Math.min(element.w, element.h) / 2 - 2);
  const cx = $derived(element.x + element.w / 2);
  const cy = $derived(element.y + r + 2);
  const on = $derived(store.indication(element.options.indication ?? ''));
  const color = $derived(element.options.color ?? 'red');
</script>

<g class="lamp" data-element={element.id}>
  <circle {cx} {cy} {r} class={`lamp-lens${on ? ' ' + color : ''}`} />
  <Plate x={element.x - 8} y={element.y + element.h - 12} w={element.w + 16}
         h={12} text={element.label || ''} />
</g>
