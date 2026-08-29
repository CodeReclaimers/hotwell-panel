/**
 * Fan-out for `chart_data` messages: the Connection has one handler slot per
 * message type (kept public so tests can intercept it), and each mounted
 * ChartRecorder subscribes here to claim responses by request id.
 */

import type { ChartDataMsg } from '../types';

type Listener = (m: ChartDataMsg) => void;

const listeners = new Set<Listener>();

export function subscribeChartData(fn: Listener): () => void {
  listeners.add(fn);
  return () => { listeners.delete(fn); };
}

export function dispatchChartData(m: ChartDataMsg): void {
  for (const fn of listeners) fn(m);
}
