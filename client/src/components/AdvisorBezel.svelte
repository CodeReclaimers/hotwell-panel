<script lang="ts">
  /**
   * The reserved phase-3 assistant region (§6): a dark CRT bezel, offline.
   * Non-functional by design — phase 2 reserves the screen region only.
   */
  import { store } from '../lib/frame.svelte';

  const region = $derived(store.hello?.manifest.regions['advisor'] ?? null);
</script>

{#if region}
  <rect x={region.x} y={region.y} width={region.w} height={region.h} rx="3"
        class="crt-bezel" />
  <text x={region.x + 12} y={region.y + 26} class="crt-text dim">ADVISOR — OFFLINE</text>
  <text x={region.x + 12} y={region.y + 44} class="crt-text dim">
    no advisory system installed on this unit
  </text>
{/if}
