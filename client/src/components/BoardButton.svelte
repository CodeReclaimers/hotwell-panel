<script lang="ts">
  /**
   * A board pushbutton (manifest kind `button`). Covered guards (the manual
   * trips, §11) need the cover lifted before the button will act — a real
   * board does not let you brush an MFT pushbutton by accident; the guard
   * re-latches after 4 s so it is armed for one press only. LAMP TEST is a
   * held button (§7), wired through the `local` handler pair.
   */
  import type { Connection } from '../lib/ws';
  import type { ManifestElement } from '../types';
  import Plate from './Plate.svelte';

  export type LocalHandlers = Record<string, (() => void) | undefined>;

  let { element, conn, handlers }: {
    element: ManifestElement; conn: Connection; handlers: LocalHandlers;
  } = $props();

  const o = $derived(element.options);
  // Deliberate initial capture: the guard's arming state machine is seeded
  // from the manifest, and the component remounts per hello.
  // svelte-ignore state_referenced_locally
  const covered = Boolean(element.options.covered);
  let uncovered = $state(!covered);

  const faceClass = $derived(
    covered ? (uncovered ? 'push-face armed' : 'push-face guarded') : 'push-face');
  const caption = $derived(covered && !uncovered ? 'LIFT COVER' : 'PRESS');

  function onClick(): void {
    if (covered && !uncovered) {
      uncovered = true;
      // Re-latch the guard shortly after, so it is armed for one press only.
      setTimeout(() => {
        if (!uncovered) return;
        uncovered = false;
      }, 4000);
      return;
    }
    if (o.local && handlers[o.local]) {
      handlers[o.local]!();
    } else if (o.action) {
      conn.action({ [o.action]: true });
    }
    if (covered) uncovered = false;
  }

  // LAMP TEST is held, not clicked (§7).
  const isLampTest = $derived(o.local === 'lamp_test');
</script>

<g class={`push-button board-button${covered ? ' covered' : ''}`}
   data-element={element.id}>
  <rect x={element.x} y={element.y} width={element.w} height={element.h} rx="3"
        class="button-body" />
  <Plate x={element.x + 4} y={element.y + 4} w={element.w - 8} h={14}
         text={element.label || element.id} />
  <rect x={element.x + 10} y={element.y + 24} width={element.w - 20}
        height={element.h - 34} rx="3" class={faceClass}
        role="button" tabindex="0" aria-label={element.label || element.id}
        onclick={onClick}
        onkeydown={(ev) => {
          if (ev.key === 'Enter' || ev.key === ' ') { onClick(); ev.preventDefault(); }
        }}
        onmousedown={isLampTest ? () => handlers.lamp_test_on?.() : undefined}
        onmouseup={isLampTest ? () => handlers.lamp_test_off?.() : undefined}
        onmouseleave={isLampTest ? () => handlers.lamp_test_off?.() : undefined} />
  <text x={element.x + element.w / 2} y={element.y + element.h - 14}
        class="push-text">{caption}</text>
</g>
