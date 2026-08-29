<script lang="ts">
  /**
   * The hand-authored mimic one-line (§2, §6): `board.svg` inlined verbatim
   * via `{@html}`. The template is opaque data with placement slots — nodes
   * declare `data-pump` / `data-indication` / `data-flow`, and this component
   * drives their classes from frames; nothing animates by itself (§6.2).
   *
   * The imperative class toggling is deliberate: the SVG is authored outside
   * Svelte, so a single `$effect` keyed on the frame is the honest interface
   * to it — the same contract the vanilla client had.
   */
  import boardSvg from '../board.svg?raw';
  import { store } from '../lib/frame.svelte';

  let host: SVGGElement | undefined = $state();

  interface Slots {
    pumps: { node: Element; pump: string }[];
    indications: { node: Element; key: string; base: string }[];
    flows: { node: Element; signal: string }[];
  }
  let slots: Slots | null = null;

  function collect(root: SVGGElement): Slots {
    return {
      pumps: [...root.querySelectorAll('[data-pump]')].map((node) => ({
        node, pump: node.getAttribute('data-pump')!,
      })),
      indications: [...root.querySelectorAll('[data-indication]')].map((node) => ({
        node,
        key: node.getAttribute('data-indication')!,
        base: (node.getAttribute('class') ?? '').split(' ')
          .filter((c) => c !== 'on' && c !== 'closed').join(' '),
      })),
      flows: [...root.querySelectorAll('[data-flow]')].map((node) => ({
        node, signal: node.getAttribute('data-flow')!,
      })),
    };
  }

  $effect(() => {
    const f = store.frame; // reactive dependency: re-run per frame
    if (!host) return;
    slots ??= collect(host);
    if (!f) return;
    for (const p of slots.pumps) {
      const running = store.indication(`${p.pump}_running`);
      const tripped = store.indication(`${p.pump}_tripped`);
      p.node.setAttribute(
        'class', `pump${running ? ' running' : ''}${tripped ? ' tripped' : ''}`);
    }
    for (const m of slots.indications) {
      const on = store.indication(m.key);
      m.node.setAttribute('class', on
        ? `${m.base} ${m.key === 'breaker_closed' ? 'closed' : 'on'}` : m.base);
    }
    // Marching dashes only where flow is actually moving (§6.2).
    for (const fl of slots.flows) {
      const v = f.values[fl.signal];
      const flowing = v !== undefined && Math.abs(v) > 0.5; // kg/s
      fl.node.classList.toggle('flowing', flowing);
    }
  });
</script>

<g bind:this={host}>{@html boardSvg}</g>
