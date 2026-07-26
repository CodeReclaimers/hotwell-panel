"""Building the per-frame telemetry block (§4 `frame`).

Split out of `session.py` to keep that module on the lifecycle and inside the
~300-line guideline (§14). These are free functions over a live `Simulator`, so
they are testable without a session.
"""
from __future__ import annotations

from typing import Any

from hotwell.simulator import Simulator

LOOP_NAMES = ("drum_level", "drum_pressure", "da_level")


def loop_state(sim: Simulator) -> dict[str, Any]:
    """Controller-station state, read straight off the live controllers.

    Not available through the observation contract — `Observation.indications`
    has no loop modes — so the panel layer reads `Simulator.control`. These are
    the same objects the actions mutate, so an AUTO/MAN lamp cannot disagree
    with the plant after a reset or a scripted scenario action.
    """
    ctl = sim.control
    out: dict[str, Any] = {}
    for name in LOOP_NAMES:
        pi = ctl.loop(name)
        out[name] = {"mode": pi.mode, "sp": pi.sp, "output": pi.output,
                     "manual_cmd": pi.manual_cmd,
                     "lo": pi.p.lo, "hi": pi.p.hi}
    out["governor"] = {
        "mode": "manual" if ctl.governor_manual is not None else "auto",
        "load_ref_mw": ctl.load_ref / 1e6,
        "droop": ctl.gov.droop,
        "output": sim.commands.throttle_cmd,
    }
    out["three_element"] = bool(ctl.three_element)
    out["loads_mw"] = load_blocks(sim)
    return out


def load_blocks(sim: Simulator) -> dict[str, float]:
    """Current load-block demand in MW, for the instructor readout."""
    loads = sim.plant.loads
    return {"vital": loads.vital.p0 / 1e6, "nonvital": loads.nonvital.p0 / 1e6}


def audit_block(sim: Simulator) -> dict[str, float]:
    """Mass/energy closure for the instructor display.

    Note `energy_residual_frac` is a *steady-state* diagnostic (core
    `audit.py`); it legitimately swings during a transient.
    """
    rep = sim.audit()
    return {"mass_drift_frac": rep.mass_drift_frac,
            "mass_drift_frac_per_hour": rep.mass_drift_frac_per_hour,
            "energy_residual_frac": rep.energy_residual_frac,
            "energy_residual_w": rep.energy_residual,
            "relief_kg": rep.mass_relief_integrated}
