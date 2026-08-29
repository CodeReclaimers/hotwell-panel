<script lang="ts">
  /** An engraved lamacoid plate with centred white text (§10). */
  let { x, y, w, h, text, cls = '' }: {
    x: number; y: number; w: number; h: number; text: string; cls?: string;
  } = $props();
</script>

<g class={`plate ${cls}`.trim()}>
  <rect {x} {y} width={w} height={h} rx="1" class="device-plate" />
  <text x={x + w / 2} y={y + h / 2} class="device-plate-text">{text}</text>
</g>
