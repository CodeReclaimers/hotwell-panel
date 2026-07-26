"""Session log and its reduction to a plain scenario (§3.4) — contract-grade.

Every applied action *and* every scenario event, operator- or
instructor-originated, is recorded with the sim tick it was applied on. The log
is therefore a complete, ordered description of everything that entered the
simulator from outside, which is what makes a live session replayable
bit-identically headlessly.

The generated scenario is built **entirely from the log**, not from the original
scenario file plus a diff. That removes the ordering hazard the core would
otherwise create: `Simulator.step()` applies scenario events before submitted
actions, so on a tick carrying both, a naive merge can reorder them. Because
`load_scenario` sorts events with a *stable* sort, replaying the log in log
order reproduces the live application order exactly, including within a tick.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from hotwell.simulator import DT

SCENARIO = "scenario"
OPERATOR = "operator"
INSTRUCTOR = "instructor"
ACTION = "action"


@dataclass
class LogRecord:
    """One thing that entered the simulator from outside, at one tick."""

    tick: int
    source: str            # scenario | operator | instructor
    kind: str              # 'action', or a hotwell scenario event type
    payload: dict[str, Any]
    accepted: bool = True
    reason: str = ""       # rejection reason, verbatim from the core

    @property
    def t(self) -> float:
        """Exact tick time — never the accumulated float from the live run."""
        return self.tick * DT

    @property
    def fire_t(self) -> float:
        """The time to stamp into a replay scenario: a **half tick early**.

        `Simulator._apply_scenario_events` fires on ``ev.t <= sim.t + 1e-9``,
        and `sim.t` is an accumulated sum of dt whose error grows with run
        length: measured −1.089e−9 s at 36000 steps (t = 1800 s, the canonical
        `max_t`), already past that 1e-9 tolerance. Stamping the exact tick time
        would therefore make a late-session action fire one step late in replay
        and silently break the hash. Half a tick early centres the stamp in the
        gap between ticks, giving 0.025 s of margin in both directions — seven
        orders of magnitude more than the drift.
        """
        return (self.tick - 0.5) * DT


@dataclass
class SessionLog:
    """Everything needed to reconstruct and verify a session."""

    scenario_ref: str
    scenario_name: str
    seed: int
    load_mw: float
    mode: str
    fidelity: dict[str, Any]
    hotwell_version: str
    records: list[LogRecord] = field(default_factory=list)
    end_tick: int = 0
    end_state: str = ""
    plant_dead: bool = False
    state_history_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "session": {
                "scenario_ref": self.scenario_ref,
                "scenario_name": self.scenario_name,
                "seed": self.seed,
                "load_mw": self.load_mw,
                "mode": self.mode,
                "hotwell_version": self.hotwell_version,
                "dt": DT,
            },
            "fidelity": dict(self.fidelity),
            "end": {
                "tick": self.end_tick,
                "t": self.end_tick * DT,
                "state": self.end_state,
                "plant_dead": self.plant_dead,
                "state_history_hash": self.state_history_hash,
            },
            "records": [asdict(r) for r in self.records],
        }

    def write(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(self.to_dict(), sort_keys=False))
        return path

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> SessionLog:
        s, e = raw["session"], raw["end"]
        return cls(
            scenario_ref=s["scenario_ref"], scenario_name=s["scenario_name"],
            seed=int(s["seed"]), load_mw=float(s["load_mw"]),
            mode=s.get("mode", "islanded"), fidelity=raw.get("fidelity", {}),
            hotwell_version=s.get("hotwell_version", ""),
            records=[LogRecord(**r) for r in raw.get("records", ())],
            end_tick=int(e["tick"]), end_state=e.get("state", ""),
            plant_dead=bool(e.get("plant_dead", False)),
            state_history_hash=e.get("state_history_hash", ""),
        )

    @classmethod
    def read(cls, path: str | Path) -> SessionLog:
        return cls.from_dict(yaml.safe_load(Path(path).read_text()))


def to_scenario_dict(log: SessionLog) -> dict[str, Any]:
    """Reduce a session log to a plain `hotwell` scenario dict (§3.4).

    Emitted in log order and stamped at exact tick times. `load_scenario`'s sort
    is stable, so same-tick records keep the order the live session applied them.
    """
    events: list[dict[str, Any]] = []
    for r in log.records:
        ev: dict[str, Any] = {"t": r.fire_t, "type": r.kind}
        if r.kind == ACTION:
            ev["command"] = dict(r.payload)
        else:
            ev.update(r.payload)
        events.append(ev)
    return {
        "name": f"{log.scenario_name}_replay",
        "seed": log.seed,
        "init": {"load_mw": log.load_mw, "mode": log.mode},
        "events": events,
        "end": {"max_t": log.end_tick * DT},
    }


def write_scenario(log: SessionLog, path: str | Path) -> Path:
    """Write the derived scenario YAML."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        f"# Derived from session '{log.scenario_name}' by session_to_scenario.py.\n"
        f"# Replaying this against hotwell {log.hotwell_version} with the fidelity\n"
        f"# config below must reproduce state-history hash:\n"
        f"#   {log.state_history_hash}\n"
        f"# fidelity: {log.fidelity}\n"
        f"#\n"
        f"# Event times are stamped HALF A TICK EARLY (dt = {DT} s), so an event\n"
        f"# listed at t = N*dt - dt/2 is applied on tick N. See LogRecord.fire_t:\n"
        f"# sim time is an accumulated float and its drift exceeds the core's\n"
        f"# 1e-9 event tolerance on long runs, so exact stamps are not safe.\n"
    )
    path.write_text(header + yaml.safe_dump(to_scenario_dict(log), sort_keys=False))
    return path


def finalize(log: SessionLog, sim, end_reason: str, tick: int) -> SessionLog:
    """Stamp a log with the state as of *now*.

    Safe to call repeatedly mid-run — the instructor's EXPORT SESSION does
    exactly that — so every field is recomputed rather than filled in once. A
    stale `end_state` beside a moved `end_tick` would misdescribe the file.
    """
    log.end_tick = tick
    log.plant_dead = bool(sim.disc.plant_dead)
    log.state_history_hash = sim.state_history_hash
    log.end_state = end_reason
    return log


def session_path(log: SessionLog, sessions_dir: Path,
                 stamp: str | None = None) -> Path:
    """`sessions/<timestamp>_<scenario>.session.yaml` (§3.4)."""
    stamp = stamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path(sessions_dir) / f"{stamp}_{log.scenario_name}.session.yaml"
