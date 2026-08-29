<script module lang="ts">
  // Drawer visibility survives the per-hello remount (the vanilla client kept
  // it as a class on a persistent div; LOAD/RESET must not slam the drawer).
  let open = $state(false);
</script>

<script lang="ts">
  /**
   * Instructor station (§9): a collapsible bottom drawer. Deliberately plain
   * HTML with modern flat styling, not SVG benchboard — it is out-of-fiction,
   * and looking like part of the 1970s board would be a lie about what the
   * player is touching (§9, §10).
   *
   * The casualty-insertion forms are generated from the injectable event types
   * the protocol advertises, and the instrument picker from the observation
   * spec, so a core release that adds an instrument shows up here without an
   * edit.
   */
  import * as audio from '../lib/audio';
  import { store } from '../lib/frame.svelte';
  import type { Connection } from '../lib/ws';

  let { conn }: { conn: Connection } = $props();

  const PUMPS = ['cp1', 'cp2', 'fp1', 'fp2'];
  const SPEEDS = [1, 2, 5];

  const hello = store.hello!; // mounted under {#key store.hello} with hello set

  // Form state, initialised from the current hello (remount refreshes it).
  let scenRef = $state(hello.scenario ? hello.status.scenario_ref : '');
  let drum = $state(hello.fidelity.drum_model ?? 'astrom_bell');
  let elem = $state(hello.fidelity.three_element ? '3' : '1');
  let speed = $state('1');
  let tripPump = $state('cp1');
  let inhibitPump = $state('cp2');
  let faultInstr = $state('drum_level');
  let faultKind = $state('bias');
  let faultBias = $state(-0.1);
  let loadTarget = $state('nonvital');
  let loadDelta = $state(6.0);
  let airFrac = $state(0.02);
  let muted = $state(audio.isMuted());

  const auditText = $derived.by(() => {
    const a = store.frame?.audit;
    if (!a) return '—';
    return `mass drift ${(a.mass_drift_frac * 100).toFixed(6)} % | `
      + `energy residual ${(a.energy_residual_frac * 100).toFixed(4)} % | `
      + `relief ${a.relief_kg.toFixed(1)} kg`;
  });
  const seedText = $derived.by(() => {
    const f = store.frame;
    if (!f) return '—';
    const loads = f.loops.loads_mw ?? {};
    return `seed ${f.status.seed} | tick ${f.status.tick} | ${f.status.state}`
      + ` | missed deadlines ${f.status.missed_deadlines}`
      + ` | loads V ${(loads['vital'] ?? 0).toFixed(1)} / NV `
      + `${(loads['nonvital'] ?? 0).toFixed(1)} MW`;
  });
  const exportText = $derived(store.sessionExported
    ? `wrote ${store.sessionExported.path} — hash ${store.sessionExported.hash.slice(0, 16)}…`
    : '');

  function toggleMute(): void {
    audio.setMuted(!audio.isMuted());
    muted = audio.isMuted();
  }
</script>

