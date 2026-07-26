"""§12.2 — the flagship: a live session replays bit-identically headlessly.

Drive a scripted casualty plus recovery through `SimSession` exactly as the
WebSocket layer does (queue an action, let the tick boundary apply it), export
the session, convert it with `session_to_scenario.py`'s own code, replay
headlessly, and compare `hotwell`'s state-history hash.

This is the contract that makes phase-4 human-vs-agent comparison possible, so
the tests here also cover the two ways it can silently break: same-tick
ordering, and float drift in the stamped event times.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from hotwell.simulator import DT

from hotwell_panel.replay import verify_session
from hotwell_panel.session import RUNNING, SimSession, tick_of
from hotwell_panel.sessionlog import LogRecord, to_scenario_dict

REPO = Path(__file__).resolve().parents[1]


def drive(session: SimSession, until_tick: int, script=None) -> None:
    """Run wall ticks, submitting scripted commands at their tick, as the
    server's real-time loop does."""
    script = dict(script or {})
    while tick_of(session.sim.t) < until_tick and session.state == RUNNING:
        for tick, submit in list(script.items()):
            if tick_of(session.sim.t) == tick:
                submit(session)
                del script[tick]
        session.tick()


# --------------------------------------------------------------- flagship


@pytest.mark.parametrize("scenario_ref,until,script_desc", [
    ("builtin:cp1_trip_unrecovered", 8600, "no operator action (cascade to dead)"),
])
def test_replay_reproduces_state_history_hash(tmp_path, scenario_ref, until,
                                              script_desc):
    s = SimSession(sessions_dir=tmp_path)
    s.load(scenario_ref)
    s.run()
    # An operator action, a rejected action, and an instructor injection —
    # everything that can enter the simulator from outside.
    script = {
        200: lambda ss: ss.submit_action({"governor.load_ref_mw": 59.5}),
        400: lambda ss: ss.submit_action({"cp1.start": True}),   # running -> reject
        7000: lambda ss: ss.inject_event("set_air_ingress", {"value": 0.02}),
    }
    drive(s, until, script)

    session_path = s.export(stamp="test")
    scenario_path = tmp_path / "derived.yaml"
    r = verify_session(session_path, scenario_path)

    print(f"\n  scenario   : {scenario_ref} ({script_desc})")
    print(f"  records    : {r['n_records']}")
    print(f"  end tick   : live {r['expected_end_tick']}  "
          f"replay {r['actual_end_tick']}")
    print(f"  plant_dead : live {r['expected_plant_dead']}  "
          f"replay {r['actual_plant_dead']}")
    print(f"  hash live  : {r['expected_hash']}")
    print(f"  hash replay: {r['actual_hash']}")

    assert r["expected_hash"], "live session recorded no hash"
    assert r["actual_end_tick"] == r["expected_end_tick"]
    assert r["actual_plant_dead"] == r["expected_plant_dead"]
    assert r["match"], "state-history hash diverged"


def test_rejected_actions_are_logged_and_replayed(tmp_path):
    s = SimSession(sessions_dir=tmp_path)
    s.load("builtin:load_step")
    s.run()
    drive(s, 40, {20: lambda ss: ss.submit_action({"cp1.start": True})})
    log = s.finalize_log()
    rejected = [r for r in log.records if not r.accepted]
    assert len(rejected) == 1
    assert rejected[0].reason == "cp1 is running, not stopped"
    assert rejected[0].tick == 20
    # it still appears in the derived scenario: the core recorded a rejection,
    # which is session state a faithful replay must reproduce
    events = to_scenario_dict(log)["events"]
    assert {"cp1.start": True} in [e.get("command") for e in events]
    print(f"\n  rejection logged verbatim: {rejected[0].reason!r}")


# ------------------------------------------------- the two silent-break modes


def test_same_tick_event_and_action_keep_their_order(tmp_path):
    """An injection and an operator action on the SAME tick.

    `Simulator.step()` applies scenario events before submitted actions, but
    replay turns both into scenario events sorted by t. The canonical 300 s /
    312 s pair never collides, so the flagship test alone would not cover this.
    """
    s = SimSession(sessions_dir=tmp_path)
    s.load("builtin:cp1_trip_recovered")
    s.run()

    def both(ss):
        ss.inject_event("trip_pump", {"target": "fp2", "reason": "test"})
        ss.submit_action({"governor.load_ref_mw": 58.0})

    drive(s, 120, {60: both})
    log = s.finalize_log()
    at60 = [r for r in log.records if r.tick == 60]
    assert [r.kind for r in at60] == ["trip_pump", "action"], at60
    # and the derived scenario preserves that order at equal t
    evs = [e for e in to_scenario_dict(log)["events"] if e["t"] == 59.5 * DT]
    assert [e["type"] for e in evs] == ["trip_pump", "action"]

    r = verify_session(s.export(stamp="sametick"), tmp_path / "sametick.yaml")
    print(f"\n  same-tick order preserved: {[e['type'] for e in evs]}")
    print(f"  hash live {r['expected_hash'][:16]} replay {r['actual_hash'][:16]}")
    assert r["match"]


def test_stamped_event_times_survive_accumulated_float_drift():
    """The exact-tick stamping that a naive implementation would use is unsafe.

    Reproduces the core's own firing predicate (`ev.t <= sim.t + 1e-9`) against
    the real accumulated-time sequence, for both stamping schemes.
    """
    tol = 1e-9
    checks = [(6000, 300.0), (18000, 900.0), (36000, 1800.0)]
    t, drift = 0.0, {}
    for n in range(1, max(c[0] for c in checks) + 1):
        t += DT
        if n in {c[0] for c in checks}:
            drift[n] = t
    exact_ok, half_ok = [], []
    for tick, _ in checks:
        live_t = drift[tick]
        rec = LogRecord(tick=tick, source="operator", kind="action", payload={})
        exact_ok.append(rec.t <= live_t + tol)          # naive: t = tick*dt
        half_ok.append(rec.fire_t <= live_t + tol)      # ours:  t = (tick-.5)*dt
        # and must NOT fire a tick early
        assert rec.fire_t > (tick - 1) * DT + tol
        print(f"  tick {tick:6d}: live t={live_t!r} drift={live_t - tick*DT:+.3e}  "
              f"exact fires={exact_ok[-1]}  half-tick fires={half_ok[-1]}")
    assert all(half_ok), "half-tick stamping must always fire on the right tick"
    assert not all(exact_ok), \
        "exact stamping is expected to fail at 36000 ticks — if this now passes, " \
        "re-derive the margin rather than deleting the guard"


# ------------------------------------------------------------------- the CLI


def test_session_to_scenario_cli_is_a_gate(tmp_path):
    """§12.2 via the committed script, exit status and all."""
    s = SimSession(sessions_dir=tmp_path)
    s.load("builtin:load_step")
    s.run()
    drive(s, 200, {100: lambda ss: ss.submit_action({"governor.load_ref_mw": 61.0})})
    session_path = s.export(stamp="cli")

    proc = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "session_to_scenario.py"),
         str(session_path), "-o", str(tmp_path / "cli.yaml"), "--replay"],
        capture_output=True, text=True, cwd=REPO)
    print("\n" + proc.stdout.strip())
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "MATCH" in proc.stdout
