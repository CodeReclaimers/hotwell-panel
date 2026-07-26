"""WebSocket message schemas (PLAN-panel.md §4). Versioned; documented here.

One JSON text message per envelope, always carrying a ``type`` field. Server ->
client: ``hello``, ``frame``, ``event``, ``action_result``, ``chart_data``.
Client -> server: ``action``, ``instructor``, ``chart_query``.

Values on the wire are **SI**, exactly as `hotwell` produces them. Display-unit
conversion happens in the browser using the table shipped in ``hello``; the
simulation contract is never re-expressed in customary units server-side.

Text intended for the operator (SOE lines, rejection reasons, annunciator
legends) IS rendered server-side, because that is domain knowledge and §1 keeps
domain knowledge out of the client.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, ClassVar

PROTOCOL_VERSION = 1

# ------------------------------------------------------------------ server -> client


@dataclass
class Hello:
    """First message on every connection: everything static about this session.

    ``obs_spec_digest`` lets a client (or a test) detect that the installed
    ``hotwell`` moved its observation contract out from under a cached page.
    """

    TYPE: ClassVar[str] = "hello"
    protocol_version: int
    hotwell_version: str
    scenario: dict[str, Any] | None      # name, source, seed, load_mw, max_t
    fidelity: dict[str, Any]             # drum model, 1E/3E, seed
    status: dict[str, Any]               # see SimSession.status()
    obs_spec: list[dict[str, Any]]       # InstrumentSpec rows, SI
    obs_spec_digest: str
    action_schema: list[dict[str, Any]]  # ActionSpec rows
    display_units: dict[str, Any]        # §5.1 conversion table
    annunciator: list[dict[str, Any]]    # window list from the protection table
    scenarios: list[dict[str, Any]]      # picker: builtin + local, labeled
    gauge_faces: dict[str, str] = field(default_factory=dict)   # id -> SVG (P1)
    manifest: dict[str, Any] = field(default_factory=dict)      # placement (P1)


@dataclass
class Frame:
    """One broadcast per wall tick (never per sim step at speed > 1)."""

    TYPE: ClassVar[str] = "frame"
    tick: int                            # sim tick = round(t / dt), authoritative
    t: float                             # [s] sim time
    values: dict[str, float]             # sensed instruments, SI
    indications: dict[str, Any]          # run lights, breaker/trip flags
    alarms: dict[str, str]               # id -> active | acknowledged
    status: dict[str, Any]
    audit: dict[str, float]              # mass/energy closure (instructor readout)


@dataclass
class Event:
    """A discrete thing that happened, at a sim tick.

    The client never diffs frames to find these: alarm edges, trips, pump mode
    changes, safety-valve lift/reseat and plant death all arrive here, each with
    a pre-rendered ``text`` for the sequence-of-events log.
    """

    TYPE: ClassVar[str] = "event"
    tick: int
    t: float
    kind: str                            # alarm|first_out|pump|safety_valve|
                                         # breaker|plant_dead|action|instructor
    id: str = ""                         # alarm id, pump name, action key
    state: str = ""                      # active|acknowledged|clear|running|...
    text: str = ""                       # rendered SOE line
    first_out: bool = False              # THE initiating event of the sequence
    is_trip: bool = False                # trip-class (red window / red SOE line)
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionResult:
    """Echo of a submitted action. Rejections surface verbatim on the panel."""

    TYPE: ClassVar[str] = "action_result"
    tick: int
    t: float
    command: dict[str, Any]
    accepted: bool
    reason: str = ""                     # rejection reason, verbatim from core
    source: str = "operator"


@dataclass
class ChartData:
    """Historian passthrough response to a chart_query."""

    TYPE: ClassVar[str] = "chart_data"
    request_id: str
    t: list[float]
    series: dict[str, list[float | None]]
    #: Requested signals the historian does not carry. Reported rather than
    #: dropped silently, so a bad pen assignment shows up as an error and not
    #: as a blank chart.
    unknown: list[str] = field(default_factory=list)


def encode(msg: Any) -> dict[str, Any]:
    """Any server message dataclass -> a JSON-ready dict with its ``type``."""
    return {"type": msg.TYPE, **asdict(msg)}


# ------------------------------------------------------------------ client -> server

#: Scenario event types the instructor station may inject live (§4).
INJECTABLE_EVENTS = ("trip_pump", "inhibit_start", "sensor_fault", "set_load",
                     "set_air_ingress")

#: Instructor commands (§4).
INSTRUCTOR_COMMANDS = ("load_scenario", "run", "pause", "speed", "reset",
                       "inject_event", "export_session")

#: Allowed speeds — steps per wall tick. dt never changes (§1).
SPEEDS = (1, 2, 5)


class ProtocolError(ValueError):
    """A malformed client message. Reported back, never fatal to the session."""


def parse_client(raw: Any) -> tuple[str, dict[str, Any]]:
    """Validate one decoded client message; returns ``(type, body)``.

    Deliberately strict: the panel is the only client, so anything unexpected is
    a bug worth surfacing rather than tolerating.
    """
    if not isinstance(raw, dict):
        raise ProtocolError(f"message must be an object, got {type(raw).__name__}")
    mtype = raw.get("type")
    if mtype == "action":
        command = raw.get("command")
        if not isinstance(command, dict) or not command:
            raise ProtocolError("action: 'command' must be a non-empty object")
        return "action", {"command": command}
    if mtype == "instructor":
        cmd = raw.get("command")
        if cmd not in INSTRUCTOR_COMMANDS:
            raise ProtocolError(f"instructor: unknown command {cmd!r}")
        body = {"command": cmd, "params": raw.get("params") or {}}
        if not isinstance(body["params"], dict):
            raise ProtocolError("instructor: 'params' must be an object")
        if cmd == "inject_event":
            etype = body["params"].get("event")
            if etype not in INJECTABLE_EVENTS:
                raise ProtocolError(f"inject_event: {etype!r} is not injectable")
        if cmd == "speed" and body["params"].get("speed") not in SPEEDS:
            raise ProtocolError(f"speed must be one of {SPEEDS}")
        return "instructor", body
    if mtype == "chart_query":
        signals = raw.get("signals")
        if not isinstance(signals, list) or not signals:
            raise ProtocolError("chart_query: 'signals' must be a non-empty list")
        return "chart_query", {
            "request_id": str(raw.get("request_id", "")),
            "signals": [str(s) for s in signals],
            "t0": float(raw.get("t0", 0.0)),
            "t1": float(raw.get("t1", 1e12)),
            "max_points": int(raw.get("max_points", 2000)),
        }
    raise ProtocolError(f"unknown message type {mtype!r}")
