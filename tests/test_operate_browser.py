"""P2 — operating the board from a browser. The automatable parts of §12.6.

The split matters: these tests drive the *controls* and assert that the right
action reaches the core and the right indication comes back. The *physics* of
the checklist items — that starting CP-2 in time actually saves the plant, that
the cascade runs in the documented order — is asserted server-side in
`test_casualty_sequence.py`, where it can run at full speed without a browser.

What is NOT covered here, and stays a manual gate in HANDOFF.md: hearing the
horn, judging shrink/swell on the recorder by eye, and 30 minutes of continuous
running without jank.
"""
from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import pytest

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="playwright not installed (dev-optional)")

import uvicorn  # noqa: E402

from hotwell_panel.server import DIST, create_app  # noqa: E402
from hotwell_panel.session import SimSession  # noqa: E402

if not (DIST / "index.html").is_file():
    pytest.skip("client/dist not built (cd client && npm run build)",
                allow_module_level=True)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def board(tmp_path):
    """A fresh server + page per test: these mutate plant state irreversibly."""
    port = _free_port()
    session = SimSession(local_scenarios=Path("scenarios"),
                         sessions_dir=tmp_path)
    app = create_app(session, scenario="builtin:cp1_trip_unrecovered")
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port,
                                        log_level="error"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    assert srv.started
    with playwright_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:
            pytest.skip(f"chromium unavailable: {exc}")
        pg = browser.new_page(viewport={"width": 1600, "height": 940})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(f"http://127.0.0.1:{port}", wait_until="networkidle")
        pg.wait_for_function("window.panel && window.panel.store.hello !== null",
                             timeout=15000)
        pg.evaluate("window.panel.conn.instructor('run')")
        pg.errors = errors
        yield pg, session
        browser.close()
    srv.should_exit = True
    thread.join(timeout=5)


