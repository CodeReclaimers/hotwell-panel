"""Generate gauge-face SVG from the contracts (§5.2).

A face is drawn from three sources, none of them hand-maintained:

* the display descriptor (`displayunits`) gives range, unit and resolution,
* the observation spec gives the instrument's own resolution,
* **the installed `hotwell`'s protection table** gives the alarm and trip marks.

That last point is the reason this is generated rather than drawn: setpoints
already have a single source of truth, so a face that shows them must read that
source. Amber tick = alarm, red arc = trip, red line = safety-valve lift.

Faces are 270-degree sweep, ivory dial, black markings (§10). Output is an SVG
``<g>`` fragment per instrument, sent in `hello` and instantiated by the client
with ``<use>``; only the needle moves at runtime.
"""
from __future__ import annotations

import math
from typing import Any

from hotwell.protection.tables import ProtectionTable
from hotwell.sensors import OBSERVATION_SPEC

from hotwell_panel.displayunits import display_table

SWEEP = 270.0          # degrees of arc
START = 135.0          # degrees clockwise from 12 o'clock to the low end
R_FACE = 50.0          # face radius in local units; the client scales it
R_TICK_MAJ = 40.0
R_TICK_MIN = 44.0
R_LABEL = 31.0
R_ARC = 46.5

DIAL = "#f2edd8"       # ivory (§10)
INK = "#1a1a1a"
AMBER = "#d99a00"
RED = "#c0392b"

_SPEC = {s.name: s for s in OBSERVATION_SPEC}


def _angle(frac: float) -> float:
    """0..1 along the scale -> degrees clockwise from 12 o'clock."""
    return START + SWEEP * frac


def _xy(frac: float, r: float) -> tuple[float, float]:
    a = math.radians(_angle(frac) - 180.0)
    return (r * math.sin(-a), r * math.cos(-a))


def _arc_path(f0: float, f1: float, r: float) -> str:
    x0, y0 = _xy(f0, r)
    x1, y1 = _xy(f1, r)
    large = 1 if (f1 - f0) * SWEEP > 180.0 else 0
    return f"M {x0:.2f} {y0:.2f} A {r} {r} 0 {large} 1 {x1:.2f} {y1:.2f}"


def _nice_step(span: float, target: int) -> float:
    """A 1/2/5 x 10^n step giving roughly `target` major divisions."""
    if span <= 0:
        return 1.0
    raw = span / max(1, target)
    mag = 10.0 ** math.floor(math.log10(raw))
    for mult in (1.0, 2.0, 2.5, 5.0, 10.0):
        if raw <= mult * mag:
            return mult * mag
    return 10.0 * mag


def _fmt(v: float, decimals: int) -> str:
    s = f"{v:.{decimals}f}"
    return s.rstrip("0").rstrip(".") if decimals and "." in s else s


def setpoint_marks(instrument: str, table: ProtectionTable,
                   d: dict[str, Any]) -> list[dict[str, Any]]:
    """Protection-table entries that apply to this instrument, in display units.

    Reading the table here is what stops setpoints being duplicated onto faces
    by hand — §5.2's whole point.
    """
    lo, hi = float(d["lo"]), float(d["hi"])
    span = hi - lo or 1.0
    marks = []
    for c in table.conditions:
        if c.signal != instrument:
            continue
        value = c.setpoint * d["scale"] + d["offset"]
        frac = (value - lo) / span
        if not -0.02 <= frac <= 1.02:
            continue        # setpoint off the face; nothing honest to draw
        marks.append({
            "id": c.id, "value": value, "frac": min(max(frac, 0.0), 1.0),
            "kind": "sv" if "safety_valve" in c.actions
                    else ("trip" if c.is_trip else "alarm"),
            "op": c.op, "legend": list(c.legend),
        })
    return marks


