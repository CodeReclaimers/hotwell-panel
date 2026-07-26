"""Session-level constants and the small pure helpers built on the contracts.

Split out of `session.py` to keep that module focused on the SimSession
lifecycle (and inside the ~300-line guideline of §14).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from hotwell.plant import load_config
from hotwell.sensors import OBSERVATION_SPEC
from hotwell.simulator import DT

# §3.3 lifecycle states.
NO_SCENARIO, LOADED, RUNNING, PAUSED, ENDED = (
    "no_scenario", "loaded", "running", "paused", "ended")

#: Panel default fidelity (§1, phase-1 D18): the Åström-Bell drum needs
#: three-element feedwater. Single-element + AB is a legitimate degraded-mode
#: training configuration the instructor can select, not a bug.
DEFAULT_FIDELITY = {"drum_model": "astrom_bell", "three_element": True}


def build_config(fidelity: dict[str, Any]) -> dict:
    """Baseline plant config with the instructor's fidelity switches applied."""
    cfg = load_config()
    cfg["drum"]["model"] = fidelity.get("drum_model", DEFAULT_FIDELITY["drum_model"])
    cfg["control"]["drum_level"]["three_element"] = bool(
        fidelity.get("three_element", DEFAULT_FIDELITY["three_element"]))
    return cfg


def tick_of(t: float) -> int:
    """Sim time -> tick index.

    `t` accumulates by ``+= dt`` and drifts in the last bits (measured
    -1.089e-9 s at 36000 steps), so every tick stamp goes through this
    rounding rather than truncating.
    """
    return int(round(t / DT))


def _spec_digest(spec) -> str:
    """Stable digest of the observation contract, shipped in `hello` so a stale
    client (or a golden file) can detect that the core moved a contract."""
    payload = json.dumps([[s.name, s.units, s.lo, s.hi, s.resolution] for s in spec],
                         sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


OBS_SPEC_DIGEST = _spec_digest(OBSERVATION_SPEC)
