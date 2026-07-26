"""§12.3 — manifest validation, including the full-coverage check.

Because this runs against the *installed* `hotwell`'s live contracts, it is
also the cross-repo compatibility gate: a core release that renames an
instrument, drops an action or adds a protection condition fails here first.
"""
from __future__ import annotations

import pytest
import yaml
from hotwell.actions import ACTION_SCHEMA
from hotwell.protection.tables import load_protection_table
from hotwell.sensors import OBSERVATION_SPEC

from hotwell_panel import manifest as M

TABLE = load_protection_table()


@pytest.fixture(scope="module")
def m():
    return M.load()


def test_shipped_manifest_is_valid(m):
    problems = M.validate(m, TABLE)
    for p in problems:
        print("  -", p)
    assert problems == []
    print(f"\n  {len(m.elements)} elements, {len(m.groups)} groups, "
          f"canvas {m.canvas['width']}x{m.canvas['height']}")


def test_every_instrument_is_placed_or_excused(m):
    """§6.1 coverage — the rule that keeps the drawing honest."""
    placed = {n for e in m.elements for n in e.instruments()}
    spec = {s.name for s in OBSERVATION_SPEC}
    unaccounted = spec - placed - set(m.unplaced)
    assert not unaccounted, f"instruments with no home: {sorted(unaccounted)}"
    print(f"\n  {len(spec & placed)}/{len(spec)} instruments placed, "
          f"{len(m.unplaced)} excused")


def test_all_action_references_exist(m):
    keys = {a.key for a in ACTION_SCHEMA}
    used = {k for e in m.elements for k in e.actions()}
    assert used <= keys, sorted(used - keys)
    # The 0.2.0 manual trips must actually be on the board (§13 P2).
    assert {"trips.manual_mft", "trips.manual_turbine"} <= used
    print(f"\n  {len(used)} distinct actions referenced")


def test_annunciator_grid_has_room_for_spares(m):
    cells = m.annunciator["cols"] * m.annunciator["rows"]
    need = len(TABLE.conditions)
    assert cells >= need * 1.3
    print(f"\n  {cells} windows for {need} conditions "
          f"({100 * (cells - need) / need:.0f}% spare)")


def test_every_pump_has_a_grip(m):
    grips = {e.options.get("pump") for e in m.elements if e.kind == "grip"}
    assert grips == {"cp1", "cp2", "fp1", "fp2"}, grips


def test_four_controller_stations_one_per_loop(m):
    """§6.3: three loop stations plus the governor."""
    loops = [e.options.get("loop") for e in m.elements if e.kind == "station"]
    assert sorted(loops) == ["da_level", "drum_level", "drum_pressure",
                             "governor"]
    lvl = next(e for e in m.elements if e.id == "station_drum_level")
    assert lvl.options["element_mode_lamp"] is True, \
        "§6.3: drum-level station shows the 1E/3E element mode"


# ----------------------------------------------------- validator behaviour


def _write(tmp_path, mutate):
    raw = yaml.safe_load((M.DEFAULT_PATH).read_text())
    mutate(raw)
    p = tmp_path / "m.yaml"
    p.write_text(yaml.safe_dump(raw))
    return p


def _by_id(raw, eid):
    """Target elements by id: index-based fixtures broke the moment the
    annunciator control buttons were prepended to the list."""
    return next(e for e in raw["elements"] if e["id"] == eid)


def test_unknown_instrument_is_caught(tmp_path):
    def mutate(raw):
        _by_id(raw, "gauge_hotwell_level")["instrument"] = "not_an_instrument"
    problems = M.validate(M.load(_write(tmp_path, mutate)), TABLE)
    assert any("not_an_instrument" in p for p in problems), problems


def test_unknown_action_is_caught(tmp_path):
    def mutate(raw):
        for e in raw["elements"]:
            if e["id"] == "grip_cp1":
                e["options"]["start_action"] = "cp1.launch"
    problems = M.validate(M.load(_write(tmp_path, mutate)), TABLE)
    assert any("cp1.launch" in p for p in problems), problems


