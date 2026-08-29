/**
 * Mounted-widget counters, exposed on `window.panel` for the Playwright suite
 * (`window.panel.gauges.count()`, `window.panel.charts.count()`). Components
 * register on mount and deregister on destroy; plain numbers — nothing in the
 * UI reads them.
 */

const counters = { gauges: 0, charts: 0 };

export function registerGauge(): () => void {
  counters.gauges += 1;
  return () => { counters.gauges -= 1; };
}

export function registerChart(): () => void {
  counters.charts += 1;
  return () => { counters.charts -= 1; };
}

export const gauges = { count: (): number => counters.gauges };
export const charts = { count: (): number => counters.charts };
