<script lang="ts">
  /**
   * A controller-station pushbutton with held-repeat: pressing and holding
   * RAISE walks the command, as a real pushbutton station does (§6.3).
   */
  let { x, y, w, h, text, cls, lit = false, onpress }: {
    x: number; y: number; w: number; h: number; text: string; cls: string;
    lit?: boolean; onpress: () => void;
  } = $props();

  const REPEAT_MS = 120; // held-repeat interval, one step per tick-ish

  let pressed = $state(false);
  let timer: ReturnType<typeof setInterval> | null = null;

  function start(ev: MouseEvent): void {
    ev.preventDefault();
    onpress();
    timer = setInterval(onpress, REPEAT_MS);
    pressed = true;
  }

  function stop(): void {
    if (timer) clearInterval(timer);
    timer = null;
    pressed = false;
  }

  $effect(() => () => { if (timer) clearInterval(timer); });
</script>

<g class={`push-button ${cls}${pressed ? ' pressed' : ''}`.trim()}
   role="button" tabindex="0" aria-label={text}
   onmousedown={start} onmouseup={stop} onmouseleave={stop}>
  <rect {x} {y} width={w} height={h} rx="2" class={`push-face${lit ? ' lit' : ''}`} />
  <text x={x + w / 2} y={y + h / 2 + 3} class="push-text">{text}</text>
</g>
