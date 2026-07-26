"""Headless replay of a session (§3.4) — the bridge to phase-4 comparisons.

A session file plus its derived scenario must reproduce the live run's
state-history hash exactly. Keeping this in the package (rather than only in
the script) means the acceptance test and the CLI exercise the same code.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from hotwell.scenario import load_scenario
from hotwell.simulator import Simulator

from hotwell_panel.session import build_config, tick_of
from hotwell_panel.sessionlog import SessionLog, write_scenario


def replay_scenario(scenario_path: Any, fidelity: dict[str, Any],
                    until_tick: int) -> Simulator:
    """Construct the sim exactly as the live session did and step it forward.

    Stepping is bounded by tick count, not wall time, so the replay executes the
    same number of steps the session did.
    """
    sc = load_scenario(scenario_path)
    sim = Simulator(build_config(fidelity), scenario=sc)
    sim.initialize_steady_state(sc.load_mw)
    while tick_of(sim.t) < until_tick:
        obs = sim.step()
        if obs.plant_dead:
            break
    return sim


def verify_session(session_path: str | Path,
                   scenario_path: str | Path | None = None) -> dict[str, Any]:
    """Replay a session file and compare state-history hashes.

    If `scenario_path` is given the scenario YAML is written there first and
    read back, so the file round-trip is part of what is verified.
    """
    log = SessionLog.read(session_path)
    if scenario_path is not None:
        write_scenario(log, scenario_path)
        source: Any = scenario_path
    else:
        import tempfile
        tmp = Path(tempfile.mkdtemp()) / "replay.yaml"
        write_scenario(log, tmp)
        source = tmp
    sim = replay_scenario(source, log.fidelity, log.end_tick)
    actual = sim.state_history_hash
    return {
        "scenario": str(source),
        "expected_hash": log.state_history_hash,
        "actual_hash": actual,
        "match": actual == log.state_history_hash,
        "expected_end_tick": log.end_tick,
        "actual_end_tick": tick_of(sim.t),
        "expected_plant_dead": log.plant_dead,
        "actual_plant_dead": bool(sim.disc.plant_dead),
        "n_records": len(log.records),
    }
