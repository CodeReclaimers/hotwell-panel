/**
 * WebSocket transport. Connects, dispatches by message type, reconnects.
 *
 * Deliberately thin: it knows the envelope shape and nothing about the plant.
 * `handlers` is a public, mutable object — the browser tests (and a live
 * console session) may swap an entry to intercept one message.
 */

import type {
  ActionCommand,
  ActionResultMsg,
  ChartDataMsg,
  ErrorMsg,
  EventMsg,
  FrameMsg,
  HelloMsg,
  InfoMsg,
  InstructorCommand,
  ServerMsg,
  SessionExportedMsg,
} from '../types';

export type ConnStatus = 'connected' | 'disconnected' | 'failed';

export interface Handlers {
  hello?: (m: HelloMsg) => void;
  frame?: (m: FrameMsg) => void;
  event?: (m: EventMsg) => void;
  action_result?: (m: ActionResultMsg) => void;
  chart_data?: (m: ChartDataMsg) => void;
  session_exported?: (m: SessionExportedMsg) => void;
  error?: (m: ErrorMsg) => void;
  info?: (m: InfoMsg) => void;
  status?: (s: ConnStatus) => void;
}

export class Connection {
  handlers: Handlers;
  private ws: WebSocket | null = null;
  private retry = 0;
  private stopped = false;

  constructor(handlers: Handlers) {
    this.handlers = handlers;
  }

  connect(): void {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    this.ws = new WebSocket(`${proto}://${location.host}/ws`);
    this.ws.onopen = () => {
      this.retry = 0;
      this.handlers.status?.('connected');
    };
    this.ws.onclose = () => {
      this.handlers.status?.('disconnected');
      if (this.stopped) return;
      // Localhost tool: a close almost always means the server restarted.
      this.retry = Math.min(this.retry + 1, 10);
      setTimeout(() => this.connect(), 250 * this.retry);
    };
    this.ws.onerror = () => this.handlers.status?.('failed');
    this.ws.onmessage = (ev: MessageEvent<string>) => {
      const msg = JSON.parse(ev.data) as ServerMsg;
      // Dispatch by envelope type; handlers are looked up at delivery time so
      // a swapped-in handler sees the next message.
      const fn = (this.handlers as Record<string, ((m: ServerMsg) => void) | undefined>)[msg.type];
      if (fn) fn(msg);
      else console.warn('unhandled message type', msg.type, msg);
    };
  }

  /** Stop for good: no reconnect. Used on a protocol-version refusal (§4). */
  stop(): void {
    this.stopped = true;
    this.ws?.close();
  }

  send(msg: Record<string, unknown>): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
    }
  }

  /** Submit one operator action, exactly the hotwell.actions schema. */
  action(command: ActionCommand): void {
    this.send({ type: 'action', command });
  }

  /** Instructor-station command (§9). */
  instructor(command: InstructorCommand, params: Record<string, unknown> = {}): void {
    this.send({ type: 'instructor', command, params });
  }

  /** Historian query for the strip charts (§8.1). */
  chartQuery(requestId: string, signals: string[], t0: number, t1: number,
             maxPoints = 900): void {
    this.send({
      type: 'chart_query', request_id: requestId, signals,
      t0, t1, max_points: maxPoints,
    });
  }
}
