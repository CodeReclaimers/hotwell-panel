<script lang="ts">
  /**
   * Strip-chart recorder styled as a paper recorder (§8.1). Three pens,
   * assignable to any instrument from a margin dropdown (a real <select> in a
   * <foreignObject>, so the whole instrument list is one click away). On load
   * and on reassignment the trace backfills from the historian via
   * `chart_query`; after that, frames append live.
   *
   * Time runs left to right with "now" at the right edge — a paper recorder
   * feeds vertically, but at this size the horizontal axis gives ten times
   * the time resolution, and reading a trend is the point. The 30-minute span
   * is genuinely coarser at its left end (historian retention tiers); that is
   * the data, not a rendering artefact.
   *
   * Pen sample arrays are deliberately NOT reactive state — they are mutated
   * at 20 Hz and can hold thousands of points; only the rendered outputs
   * (path d strings, select values, axis labels) are `$state`.
   */
  import { subscribeChartData } from '../lib/chartdata';
  import { store } from '../lib/frame.svelte';
  import { registerChart } from '../lib/registry';
  import type { Connection } from '../lib/ws';
  import type { ChartDataMsg, ManifestElement } from '../types';
  import Plate from './Plate.svelte';

  let { element, conn }: { element: ManifestElement; conn: Connection } = $props();

  const SPANS = [2, 10, 30]; // minutes
  const PEN_CLASSES = ['chart-pen-1', 'chart-pen-2', 'chart-pen-3'];
  const MAX_POINTS = 900;

  const margin = { l: 46, r: 10, t: 20, b: 16 };
  const plotX = $derived(element.x + margin.l);
  const plotY = $derived(element.y + margin.t);
  const plotW = $derived(element.w - margin.l - margin.r);
  const plotH = $derived(element.h - margin.t - margin.b);

  interface PenData { name: string; t: number[]; v: (number | null)[] }
  // Initial-value captures are deliberate: pen sample arrays and the span are
  // stateful containers seeded from the manifest; the component remounts per
  // hello, so the props never change under a live instance.
  // svelte-ignore state_referenced_locally
  const pens: PenData[] = (element.options.pens ?? []).slice(0, 3)
    .map((name) => ({ name, t: [], v: [] }));

  let penNames = $state<string[]>(pens.map((p) => p.name));
  let penDs = $state<string[]>(pens.map(() => ''));
  let axisSpan = $state<[number, number] | null>(null);
  // svelte-ignore state_referenced_locally
  let span = $state(((element.options.span_min as number | undefined) ?? 10) * 60);
  const requests = new Map<string, string[]>();
  let backfilled = false;

  const names = $derived(Object.keys(store.units).sort());
  const scaleLabels = $derived(penNames.map((name, i) => {
    const d = store.units[name];
    return d ? { cls: PEN_CLASSES[i], text: `${d.lo}–${d.hi} ${d.unit}` } : null;
  }));

  /** Request history for every pen (window anchored on current sim time). */
  function backfill(): void {
    if (!store.frame) return;
    const now = store.frame.t;
    const signals = pens.map((p) => store.units[p.name]?.source || p.name);
    const id = `${element.id}:${Math.round(now * 20)}`;
    requests.set(id, signals);
    conn.chartQuery(id, signals, Math.max(0, now - span), now + 1, MAX_POINTS);
  }

  /** Reassign one pen and refetch its history rather than starting blank. */
  function assignPen(index: number, name: string): void {
    pens[index].name = name;
    pens[index].t = [];
    pens[index].v = [];
    penNames[index] = name;
    backfill();
  }

  function onChartData(m: ChartDataMsg): void {
    const signals = requests.get(m.request_id);
    if (!signals) return; // another recorder's response
    requests.delete(m.request_id);
    if (m.unknown.length) console.warn('historian has no signal', m.unknown);
    pens.forEach((pen, i) => {
      const series = m.series[signals[i]];
      if (!series) return;
      pen.t = m.t.slice();
      pen.v = series.slice();
    });
    draw();
  }

  function draw(): void {
    const f = store.frame;
    if (!f) return;
    const t1 = f.t;
    const t0 = t1 - span;
    pens.forEach((pen, i) => {
      const d = store.units[pen.name];
      if (!d || !pen.t.length) { penDs[i] = ''; return; }
      let out = '';
      let pending = true; // pen lifts over gaps (nulls, NaN, off-window)
      for (let k = 0; k < pen.t.length; k += 1) {
        const tv = pen.t[k];
        const raw = pen.v[k];
        if (tv < t0 || raw === null || raw === undefined || Number.isNaN(raw)) {
          pending = true;
          continue;
        }
        const disp = raw * d.scale + d.offset;
        const x = plotX + ((tv - t0) / (t1 - t0)) * plotW;
        const frac = Math.min(Math.max((disp - d.lo) / (d.hi - d.lo), 0), 1);
        const y = plotY + plotH * (1 - frac);
        out += `${pending ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)} `;
        pending = false;
      }
      penDs[i] = out;
    });
    axisSpan = [t0, t1];
  }

  // Live append per frame; the first frame triggers the initial backfill.
  $effect(() => {
    const f = store.frame;
    if (!f) return;
    if (!backfilled) {
      backfilled = true;
      backfill();
    }
    for (const pen of pens) {
      const si = store.siValue(pen.name);
      if (si === undefined) continue;
      if (pen.t.length && pen.t[pen.t.length - 1] >= f.t) continue;
      pen.t.push(f.t);
      pen.v.push(si);
      // Trim to the visible span plus a little slack.
      const cutoff = f.t - span * 1.05;
      let drop = 0;
      while (drop < pen.t.length && pen.t[drop] < cutoff) drop += 1;
      if (drop > 0) {
        pen.t.splice(0, drop);
        pen.v.splice(0, drop);
      }
    }
    draw();
  });

  $effect(() => {
    const unsubscribe = subscribeChartData(onChartData);
    const unregister = registerChart();
    return () => { unsubscribe(); unregister(); };
  });

  function fmtAxis(t: number): string {
    const m = Math.floor(Math.max(0, t) / 60);
    return `${m}:${String(Math.floor(Math.max(0, t) - m * 60)).padStart(2, '0')}`;
  }
