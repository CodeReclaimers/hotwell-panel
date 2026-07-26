"""Panel placement manifest: loading and validation against live contracts (§6.1).

The manifest is what keeps the drawing honest as the core evolves. Because it is
validated against the *installed* `hotwell`'s ObservationSpec, ACTION_SCHEMA and
protection table, a core release that moves a contract fails here first — this
doubles as the cross-repo compatibility gate (§12.3).

The coverage rule is the important one: every instrument in the observation spec
is either placed on the board or listed under ``unplaced:`` with a reason. A
silently missing gauge is indistinguishable from a deliberate omission
otherwise.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from hotwell.actions import ACTION_SCHEMA
from hotwell.protection.tables import ProtectionTable
from hotwell.sensors import OBSERVATION_SPEC

#: The element kinds §6.1 defines. Group title plates and region boxes are
#: separate top-level sections, not elements, so this list stays closed.
KINDS = {"gauge", "lamp", "grip", "station", "breaker", "annunciator", "chart",
         "button"}

#: §7: room for every protection-table window plus ~30% engraved blank spares.
SPARE_FRACTION = 0.30

#: Instrument references may appear under these option keys as well as the
#: element's own `instrument` field.
INSTRUMENT_OPTION_KEYS = ("output_instrument", "extra_instruments", "pens")

#: Action references may appear under these option keys.
ACTION_OPTION_KEYS = ("mode_action", "manual_action", "start_action",
                      "stop_action", "action", "raise_action", "lower_action")

GRID = 8  # §10: align everything to an 8 px grid.


class ManifestError(ValueError):
    """Manifest does not match the installed contracts, or is malformed."""


@dataclass
class Element:
    id: str
    kind: str
    x: int
    y: int
    instrument: str | None = None
    size: int | None = None
    w: int | None = None
    h: int | None = None
    label: str | None = None
    options: dict[str, Any] = field(default_factory=dict)

    def instruments(self) -> list[str]:
        out = [self.instrument] if self.instrument else []
        for key in INSTRUMENT_OPTION_KEYS:
            v = self.options.get(key)
            if isinstance(v, str):
                out.append(v)
            elif isinstance(v, list):
                out += [s for s in v if isinstance(s, str)]
        return out

    def actions(self) -> list[str]:
        out = []
        for key in ACTION_OPTION_KEYS:
            v = self.options.get(key)
            if isinstance(v, str):
                out.append(v)
            elif isinstance(v, list):
                out += [s for s in v if isinstance(s, str)]
        return out


@dataclass
class Manifest:
    version: int
    canvas: dict[str, int]
    regions: dict[str, dict[str, int]]
    groups: list[dict[str, Any]]
    elements: list[Element]
    annunciator: dict[str, int]
    unplaced: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready form for the `hello` message."""
        return {
            "version": self.version,
            "canvas": self.canvas,
            "regions": self.regions,
            "groups": self.groups,
            "annunciator": self.annunciator,
            "unplaced": self.unplaced,
            "elements": [{
                "id": e.id, "kind": e.kind, "x": e.x, "y": e.y,
                "instrument": e.instrument, "size": e.size,
                "w": e.w, "h": e.h, "label": e.label, "options": e.options,
            } for e in self.elements],
        }


DEFAULT_PATH = Path(__file__).parent / "panel_manifest.yaml"


def load(path: str | Path | None = None) -> Manifest:
    """Parse the manifest (structure only — see `validate` for the contracts)."""
    raw = yaml.safe_load(Path(path or DEFAULT_PATH).read_text())
    elements = []
    for row in raw.get("elements", ()):
        unknown = set(row) - {"id", "kind", "x", "y", "instrument", "size",
                              "w", "h", "label", "options"}
        if unknown:
            raise ManifestError(f"{row.get('id')}: unknown keys {sorted(unknown)}")
        elements.append(Element(
            id=row["id"], kind=row["kind"], x=int(row["x"]), y=int(row["y"]),
            instrument=row.get("instrument"), size=row.get("size"),
            w=row.get("w"), h=row.get("h"), label=row.get("label"),
            options=row.get("options") or {}))
    return Manifest(
        version=int(raw.get("version", 1)),
        canvas=raw["canvas"], regions=raw.get("regions", {}),
        groups=raw.get("groups", []), elements=elements,
        annunciator=raw["annunciator"], unplaced=raw.get("unplaced", {}) or {})


