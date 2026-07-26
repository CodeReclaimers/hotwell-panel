"""§12.6(a): the annunciator/SOE sequence a player sees during the casualty.

**A conflict in the plan is made explicit here rather than papered over.**
§1 locks the panel's default fidelity to `astrom_bell` + three-element
feedwater. §12.6(a) asks for "the exact annunciator/SOE sequence from the
phase-1 handoff table" — but that table was measured on `two_state` +
single-element, which was phase 1's default. Both statements are true; they
cannot describe the same run.

So there are two tests:

* `test_handoff_sequence_under_two_state` is a **specification** test. It pins
  the phase-1 handoff table to within 0.1 s and is the real regression gate on
  `events.py`: those alarm edges exist only because the panel diffs
  observations, since the core emits no FiredAction for alarm-only conditions.
* `test_panel_default_fidelity_cascade` is a **characterization** test. Under
  AB + 3E the casualty is genuinely different — losing feed reduces in-drum
  condensation so level RISES first (phase-1 D18's inverted short-term
  response), tripping DRUM_LVL_HIHI long before the low-low. Ordering and
  first-out are asserted; times carry loose tolerances because this is a record
  of behaviour, not a spec.

Which of the two is the §12.6(a) acceptance target is Alan's call; see HANDOFF.
"""
from __future__ import annotations

import pytest

from hotwell_panel.session import RUNNING, SimSession

CP1_TRIP_T = 300.0
TWO_STATE = {"drum_model": "two_state", "three_element": False}
PANEL_DEFAULT = {"drum_model": "astrom_bell", "three_element": True}


def run_casualty(fidelity, max_tick=40000):
    """Play the unrecovered casualty with no operator action; collect events."""
    s = SimSession()
    s.load("builtin:cp1_trip_unrecovered", fidelity)
    s.run()
    seq = []
    while s.state == RUNNING and s.sim.t < max_tick * 0.05:
        _, events, _ = s.tick()
        for e in events:
            seq.append((round(e.t - CP1_TRIP_T, 2), e.kind, e.id, e.state,
                        e.first_out))
    return s, seq


def firsts(seq, kind, state=None):
    """First occurrence time of each (id) for a kind, in order of occurrence."""
    out = {}
    for dt, k, i, st, _ in seq:
        if k == kind and (state is None or st == state) and i not in out:
            out[i] = dt
    return out


# ------------------------------------------------- specification: two_state


def test_handoff_sequence_under_two_state():
    """Reproduces the phase-1 HANDOFF casualty table exactly (±0.1 s)."""
    s, seq = run_casualty(TWO_STATE)
    alarms = firsts(seq, "alarm", "active")
    trips = firsts(seq, "first_out")

    # HANDOFF "Achieved casualty timings vs targets", relative to the CP-1 trip.
    expected = {
        "DRUM_P_HI": 19.9,      # pegging-steam demand lost, transient
        "DA_LO": 23.2,          # DA draining
        "HOTWELL_HI": 57.2,     # condensate backing up
        "FP1_SUCTION": 92.7,    # NPSH margin < 0.5 m sustained 5 s
        "SAFETY_VALVE": 98.0,   # feed lost at full steam draw
        "DRUM_LVL_LO": 112.5,
        "DRUM_LVL_LOLO": 127.4,  # -> MFT + turbine trip -> bus dead
    }
    print("\n  event            handoff   observed    delta")
    for aid, want in expected.items():
        got = alarms.get(aid)
        assert got is not None, f"{aid} never annunciated"
        print(f"  {aid:<16} {want:+7.1f}  {got:+8.2f}  {got - want:+7.2f}")
        assert got == pytest.approx(want, abs=0.1), aid

    # First-out order, and the initiator flag on the right entry.
    order = list(trips)
    assert order[:4] == ["CP1_TRIP:overload", "FP1_SUCTION",
                         "FP1_TRIP:FP1_SUCTION", "DRUM_LVL_LOLO"], order
    initiating = [i for _, k, i, _, fo in seq if k == "first_out" and fo]
    assert initiating == ["CP1_TRIP:overload"], initiating

    # The window for the first protective trip (HANDOFF target 45-120 s).
    assert 45.0 <= trips["FP1_SUCTION"] <= 120.0
    assert s.sim.disc.plant_dead is True
    print(f"  first-out (initiating): {initiating[0]}")
    print(f"  plant dead at {s.sim.t - CP1_TRIP_T:+.2f} s rel CP-1 trip")


def test_alarm_clears_are_emitted_too():
    """A clear is a *disappearance* from `alarm_states()`, not an event.

    DRUM_P_HI is transient in this casualty — it clears around +40 s. If the
    synthesizer missed clears, that window would stay lit forever.
    """
    _, seq = run_casualty(TWO_STATE)
    clears = [(dt, i) for dt, k, i, st, _ in seq if k == "alarm" and st == "clear"]
    assert any(i == "DRUM_P_HI" for _, i in clears), clears
    first_clear = next(dt for dt, i in clears if i == "DRUM_P_HI")
    print(f"\n  DRUM_P_HI clears at {first_clear:+.2f} s rel CP-1 trip")
    assert 35.0 < first_clear < 50.0


