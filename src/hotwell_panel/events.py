"""Turn simulator state changes into discrete `event` messages (§4).

Why this module exists: `hotwell`'s protection engine emits a `FiredAction`
only for non-`alarm` actions, so pure-alarm conditions — DRUM_P_HI, DA_LO,
HOTWELL_HI, DRUM_LVL_LO, i.e. most of the phase-1 casualty cascade — produce no
firing record at all, and `alarm_states()` returns only non-clear entries, so a
clear shows up as a *disappearance*. The panel must therefore diff the
observation step over step to recover alarm edges. `hotwell`'s own
`scripts/run_scenario.py` builds its timeline strip the same way.

Diffing happens per **sim step**, not per wall tick, so nothing is lost at
speed > 1.

Operator-facing text is rendered here, server-side, because the legends, trip
classes and pump names are domain knowledge and §1 keeps that out of the client.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from hotwell.protection.tables import ProtectionTable
from hotwell.simulator import Simulator

from hotwell_panel.protocol import Event

# Sequence-of-events log column widths (line-printer styling, §8.2).
_CAT_W, _ID_W = 7, 16


def soe_line(category: str, ident: str, detail: str) -> str:
    """One fixed-column sequence-of-events line."""
    return f"{category:<{_CAT_W}}{ident:<{_ID_W}}{detail}"


def pump_label(pump: str) -> str:
    """cp1 -> CP-1, matching the engraved plates on the board."""
    return f"{pump[:2].upper()}-{pump[2:]}"


@dataclass
class EventSynthesizer:
    """Holds the previous step's observable state and emits the deltas."""

    table: ProtectionTable
    _alarms: dict[str, str] = field(default_factory=dict)
    _pumps: dict[str, str] = field(default_factory=dict)
    _first_out: int = 0
    _sv_open: bool = False
    _breaker: bool = True
    _dead: bool = False
    _primed: bool = False

    def prime(self, sim: Simulator) -> None:
        """Adopt the current state as the baseline without emitting events.

        Called once after a scenario loads so the steady-state starting point
        does not fire a burst of spurious transitions.
        """
        self._alarms = dict(sim.last_obs.alarms)
        self._pumps = dict(sim.disc.pump_modes)
        self._first_out = len(sim.engine.first_out)
        self._sv_open = bool(sim.disc.safety_open)
        self._breaker = bool(sim.disc.breaker_closed)
        self._dead = bool(sim.disc.plant_dead)
        self._primed = True

    # ------------------------------------------------------------------ diff

    def diff(self, sim: Simulator, tick: int) -> list[Event]:
        """Every discrete change since the previous call, in reading order."""
        assert self._primed, "call prime() after loading a scenario"
        t = sim.t
        out: list[Event] = []
        out += self._alarm_events(sim, tick, t)
        out += self._first_out_events(sim, tick, t)
        out += self._pump_events(sim, tick, t)
        out += self._plant_events(sim, tick, t)
        return out

    # ------------------------------------------------------------- alarms

    def _alarm_events(self, sim: Simulator, tick: int, t: float) -> list[Event]:
        current = dict(sim.last_obs.alarms)
        out: list[Event] = []
        for aid, state in current.items():
            if self._alarms.get(aid) != state:
                out.append(self._alarm_event(aid, state, tick, t))
        for aid in self._alarms:
            if aid not in current:          # a clear is a disappearance
                out.append(self._alarm_event(aid, "clear", tick, t))
        self._alarms = current
        return out

    def _alarm_event(self, aid: str, state: str, tick: int, t: float) -> Event:
        try:
            cond = self.table.by_id(aid)
            legend, is_trip = list(cond.legend), cond.is_trip
        except KeyError:                    # defensive: id not in the table
            legend, is_trip = [aid], False
        return Event(
            tick=tick, t=t, kind="alarm", id=aid, state=state,
            is_trip=is_trip,
            text=soe_line("TRIP" if is_trip else "ALARM", aid, state.upper()),
            detail={"legend": legend},
        )

    # ------------------------------------------------------------ first-out

    def _first_out_events(self, sim: Simulator, tick: int, t: float) -> list[Event]:
        """New entries in the engine's first-out record.

        Note these are NOT all protection-table ids: `record_external_trip`
        appends free-form labels (`CP1_TRIP:overload`, `MANUAL_MFT`), and the
        canonical casualty's *initiator* is one of them — which is exactly why
        the panel needs a first-out display separate from the annunciator
        windows.
        """
        out: list[Event] = []
        record = sim.engine.first_out
        for i in range(self._first_out, len(record)):
            _, label = record[i]
            initiating = i == 0
            out.append(Event(
                tick=tick, t=t, kind="first_out", id=label, state="trip",
                first_out=initiating, is_trip=True,
                text=soe_line("TRIP", label,
                              "FIRST OUT" if initiating else "TRIP"),
                detail={"index": i, "in_table": self._in_table(label)},
            ))
        self._first_out = len(record)
        return out

    def _in_table(self, label: str) -> bool:
        try:
            self.table.by_id(label)
            return True
        except KeyError:
            return False

    # ---------------------------------------------------------------- pumps

    def _pump_events(self, sim: Simulator, tick: int, t: float) -> list[Event]:
        out: list[Event] = []
        for pump, mode in sim.disc.pump_modes.items():
            if self._pumps.get(pump) == mode:
                continue
            reason = sim.disc.pump_trip_reason.get(pump, "") if mode == "tripped" else ""
            detail = f"{mode.upper()}" + (f" ({reason})" if reason else "")
            out.append(Event(
                tick=tick, t=t, kind="pump", id=pump, state=mode,
                is_trip=mode == "tripped",
                text=soe_line("PUMP", pump_label(pump), detail),
                detail={"reason": reason},
            ))
        self._pumps = dict(sim.disc.pump_modes)
        return out

    # --------------------------------------------------------- plant-level

    def _plant_events(self, sim: Simulator, tick: int, t: float) -> list[Event]:
        out: list[Event] = []
        disc = sim.disc
        if bool(disc.safety_open) != self._sv_open:
            self._sv_open = bool(disc.safety_open)
            out.append(Event(
                tick=tick, t=t, kind="safety_valve",
                id="SAFETY_VALVE", state="open" if self._sv_open else "reseat",
                is_trip=False,
                text=soe_line("SV", "SAFETY VALVE",
                              "LIFT" if self._sv_open else "RESEAT")))
        if bool(disc.breaker_closed) != self._breaker:
            self._breaker = bool(disc.breaker_closed)
            out.append(Event(
                tick=tick, t=t, kind="breaker", id="GEN_BREAKER",
                state="closed" if self._breaker else "open",
                is_trip=not self._breaker,
                text=soe_line("BKR", "GEN OUTPUT",
                              "CLOSED" if self._breaker else "OPEN")))
        if bool(disc.plant_dead) and not self._dead:
            self._dead = True
            out.append(Event(
                tick=tick, t=t, kind="plant_dead", id="PLANT", state="dead",
                is_trip=True,
                text=soe_line("PLANT", "PLANT DEAD",
                              "MFT + ALL PUMPS STOPPED")))
        return out