def validate(m: Manifest, table: ProtectionTable) -> list[str]:
    """Check the manifest against the installed contracts.

    Returns the list of problems; empty means valid. Returning rather than
    raising lets the server report every fault at once instead of the first.
    """
    problems: list[str] = []
    spec_names = {s.name for s in OBSERVATION_SPEC}
    action_keys = {a.key for a in ACTION_SCHEMA}
    # `shaft_rpm` is derived from `frequency` in displayunits, not a sensed
    # instrument; it is a legitimate gauge reference even though the core has
    # no such signal.
    derived = {"shaft_rpm"}

    seen: set[str] = set()
    for e in m.elements:
        if e.id in seen:
            problems.append(f"duplicate element id: {e.id}")
        seen.add(e.id)
        if e.kind not in KINDS:
            problems.append(f"{e.id}: unknown kind {e.kind!r} (want {sorted(KINDS)})")
        if e.x % GRID or e.y % GRID:
            problems.append(f"{e.id}: ({e.x},{e.y}) is off the {GRID} px grid")
        for name in e.instruments():
            if name not in spec_names and name not in derived:
                problems.append(f"{e.id}: no instrument {name!r} in ObservationSpec")
        for key in e.actions():
            if key not in action_keys:
                problems.append(f"{e.id}: no action {key!r} in ACTION_SCHEMA")

    problems += _check_coverage(m, spec_names)
    problems += _check_annunciator(m, table)
    problems += _check_bounds(m)
    problems += _check_overlaps(m)
    return problems


#: A gauge's footprint is bigger than its dial: the bezel rings it and an
#: engraved label plate sits underneath. Both must participate in the overlap
#: and bounds checks, or a plate silently lands on the row below.
GAUGE_BEZEL = 3
GAUGE_PLATE_H = 17


def _box(e: Element) -> tuple[int, int, int, int]:
    if e.kind == "gauge" and e.size:
        return (e.x - GAUGE_BEZEL, e.y - GAUGE_BEZEL,
                e.x + e.size + GAUGE_BEZEL,
                e.y + e.size + GAUGE_BEZEL + GAUGE_PLATE_H)
    w = e.w or e.size or 0
    h = e.h or e.size or 0
    return e.x, e.y, e.x + w, e.y + h


def _check_overlaps(m: Manifest) -> list[str]:
    """No two placed elements may occupy the same board area.

    §1 puts layout validation server-side precisely so a drawing mistake is a
    startup failure rather than something a human has to spot in a screenshot.
    """
    problems = []
    boxes = [(e.id, _box(e)) for e in m.elements]
    for i, (id_a, a) in enumerate(boxes):
        for id_b, b in boxes[i + 1:]:
            if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]:
                ox = min(a[2], b[2]) - max(a[0], b[0])
                oy = min(a[3], b[3]) - max(a[1], b[1])
                problems.append(
                    f"{id_a} overlaps {id_b} by {ox}x{oy} px")
    return problems


def _check_coverage(m: Manifest, spec_names: set[str]) -> list[str]:
    """Every instrument is placed, or explicitly unplaced with a reason."""
    problems = []
    placed = {n for e in m.elements for n in e.instruments()}
    for name in sorted(spec_names):
        if name in placed:
            if name in m.unplaced:
                problems.append(
                    f"{name}: both placed and listed under unplaced:")
            continue
        if name not in m.unplaced:
            problems.append(
                f"{name}: in ObservationSpec but neither placed nor listed "
                f"under unplaced: with a reason")
        elif not str(m.unplaced[name]).strip():
            problems.append(f"{name}: unplaced: entry needs a reason")
    for name in sorted(m.unplaced):
        if name not in spec_names:
            problems.append(f"unplaced: {name!r} is not in ObservationSpec")
    return problems


def _check_annunciator(m: Manifest, table: ProtectionTable) -> list[str]:
    """Grid must hold every protection-table window plus ~30% blank spares."""
    problems = []
    cells = int(m.annunciator["cols"]) * int(m.annunciator["rows"])
    needed = len(table.conditions)
    want = math.ceil(needed * (1.0 + SPARE_FRACTION))
    if cells < want:
        problems.append(
            f"annunciator grid holds {cells} windows; needs >= {want} "
            f"({needed} conditions + {int(SPARE_FRACTION * 100)}% spares)")
    return problems


def _check_bounds(m: Manifest) -> list[str]:
    """Nothing may be placed off the canvas."""
    problems = []
    cw, ch = int(m.canvas["width"]), int(m.canvas["height"])
    for e in m.elements:
        w = e.w or e.size or 0
        h = e.h or e.size or 0
        if e.x < 0 or e.y < 0 or e.x + w > cw or e.y + h > ch:
            problems.append(
                f"{e.id}: ({e.x},{e.y})+({w}x{h}) outside canvas {cw}x{ch}")
    return problems


def load_validated(path: str | Path | None, table: ProtectionTable) -> Manifest:
    """Load and validate; raises with every problem listed (server startup)."""
    m = load(path)
    problems = validate(m, table)
    if problems:
        raise ManifestError(
            f"{len(problems)} manifest problem(s):\n  " + "\n  ".join(problems))
    return m
