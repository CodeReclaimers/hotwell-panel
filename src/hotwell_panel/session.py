"""SimSession: the only owner of the `hotwell` Simulator (§2).

WebSocket handlers never touch the simulator. They enqueue, and the real-time
loop drains the queue at a tick boundary — so an operator action is applied at
exactly the same point in the step sequence as a scenario `action` event, and
carries a sim tick rather than a wall-clock time. That is what makes a live
session reduce to a scenario file (§1, §3.4).

This class is deliberately synchronous: `tick()` is a plain method the asyncio
loop in `server.py` calls at 20 Hz, and the replay tests drive it directly with
no event loop at all.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from hotwell import __version__ as HOTWELL_VERSION
from hotwell.protection.tables import load_protection_table
from hotwell.scenario import ScenarioEvent, load_scenario
from hotwell.simulator import DT, Simulator

from hotwell_panel import scenarios as scenario_catalog
from hotwell_panel import sessionlog, telemetry
from hotwell_panel.events import EventSynthesizer, soe_line
from hotwell_panel.protocol import ActionResult, Event, Frame
from hotwell_panel.sessionlog import ACTION, INSTRUCTOR, OPERATOR, SCENARIO, LogRecord, SessionLog
from hotwell_panel.simconfig import (
    DEFAULT_FIDELITY,
    ENDED,
    LOADED,
    NO_SCENARIO,
    OBS_SPEC_DIGEST,
    PAUSED,
    RUNNING,
    build_config,
    tick_of,
)

__all__ = ["SimSession", "DEFAULT_FIDELITY", "OBS_SPEC_DIGEST", "build_config",
           "tick_of", "NO_SCENARIO", "LOADED", "RUNNING", "PAUSED", "ENDED"]


class SimSession:
    """Owns the simulator, the action queue, the session log, and time control."""

    def __init__(self, local_scenarios: Path | None = None,
                 sessions_dir: Path | None = None) -> None:
        self.local_scenarios = local_scenarios
        self.sessions_dir = sessions_dir or Path("sessions")
        self.table = load_protection_table()
        self.sim: Simulator | None = None
        self.state = NO_SCENARIO
        self.speed = 1
        self.fidelity = dict(DEFAULT_FIDELITY)
        self.scenario_ref = ""
        self.log: SessionLog | None = None
        self._queue: list[tuple[str, Any, str]] = []   # (kind, payload, source)
        self._synth: EventSynthesizer | None = None
        self._missed_deadlines = 0
        self._end_reason = ""   # why the scenario ended; "" while still runnable

    # ------------------------------------------------------------- lifecycle

    def load(self, ref: str, fidelity: dict[str, Any] | None = None) -> None:
        """Construct a fresh Simulator at t=0, frozen (§3.3). Reset = reload."""
        if fidelity is not None:
            self.fidelity = {**DEFAULT_FIDELITY, **fidelity}
        resource = scenario_catalog.resolve(ref, self.local_scenarios)
        sc = load_scenario(resource)
        cfg = build_config(self.fidelity)
        sim = Simulator(cfg, scenario=sc)
        sim.initialize_steady_state(sc.load_mw)
        self.sim = sim
        self.scenario_ref = ref
        self.state = LOADED
        self._queue.clear()
        self._end_reason = ""
        self._synth = EventSynthesizer(self.table)
        self._synth.prime(sim)
        self.log = SessionLog(
            scenario_ref=ref, scenario_name=sc.name, seed=sim.seed,
            load_mw=sc.load_mw, mode=sc.mode, fidelity=dict(self.fidelity),
            hotwell_version=HOTWELL_VERSION)

    def reset(self) -> None:
        """Reset is reload — no snapshot/restore machinery exists (§15)."""
        if not self.scenario_ref:
            raise RuntimeError("no scenario to reset to")
        self.load(self.scenario_ref)

    def run(self) -> None:
        if self.state in (LOADED, PAUSED):
            self.state = RUNNING

    def pause(self) -> None:
        if self.state == RUNNING:
            self.state = PAUSED

    def set_speed(self, speed: int) -> None:
        self.speed = int(speed)

    # ----------------------------------------------------------- submission

    def submit_action(self, command: dict[str, Any],
                      source: str = OPERATOR) -> None:
        """Queue an operator action; applied at the next tick boundary."""
        self._queue.append((ACTION, dict(command), source))

    def inject_event(self, etype: str, params: dict[str, Any]) -> None:
        """Queue a live casualty insertion (instructor station, §9).

        `set_load` is translated here. The instructor station offers a **MW
        delta** (§9) but `hotwell`'s `set_load` event takes an **absolute p0 in
        watts**; doing the conversion at this edge keeps plant units out of the
        browser and puts them in one tested place, rather than leaving a
        units mismatch spread across the UI.
        """
        params = dict(params)
        if etype == "set_load":
            params = self._resolve_set_load(params)
        self._queue.append((etype, params, INSTRUCTOR))

    def _resolve_set_load(self, params: dict[str, Any]) -> dict[str, Any]:
        """{target, delta_mw | p0_mw} -> {target, p0} in absolute watts."""
        target = params.get("target", "nonvital")
        if "p0" in params:                      # already absolute watts
            return {"target": target, "p0": float(params["p0"])}
        block = getattr(self.sim.plant.loads, target)
        if "p0_mw" in params:
            p0 = float(params["p0_mw"]) * 1e6
        else:
            p0 = block.p0 + float(params.get("delta_mw", 0.0)) * 1e6
        return {"target": target, "p0": max(0.0, p0)}

    # ---------------------------------------------------------------- stepping

    def tick(self) -> tuple[Frame | None, list[Event], list[ActionResult]]:
        """One wall tick: `speed` sim steps, one frame, all events between."""
        events: list[Event] = []
        results: list[ActionResult] = []
        if self.state != RUNNING:
            return None, events, results
        for _ in range(self.speed):
            evs, res = self._step_once()
            events += evs
            results += res
            if self.state != RUNNING:
                break
        return self.frame(), events, results

    def _step_once(self) -> tuple[list[Event], list[ActionResult]]:
        sim = self.sim
        assert sim is not None and self.log is not None and self._synth is not None
        # `Simulator` accepts scenario=None, but this session type always loads
        # one; the event splice and the consumed-event slice below both assume
        # it. Fail here with a clear message rather than an AttributeError deep
        # in the hot loop if free-play is ever added.
        assert sim.scenario is not None, "SimSession requires a loaded scenario"
        tick = tick_of(sim.t)          # events/actions stamp to the PRE-step tick
        injected, actions, sources = self._drain()
        if injected:
            self._insert_events(injected)
        idx0 = sim._event_idx          # see HANDOFF: proposed core API for 0.3.0
        n_rejected = len(sim.rejected)

        obs = sim.step(actions or None)

        self._log_scenario_events(tick, sim.scenario.events[idx0:sim._event_idx],
                                  injected)
        results = self._log_actions(tick, actions, sources,
                                    sim.rejected[n_rejected:])
        events = self._synth.diff(sim, tick_of(sim.t))
        events += [self._action_event(r) for r in results]
        self.log.end_tick = tick_of(sim.t)
        if obs.plant_dead:
            self.state = ENDED
            self._end_reason = "plant_dead"
        elif sim.scenario is not None and sim.t >= sim.scenario.max_t - 0.5 * DT:
            self.state = ENDED
            self._end_reason = "max_t"
        return events, results

    def _drain(self) -> tuple[list[ScenarioEvent], dict[str, Any], dict[str, str]]:
        """Empty the queue into (injected events, action dict, sources).

        `Simulator.step()` accepts one flat action dict per step, so two
        submissions of the same key with *different* values cannot both be
        applied this tick. Rather than collapsing them — which would silently
        drop one — the conflicting submission and everything queued behind it
        are deferred to the next tick, in order.

        This is not hypothetical: ACK-ALL sends one `alarm.ack` per flashing
        window, and last-wins would acknowledge exactly one of them. Deferral
        also keeps each ack on its own tick in the session log, so replay
        reproduces them individually.
        """
        injected: list[ScenarioEvent] = []
        actions: dict[str, Any] = {}
        sources: dict[str, str] = {}
        deferred: list[tuple[str, Any, str]] = []
        t = self.sim.t if self.sim else 0.0
        for kind, payload, source in self._queue:
            if kind != ACTION:
                injected.append(ScenarioEvent(t=t, type=kind, params=payload))
                continue
            hold: dict[str, Any] = {}
            for key, value in payload.items():
                # Once anything is held back, later actions wait too, so the
                # operator's ordering is never rearranged.
                if deferred or hold or (key in actions and actions[key] != value):
                    hold[key] = value
                else:
                    actions[key] = value
                    sources[key] = source
            if hold:
                deferred.append((ACTION, hold, source))
        self._queue = deferred
        return injected, actions, sources

    def _insert_events(self, evs: list[ScenarioEvent]) -> None:
        """Splice injected events in at the head of the unconsumed portion.

        They carry t = now, and every unconsumed scenario event has t >= now, so
        the sequence stays sorted and the core's own `_apply_scenario_events`
        applies them — the panel never reimplements event semantics.

        This reads `Simulator._event_idx`, a private attribute. A public
        `Simulator.inject_event()` is proposed for hotwell 0.3.0 in HANDOFF.md.
        """
        sim = self.sim
        items = list(sim.scenario.events)
        at = sim._event_idx
        items[at:at] = evs
        sim.scenario = replace(sim.scenario, events=tuple(items))

    # ------------------------------------------------------------- logging

    def _log_scenario_events(self, tick: int, consumed, injected) -> None:
        """Record the events the core actually applied, in application order."""
        injected_ids = {id(e) for e in injected}
        for ev in consumed:
            self.log.records.append(LogRecord(
                tick=tick,
                source=INSTRUCTOR if id(ev) in injected_ids else SCENARIO,
                kind=ev.type, payload=dict(ev.params)))

    def _log_actions(self, tick: int, actions: dict[str, Any],
                     sources: dict[str, str], new_rejections) -> list[ActionResult]:
        """Record each submitted action with the core's own verdict."""
        reasons = {k: r.reason for r in new_rejections for k in r.action}
        results: list[ActionResult] = []
        for key, value in actions.items():
            reason = reasons.get(key, "")
            accepted = key not in reasons
            self.log.records.append(LogRecord(
                tick=tick, source=sources.get(key, OPERATOR), kind=ACTION,
                payload={key: value}, accepted=accepted, reason=reason))
            results.append(ActionResult(
                tick=tick, t=tick * DT, command={key: value},
                accepted=accepted, reason=reason,
                source=sources.get(key, OPERATOR)))
        return results

    def _action_event(self, r: ActionResult) -> Event:
        key = next(iter(r.command))
        verdict = "ACCEPTED" if r.accepted else f"REJECTED: {r.reason}"
        return Event(
            tick=r.tick, t=r.t, kind="action", id=key,
            state="accepted" if r.accepted else "rejected",
            text=soe_line("ACTION", key, verdict),
            detail={"command": r.command, "source": r.source})

    # ------------------------------------------------------------- reporting

    def status(self) -> dict[str, Any]:
        sim = self.sim
        return {
            "state": self.state,
            "speed": self.speed,
            "scenario_ref": self.scenario_ref,
            "scenario_name": self.log.scenario_name if self.log else "",
            "fidelity": dict(self.fidelity),
            "seed": sim.seed if sim else None,
            "tick": tick_of(sim.t) if sim else 0,
            "t": sim.t if sim else 0.0,
            "dt": DT,
            "max_t": sim.scenario.max_t if sim and sim.scenario else 0.0,
            "missed_deadlines": self._missed_deadlines,
        }

    def frame(self) -> Frame | None:
        sim = self.sim
        if sim is None or sim.last_obs is None:
            return None
        obs = sim.last_obs
        return Frame(
            tick=tick_of(sim.t), t=sim.t,
            values=dict(obs.values),
            indications=dict(obs.indications),
            alarms=dict(obs.alarms),
            status=self.status(),
            loops=telemetry.loop_state(sim),
            audit=telemetry.audit_block(sim),
        )

    def note_missed_deadline(self) -> None:
        """Wall-clock overrun. Determinism is unaffected — dt never changes."""
        self._missed_deadlines += 1

    # -------------------------------------------------------------- export

    def finalize_log(self) -> SessionLog:
        """Stamp the log with the state as of now (safe to call repeatedly)."""
        assert self.log is not None and self.sim is not None
        return sessionlog.finalize(self.log, self.sim, self._end_reason,
                                   tick_of(self.sim.t))

    def export(self, stamp: str | None = None) -> Path:
        """Write the session file (§3.4)."""
        log = self.finalize_log()
        return log.write(sessionlog.session_path(log, self.sessions_dir, stamp))
