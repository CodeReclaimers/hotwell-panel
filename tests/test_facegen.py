"""§12.4 — generated gauge faces, with goldens for two representative faces.

The goldens intentionally track the *installed* core's protection table: if a
setpoint moves, these fail, and that is the point — a face showing a stale trip
mark is worse than no mark. Regenerate deliberately on a core revision:

    .venv/bin/python -m pytest tests/test_facegen.py --regen-goldens
"""
from __future__ import annotations

from pathlib import Path

import pytest
from hotwell.protection.tables import load_protection_table

from hotwell_panel import facegen
from hotwell_panel.displayunits import display_table

GOLDEN_DIR = Path(__file__).parent / "goldens"
TABLE = load_protection_table()

# One face with a two-sided trip band and alarm ticks, one with a safety-valve
# line and a single-sided trip — between them they exercise every mark type.
GOLDEN_FACES = ("drum_level", "drum_pressure")


@pytest.mark.parametrize("instrument", GOLDEN_FACES)
def test_face_matches_golden(instrument, request):
    svg = facegen.render_face(instrument, TABLE)
    path = GOLDEN_DIR / f"face_{instrument}.svg"
    if request.config.getoption("--regen-goldens", default=False):
        GOLDEN_DIR.mkdir(exist_ok=True)
        path.write_text(svg)
        pytest.skip(f"regenerated {path.name}")
    assert path.is_file(), f"missing golden {path}; run with --regen-goldens"
    want = path.read_text()
    if svg != want:
        print(f"\n  generated {len(svg)} chars, golden {len(want)} chars")
    assert svg == want, (
        f"{instrument} face drifted from its golden. If a hotwell setpoint "
        f"moved this is expected — regenerate with --regen-goldens.")


def test_setpoints_come_from_the_protection_table():
    """The whole reason faces are generated: no duplicated setpoints."""
    marks = facegen.setpoint_marks("drum_level", TABLE,
                                   display_table()["drum_level"])
    by_id = {m["id"]: m for m in marks}
    assert set(by_id) == {"DRUM_LVL_LO", "DRUM_LVL_LOLO",
                          "DRUM_LVL_HI", "DRUM_LVL_HIHI"}
    # -0.300 m LOLO -> -11.81 in, matching the §5.1 anchor.
    assert by_id["DRUM_LVL_LOLO"]["value"] == pytest.approx(-11.81, abs=0.01)
    assert by_id["DRUM_LVL_LOLO"]["kind"] == "trip"
    assert by_id["DRUM_LVL_LO"]["kind"] == "alarm"
    print("\n  drum_level marks (display units):")
    for m in marks:
        print(f"    {m['id']:<14} {m['value']:+7.2f} in  {m['kind']}")


def test_safety_valve_lift_is_a_red_line_on_the_pressure_face():
    marks = facegen.setpoint_marks("drum_pressure", TABLE,
                                   display_table()["drum_pressure"])
    sv = next(m for m in marks if m["id"] == "SAFETY_VALVE")
    assert sv["kind"] == "sv"
    assert sv["value"] == pytest.approx(1233, abs=1)     # §5.1 anchor
    svg = facegen.render_face("drum_pressure", TABLE)
    assert "safety valve lift" in svg


def test_overspeed_setpoint_is_visible_on_the_frequency_face():
    """The handoff's warning: a 55-65 Hz face would clamp below the trip."""
    marks = facegen.setpoint_marks("frequency", TABLE,
                                   display_table()["frequency"])
    ids = {m["id"] for m in marks}
    assert "OVERSPEED" in ids, "66 Hz overspeed trip must appear on the face"
    ov = next(m for m in marks if m["id"] == "OVERSPEED")
    assert ov["value"] == pytest.approx(66.0)
    assert 0.0 < ov["frac"] < 1.0, "must land inside the face, not clamped"
    print(f"\n  OVERSPEED at {ov['value']} Hz -> {ov['frac']:.3f} of the sweep")


def test_every_instrument_renders_a_face():
    faces = facegen.render_all(TABLE)
    assert set(faces) == set(display_table())
    for name, svg in faces.items():
        assert svg.startswith(f'<g id="face-{name}"'), name
        assert svg.endswith("</g>")
        assert "NaN" not in svg, name


def test_needle_angle_spans_the_sweep_and_clamps():
    lo = facegen.needle_angle("drum_level", -0.381)    # -15 in, face minimum
    hi = facegen.needle_angle("drum_level", 0.381)     # +15 in, face maximum
    assert lo == pytest.approx(135.0, abs=0.5)
    assert hi == pytest.approx(405.0, abs=0.5)
    # Off-scale values clamp rather than wrapping around the dial.
    assert facegen.needle_angle("drum_level", -5.0) == pytest.approx(135.0)
    assert facegen.needle_angle("drum_level", 5.0) == pytest.approx(405.0)
    mid = facegen.needle_angle("drum_level", 0.0)
    assert mid == pytest.approx(270.0, abs=0.5)        # NWL at 12 o'clock
    print(f"\n  drum_level sweep: {lo:.1f} .. {mid:.1f} .. {hi:.1f} deg")


def test_faces_are_pure_functions_of_the_contracts():
    """Two renders must be byte-identical — no timestamps, no ordering slop."""
    assert facegen.render_face("feed_flow", TABLE) == \
        facegen.render_face("feed_flow", TABLE)
