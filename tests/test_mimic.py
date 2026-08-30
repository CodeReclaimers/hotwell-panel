"""Mimic-completeness gate: validate the hand-authored one-line
(client/src/board.svg) against the installed hotwell's contracts and its own
geometry.

Two real omissions motivated this (progress-20260830): the LCV was never
drawn, and the condenser sat off the exhaust run with the line passing under
its corner. Checking for those two instances would re-ship the blind spot, so:

* the required-symbol set is DERIVED from the plant config — every top-level
  config section and every network valve/actuator must be drawn or explicitly
  waived with a reason, so a future core release that adds one fails here
  until the drawing catches up (the same closure design as the manifest
  coverage check);
* connectivity is geometric — every flow-line/pipe/shaft endpoint must land
  on a symbol, another line, or a labeled terminal, so a symbol that drifts
  off its line fails no matter which symbol it is.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from hotwell.plant import PUMP_NAMES, load_config
from hotwell.sensors import OBSERVATION_SPEC
from hotwell.simulator import Simulator

BOARD = Path("client/src/board.svg")
SYMBOL_CLASSES = ("vessel", "pump", "valve", "machine", "sv-stack", "breaker-sym")
LINE_CLASSES = ("flow-line", "pipe", "shaft")
TOL = 2.0            # px: endpoint-to-symbol/line tolerance
TEXT_TOL = (16.0, 10.0)  # px: looser box around a labeled terminal (e.g. BUS)

# Config sections / keys with deliberately NO mimic symbol. Every waiver
# carries its reason; an unmapped, unwaived key fails the coverage test.
WAIVED = {
    "design": "parameter block, not a component",
    "firing": "burner/furnace is not on the flow path; firing shows on its gauge",
    "actuators.firing": "same as `firing`",
    "audit": "bookkeeping, not hardware",
    "control": "loops live on the M/A stations, not the one-line",
    "pumps": "pump SYMBOLS are covered by the data-pump test below",
}


# ------------------------------------------------------------------ parsing


def load_board(path: Path = BOARD):
    """Parse the SVG fragment (wrapped exactly the way the client inlines it)."""
    root = ET.fromstring(f'<svg xmlns="http://www.w3.org/2000/svg">'
                         f"{path.read_text()}</svg>")
    return root


def classes(el) -> set[str]:
    return set((el.get("class") or "").split())


def walk(root):
    yield from root.iter()


def parse_path(d: str) -> list[list[tuple[float, float]]]:
    """Absolute M/L/H/V/Z path -> list of polylines (one per subpath).

    The mimic uses only these commands; anything else must extend this parser
    rather than silently escaping the geometry check.
    """
    tokens = re.findall(r"[A-Za-z]|-?\d+\.?\d*", d)
    polys: list[list[tuple[float, float]]] = []
    cur: list[tuple[float, float]] = []
    x = y = 0.0
    i = 0
    while i < len(tokens):
        cmd = tokens[i]
        assert cmd in "MLHVZ", f"unsupported path command {cmd!r} in {d!r}"
        i += 1
        if cmd == "Z":
            if cur:
                cur.append(cur[0])
            continue
        while i < len(tokens) and not tokens[i].isalpha():
            if cmd == "M":
                x, y = float(tokens[i]), float(tokens[i + 1])
                i += 2
                if cur:
                    polys.append(cur)
                cur = [(x, y)]
                cmd = "L"  # subsequent pairs are implicit LineTos
                continue
            if cmd == "L":
                x, y = float(tokens[i]), float(tokens[i + 1])
                i += 2
            elif cmd == "H":
                x = float(tokens[i])
                i += 1
            else:  # V
                y = float(tokens[i])
                i += 1
            cur.append((x, y))
    if cur:
        polys.append(cur)
    return polys


def bbox_of(el) -> tuple[float, float, float, float] | None:
    """(xmin, ymin, xmax, ymax) for rect / circle / path symbols."""
    tag = el.tag.split("}")[-1]
    if tag == "rect":
        x, y = float(el.get("x")), float(el.get("y"))
        return (x, y, x + float(el.get("width")), y + float(el.get("height")))
    if tag == "circle":
        cx, cy, r = (float(el.get(a)) for a in ("cx", "cy", "r"))
        return (cx - r, cy - r, cx + r, cy + r)
    if tag == "path":
        pts = [p for poly in parse_path(el.get("d")) for p in poly]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        return (min(xs), min(ys), max(xs), max(ys))
    if tag == "g":  # symbol group (e.g. valve, breaker-sym): union of children
        boxes = [b for c in el if (b := bbox_of(c)) is not None]
        if not boxes:
            return None
        return (min(b[0] for b in boxes), min(b[1] for b in boxes),
                max(b[2] for b in boxes), max(b[3] for b in boxes))
    return None


def collect(root):
    """Symbols (class -> [(el, bbox)]), lines [(el, polylines)], texts."""
    symbols: dict[str, list] = {c: [] for c in SYMBOL_CLASSES}
    lines = []
    texts = []
    for el in walk(root):
        cls = classes(el)
        tag = el.tag.split("}")[-1]
        for c in SYMBOL_CLASSES:
            if c in cls and tag != "text":
                box = bbox_of(el)
                if box:
                    symbols[c].append((el, box))
        if cls & set(LINE_CLASSES) and tag == "path":
            lines.append((el, parse_path(el.get("d"))))
        if tag == "text":
            texts.append(((el.text or "").strip(),
                          float(el.get("x")), float(el.get("y")), cls))
    return symbols, lines, texts


# ------------------------------------------------------------------ fixtures


@pytest.fixture(scope="module")
def board():
    return collect(load_board())


@pytest.fixture(scope="module")
def contracts():
    sim = Simulator(seed=0)
    obs = sim.initialize_steady_state(60.0)
    return {
        "indications": set(obs.indications),
        "instruments": {s.name for s in OBSERVATION_SPEC},
        "cfg": load_config(),
    }


# ------------------------------------------------------------------- tests


def test_every_pump_in_the_network_is_drawn(board):
    symbols, _, _ = board
    drawn = {el.get("data-pump") for el, _ in symbols["pump"]}
    print(f"\n  data-pump symbols: {sorted(drawn)}")
    assert drawn == set(PUMP_NAMES), (
        f"mimic pumps {sorted(drawn)} != plant pumps {sorted(PUMP_NAMES)}")


def test_data_hooks_name_real_contract_keys(board, contracts):
    _, _, _ = board
    root = load_board()
    hooks = {"data-pump": set(PUMP_NAMES),
             "data-indication": contracts["indications"],
             "data-flow": contracts["instruments"]}
    checked = 0
    for el in walk(root):
        for attr, valid in hooks.items():
            v = el.get(attr)
            if v is not None:
                checked += 1
                assert v in valid, f"{attr}={v!r} names nothing in the contract"
    print(f"\n  {checked} data-* hooks all name live contract keys")
    assert checked >= 8  # pumps + flows + indications actually present


def test_flow_network_components_all_drawn_or_waived(board, contracts):
    """Coverage derived from the config: new hardware fails until drawn."""
    symbols, _, texts = board
    labels = {t for t, _, _, _ in texts}
    cfg = contracts["cfg"]

    # requirement -> how it must appear on the one-line
    text_of = {
        "drum": ["DRUM"], "turbine": ["TURB"], "rotor": ["GEN"],
        "condenser": ["COND", "HOTWELL"], "deaerator": ["DA"],
        "loads": ["BUS"],
        "network.cv_lcv": ["LCV"], "network.cv_frv": ["FRV"],
        "actuators.throttle": ["THR"], "actuators.fw_valve": ["FRV"],
    }
    class_of = {"safety_valve": "sv-stack"}

    requirements = list(cfg.keys())
    requirements += [f"network.{k}" for k in cfg["network"] if k.startswith("cv_")]
    requirements += [f"actuators.{k}" for k in cfg["actuators"]]

    missing, covered = [], 0
    for req in requirements:
        if req in ("network", "actuators"):
            continue  # expanded into their subkeys above
        if req in WAIVED:
            continue
        if req in text_of:
            for want in text_of[req]:
                if want not in labels:
                    missing.append(f"{req}: label {want!r} not on the board")
                else:
                    covered += 1
        elif req in class_of:
            if not symbols[class_of[req]]:
                missing.append(f"{req}: no .{class_of[req]} symbol")
            else:
                covered += 1
        else:
            missing.append(f"{req}: config key has no mapping and no waiver — "
                           f"draw it (add to text_of/class_of) or waive it "
                           f"with a reason")
    print(f"\n  {covered} required symbols present, {len(WAIVED)} waived")
    assert not missing, "\n".join(missing)


def _near_box(p, box, tol):
    return (box[0] - tol <= p[0] <= box[2] + tol
            and box[1] - tol <= p[1] <= box[3] + tol)


def _seg_dist(p, a, b):
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    if dx == dy == 0.0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    cx, cy = ax + t * dx, ay + t * dy
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5


def test_every_line_endpoint_lands_on_something(board):
    """The condenser bug, generalized: no line may end in mid-air."""
    symbols, lines, texts = board
    boxes = [box for c in SYMBOL_CLASSES for _, box in symbols[c]]
    dangling = []
    for li, (el, polys) in enumerate(lines):
        for poly in polys:
            for p in (poly[0], poly[-1]):
                if any(_near_box(p, box, TOL) for box in boxes):
                    continue
                if any(_seg_dist(p, a, b) <= TOL
                       for lj, (_, other) in enumerate(lines) if lj != li
                       for op in other
                       for a, b in zip(op, op[1:], strict=False)):
                    continue
                if any("tag" in cls and abs(p[0] - tx) <= TEXT_TOL[0]
                       and abs(p[1] - ty) <= TEXT_TOL[1]
                       for _, tx, ty, cls in texts):
                    continue
                dangling.append(
                    f"{'/'.join(sorted(classes(el)))} endpoint at {p} "
                    f"touches no symbol, line, or terminal")
    n_ends = sum(2 * len(polys) for _, polys in lines)
    print(f"\n  {len(lines)} lines, {n_ends} endpoints checked, "
          f"{len(dangling)} dangling")
    assert not dangling, "\n".join(dangling)