</script>

<g class="recorder" data-element={element.id}>
  <rect x={element.x} y={element.y} width={element.w} height={element.h} rx="2"
        class="chart-paper" />
  <Plate x={element.x} y={element.y - 16} w={120} h={14}
         text={element.label || 'RECORDER'} />

  <!-- Chart grid: period recorders use a printed rule, not a screen grid. -->
  <g class="chart-grid-group">
    {#each { length: 11 } as _, i (i)}
      <line x1={plotX + (plotW * i) / 10} y1={plotY}
            x2={plotX + (plotW * i) / 10} y2={plotY + plotH}
            class={`chart-grid${i % 5 === 0 ? ' major' : ''}`} />
    {/each}
    {#each { length: 5 } as _, i (i)}
      <line x1={plotX} y1={plotY + (plotH * i) / 4}
            x2={plotX + plotW} y2={plotY + (plotH * i) / 4}
            class={`chart-grid${i % 4 === 0 ? ' major' : ''}`} />
    {/each}
  </g>

  {#each penDs as d, i (i)}
    <path class={`chart-pen ${PEN_CLASSES[i]}`} {d} />
  {/each}

  <!-- Pen legend + assignment dropdown down the left margin (§8.1). -->
  {#each pens as _, i (i)}
    <line x1={element.x + 6} y1={plotY + 11 + i * 15}
          x2={element.x + 16} y2={plotY + 11 + i * 15}
          class={`chart-pen ${PEN_CLASSES[i]}`} />
    <foreignObject x={element.x + 18} y={plotY + 4 + i * 15} width="120" height="14">
      <select class="pen-select" value={penNames[i]}
              onchange={(e) => assignPen(i, e.currentTarget.value)}>
        {#each names as n (n)}
          <option value={n}>{n}</option>
        {/each}
      </select>
    </foreignObject>
  {/each}

  <!-- Span selector along the bottom margin. -->
  {#each SPANS as mins, i (mins)}
    <g class="span-btn" data-span={String(mins)} role="button" tabindex="0"
       aria-label={`${mins} minute span`}
       onclick={() => { span = mins * 60; backfill(); }}
       onkeydown={(ev) => {
         if (ev.key === 'Enter' || ev.key === ' ') {
           span = mins * 60;
           backfill();
           ev.preventDefault();
         }
       }}>
      <rect x={element.x + element.w - 100 + i * 32} y={element.y + element.h - 14}
            width="28" height="12" rx="2" class="span-face" />
      <text x={element.x + element.w - 100 + i * 32 + 14} y={element.y + element.h - 5}
            class="span-text">{mins}M</text>
    </g>
  {/each}

  <g class="chart-axis">
    {#if axisSpan}
      {#each { length: 3 } as _, i (i)}
        <text x={plotX + (plotW * i) / 2} y={plotY + plotH + 11}
              class="chart-axis-text">
          {fmtAxis(axisSpan[0] + ((axisSpan[1] - axisSpan[0]) * i) / 2)}
        </text>
      {/each}
    {/if}
    <!-- Each pen's scale endpoints, in its own display units. -->
    {#each scaleLabels as s, i (i)}
      {#if s}
        <text x={element.x + element.w - 6} y={plotY + 10 + i * 10}
              class={`chart-scale ${s.cls}`}>{s.text}</text>
      {/if}
    {/each}
  </g>
</g>
