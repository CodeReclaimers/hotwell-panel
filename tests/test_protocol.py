"""§12.1 — protocol tests over the real WebSocket, plus the tick-level semantics.

Split deliberately. Message *shape* and round-trips are exercised through
`fastapi.testclient` against the live app. Time semantics (pause, speed, action
tick-stamping) are exercised against `SimSession` directly, because they are
properties of sim ticks, not of wall clock — asserting them through a 20 Hz
socket would test the test's own timing, not the contract.

Frame cadence IS checked over the socket, and timing-independently: every frame
carries its tick, so consecutive frames must differ by exactly `speed`.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from hotwell import __version__ as HOTWELL_VERSION
from hotwell.actions import ACTION_SCHEMA
from hotwell.sensors import OBSERVATION_SPEC

from hotwell_panel.protocol import PROTOCOL_VERSION, ProtocolError, parse_client
from hotwell_panel.server import create_app
from hotwell_panel.session import LOADED, PAUSED, RUNNING, SimSession, tick_of

SCEN = "builtin:cp1_trip_unrecovered"


@pytest.fixture
def client(tmp_path):
    session = SimSession(local_scenarios=Path("scenarios"), sessions_dir=tmp_path)
    # Fast wall clock so tests finish quickly; the cadence assertions below are
    # tick-based and independent of the rate.
    app = create_app(session, wall_hz=500.0, scenario=SCEN)
    with TestClient(app) as c:
        yield c, session


def recv_until(ws, mtype, limit=400):
    for _ in range(limit):
        m = ws.receive_json()
        if m["type"] == mtype:
            return m
    raise AssertionError(f"no {mtype} in {limit} messages")


# ------------------------------------------------------------------ hello


def test_hello_contents(client):
    c, session = client
    with c.websocket_connect("/ws") as ws:
        h = ws.receive_json()
    assert h["type"] == "hello"
    assert h["protocol_version"] == PROTOCOL_VERSION
    assert h["hotwell_version"] == HOTWELL_VERSION
    assert h["scenario"]["name"] == "cp1_trip_unrecovered"
    assert h["fidelity"] == {"drum_model": "astrom_bell", "three_element": True}
    assert len(h["obs_spec"]) == len(OBSERVATION_SPEC) == 22
    assert len(h["action_schema"]) == len(ACTION_SCHEMA)
    assert {"trips.manual_mft", "trips.manual_turbine"} <= \
        {a["key"] for a in h["action_schema"]}, "0.2.0 manual trips missing"
    assert len(h["annunciator"]) == 19
    assert h["annunciator"][0]["legend"] == ["DRUM LEVEL", "LOW"]
    # every sensed instrument has a display descriptor
    missing = {s.name for s in OBSERVATION_SPEC} - set(h["display_units"])
    assert not missing, f"no display units for {missing}"
    assert h["display_units"]["frequency"]["lo"] == 50
    assert h["display_units"]["frequency"]["hi"] == 70   # must span 66 Hz
    refs = {s["ref"] for s in h["scenarios"]}
    assert SCEN in refs
    print(f"\n  hello: {len(h['obs_spec'])} instruments, "
          f"{len(h['annunciator'])} windows, {len(h['scenarios'])} scenarios, "
          f"digest {h['obs_spec_digest']}")


def test_hello_is_followed_by_a_frame(client):
    c, _ = client
    with c.websocket_connect("/ws") as ws:
        ws.receive_json()
        f = ws.receive_json()
    assert f["type"] == "frame"
    assert set(f["values"]) == {s.name for s in OBSERVATION_SPEC}
    assert f["values"]["drum_pressure"] == pytest.approx(8.0e6, rel=1e-3)
    assert "mass_drift_frac" in f["audit"]


# ------------------------------------------------------------ frame cadence


@pytest.mark.parametrize("speed", [1, 2, 5])
def test_frame_ticks_advance_by_exactly_speed(client, speed):
    """§12.1 cadence: one frame per wall tick, `speed` sim steps apart."""
    c, session = client
    with c.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "instructor", "command": "speed",
                      "params": {"speed": speed}})
        ws.send_json({"type": "instructor", "command": "run"})
        ticks = []
        while len(ticks) < 6:
            m = ws.receive_json()
            if m["type"] == "frame" and m["status"]["state"] == RUNNING \
                    and m["status"]["speed"] == speed:
                ticks.append(m["tick"])
    # strict=False is intentional: pairwise over a sliding window.
    deltas = {b - a for a, b in zip(ticks, ticks[1:], strict=False)}
    print(f"\n  speed {speed}: ticks {ticks} deltas {sorted(deltas)}")
    assert deltas == {speed}, f"expected every frame {speed} ticks apart"


# ---------------------------------------------------------- action round-trip


def test_action_accepted_round_trip(client):
    c, _ = client
    with c.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "instructor", "command": "run"})
        ws.send_json({"type": "action", "command": {"cp2.start": True}})
        r = recv_until(ws, "action_result")
    assert r["accepted"] is True
    assert r["command"] == {"cp2.start": True}
    assert r["reason"] == ""


def test_action_rejected_round_trip_carries_the_core_reason(client):
    """Rejections surface verbatim on the panel (§4, §8.2)."""
    c, _ = client
    with c.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "instructor", "command": "run"})
        ws.send_json({"type": "action", "command": {"cp1.start": True}})
        r = recv_until(ws, "action_result")
    assert r["accepted"] is False
    assert r["reason"] == "cp1 is running, not stopped"
    print(f"\n  verbatim rejection: {r['reason']!r}")


def test_rejected_action_also_reaches_the_soe_log(client):
    c, _ = client
    with c.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "instructor", "command": "run"})
        ws.send_json({"type": "action", "command": {"cp1.start": True}})
        for _ in range(400):
            m = ws.receive_json()
            if m["type"] == "event" and m["kind"] == "action":
                assert "REJECTED: cp1 is running, not stopped" in m["text"]
                print(f"\n  SOE line: {m['text']!r}")
                return
    raise AssertionError("no action event reached the SOE log")


# ---------------------------------------------------------------- instructor


def test_instructor_pause_stops_frames_then_run_resumes(client):
    c, session = client
    with c.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "instructor", "command": "run"})
        recv_until(ws, "frame")
        ws.send_json({"type": "instructor", "command": "pause"})
        recv_until(ws, "frame")            # the immediate post-command frame
    assert session.state == PAUSED
    tick_a = tick_of(session.sim.t)
    assert session.tick() == (None, [], []), "paused session must not step"
    assert tick_of(session.sim.t) == tick_a


def test_instructor_inject_event_reaches_the_simulator(client):
    c, session = client
    with c.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "instructor", "command": "run"})
        ws.send_json({"type": "instructor", "command": "inject_event",
                      "params": {"event": "trip_pump",
                                 "params": {"target": "cp1", "reason": "test"}}})
        for _ in range(400):
            m = ws.receive_json()
            if m["type"] == "event" and m["kind"] == "pump" and m["id"] == "cp1":
                assert m["state"] == "tripped"
                assert m["detail"]["reason"] == "test"
                print(f"\n  injected casualty: {m['text']!r}")
                return
    raise AssertionError("injected trip_pump never surfaced")


def test_instructor_load_scenario_resends_hello(client):
    c, session = client
    with c.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "instructor", "command": "load_scenario",
                      "params": {"ref": "builtin:load_step"}})
        h = recv_until(ws, "hello")
    assert h["scenario"]["name"] == "load_step"
    assert session.state == LOADED


def test_instructor_export_session_writes_a_file(client, tmp_path):
    c, session = client
    with c.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "instructor", "command": "run"})
        recv_until(ws, "frame")
        ws.send_json({"type": "instructor", "command": "export_session"})
        m = recv_until(ws, "session_exported")
    assert Path(m["path"]).is_file()
    assert len(m["hash"]) == 64


# --------------------------------------------------------------- chart_query


def test_chart_query_passthrough(client):
    c, _ = client
    with c.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "instructor", "command": "run"})
        recv_until(ws, "frame")
        ws.send_json({"type": "chart_query", "request_id": "r1",
                      "signals": ["drum_level", "feed_flow", "steam_flow"],
                      "t0": 0.0, "t1": 1e9, "max_points": 500})
        d = recv_until(ws, "chart_data")
    assert d["request_id"] == "r1"
    assert set(d["series"]) == {"drum_level", "feed_flow", "steam_flow"}
    assert len(d["t"]) == len(d["series"]["drum_level"]) > 0
    assert all(isinstance(v, (float, int)) or v is None
               for v in d["series"]["feed_flow"])
    print(f"\n  chart_data: {len(d['t'])} points")


def test_unknown_message_is_reported_not_fatal(client):
    c, _ = client
    with c.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "nonsense"})
        m = recv_until(ws, "error")
        assert "unknown message type" in m["reason"]
        ws.send_json({"type": "instructor", "command": "run"})
        ws.send_json({"type": "action", "command": {"cp2.start": True}})
        recv_until(ws, "action_result")   # socket still alive


def test_actions_queued_while_frozen_apply_on_resume():
    """A switch thrown on a frozen panel takes effect when stepping resumes.

    Actions apply at a tick boundary (§1), and a paused session has no tick
    boundaries — so they wait rather than being dropped or applied out of band.
    """
    s = SimSession()
    s.load("builtin:load_step")          # LOADED: frozen at t = 0
    s.submit_action({"cp2.start": True})
    assert s.tick() == (None, [], []), "frozen session must not apply actions"
    assert not s.log.records
    s.run()
    _, _, results = s.tick()
    assert [r.command for r in results] == [{"cp2.start": True}]
    assert results[0].accepted is True
    assert s.log.records[0].tick == 0


# --------------------------------------------- tick semantics (no socket)


def test_speed_equivalence_n_at_5x_is_5n_at_1x():
    """§12.1: N sim steps at 5x == 5N at 1x for identical action tick-stamps."""
    def run(speed, wall_ticks, action_at_tick):
        s = SimSession()
        s.load("builtin:load_step")
        s.run()
        s.set_speed(speed)
        for _ in range(wall_ticks):
            if tick_of(s.sim.t) <= action_at_tick < tick_of(s.sim.t) + speed:
                s.submit_action({"governor.load_ref_mw": 58.0})
            s.tick()
        return s

    fast = run(5, 40, 100)
    slow = run(1, 200, 100)
    print(f"\n  5x: tick {tick_of(fast.sim.t)}  1x: tick {tick_of(slow.sim.t)}")
    assert tick_of(fast.sim.t) == tick_of(slow.sim.t) == 200
    assert [(r.tick, r.kind) for r in fast.log.records] == \
           [(r.tick, r.kind) for r in slow.log.records]
    assert fast.sim.state_history_hash == slow.sim.state_history_hash


def test_actions_are_stamped_to_the_tick_they_apply_on():
    s = SimSession()
    s.load("builtin:load_step")
    s.run()
    for _ in range(10):
        s.tick()
    at = tick_of(s.sim.t)
    s.submit_action({"governor.load_ref_mw": 57.0})
    s.tick()
    rec = [r for r in s.log.records if r.kind == "action"]
    assert len(rec) == 1 and rec[0].tick == at
    assert rec[0].t == pytest.approx(at * 0.05)


def test_parse_client_rejects_malformed_messages():
    for bad, match in [
        ({"type": "action"}, "non-empty object"),
        ({"type": "instructor", "command": "nope"}, "unknown command"),
        ({"type": "instructor", "command": "speed", "params": {"speed": 3}}, "speed"),
        ({"type": "instructor", "command": "inject_event",
          "params": {"event": "mft"}}, "not injectable"),
        ({"type": "chart_query", "signals": []}, "non-empty list"),
        ("nope", "must be an object"),
    ]:
        with pytest.raises(ProtocolError, match=match):
            parse_client(bad)
