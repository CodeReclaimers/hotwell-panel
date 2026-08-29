"""§12.5 — one browser smoke test. Dev-optional; skips cleanly when absent.

Everything else in the suite tests the server. This is the only test that
proves the *page* works: that hello arrives, faces install, needles actually
move against live frames, and an alarm reaches an annunciator window.

It runs uvicorn in a background thread rather than a subprocess so a failure
surfaces as a normal traceback.
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

# §12.6: the smoke test runs against the BUILT client served by server.py.
if not (DIST / "index.html").is_file():
    pytest.skip("client/dist not built (cd client && npm run build)",
                allow_module_level=True)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    port = _free_port()
    session = SimSession(local_scenarios=Path("scenarios"),
                         sessions_dir=tmp_path_factory.mktemp("sessions"))
    app = create_app(session, scenario="builtin:cp1_trip_unrecovered")
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    srv = uvicorn.Server(config)
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    assert srv.started, "uvicorn did not start"
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="module")
def page(server):
    with playwright_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:                      # no browser downloaded
            pytest.skip(f"chromium unavailable: {exc}")
        pg = browser.new_page(viewport={"width": 1600, "height": 940})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(server, wait_until="networkidle")
        pg.wait_for_function("window.panel && window.panel.store.hello !== null",
                             timeout=15000)
        pg.errors = errors
        yield pg
        browser.close()


def test_page_loads_and_receives_hello(page):
    info = page.evaluate("""() => ({
        hotwell: window.panel.store.hello.hotwell_version,
        protocol: window.panel.store.hello.protocol_version,
        gauges: window.panel.gauges.count(),
        windows: window.panel.annunciator.count(),
        faces_in_hello: Object.keys(window.panel.store.hello.gauge_faces).length,
        faces_in_dom: document.querySelectorAll(
            '#layer-elements .gauge [id^="face-"]').length,
        elements: document.querySelectorAll('#layer-elements > g').length,
    })""")
    print(f"\n  {info}")
    assert info["protocol"] == 1
    assert info["gauges"] == 17
    assert info["windows"] == 19          # one per protection-table condition
    # §5.2 (Svelte migration): every generated face arrives in hello; the DOM
    # carries one {@html}-injected face per PLACED gauge, not a shared defs.
    assert info["faces_in_hello"] == 23
    assert info["faces_in_dom"] == 17
    assert info["elements"] == 39   # 35 board devices + 4 annunciator controls
    assert page.errors == [], page.errors


def test_display_values_match_the_plan_anchors(page):
    """The §5.1 anchors, read off the live board rather than a unit test."""
    vals = page.evaluate("""() => ({
        drum_pressure: window.panel.store.formatted('drum_pressure'),
        da_pressure: window.panel.store.formatted('da_pressure'),
        feed_flow: window.panel.store.formatted('feed_flow'),
        steam_flow: window.panel.store.formatted('steam_flow'),
        mw_out: window.panel.store.formatted('mw_out'),
    })""")
    print(f"\n  on-board readings: {vals}")
    assert vals["drum_pressure"] == "1146"     # 8.0 MPa
    assert vals["da_pressure"] == "7.1"        # 0.15 MPa
    assert vals["feed_flow"] == "691"          # 87.1 kg/s sensed
    # 610, not the plan's 611. The steam-flow instrument quantizes to 0.1 kg/s
    # (ObservationSpec), so the panel is handed 76.9 and never the achieved
    # 76.923; 76.9 klb/hr-converts to 610.3. The plan's 611 requires the
    # unquantized truth, which no panel can see. See test_displayunits.
    assert vals["steam_flow"] == "610"
    assert vals["mw_out"] == "60.0"


def test_a_needle_transform_changes_across_frames(page):
    page.evaluate("window.panel.conn.instructor('run')")
    before = page.evaluate(
        "document.querySelector('[data-instrument=\"drum_level\"] "
        ".needle-group').getAttribute('transform')")
    page.evaluate("window.panel.conn.instructor('inject_event',"
                  " {event: 'trip_pump', params: {target: 'cp1'}})")
    page.wait_for_timeout(2500)
    after = page.evaluate(
        "document.querySelector('[data-instrument=\"drum_level\"] "
        ".needle-group').getAttribute('transform')")
    tick = page.evaluate("window.panel.store.frame.tick")
    print(f"\n  drum_level needle {before} -> {after} (tick {tick})")
    assert tick > 0, "sim did not advance"
    assert before != after, "needle did not move"


def test_annunciator_window_lights_on_an_alarm(page):
    """Force a fast alarm with a sensor fault and watch the window light."""
    page.evaluate("window.panel.conn.instructor('run')")
    page.evaluate("""window.panel.conn.instructor('inject_event', {
        event: 'sensor_fault',
        params: {target: 'drum_level', kind: 'bias', bias: -0.25}
    })""")
    page.wait_for_function(
        """() => {
            const g = document.querySelector('[data-alarm="DRUM_LVL_LO"]');
            return g && g.classList.contains('lit');
        }""", timeout=20000)
    state = page.evaluate("""() => {
        const g = document.querySelector('[data-alarm="DRUM_LVL_LO"]');
        return {cls: g.getAttribute('class'),
                alarm: window.panel.store.frame.alarms['DRUM_LVL_LO']};
    }""")
    print(f"\n  DRUM_LVL_LO window: {state}")
    assert "lit" in state["cls"]
    assert "flash-fast" in state["cls"], "a new alarm must fast-flash (§7)"
    assert state["alarm"] == "active"
    assert page.errors == [], page.errors