<div id="instructor" class:open>
  <button class="ins-toggle" onclick={() => { open = !open; }}>INSTRUCTOR STATION</button>
  <div class="ins-body">
    <div class="ins-group">
      <h3>SCENARIO</h3>
      <label class="ins-field"><span>scenario</span>
        <select id="ins-scenario" bind:value={scenRef}>
          {#each hello.scenarios as s (s.ref)}
            <option value={s.ref}>
              {`${s.name} (${s.source}${s.self_playing ? ', self-playing' : ''})`}
            </option>
          {/each}
        </select>
      </label>
      <label class="ins-field"><span>drum model</span>
        <select id="ins-drum" bind:value={drum}>
          <option value="astrom_bell">Åström–Bell (default)</option>
          <option value="two_state">two-state</option>
        </select>
      </label>
      <label class="ins-field"><span>level control</span>
        <select id="ins-element" bind:value={elem}>
          <option value="3">three-element (default)</option>
          <option value="1">single-element (degraded)</option>
        </select>
      </label>
      <div class="ins-note">fidelity applies on the next LOAD — it constructs the simulator</div>
      <div class="ins-row">
        <button id="ins-load" onclick={() => conn.instructor('load_scenario', {
          ref: scenRef,
          fidelity: { drum_model: drum, three_element: elem === '3' },
        })}>LOAD</button>
        <button id="ins-reset" onclick={() => conn.instructor('reset')}>RESET</button>
      </div>
    </div>

    <div class="ins-group">
      <h3>TIME</h3>
      <div class="ins-row">
        <button id="ins-run" class="primary" onclick={() => conn.instructor('run')}>RUN</button>
        <button id="ins-freeze" onclick={() => conn.instructor('pause')}>FREEZE</button>
      </div>
      <label class="ins-field"><span>speed</span>
        <select id="ins-speed" bind:value={speed}
                onchange={() => conn.instructor('speed', { speed: Number(speed) })}>
          {#each SPEEDS as s (s)}<option value={String(s)}>{s}x</option>{/each}
        </select>
      </label>
      <div class="ins-note">speed multiplies steps per wall tick; dt is always 0.05 s</div>
    </div>

    <div class="ins-group wide">
      <h3>CASUALTY INSERTION</h3>
      <div class="ins-row">
        <select id="ins-trip-pump" bind:value={tripPump}>
          {#each PUMPS as p (p)}<option value={p}>{p.toUpperCase()}</option>{/each}
        </select>
        <button id="ins-trip-btn" class="danger" onclick={() => conn.instructor('inject_event',
          { event: 'trip_pump', params: { target: tripPump, reason: 'instructor' } })}>
          TRIP PUMP</button>
      </div>
      <div class="ins-row">
        <select id="ins-inhibit-pump" bind:value={inhibitPump}>
          {#each PUMPS as p (p)}<option value={p}>{p.toUpperCase()}</option>{/each}
        </select>
        <button id="ins-inhibit-btn" onclick={() => conn.instructor('inject_event',
          { event: 'inhibit_start', params: { target: inhibitPump } })}>INHIBIT START</button>
      </div>
      <div class="ins-row">
        <select id="ins-fault-instr" bind:value={faultInstr}>
          {#each hello.obs_spec as s (s.name)}<option value={s.name}>{s.name}</option>{/each}
        </select>
        <select id="ins-fault-kind" bind:value={faultKind}>
          <option value="bias">bias</option>
          <option value="stuck">stuck</option>
        </select>
        <input id="ins-fault-bias" type="number" step="0.01" bind:value={faultBias} />
        <button id="ins-fault-btn" onclick={() => conn.instructor('inject_event',
          { event: 'sensor_fault', params: { target: faultInstr, kind: faultKind,
                                             bias: Number(faultBias) } })}>SENSOR FAULT</button>
      </div>
      <div class="ins-row">
        <select id="ins-load-target" bind:value={loadTarget}>
          <option value="nonvital">NON-VITAL</option>
          <option value="vital">VITAL</option>
        </select>
        <input id="ins-load-delta" type="number" step="0.5" bind:value={loadDelta} />
        <!-- §9 asks for a MW delta; hotwell's set_load takes absolute watts.
             The server converts (SimSession._resolve_set_load) so the units
             live in one tested place. -->
        <button id="ins-load-btn" onclick={() => conn.instructor('inject_event',
          { event: 'set_load', params: { target: loadTarget,
                                         delta_mw: Number(loadDelta) } })}>LOAD STEP MW</button>
      </div>
      <div class="ins-row">
        <input id="ins-air" type="number" step="0.01" bind:value={airFrac} />
        <button id="ins-air-btn" onclick={() => conn.instructor('inject_event',
          { event: 'set_air_ingress', params: { value: Number(airFrac) } })}>AIR INGRESS</button>
      </div>
    </div>

    <div class="ins-group">
      <h3>DIAGNOSTICS</h3>
      <div class="ins-readout" id="ins-audit">{auditText}</div>
      <div class="ins-readout" id="ins-seed">{seedText}</div>
      <div class="ins-row">
        <button id="ins-mute" class:active={muted} onclick={toggleMute}>
          {muted ? 'HORN MUTED' : 'MUTE HORN'}</button>
        <button id="ins-export-btn" onclick={() => conn.instructor('export_session')}>
          EXPORT SESSION</button>
      </div>
      <div class="ins-note" id="ins-export">{exportText}</div>
    </div>
  </div>
</div>
