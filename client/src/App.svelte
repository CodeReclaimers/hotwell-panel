<script lang="ts">
  /**
   * Root layout (§6): annunciator strip, mimic board with manifest-placed
   * widgets, right pane (recorders / SOE / advisor bezel), instructor drawer,
   * status bar. The whole board is one SVG in a 1600×900 design space; the
   * manifest places everything inside it, and scaling is handled by viewBox so
   * the layout degrades gracefully to 1280 without reflowing.
   *
   * Everything under {#key store.hello} rebuilds when a new hello arrives
   * (LOAD / RESET send one) — the same render-from-scratch semantics the
   * vanilla client had.
   */
  import AdvisorBezel from './components/AdvisorBezel.svelte';
  import Annunciator from './components/Annunciator.svelte';
  import BoardButton from './components/BoardButton.svelte';
  import type { LocalHandlers } from './components/BoardButton.svelte';
  import Breaker from './components/Breaker.svelte';
  import ChartRecorder from './components/ChartRecorder.svelte';
  import Gauge from './components/Gauge.svelte';
  import Instructor from './components/Instructor.svelte';
  import Lamp from './components/Lamp.svelte';
  import MAStation from './components/MAStation.svelte';
  import Mimic from './components/Mimic.svelte';
  import PistolGrip from './components/PistolGrip.svelte';
  import Plate from './components/Plate.svelte';
  import SoeLog from './components/SoeLog.svelte';
  import { store } from './lib/frame.svelte';
  import { needles } from './lib/smoothing.svelte';
  import type { Connection } from './lib/ws';

  let { conn, handlers }: { conn: Connection; handlers: LocalHandlers } = $props();

  /** T + MMM:SS.s, the way a plant clock reads. */
  function formatClock(t: number): string {
    const m = Math.floor(t / 60);
    const s = t - m * 60;
    return `T + ${String(m).padStart(3, '0')}:${s.toFixed(1).padStart(4, '0')}`;
  }

  const clock = $derived(formatClock(store.frame?.t ?? 0));
  const stateText = $derived.by(() => {
    const st = store.frame?.status;
    if (!st) return '—';
    return `${st.state.toUpperCase()}${st.speed > 1 ? ` ${st.speed}X` : ''}`;
  });
  const fidelityText = $derived.by(() => {
    const f = store.hello?.fidelity;
    if (!f) return '—';
    return `${(f.drum_model || '?').toUpperCase()} / ${f.three_element ? '3E' : '1E'}`;
  });
  // The vanilla client showed CONNECTING with the amber 'disconnected' style;
  // keep the class set {connected, disconnected, failed} the CSS knows.
  const connClass = $derived(
    store.connStatus === 'connecting' ? 'disconnected' : store.connStatus);
  const manifest = $derived(store.hello?.manifest ?? null);

  let fps = $state('—');
  $effect(() => {
    const id = setInterval(() => {
      fps = `${store.framesReceived} FPS`;
      store.framesReceived = 0;
    }, 1000);
    return () => clearInterval(id);
  });

  // The wall-clock animation loop for needle smoothing (§6.2, §3.2).
  $effect(() => {
    needles.start();
    return () => needles.stop();
  });

  function groupPlateW(title: string): number {
    return Math.max(96, title.length * 8);
  }
</script>

{#if store.fatal}
  <div id="fatal">{store.fatal}</div>
{:else}
  <div id="board-wrap">
    <svg id="board" viewBox="0 0 1600 900" preserveAspectRatio="xMidYMid meet"
         role="img" aria-label="Steam plant control board">
      <rect class="board-field" x="0" y="0" width="1600" height="900" />
      {#key store.hello}
        {#if store.hello && manifest}
          <g id="layer-annunciator"><Annunciator /></g>
          <g id="layer-groups">
            <!-- Group title plates and separator boxes (§10). -->
            {#each manifest.groups as g (g.title)}
              <rect x={g.x} y={g.y} width={g.w} height={g.h} rx="2" class="group-box" />
              <rect x={g.x + 8} y={g.y - 8} width={groupPlateW(g.title)} height="16"
                    rx="1" class="group-plate" />
              <text x={g.x + 8 + groupPlateW(g.title) / 2} y={g.y}
                    class="group-title">{g.title}</text>
            {/each}
          </g>
          <g id="layer-mimic"><Mimic /></g>
          <g id="layer-elements">
            {#each manifest.elements as e (e.id)}
              {#if e.kind === 'gauge'}
                <Gauge element={e} />
              {:else if e.kind === 'lamp'}
                <Lamp element={e} />
              {:else if e.kind === 'grip'}
                <PistolGrip element={e} {conn} />
              {:else if e.kind === 'breaker'}
                <Breaker element={e} {conn} />
              {:else if e.kind === 'station'}
                <MAStation element={e} {conn} />
              {:else if e.kind === 'button'}
                <BoardButton element={e} {conn} {handlers} />
              {:else if e.kind === 'chart'}
                <ChartRecorder element={e} {conn} />
              {:else}
                <!-- Footprint for a kind this client does not know. -->
                <g class={`placeholder kind-${e.kind}`} data-element={e.id}>
                  <rect x={e.x} y={e.y} width={e.w} height={e.h} rx="2" class="group-box" />
                  <Plate x={e.x} y={e.y} w={e.w} h={14} text={e.label || e.id} />
                  <text x={e.x + e.w / 2} y={e.y + e.h / 2}
                        class="device-plate-text">{e.kind.toUpperCase()}</text>
                </g>
              {/if}
            {/each}
          </g>
          <g id="layer-right"><SoeLog /><AdvisorBezel /></g>
        {/if}
      {/key}
    </svg>
  </div>
  {#key store.hello}
    {#if store.hello}
      <Instructor {conn} />
    {/if}
  {/key}
{/if}

<div id="status-bar">
  <span id="conn" class={connClass}>{store.connStatus.toUpperCase()}</span>
  <span id="scenario-name">{store.hello?.scenario?.name ?? 'NO SCENARIO'}</span>
  <span id="sim-clock">{clock}</span>
  <span id="sim-state">{stateText}</span>
  <span id="fidelity" title="plant fidelity configuration">{fidelityText}</span>
  <span id="fps" title="frames received per second">{fps}</span>
</div>
