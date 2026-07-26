"""§12.4 — the §5.1 conversion anchors, pinned.

Anchors come from the phase-1 achieved design point, not from the plan's
rounded prose. Where the two differ the discrepancy is asserted explicitly
rather than absorbed into a tolerance.
"""
from __future__ import annotations

import pytest
from hotwell.sensors import OBSERVATION_SPEC

from hotwell_panel.displayunits import (
    convert,
    degf_from_degc,
    display_table,
    inches,
    inhg_vacuum,
    klb_per_hr,
    psig,
    rpm,
)

# Achieved design point, hotwell HANDOFF "Reference design point".
STEAM_FLOW_KG_S = 76.923
FEED_FLOW_KG_S = 87.121

_SPEC = {s.name: s for s in OBSERVATION_SPEC}


def quantize(name: str, si: float) -> float:
    """Put a truth value through the instrument's own resolution, as the
    sensing pipeline does before the panel ever sees it."""
    res = _SPEC[name].resolution
    return round(si / res) * res


def test_pressure_anchors_psig():
    rows = [("drum, nominal", 8.0e6, 1146),
            ("safety valve lift", 8.6e6, 1233),
            ("deaerator", 0.15e6, 7.1)]
    print()
    for label, pa, want in rows:
        got = psig(pa)
        print(f"  {label:<20} {pa:>10.0f} Pa -> {got:8.2f} psig (plan {want})")
        assert got == pytest.approx(want, abs=0.5 if want > 100 else 0.05)


def test_condenser_vacuum_anchor():
    got = inhg_vacuum(7.0e3)
    print(f"\n  7 kPa abs -> {got:.2f} inHg vacuum (plan 27.9)")
    assert got == pytest.approx(27.9, abs=0.05)
    # Higher absolute pressure must read as LESS vacuum — the gauge is inverted.
    assert inhg_vacuum(12.0e3) < got


def test_level_anchors_inches():
    got = inches(-0.300)
    print(f"\n  drum LOLO -0.300 m -> {got:.2f} in (plan -11.8)")
    assert got == pytest.approx(-11.8, abs=0.05)
    d = display_table()["drum_level"]
    assert (d["lo"], d["hi"]) == (-15, 15), "plan §5.1: drum gauge +/-15 in"


def test_flow_anchors_klb_per_hr():
    """The plan's 611 klb/hr steam row is not reachable on the panel.

    Two separate points, both worth pinning:

    1. Arithmetically, 611 requires the achieved 76.923 kg/s. The plan writes
       "76.9 kg/s", which converts to 610.3 and rounds to 610.
    2. More decisively, the panel never sees 76.923. `steam_flow` quantizes to
       0.1 kg/s in the observation contract, so what reaches the display *is*
       76.9 — and the gauge therefore reads 610, correctly. Reaching 611 would
       mean displaying truth the instrument did not report.

    The feed-flow row survives quantization (87.121 -> 87.1 -> 691) and is
    unaffected.
    """
    steam_truth = klb_per_hr(STEAM_FLOW_KG_S)
    steam_sensed = klb_per_hr(quantize("steam_flow", STEAM_FLOW_KG_S))
    feed_sensed = klb_per_hr(quantize("feed_flow", FEED_FLOW_KG_S))
    print(f"\n  steam truth  76.923 kg/s -> {steam_truth:.2f} klb/hr -> "
          f"{round(steam_truth)} (the plan's 611)")
    print(f"  steam sensed 76.900 kg/s -> {steam_sensed:.2f} klb/hr -> "
          f"{round(steam_sensed)}  <- what the panel can show")
    print(f"  feed  sensed 87.100 kg/s -> {feed_sensed:.2f} klb/hr -> "
          f"{round(feed_sensed)} (plan 691)")
    assert round(steam_truth) == 611, "the plan's figure needs unquantized truth"
    assert round(steam_sensed) == 610, "what the instrument actually reports"
    assert round(feed_sensed) == 691


def test_shaft_speed_and_frequency():
    assert rpm(60.0) == pytest.approx(3600.0)
    assert rpm(66.0) == pytest.approx(3960.0)   # 110% overspeed trip
    d = display_table()["frequency"]
    # MANDATED by §5.1 and the phase-1 handoff: the face must span 66 Hz.
    assert d["lo"] == 50 and d["hi"] == 70, "frequency face must span 66 Hz"
    assert d["lo"] <= 66.0 <= d["hi"]
    print(f"\n  60 Hz -> {rpm(60.0):.0f} RPM; 66 Hz -> {rpm(66.0):.0f} RPM; "
          f"freq face {d['lo']}-{d['hi']} Hz")


def test_temperature_anchor():
    got = degf_from_degc(295.06)      # Tsat(8 MPa), phase-1 T1
    print(f"\n  Tsat(8 MPa) 295.06 C -> {got:.1f} F (plan 563)")
    assert got == pytest.approx(563.1, abs=0.5)


def test_electrical_face_range():
    d = display_table()["mw_out"]
    assert (d["lo"], d["hi"]) == (0, 75)      # §5.1: MW, 0-75
    assert convert("mw_out", 60.0e6) == pytest.approx(60.0)


def test_pump_current_is_percent_of_rated():
    t = display_table(cp_rated_a=60.0, fp_rated_a=400.0)
    assert convert("cp1_current", 60.0, t) == pytest.approx(100.0)
    assert convert("fp1_current", 400.0, t) == pytest.approx(100.0)
    assert t["cp1_current"]["hi"] == 125      # §5.1: 0-125% rated


def test_every_sensed_instrument_has_a_descriptor():
    t = display_table()
    missing = [s.name for s in OBSERVATION_SPEC if s.name not in t]
    assert not missing, missing
    for name, d in t.items():
        assert d["hi"] > d["lo"], name
        assert isinstance(d["decimals"], int)
        assert d["unit"], name


def test_conversions_are_affine_and_match_the_helpers():
    """The client applies scale/offset mechanically — it must agree exactly."""
    t = display_table()
    checks = [("drum_pressure", 8.0e6, psig(8.0e6)),
              ("cond_pressure", 7.0e3, inhg_vacuum(7.0e3)),
              ("drum_level", -0.300, inches(-0.300)),
              ("steam_flow", STEAM_FLOW_KG_S, klb_per_hr(STEAM_FLOW_KG_S)),
              ("shaft_rpm", 60.0, rpm(60.0))]
    for name, si, want in checks:
        assert convert(name, si, t) == pytest.approx(want, rel=1e-12), name


def test_derived_entries_declare_their_source():
    """`shaft_rpm` has no sensed instrument; the client needs to know that."""
    d = display_table()["shaft_rpm"]
    assert d["source"] == "frequency"
    assert {s.name for s in OBSERVATION_SPEC}.isdisjoint({"shaft_rpm"})
