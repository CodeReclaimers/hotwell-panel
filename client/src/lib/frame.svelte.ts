/**
 * Client-side state: the last hello, the latest frame, and the unit conversion
 * the server shipped.
 *
 * The panel holds as little domain knowledge as possible (§1). Everything here
 * is either verbatim from the server or a mechanical application of the affine
 * display table.
 *
 * `hello` and `frame` are `$state.raw`: each arrives as a fresh object and is
 * replaced wholesale (frames at 20 Hz), so deep proxying would be pure
 * overhead. Reactivity is at the reference level — every `$derived`/`$effect`
 * that reads `store.frame` re-evaluates once per frame, which is exactly the
 * one-stream-fans-out shape §1 chose Svelte for.
 */

import type {
  AnnunciatorWindowSpec,
  DisplayDescriptor,
  FrameMsg,
  HelloMsg,
  ManifestElement,
  SessionExportedMsg,
} from '../types';

export class PanelStore {
  hello = $state.raw<HelloMsg | null>(null);
  frame = $state.raw<FrameMsg | null>(null);
  connStatus = $state<'connecting' | 'connected' | 'disconnected' | 'failed'>('connecting');
  connected = $state(false);
  /** §4 protocol refusal (or another unrecoverable fault): set once, fatal. */
  fatal = $state<string | null>(null);
  /** Last `session_exported` echo, shown on the instructor station (§9). */
  sessionExported = $state.raw<SessionExportedMsg | null>(null);
  /** Frames received since the FPS readout last sampled; plain counter. */
  framesReceived = 0;

  readonly units: Record<string, DisplayDescriptor> = $derived(
    this.hello?.display_units ?? {});

  /** alarm id -> window spec */
  readonly windows: Record<string, AnnunciatorWindowSpec> = $derived(
    Object.fromEntries((this.hello?.annunciator ?? []).map((w) => [w.id, w])));

  /** manifest id -> element */
  readonly elements: Record<string, ManifestElement> = $derived(
    Object.fromEntries(
      (this.hello?.manifest?.elements ?? []).map((e) => [e.id, e])));

  setHello(hello: HelloMsg): void {
    this.hello = hello;
  }

  setFrame(frame: FrameMsg): void {
    this.frame = frame;
    this.framesReceived += 1;
  }

  /** SI value for an instrument, following a derived signal's `source`. */
  siValue(name: string): number | undefined {
    if (!this.frame) return undefined;
    const d = this.units[name];
    const key = d?.source ? d.source : name;
    return this.frame.values[key];
  }

  /** Display value: the server's affine conversion, applied mechanically. */
  displayValue(name: string): number | undefined {
    const si = this.siValue(name);
    const d = this.units[name];
    if (si === undefined || !d) return undefined;
    return si * d.scale + d.offset;
  }

  /** Display value formatted at the instrument's resolution. */
  formatted(name: string): string {
    const v = this.displayValue(name);
    const d = this.units[name];
    if (v === undefined || !d) return '—';
    return v.toFixed(d.decimals);
  }

  indication(key: string): boolean {
    return Boolean(this.frame?.indications[key]);
  }
}

export const store = new PanelStore();
