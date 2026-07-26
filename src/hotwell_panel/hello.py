"""Build the `hello` message: everything static a client needs (§4).

Kept separate from the server so the contents are testable without a socket,
and so P1's generated gauge faces and placement manifest drop in here.
"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from hotwell import __version__ as HOTWELL_VERSION
from hotwell.actions import ACTION_SCHEMA
from hotwell.sensors import OBSERVATION_SPEC

from hotwell_panel import scenarios as scenario_catalog
from hotwell_panel.protocol import PROTOCOL_VERSION, Hello
from hotwell_panel.session import OBS_SPEC_DIGEST, SimSession


def annunciator_windows(session: SimSession) -> list[dict[str, Any]]:
    """One entry per protection-table condition — the annunciator window list.

    Setpoints ride along so the client can render them without a second source;
    the protection table remains the only place they are defined.
    """
    return [{
        "id": c.id,
        "legend": list(c.legend),
        "signal": c.signal,
        "op": c.op,
        "setpoint": c.setpoint,
        "reseat": c.reseat,
        "delay": c.delay,
        "latching": c.latching,
        "actions": list(c.actions),
        "is_trip": c.is_trip,
        "target": c.target,
    } for c in session.table.conditions]


def build(session: SimSession, local_scenarios: Path | None = None,
          gauge_faces: dict[str, str] | None = None,
          manifest: dict[str, Any] | None = None) -> Hello:
    """Assemble the hello for the current session state."""
    from hotwell_panel.displayunits import display_table

    scenario_info = None
    if session.log is not None:
        scenario_info = {
            "ref": session.scenario_ref,
            "name": session.log.scenario_name,
            "seed": session.log.seed,
            "load_mw": session.log.load_mw,
            "mode": session.log.mode,
            "max_t": session.sim.scenario.max_t if session.sim else 0.0,
        }
    return Hello(
        protocol_version=PROTOCOL_VERSION,
        hotwell_version=HOTWELL_VERSION,
        scenario=scenario_info,
        fidelity=dict(session.fidelity),
        status=session.status(),
        obs_spec=[asdict(s) for s in OBSERVATION_SPEC],
        obs_spec_digest=OBS_SPEC_DIGEST,
        action_schema=[asdict(a) for a in ACTION_SCHEMA],
        display_units=display_table(),
        annunciator=annunciator_windows(session),
        scenarios=scenario_catalog.discover(local_scenarios),
        gauge_faces=gauge_faces or {},
        manifest=manifest or {},
    )