def drag_grip(page, element_id, direction):
    """Throw a pistol grip and release: the action fires on release (§6.2)."""
    box = page.locator(f'[data-element="{element_id}"] .grip-hit').bounding_box()
    x = box["x"] + (box["width"] * (0.8 if direction == "start" else 0.2))
    y = box["y"] + box["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.wait_for_timeout(80)
    page.mouse.up()


# ------------------------------------------------------- (b) pistol grips


def test_pistol_grip_starts_the_standby_pump(board):
    """§12.6(b) control half: gripping CP-2 to START runs the standby pump."""
    page, session = board
    assert page.evaluate(
        "window.panel.store.frame.indications.cp2_running") is False
    drag_grip(page, "grip_cp2", "start")
    page.wait_for_function(
        "() => window.panel.store.frame.indications.cp2_running === true",
        timeout=10000)
    lamp = page.get_attribute('[data-element="grip_cp2"] .lamp-lens', "class")
    print(f"\n  CP-2 lamp after start: {lamp!r}")
    assert "red" in lamp, "a running pump shows RED (power plant convention)"
    assert session.sim.disc.pump_modes["cp2"] == "running"
    assert page.errors == []


def test_pistol_grip_stops_a_running_pump(board):
    page, session = board
    drag_grip(page, "grip_cp1", "stop")
    page.wait_for_function(
        "() => window.panel.store.frame.indications.cp1_running === false",
        timeout=10000)
    lamp = page.get_attribute('[data-element="grip_cp1"] .lamp-lens', "class")
    print(f"\n  CP-1 lamp after stop: {lamp!r}")
    assert "green" in lamp, "a stopped pump shows GREEN"


# ------------------------------------------- (f) rejections reach the log


def test_rejected_action_prints_its_reason_in_the_soe_log(board):
    """§12.6(f), verbatim from the core."""
    page, _ = board
    drag_grip(page, "grip_cp1", "start")           # already running -> reject
    page.wait_for_function(
        """() => [...document.querySelectorAll('.soe-lines text')]
                 .some(n => n.textContent.includes('REJECTED'))""",
        timeout=10000)
    line = page.evaluate(
        """() => [...document.querySelectorAll('.soe-lines text')]
                 .map(n => n.textContent)
                 .find(t => t.includes('REJECTED'))""")
    print(f"\n  SOE: {line!r}")
    assert "cp1 is running, not stopped" in line
    assert "cp1.start" in line


# ------------------------------- (c) annunciator: flash, silence, ack, reset


def force_alarm(page):
    """Bias the drum-level sensor low enough to raise DRUM_LVL_LO in 2 s."""
    page.evaluate("""window.panel.conn.instructor('inject_event', {
        event: 'sensor_fault',
        params: {target: 'drum_level', kind: 'bias', bias: -0.25}})""")
    page.wait_for_function(
        """() => {const g = document.querySelector('[data-alarm="DRUM_LVL_LO"]');
                  return g && g.classList.contains('flash-fast');}""",
        timeout=20000)


def test_new_alarm_fast_flashes_and_sounds_the_horn(board):
    page, _ = board
    page.evaluate("window.panel.audio.unlock()")
    force_alarm(page)
    state = page.evaluate("""() => ({
        cls: document.querySelector('[data-alarm="DRUM_LVL_LO"]').getAttribute('class'),
        horn: window.panel.audio.isSounding(),
        flashing: window.panel.annunciator.flashing()})""")
    print(f"\n  {state}")
    assert "flash-fast" in state["cls"]
    assert state["horn"] is True
    assert "DRUM_LVL_LO" in state["flashing"]


def test_silence_stops_the_horn_but_leaves_the_window_flashing(board):
    """The ISA sequence: SILENCE is not ACK (§7)."""
    page, _ = board
    page.evaluate("window.panel.audio.unlock()")
    force_alarm(page)
    page.click('[data-element="button_ann_silence"] .push-face')
    state = page.evaluate("""() => ({
        cls: document.querySelector('[data-alarm="DRUM_LVL_LO"]').getAttribute('class'),
        horn: window.panel.audio.isSounding()})""")
    print(f"\n  after SILENCE: {state}")
    assert state["horn"] is False, "SILENCE must stop the horn"
    assert "flash-fast" in state["cls"], "flashing must continue after SILENCE"


def test_acknowledge_takes_the_window_steady_and_reaches_the_core(board):
    page, session = board
    page.evaluate("window.panel.audio.unlock()")
    force_alarm(page)
    page.click('[data-element="button_ann_ack"] .push-face')
    page.wait_for_function(
        "() => window.panel.store.frame.alarms.DRUM_LVL_LO === 'acknowledged'",
        timeout=10000)
    cls = page.get_attribute('[data-alarm="DRUM_LVL_LO"]', "class")
    print(f"\n  after ACK: {cls!r}; core state "
          f"{dict(session.sim.last_obs.alarms)['DRUM_LVL_LO']}")
    assert "lit" in cls and "flash-fast" not in cls
    # The core tracks acknowledged state — the panel is not faking it.
    assert dict(session.sim.last_obs.alarms)["DRUM_LVL_LO"] == "acknowledged"


def test_ringback_then_reset_returns_the_window_to_dark(board):
    """Cleared while acked -> slow flash until RESET (§7)."""
    page, _ = board
    page.evaluate("window.panel.audio.unlock()")
    force_alarm(page)
    page.click('[data-element="button_ann_ack"] .push-face')
    page.wait_for_function(
        "() => window.panel.store.frame.alarms.DRUM_LVL_LO === 'acknowledged'",
        timeout=10000)
    # Remove the fault: the condition clears while acknowledged.
    page.evaluate("""window.panel.conn.instructor('inject_event', {
        event: 'sensor_fault',
        params: {target: 'drum_level', kind: 'bias', bias: 0.0}})""")
    page.wait_for_function(
        """() => document.querySelector('[data-alarm="DRUM_LVL_LO"]')
                 .classList.contains('flash-slow')""", timeout=15000)
    print("\n  ringback: slow flash after the condition cleared")
    page.click('[data-element="button_ann_reset"] .push-face')
    cls = page.get_attribute('[data-alarm="DRUM_LVL_LO"]', "class")
    print(f"  after RESET: {cls!r}")
    assert "flash-slow" not in cls and "lit" not in cls


def test_lamp_test_lights_every_window_while_held(board):
    page, _ = board
    lit_before = page.evaluate(
        "document.querySelectorAll('.ann-window-group.lit').length")
    page.hover('[data-element="button_ann_lamptest"] .push-face')
    page.mouse.down()
    lit_held = page.evaluate(
        "document.querySelectorAll('.ann-window-group.lit').length")
    page.mouse.up()
    lit_after = page.evaluate(
        "document.querySelectorAll('.ann-window-group.lit').length")
    print(f"\n  lit windows: {lit_before} -> held {lit_held} -> {lit_after}")
    assert lit_held == 19, "every protection-table window lights (§7)"
    assert lit_after == lit_before


# --------------------------------------------- (e) covered manual trips


def test_manual_turbine_trip_needs_the_cover_lifted_then_kills_the_bus(board):
    """§12.6(e). The guard is not decoration: one click must not trip a plant."""
    page, session = board
    face = '[data-element="button_manual_turbine"] .push-face'
    assert "guarded" in page.get_attribute(face, "class")
    page.click(face)                                   # lifts the cover only
    page.wait_for_timeout(200)
    assert session.sim.disc.turbine_trip is False, \
        "lifting the cover must not trip the turbine"
    assert "armed" in page.get_attribute(face, "class")

    page.click(face)                                   # now it acts
    page.wait_for_function(
        "() => window.panel.store.frame.indications.turbine_trip === true",
        timeout=10000)
    ind = page.evaluate("window.panel.store.frame.indications")
    print(f"\n  after manual turbine trip: breaker_closed="
          f"{ind['breaker_closed']}, cp1_running={ind['cp1_running']}, "
          f"fp1_running={ind['fp1_running']}")
    assert ind["breaker_closed"] is False, "the bus must go dead (D10)"
    assert ind["cp1_running"] is False and ind["fp1_running"] is False
    labels = [lbl for _, lbl in session.sim.engine.first_out]
    assert labels[0] == "MANUAL_TURBINE_TRIP", labels
    # and it reaches the FIRST OUT plate
    fo = page.text_content(".fo-value")
    print(f"  FIRST OUT plate: {fo!r}")
    assert "MANUAL_TURBINE_TRIP" in fo


def test_first_out_plate_shows_a_label_with_no_annunciator_window(board):
    """`CP1_TRIP:overload` is a free-form first-out label, not a table id.

    The plate exists precisely so the initiating event of the canonical
    casualty is visible even though no window can light for it.
    """
    page, _ = board
    page.evaluate("""window.panel.conn.instructor('inject_event', {
        event: 'trip_pump', params: {target: 'cp1', reason: 'overload'}})""")
    page.wait_for_function(
        "() => !document.querySelector('.fo-value').textContent.includes('NONE')",
        timeout=10000)
    fo = page.text_content(".fo-value")
    print(f"\n  FIRST OUT plate: {fo!r}")
    assert "CP1_TRIP:overload" in fo
    # No window carries that id — which is the whole point of the plate.
    assert page.evaluate(
        """document.querySelector('[data-alarm="CP1_TRIP:overload"]')""") is None


def test_grips_are_operable_from_the_keyboard(board):
    """§6.2: 'click-and-hold left/right **or** keyboard'."""
    page, session = board
    hit = '[data-element="grip_cp2"] .grip-hit'
    page.focus(hit)
    page.keyboard.down("ArrowRight")            # throw to START
    thrown = page.get_attribute('[data-element="grip_cp2"] .grip-handle',
                                "transform")
    page.keyboard.up("ArrowRight")              # spring return fires the action
    centred = page.get_attribute('[data-element="grip_cp2"] .grip-handle',
                                 "transform")
    page.wait_for_function(
        "() => window.panel.store.frame.indications.cp2_running === true",
        timeout=10000)
    print(f"\n  handle {thrown} -> {centred}; CP-2 running")
    assert "rotate(38" in thrown, "Right arrow must throw the grip to START"
    assert "rotate(0" in centred, "and it must spring back to NORM on release"
    assert session.sim.disc.pump_modes["cp2"] == "running"


def test_keyboard_grip_stop_uses_the_left_arrow(board):
    page, session = board
    page.focus('[data-element="grip_cp1"] .grip-hit')
    page.keyboard.down("ArrowLeft")
    page.keyboard.up("ArrowLeft")
    page.wait_for_function(
        "() => window.panel.store.frame.indications.cp1_running === false",
        timeout=10000)
    assert session.sim.disc.pump_modes["cp1"] == "stopped"
