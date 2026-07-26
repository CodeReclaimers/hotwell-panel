/**
 * @file WebSocket transport. Connects, dispatches by message type, reconnects.
 *
 * Deliberately thin: it knows the envelope shape and nothing about the plant.
 */

/**
 * @typedef {Object} Handlers
 * @property {function(Object):void} [hello]
 * @property {function(Object):void} [frame]
 * @property {function(Object):void} [event]
 * @property {function(Object):void} [action_result]
 * @property {function(Object):void} [chart_data]
 * @property {function(Object):void} [session_exported]
 * @property {function(Object):void} [error]
 * @property {function(string):void} [status]
 */

export class Connection {
  /** @param {Handlers} handlers */
  constructor(handlers) {
    this.handlers = handlers;
    this.ws = null;
    this.retry = 0;
  }

  connect() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    this.ws = new WebSocket(`${proto}://${location.host}/ws`);
    this.ws.onopen = () => {
      this.retry = 0;
      this.handlers.status?.('connected');
    };
    this.ws.onclose = () => {
      this.handlers.status?.('disconnected');
      // Localhost tool: a close almost always means the server restarted.
      this.retry = Math.min(this.retry + 1, 10);
      setTimeout(() => this.connect(), 250 * this.retry);
    };
    this.ws.onerror = () => this.handlers.status?.('failed');
    this.ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      const fn = this.handlers[msg.type];
      if (fn) fn(msg);
      else console.warn('unhandled message type', msg.type, msg);
    };
  }

  /** @param {Object} msg */
  send(msg) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
    }
  }

  /** Submit one operator action, exactly the hotwell.actions schema. */
  action(command) { this.send({ type: 'action', command }); }

  /** Instructor-station command (§9). */
  instructor(command, params = {}) {
    this.send({ type: 'instructor', command, params });
  }

  /** Historian query for the strip charts (§8.1). */
  chartQuery(requestId, signals, t0, t1, maxPoints = 900) {
    this.send({
      type: 'chart_query', request_id: requestId, signals,
      t0, t1, max_points: maxPoints,
    });
  }
}