def test_dropping_an_instrument_fails_coverage(tmp_path):
    """The check that would catch a gauge quietly disappearing."""
    def mutate(raw):
        raw["elements"] = [e for e in raw["elements"]
                           if e.get("instrument") != "hotwell_level"]
    problems = M.validate(M.load(_write(tmp_path, mutate)), TABLE)
    assert any("hotwell_level" in p and "unplaced" in p for p in problems), \
        problems


def test_unplaced_without_a_reason_is_caught(tmp_path):
    def mutate(raw):
        raw["elements"] = [e for e in raw["elements"]
                           if e.get("instrument") != "hotwell_level"]
        raw["unplaced"] = {"hotwell_level": "  "}
    problems = M.validate(M.load(_write(tmp_path, mutate)), TABLE)
    assert any("needs a reason" in p for p in problems), problems


def test_placed_and_unplaced_is_contradictory(tmp_path):
    def mutate(raw):
        raw["unplaced"] = {"hotwell_level": "shown elsewhere"}
    problems = M.validate(M.load(_write(tmp_path, mutate)), TABLE)
    assert any("both placed and listed" in p for p in problems), problems


def test_overlap_is_caught(tmp_path):
    def mutate(raw):
        for e in raw["elements"]:
            if e["id"] == "gauge_condensate_flow":
                e["x"], e["y"] = 16, 248      # on top of gauge_hotwell_level
    problems = M.validate(M.load(_write(tmp_path, mutate)), TABLE)
    assert any("overlaps" in p for p in problems), problems


def test_off_canvas_is_caught(tmp_path):
    def mutate(raw):
        _by_id(raw, "gauge_hotwell_level")["x"] = 1592
    problems = M.validate(M.load(_write(tmp_path, mutate)), TABLE)
    assert any("outside canvas" in p for p in problems), problems


def test_off_grid_is_caught(tmp_path):
    def mutate(raw):
        _by_id(raw, "gauge_hotwell_level")["y"] = 249    # §10: 8 px grid
    problems = M.validate(M.load(_write(tmp_path, mutate)), TABLE)
    assert any("off the 8 px grid" in p for p in problems), problems


def test_shrinking_the_annunciator_grid_is_caught(tmp_path):
    def mutate(raw):
        raw["annunciator"]["rows"] = 3        # 18 cells < 19 conditions
    problems = M.validate(M.load(_write(tmp_path, mutate)), TABLE)
    assert any("annunciator grid" in p for p in problems), problems


def test_load_validated_raises_with_every_problem(tmp_path):
    """Startup reports all faults at once, not just the first."""
    def mutate(raw):
        _by_id(raw, "gauge_hotwell_level")["instrument"] = "nope"
        _by_id(raw, "gauge_condensate_flow")["y"] = 249
    with pytest.raises(M.ManifestError) as exc:
        M.load_validated(_write(tmp_path, mutate), TABLE)
    msg = str(exc.value)
    print(f"\n  {msg}")
    # Three, not two: renaming an instrument also orphans the real one from
    # the coverage check, which is the validator working as intended.
    assert "3 manifest problem(s)" in msg
    assert "no instrument 'nope'" in msg
    assert "off the 8 px grid" in msg
    assert "neither placed nor listed" in msg


def test_a_broken_manifest_fails_server_startup(tmp_path):
    """§12.3's real claim: the gate is wired, not merely available.

    `create_app` -> `PanelAssets.build` -> `load_validated`, so a contract
    mismatch must stop the server rather than producing a subtly wrong board.
    """
    from hotwell_panel.server import create_app
    from hotwell_panel.session import SimSession

    def mutate(raw):
        _by_id(raw, "gauge_drum_level")["instrument"] = "gone_from_the_core"
    bad = _write(tmp_path, mutate)
    with pytest.raises(M.ManifestError, match="gone_from_the_core"):
        create_app(SimSession(sessions_dir=tmp_path), manifest_path=bad)
