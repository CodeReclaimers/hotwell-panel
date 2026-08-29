<script lang="ts">
  /**
   * Pistol-grip pump switch (§6.2): three-position, spring-return-to-centre,
   * START / NORM / STOP. Hold the grip over and release; the action fires
   * **on release**, as a real spring-return switch does. Mouse (click-and-hold
   * left/right of the pivot) or keyboard (focus, hold Left or Right arrow).
   *
   * Lamps read from `indications`, which phase 1 guarantees honest: red =
   * running, green = stopped, amber = tripped — the power plant convention,
   * not the traffic-light one (§10).
   */
  import { store } from '../lib/frame.svelte';
  import type { Connection } from '../lib/ws';
  import type { ManifestElement } from '../types';
  import Plate from './Plate.svelte';

  let { element, conn }: { element: ManifestElement; conn: Connection } = $props();

  const o = $derived(element.options);
  const THROW_DEG = 38;
  const cx = $derived(element.x + element.w / 2);
  const lampY = $derived(element.y + 9);
  const pivotY = $derived(element.y + 52);

  type Pos = 'start' | 'norm' | 'stop';
  let pos = $state<Pos>('norm');

  const throwDeg = $derived(pos === 'start' ? THROW_DEG : pos === 'stop' ? -THROW_DEG : 0);
  const lampClass = $derived.by(() => {
    if (!store.frame) return 'lamp-lens';
    const running = store.indication(o.running_indication ?? '');
    const tripped = store.indication(o.tripped_indication ?? '');
    return `lamp-lens ${tripped ? 'amber' : running ? 'red' : 'green'}`;
  });

  function release(): void {
    if (pos === 'start' && o.start_action) conn.action({ [o.start_action]: true });
    else if (pos === 'stop' && o.stop_action) conn.action({ [o.stop_action]: true });
    pos = 'norm';
  }

  function onMouseDown(ev: MouseEvent): void {
    const box = (ev.currentTarget as SVGRectElement).getBoundingClientRect();
    pos = ev.clientX < box.left + box.width / 2 ? 'stop' : 'start';
  }

  function onKeyDown(ev: KeyboardEvent): void {
    if (ev.repeat) return;
    if (ev.key === 'ArrowLeft') { pos = 'stop'; ev.preventDefault(); }
    else if (ev.key === 'ArrowRight') { pos = 'start'; ev.preventDefault(); }
  }

  function onKeyUp(ev: KeyboardEvent): void {
    if (ev.key === 'ArrowLeft' || ev.key === 'ArrowRight') {
      release();
      ev.preventDefault();
    }
  }
</script>

<g class="grip" data-element={element.id} data-pump={o.pump}>
  <Plate x={element.x} y={element.y + element.h - 14} w={element.w} h={14}
         text={element.label || ''} />
  <circle {cx} cy={lampY} r="7" class={lampClass} />

  <!-- Engraved STOP / START legend, either side of the pivot boss. -->
  <text x={element.x + 6} y={pivotY + 14} class="grip-legend">STOP</text>
  <text x={element.x + element.w - 6} y={pivotY + 14} class="grip-legend end">START</text>

  <g class="grip-handle" transform={`rotate(${throwDeg} ${cx} ${pivotY})`}>
    <circle {cx} cy={pivotY} r="8" class="grip-boss" />
    <!-- The grip itself: a stubby pistol shape pointing up from the boss. -->
    <path class="grip-lever"
          d={`M ${cx - 4} ${pivotY} L ${cx - 5} ${pivotY - 16} `
             + `Q ${cx} ${pivotY - 22} ${cx + 5} ${pivotY - 16} `
             + `L ${cx + 4} ${pivotY} Z`} />
  </g>

  <!-- A transparent hit area split left/right of the pivot. Keyboard: §6.2
       asks for both; same spring-return semantics, action on key release. -->
  <rect x={element.x} y={element.y + 26} width={element.w} height="40"
        class="grip-hit" tabindex="0" role="button"
        aria-label={`${element.label} pump control switch`}
        onmousedown={onMouseDown}
        onmouseup={release}
        onmouseleave={() => { if (pos !== 'norm') release(); }}
        onkeydown={onKeyDown}
        onkeyup={onKeyUp}
        onblur={() => { if (pos !== 'norm') release(); }} />
</g>
