<script lang="ts">
  /**
   * Root layout: board region, instructor drawer slot, status bar. M0 renders
   * the scaffold with a typed-hello readout in place of the board; the mimic,
   * manifest widgets and drawers land in M2.
   */
  import { store } from './lib/frame.svelte';

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

  let fps = $state('—');
  $effect(() => {
    const id = setInterval(() => {
      fps = `${store.framesReceived} FPS`;
      store.framesReceived = 0;
    }, 1000);
    return () => clearInterval(id);
  });
</script>

{#if store.fatal}
  <div id="fatal">{store.fatal}</div>
{:else}
  <div id="board-wrap">
    <svg id="board" viewBox="0 0 1600 900" preserveAspectRatio="xMidYMid meet"
         role="img" aria-label="Steam plant control board">
      <rect class="board-field" x="0" y="0" width="1600" height="900" />
      <!-- M0 scaffold readout: replaced by the board in M2. Proves the typed
           hello arrived in a component through the dev proxy (§13 P1). -->
      <text class="m0-note" x="800" y="430">HOTWELL PANEL — SVELTE CLIENT SCAFFOLD (M0)</text>
      {#if store.hello}
        <text class="m0-note" x="800" y="460">
          HOTWELL {store.hello.hotwell_version}
          | PROTOCOL {store.hello.protocol_version}
          | {store.hello.obs_spec.length} INSTRUMENTS
          | {store.hello.annunciator.length} WINDOWS
          | SCENARIO {store.hello.scenario?.name ?? 'NONE'}
        </text>
      {:else}
        <text class="m0-note" x="800" y="460">AWAITING HELLO…</text>
      {/if}
    </svg>
  </div>
{/if}

<div id="status-bar">
  <span id="conn" class={connClass}>{store.connStatus.toUpperCase()}</span>
  <span id="scenario-name">{store.hello?.scenario?.name ?? 'NO SCENARIO'}</span>
  <span id="sim-clock">{clock}</span>
  <span id="sim-state">{stateText}</span>
  <span id="fidelity" title="plant fidelity configuration">{fidelityText}</span>
  <span id="fps" title="frames received per second">{fps}</span>
</div>
