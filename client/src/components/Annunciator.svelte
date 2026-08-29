<script lang="ts">
  /**
   * The annunciator array (§7): a grid of windows from the protection table,
   * with the remaining cells left as engraved blank spares — period-correct,
   * and room to grow. All sequencing state lives in the pure machine
   * (`lib/annunciator.svelte.ts`); this component only renders it. Flash
   * timing is CSS on the wall clock, so it keeps running when the sim pauses.
   */
  import { annunciator, groupClasses, windowClasses } from '../lib/annunciator.svelte';
  import { store } from '../lib/frame.svelte';
  import type { AnnunciatorWindowSpec } from '../types';

  const grid = $derived(store.hello?.manifest.annunciator ?? null);
  const specs = $derived(store.hello?.annunciator ?? []);

  interface Cell {
    x: number;
    y: number;
    spec: AnnunciatorWindowSpec | null;
  }

  const cells = $derived.by((): Cell[] => {
    if (!grid) return [];
    const out: Cell[] = [];
    for (let i = 0; i < grid.cols * grid.rows; i += 1) {
      out.push({
        x: grid.x + (i % grid.cols) * grid.cell_w,
        y: grid.y + Math.floor(i / grid.cols) * grid.cell_h,
        spec: specs[i] ?? null,
      });
    }
    return out;
  });
</script>

{#if grid}
  {#each cells as cell, i (i)}
    {#if cell.spec}
      {@const w = annunciator.windows[cell.spec.id]}
      {#if w}
        <g class={groupClasses(w, annunciator.lampTest)} data-alarm={cell.spec.id}>
          <rect x={cell.x + 2} y={cell.y + 2} width={grid.cell_w - 4}
                height={grid.cell_h - 4} rx="1"
                class={windowClasses(w, annunciator.lampTest)} />
          <!-- Two-line engraved legend, exactly as the protection table
               declares it. -->
          {#each cell.spec.legend as line, n (n)}
            <text x={cell.x + grid.cell_w / 2}
                  y={cell.y + grid.cell_h / 2 + (cell.spec.legend.length > 1 ? -3 : 3) + n * 9}
                  class="ann-legend">{line}</text>
          {/each}
          <text x={cell.x + grid.cell_w - 5} y={cell.y + 9} class="ann-fo-tag">
            {w.firstOut ? '1ST' : ''}
          </text>
        </g>
      {/if}
    {:else}
      <g class="ann-window-group" data-alarm="">
        <rect x={cell.x + 2} y={cell.y + 2} width={grid.cell_w - 4}
              height={grid.cell_h - 4} rx="1" class="ann-window spare" />
      </g>
    {/if}
  {/each}
{/if}
