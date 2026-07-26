"""SI -> US customary display conversion (§5.1). Panel layer only.

`hotwell` is SI throughout and stays that way; everything here is presentation.
Every conversion is **affine** (``display = si * scale + offset``), so the table
ships to the browser in `hello` and the client applies it mechanically without
knowing any plant physics (§1).

Two entries are *derived* rather than sensed: the tachometer reads shaft RPM off
the same signal the frequency meter uses (2-pole machine, 60 Hz = 3600 RPM), and
saturation temperature is a placard value. Each carries a ``source`` naming the
instrument it is computed from.
"""
from __future__ import annotations

from typing import Any

# Exact unit definitions.
PA_PER_PSI = 6894.757293168361
PA_PER_INHG = 3386.388640341
ATM_PA = 101325.0
M_PER_IN = 0.0254
M_PER_FT = 0.3048
KG_PER_LB = 0.45359237
POLES = 2  # 2-pole machine: 60 Hz -> 3600 RPM


def psig(p_abs_pa: float) -> float:
    """Absolute Pa -> gauge psi."""
    return (p_abs_pa - ATM_PA) / PA_PER_PSI


def inhg_vacuum(p_abs_pa: float) -> float:
    """Absolute Pa -> inches of mercury of VACUUM (higher = better, §5.1)."""
    return (ATM_PA - p_abs_pa) / PA_PER_INHG


def inches(m: float) -> float:
    return m / M_PER_IN


def feet(m: float) -> float:
    return m / M_PER_FT


def klb_per_hr(kg_s: float) -> float:
    return kg_s * 3600.0 / KG_PER_LB / 1000.0


def rpm(hz: float) -> float:
    """Electrical Hz -> shaft RPM for a 2-pole machine."""
    return hz * 120.0 / POLES


def degf_from_degc(c: float) -> float:
    return c * 9.0 / 5.0 + 32.0


def degf_from_k(k: float) -> float:
    return degf_from_degc(k - 273.15)


def _affine(unit: str, scale: float, offset: float, lo: float, hi: float,
            decimals: int, label: str, source: str | None = None) -> dict[str, Any]:
    d = {"unit": unit, "scale": scale, "offset": offset,
         "lo": lo, "hi": hi, "decimals": decimals, "label": label}
    if source:
        d["source"] = source
    return d


_PSIG = (1.0 / PA_PER_PSI, -ATM_PA / PA_PER_PSI)
_INHG_VAC = (-1.0 / PA_PER_INHG, ATM_PA / PA_PER_INHG)
_IN = (1.0 / M_PER_IN, 0.0)
_FT = (1.0 / M_PER_FT, 0.0)
_KLBH = (3600.0 / KG_PER_LB / 1000.0, 0.0)
_MW = (1e-6, 0.0)
_PCT = (100.0, 0.0)


def display_table(cp_rated_a: float = 60.0, fp_rated_a: float = 400.0
                  ) -> dict[str, dict[str, Any]]:
    """The full instrument -> display descriptor table shipped in `hello`.

    Pump currents read as percent of rated amps (§5.1), so the rated values come
    from the plant config rather than being hard-coded into a gauge face.
    """
    t: dict[str, dict[str, Any]] = {
        # --- pressures -----------------------------------------------------
        "drum_pressure": _affine("PSIG", *_PSIG, 0, 1800, 0, "DRUM PRESS"),
        "chest_pressure": _affine("PSIG", *_PSIG, 0, 1800, 0, "CHEST PRESS"),
        "da_pressure": _affine("PSIG", *_PSIG, 0, 30, 1, "DA PRESS"),
        # Condenser gauge reads VACUUM: higher is better, so the scale is
        # negative and the face runs 0..30 inHg with normal near the top.
        "cond_pressure": _affine("IN HG VAC", *_INHG_VAC, 0, 30, 1, "COND VAC"),
        # --- levels --------------------------------------------------------
        "drum_level": _affine("INCHES", *_IN, -15, 15, 1, "DRUM LEVEL"),
        "hotwell_level": _affine("INCHES", *_IN, -40, 60, 0, "HOTWELL LVL"),
        "da_level": _affine("INCHES", *_IN, -100, 20, 0, "DA LEVEL"),
        # --- flows ---------------------------------------------------------
        "steam_flow": _affine("KLB/HR", *_KLBH, 0, 1200, 0, "STEAM FLOW"),
        "feed_flow": _affine("KLB/HR", *_KLBH, 0, 1200, 0, "FEED FLOW"),
        "condensate_flow": _affine("KLB/HR", *_KLBH, 0, 1200, 0, "COND FLOW"),
        # --- electrical ----------------------------------------------------
        # 50-70 Hz is MANDATED (§5.1): the face must span the 66 Hz overspeed
        # trip. Do not "improve" this to 55-65.
        "frequency": _affine("HZ", 1.0, 0.0, 50, 70, 2, "FREQUENCY"),
        "mw_out": _affine("MW", *_MW, 0, 75, 1, "GEN OUTPUT"),
        # --- valve / firing positions --------------------------------------
        "fw_valve_pos": _affine("PERCENT", *_PCT, 0, 100, 0, "FEED REG VLV"),
        "throttle_pos": _affine("PERCENT", *_PCT, 0, 100, 0, "THROTTLE"),
        "firing_rate": _affine("PERCENT", *_PCT, 0, 100, 0, "FIRING RATE"),
        "da_lcv_pos": _affine("PERCENT", *_PCT, 0, 100, 0, "DA LCV"),
        # --- pump motor currents, percent of rated -------------------------
        "cp1_current": _affine("PCT RATED", 100.0 / cp_rated_a, 0.0, 0, 125, 0,
                               "CP-1 AMPS"),
        "cp2_current": _affine("PCT RATED", 100.0 / cp_rated_a, 0.0, 0, 125, 0,
                               "CP-2 AMPS"),
        "fp1_current": _affine("PCT RATED", 100.0 / fp_rated_a, 0.0, 0, 125, 0,
                               "FP-1 AMPS"),
        "fp2_current": _affine("PCT RATED", 100.0 / fp_rated_a, 0.0, 0, 125, 0,
                               "FP-2 AMPS"),
        # --- pump suction margin -------------------------------------------
        # §5.1's table has no row for NPSH margin; feet is the period-correct
        # unit for a US plant. Recorded as a plan gap in HANDOFF.md.
        "fp1_npsh_margin": _affine("FEET", *_FT, -15, 50, 1, "FP-1 NPSH"),
        "fp2_npsh_margin": _affine("FEET", *_FT, -15, 50, 1, "FP-2 NPSH"),
    }
    # --- derived indications (no sensed instrument of their own) ------------
    t["shaft_rpm"] = _affine("RPM", 120.0 / POLES, 0.0, 3000, 4200, 0,
                             "SHAFT SPEED", source="frequency")
    return t


def convert(name: str, si_value: float,
            table: dict[str, dict[str, Any]] | None = None) -> float:
    """Apply the table's affine conversion — the same arithmetic the client does."""
    d = (table or display_table())[name]
    return si_value * d["scale"] + d["offset"]


def format_value(name: str, si_value: float,
                 table: dict[str, dict[str, Any]] | None = None) -> str:
    """Conversion plus per-instrument resolution, for server-rendered text."""
    tbl = table or display_table()
    d = tbl[name]
    return f"{convert(name, si_value, tbl):.{d['decimals']}f} {d['unit']}"