def render_face(instrument: str, table: ProtectionTable,
                d: dict[str, Any] | None = None) -> str:
    """One instrument's face as an SVG ``<g>`` fragment (no needle)."""
    d = d or display_table()[instrument]
    lo, hi = float(d["lo"]), float(d["hi"])
    span = hi - lo or 1.0
    decimals = int(d["decimals"])
    # Five major divisions, not six: at 64-112 px on screen a ring of 4-digit
    # numerals collides with itself past about five.
    step = _nice_step(span, 5)
    parts: list[str] = [
        f'<g id="face-{instrument}" class="gauge-face">',
        f'<circle cx="0" cy="0" r="{R_FACE}" fill="{DIAL}" stroke="{INK}" '
        f'stroke-width="1.5"/>',
    ]

    # --- setpoint arcs and marks, from the protection table -----------------
    for mk in setpoint_marks(instrument, table, d):
        f = mk["frac"]
        if mk["kind"] == "trip":
            # A trip arc runs from the setpoint to the end of the scale the
            # condition trips toward, so the red band is the forbidden region.
            f0, f1 = (0.0, f) if mk["op"] == "lt" else (f, 1.0)
            if f1 > f0:
                parts.append(
                    f'<path d="{_arc_path(f0, f1, R_ARC)}" fill="none" '
                    f'stroke="{RED}" stroke-width="3" opacity="0.85">'
                    f'<title>{mk["id"]}</title></path>')
        elif mk["kind"] == "sv":
            x0, y0 = _xy(f, R_TICK_MAJ - 3)
            x1, y1 = _xy(f, R_FACE - 1)
            parts.append(
                f'<line x1="{x0:.2f}" y1="{y0:.2f}" x2="{x1:.2f}" y2="{y1:.2f}" '
                f'stroke="{RED}" stroke-width="2.5"><title>{mk["id"]} '
                f'(safety valve lift)</title></line>')
        else:
            x0, y0 = _xy(f, R_TICK_MAJ)
            x1, y1 = _xy(f, R_FACE - 1)
            parts.append(
                f'<line x1="{x0:.2f}" y1="{y0:.2f}" x2="{x1:.2f}" y2="{y1:.2f}" '
                f'stroke="{AMBER}" stroke-width="2.5">'
                f'<title>{mk["id"]}</title></line>')

    # --- ticks and engraved numerals ---------------------------------------
    n_major = int(round(span / step))
    for i in range(n_major + 1):
        value = lo + i * step
        if value > hi + 1e-9:
            break
        f = (value - lo) / span
        x0, y0 = _xy(f, R_TICK_MAJ)
        x1, y1 = _xy(f, R_FACE - 2)
        parts.append(f'<line x1="{x0:.2f}" y1="{y0:.2f}" x2="{x1:.2f}" '
                     f'y2="{y1:.2f}" stroke="{INK}" stroke-width="1.6"/>')
        lx, ly = _xy(f, R_LABEL)
        parts.append(
            f'<text x="{lx:.2f}" y="{ly + 3:.2f}" text-anchor="middle" '
            f'font-size="8" fill="{INK}" class="gauge-numeral">'
            f'{_fmt(value, decimals if step < 1 else 0)}</text>')
        if i < n_major:
            for k in range(1, 5):
                fm = (value + k * step / 5.0 - lo) / span
                if fm > 1.0:
                    break
                mx0, my0 = _xy(fm, R_TICK_MIN)
                mx1, my1 = _xy(fm, R_FACE - 2)
                parts.append(
                    f'<line x1="{mx0:.2f}" y1="{my0:.2f}" x2="{mx1:.2f}" '
                    f'y2="{my1:.2f}" stroke="{INK}" stroke-width="0.8"/>')

    # Units legend sits low in the bottom gap of the 270-degree sweep. Above
    # the hub it collided with the mid-scale numeral at 12 o'clock; the two
    # lowest numerals are out at x = +/-22, so the centre down here is clear.
    # The client's digital readout goes just above it, at y = 26.
    parts.append(f'<text x="0" y="40" text-anchor="middle" font-size="7" '
                 f'fill="{INK}" class="gauge-units">{d["unit"]}</text>')
    parts.append(f'<circle cx="0" cy="0" r="3.5" fill="{INK}"/>')
    parts.append("</g>")
    return "".join(parts)


def render_all(table: ProtectionTable,
               units: dict[str, dict[str, Any]] | None = None
               ) -> dict[str, str]:
    """Every face in the display table, regenerated at server start."""
    units = units or display_table()
    return {name: render_face(name, table, d) for name, d in units.items()}


def needle_angle(instrument: str, si_value: float,
                 d: dict[str, Any] | None = None) -> float:
    """Needle rotation in degrees, clamped to the face (server-side reference
    for the client's identical computation; used by tests)."""
    d = d or display_table()[instrument]
    lo, hi = float(d["lo"]), float(d["hi"])
    value = si_value * d["scale"] + d["offset"]
    frac = 0.0 if hi == lo else (value - lo) / (hi - lo)
    return _angle(min(max(frac, 0.0), 1.0))


def face_report() -> list[dict[str, Any]]:
    """Per-instrument summary (used by tests and the golden files)."""
    units = display_table()
    return [{"instrument": n, "unit": d["unit"], "lo": d["lo"], "hi": d["hi"],
             "si_units": _SPEC[n].units if n in _SPEC else "derived"}
            for n, d in sorted(units.items())]
