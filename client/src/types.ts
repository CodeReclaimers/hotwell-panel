/**
 * Hand-mirrored WebSocket message schemas from `src/hotwell_panel/protocol.py`
 * (PLAN-panel.md §4). One JSON text message per envelope, always carrying a
 * `type` field; values on the wire are SI, exactly as `hotwell` produces them.
 *
 * This file is the client's half of the protocol contract: when `protocol.py`
 * changes shape, this file changes with it, and `PROTOCOL_VERSION` gates the
 * pairing — the client refuses to run on a mismatch (§4). Open-ended dicts the
 * server forwards verbatim (status, fidelity, options, detail) keep index
 * signatures rather than pretending to a precision the contract does not have.
 */

export const PROTOCOL_VERSION = 1;

/**
 * §4: the client refuses to run on a `protocol_version` mismatch. Returns the
 * refusal text, or null when the versions agree.
 */
export function protocolMismatch(serverVersion: number): string | null {
  if (serverVersion === PROTOCOL_VERSION) return null;
  return (
    `PROTOCOL VERSION MISMATCH — server speaks v${serverVersion}, ` +
    `this client speaks v${PROTOCOL_VERSION}. Refusing to run; ` +
    `rebuild the client against the installed hotwell-panel.`
  );
}

// ------------------------------------------------------------ shared shapes

/** One §5.1 display descriptor: display = si * scale + offset. */
export interface DisplayDescriptor {
  unit: string;
  scale: number;
  offset: number;
  lo: number;
  hi: number;
  decimals: number;
  label: string;
  /** Derived signals read another frame key (e.g. percent-of-rated amps). */
  source?: string;
}

/** One protection-table condition, shipped as an annunciator window spec. */
export interface AnnunciatorWindowSpec {
  id: string;
  legend: string[];
  signal: string;
  op: string;
  setpoint: number;
  reseat: number | null;
  delay: number;
  latching: boolean;
  actions: string[];
  is_trip: boolean;
  target: string;
}

export interface ScenarioInfo {
  ref: string;
  name: string;
  seed: number;
  load_mw: number;
  mode: string;
  max_t: number;
}

export interface ScenarioListing {
  ref: string;
  name: string;
  source: string;
  self_playing?: boolean;
  [key: string]: unknown;
}

export interface Fidelity {
  drum_model: string;
  three_element: boolean;
  [key: string]: unknown;
}

/** SimSession.status() — mirrored fields the panel reads, rest open. */
export interface SimStatus {
  state: string;
  speed: number;
  scenario_ref: string;
  scenario_name: string;
  seed: number | null;
  tick: number;
  t: number;
  dt: number;
  max_t: number;
  missed_deadlines: number;
  [key: string]: unknown;
}

// ----------------------------------------------------------- manifest (§6.1)

/** Manifest element options; known keys per widget kind, open beyond them. */
export interface ElementOptions {
  pump?: string;
  start_action?: string;
  stop_action?: string;
  running_indication?: string;
  tripped_indication?: string;
  indication?: string;
  color?: string;
  controllable?: boolean;
  action?: string;
  covered?: boolean;
  local?: string;
  loop?: string;
  mode_action?: string;
  manual_action?: string;
  slew?: number;
  output_instrument?: string;
  element_mode_lamp?: boolean;
  raise_action?: string;
  step_mw?: number;
  pens?: string[];
  span_min?: number;
  [key: string]: unknown;
}

export interface ManifestElement {
  id: string;
  kind: string;
  x: number;
  y: number;
  w: number;
  h: number;
  size: number;
  instrument: string;
  label: string;
  options: ElementOptions;
}

export interface Region {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface GroupBox extends Region {
  title: string;
}

export interface AnnunciatorGrid {
  x: number;
  y: number;
  cols: number;
  rows: number;
  cell_w: number;
  cell_h: number;
}

export interface Manifest {
  version: number;
  canvas: { w: number; h: number };
  regions: Record<string, Region>;
  groups: GroupBox[];
  annunciator: AnnunciatorGrid | null;
  unplaced: Record<string, string>;
  elements: ManifestElement[];
}

// ------------------------------------------------------- server -> client

export interface HelloMsg {
  type: 'hello';
  protocol_version: number;
  hotwell_version: string;
  scenario: ScenarioInfo | null;
  fidelity: Fidelity;
  status: SimStatus;
  obs_spec: { name: string; [key: string]: unknown }[];
  obs_spec_digest: string;
  action_schema: Record<string, unknown>[];
  display_units: Record<string, DisplayDescriptor>;
  annunciator: AnnunciatorWindowSpec[];
  scenarios: ScenarioListing[];
  gauge_faces: Record<string, string>;
  manifest: Manifest;
}

export type AlarmState = 'active' | 'acknowledged';

/** Per-loop controller state in `frame.loops` (server-enriched; see HANDOFF). */
export interface LoopState {
  mode?: 'auto' | 'manual';
  sp?: number;
  output?: number;
  manual_cmd?: number;
  lo?: number;
  hi?: number;
  load_ref_mw?: number;
}

export interface LoopsBlock {
  three_element?: boolean;
  loads_mw?: Record<string, number>;
  governor?: LoopState;
  [loop: string]: LoopState | boolean | Record<string, number> | undefined;
}

export interface FrameMsg {
  type: 'frame';
  tick: number;
  t: number;
  values: Record<string, number>;
  indications: Record<string, boolean>;
  alarms: Record<string, AlarmState>;
  status: SimStatus;
  audit: Record<string, number>;
  loops: LoopsBlock;
}

export interface EventMsg {
  type: 'event';
  tick: number;
  t: number;
  kind: string;
  id: string;
  state: string;
  text: string;
  first_out: boolean;
  is_trip: boolean;
  detail: Record<string, unknown>;
}

export interface ActionResultMsg {
  type: 'action_result';
  tick: number;
  t: number;
  command: Record<string, unknown>;
  accepted: boolean;
  reason: string;
  source: string;
}

export interface ChartDataMsg {
  type: 'chart_data';
  request_id: string;
  t: number[];
  series: Record<string, (number | null)[]>;
  unknown: string[];
}

export interface SessionExportedMsg {
  type: 'session_exported';
  path: string;
  hash: string;
}

export interface ErrorMsg {
  type: 'error';
  reason: string;
}

export interface InfoMsg {
  type: 'info';
  text: string;
}

export type ServerMsg =
  | HelloMsg
  | FrameMsg
  | EventMsg
  | ActionResultMsg
  | ChartDataMsg
  | SessionExportedMsg
  | ErrorMsg
  | InfoMsg;

// ------------------------------------------------------- client -> server

/** One operator command, exactly the hotwell.actions schema (§4). */
export type ActionCommand = Record<string, unknown>;

export type InstructorCommand =
  | 'load_scenario'
  | 'run'
  | 'pause'
  | 'speed'
  | 'reset'
  | 'inject_event'
  | 'export_session';
