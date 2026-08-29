<script lang="ts">
  /**
   * Sequence-of-events log (§8.2) and the FIRST OUT plate. Line-printer
   * styling on phosphor green — one of only two "terminal" surfaces on the
   * page (§10). Every line is a server-rendered `event.text`.
   *
   * The FIRST OUT plate exists because the canonical casualty's initiator is
   * `CP1_TRIP:overload`, a free-form label with no protection-table id and
   * therefore no annunciator window (§7).
   */
  import { fmtT, soe } from '../lib/events.svelte';
  import type { SoeFilter } from '../lib/events.svelte';
  import { store } from '../lib/frame.svelte';

  const VISIBLE = 15;
  const LINE_H = 11;
  const FILTERS: [string, SoeFilter][] = [
    ['ALL', 'all'], ['ALARMS', 'alarms'], ['ACTIONS', 'actions'],
  ];

  const region = $derived(store.hello?.manifest.regions['soe'] ?? null);
  const rows = $derived(soe.visible().slice(-VISIBLE));

  /** Export the whole log (not just the visible window) as a text file. */
  function exportText(): void {
    const scenario = store.hello?.scenario ? store.hello.scenario.name : 'session';
    const body = soe.lines.map((l) => `${fmtT(l.t)}  ${l.text}`).join('\n');
    const blob = new Blob([`SEQUENCE OF EVENTS — ${scenario}\n\n${body}\n`],
                          { type: 'text/plain' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `${scenario}_soe.txt`;
    a.click();
    URL.revokeObjectURL(a.href);
  }
</script>

{#if region}
  <g class="soe">
    <rect x={region.x} y={region.y} width={region.w} height={region.h} rx="3"
          class="crt-bezel" />
    <text x={region.x + 10} y={region.y + 15} class="crt-text dim">SEQUENCE OF EVENTS</text>

    <!-- Filter toggles and export, in the header strip. -->
    {#each FILTERS as [label, key], i (key)}
      {@const bx = region.x + region.w - 250 + i * 60}
      <g class={`soe-filter${soe.filter === key ? ' active' : ''}`}
         data-filter={key} role="button" tabindex="0" aria-label={`filter ${label}`}
         onclick={() => { soe.filter = key; }}
         onkeydown={(ev) => {
           if (ev.key === 'Enter' || ev.key === ' ') { soe.filter = key; ev.preventDefault(); }
         }}>
        <rect x={bx} y={region.y + 5} width="54" height="14" rx="2"
              class="soe-filter-face" />
        <text x={bx + 27} y={region.y + 15} class="soe-filter-text">{label}</text>
      </g>
    {/each}
    <g class="soe-filter" data-filter="export" role="button" tabindex="0"
       aria-label="export log" onclick={exportText}
       onkeydown={(ev) => {
         if (ev.key === 'Enter' || ev.key === ' ') { exportText(); ev.preventDefault(); }
       }}>
      <rect x={region.x + region.w - 66} y={region.y + 5} width="56" height="14"
            rx="2" class="soe-filter-face" />
      <text x={region.x + region.w - 38} y={region.y + 15}
            class="soe-filter-text">EXPORT</text>
    </g>

    <g class="soe-lines">
      {#each rows as l, i (i)}
        <text x={region.x + 10} y={region.y + 30 + i * LINE_H}
              class={`crt-text${l.trip ? ' trip' : ''}`}>{`${fmtT(l.t)}  ${l.text}`}</text>
      {/each}
    </g>

    <!-- FIRST OUT plate, immediately above the log. -->
    <g class={`first-out-plate${soe.firstOut ? ' active' : ''}`}>
      <rect x={region.x} y={region.y - 26} width={region.w} height="22" rx="2"
            class="fo-plate" />
      <text x={region.x + 10} y={region.y - 11} class="fo-label">FIRST OUT</text>
      <text x={region.x + 90} y={region.y - 11} class="fo-value">
        {soe.firstOut ? `${fmtT(soe.firstOut.t)}  ${soe.firstOut.id}` : '— NONE —'}
      </text>
    </g>
  </g>
{/if}