# ------------------------------ characterization: the panel's default fidelity


def test_panel_default_fidelity_cascade():
    """AB + 3E: a different, physically coherent casualty (D18)."""
    s, seq = run_casualty(PANEL_DEFAULT)
    alarms = firsts(seq, "alarm", "active")
    trips = firsts(seq, "first_out")

    print("\n  AB + 3E cascade (s rel CP-1 trip):")
    for aid in ("DA_LO", "HOTWELL_HI", "FP1_SUCTION", "DRUM_LVL_HI",
                "DRUM_LVL_HIHI", "SAFETY_VALVE", "DRUM_LVL_LO", "DRUM_LVL_LOLO"):
        if aid in alarms:
            print(f"    {aid:<16} {alarms[aid]:+8.2f}")

    # The initiator is unchanged — that is what first-out is for.
    initiating = [i for _, k, i, _, fo in seq if k == "first_out" and fo]
    assert initiating == ["CP1_TRIP:overload"], initiating

    # Level rises BEFORE it falls: the D18 inverted short-term response.
    assert "DRUM_LVL_HI" in alarms, "expected the AB drum's level rise"
    assert alarms["DRUM_LVL_HI"] < alarms["DRUM_LVL_LO"], \
        "AB drum must swell before it shrinks"
    assert alarms["DRUM_LVL_HIHI"] < alarms["DRUM_LVL_LOLO"]

    # First protective trip is still FP suction, still inside the 45-120 s window.
    assert 45.0 <= trips["FP1_SUCTION"] <= 120.0
    # Loose bounds: characterization, not specification.
    assert alarms["FP1_SUCTION"] == pytest.approx(77.9, abs=5.0)
    assert alarms["DRUM_LVL_HIHI"] == pytest.approx(101.1, abs=10.0)
    assert alarms["DRUM_LVL_LOLO"] == pytest.approx(222.8, abs=20.0)
    assert s.sim.disc.plant_dead is True
    print(f"    plant dead at {s.sim.t - CP1_TRIP_T:+.2f}")


def test_recovered_casualty_has_no_trips_under_either_fidelity():
    """§12.6(b): starting the standby CP in time saves the plant."""
    for fidelity, tag in ((TWO_STATE, "two_state+1E"),
                          (PANEL_DEFAULT, "AB+3E")):
        s = SimSession()
        s.load("builtin:cp1_trip_recovered", fidelity)
        s.run()
        seq = []
        while s.state == RUNNING:
            _, events, _ = s.tick()
            seq += events
        trips = [e.id for e in seq if e.kind == "first_out"]
        alarms = [e.id for e in seq if e.kind == "alarm" and e.state == "active"]
        print(f"\n  {tag}: first_out={trips} alarms={sorted(set(alarms))}")
        assert trips == ["CP1_TRIP:overload"], trips
        assert s.sim.disc.plant_dead is False
        assert s.sim.disc.pump_modes["cp2"] == "running"


# ------------------------------ §12.6(d): shrink/swell on recorder 1 ---------


def test_recorder_one_data_contains_the_shrink_swell():
    """The data behind the visual check in §12.6(d).

    Judging the trace by eye stays a manual gate, but whether the phenomenon is
    *in the data recorder 1 plots* is testable: this queries the historian for
    exactly the three signals that recorder is assigned, over the load step.

    Classic inverse response — a step increase in steam demand flashes steam in
    the drum and level RISES before feedwater catches up and it settles low.
    """
    import numpy as np

    s = SimSession()
    s.load("builtin:load_step", PANEL_DEFAULT)
    s.run()
    while s.state == RUNNING and s.sim.t < 420.0:
        s.tick()

    pens = ["drum_level", "feed_flow", "steam_flow"]      # recorder 1 (§8.1)
    t, series = s.sim.historian.query(pens, 280.0, 420.0, 5000)
    assert set(series) == set(pens)

    i_pre = int(np.argmin(np.abs(t - 299.0)))
    level_pre = series["drum_level"][i_pre]
    steam_pre = series["steam_flow"][i_pre]

    window = (t >= 300.0) & (t <= 340.0)
    i_peak = int(np.argmax(series["drum_level"][window]))
    swell = series["drum_level"][window][i_peak] - level_pre
    t_peak = t[window][i_peak] - 300.0
    steam_peak = series["steam_flow"][window][i_peak]

    i_end = int(np.argmin(np.abs(t - 420.0)))
    level_end = series["drum_level"][i_end]

    print(f"\n  pre-step  level {level_pre * 1000:+6.1f} mm, "
          f"steam {steam_pre:.2f} kg/s")
    print(f"  swell     {swell * 1000:+6.2f} mm at +{t_peak:.1f} s, "
          f"steam {steam_peak:.2f} kg/s")
    print(f"  settling  level {level_end * 1000:+6.1f} mm")

    assert steam_peak > steam_pre, "the step must raise steam demand"
    assert swell > 0.010, f"expected a visible swell, got {swell * 1000:.1f} mm"
    assert t_peak < 30.0, "the swell must lead, not lag, the flow change"
    assert level_end < level_pre, "and the level must then fall away"
