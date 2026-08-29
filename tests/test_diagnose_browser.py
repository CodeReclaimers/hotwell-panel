"""P3 — chart recorders and the instructor station in a browser.

The visual half of §12.6(d) — judging shrink/swell by eye on the paper — stays
a manual gate. What is asserted here is that recorder 1 actually carries the
three signals that make it legible, that its trace is the historian's data and
not something the client invented, and that every instructor control reaches
the simulator.
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
    port = _free_port()
    session = SimSession(local_scenarios=Path("scenarios"), sessions_dir=tmp_path)
    app = create_app(session, scenario="builtin:load_step")
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
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(f"http://127.0.0.1:{port}", wait_until="networkidle")
        pg.wait_for_function("window.panel && window.panel.store.hello !== null",
                             timeout=15000)
        pg.evaluate("window.panel.conn.instructor('speed', {speed: 5})")
        pg.evaluate("window.panel.conn.instructor('run')")
        pg.errors = errors
        yield pg, session
        browser.close()
    srv.should_exit = True
    thread.join(timeout=5)


# ------------------------------------------------------ chart recorders


def test_recorder_one_is_the_shrink_swell_set(board):
    """§8.1: drum level, feed flow, steam flow on the same paper."""
    page, _ = board
    page.wait_for_function(
        """() => document.querySelectorAll(
             '[data-element="chart_recorder_1"] .pen-select')[0].options.length > 1""",
        timeout=20000)
    pens = page.evaluate(
        """() => [...document.querySelectorAll(
             '[data-element="chart_recorder_1"] .pen-select')].map(n => n.value)""")
    print(f"\n  recorder 1 pens: {pens}")
    assert pens == ["drum_level", "feed_flow", "steam_flow"]


def test_traces_backfill_from_the_historian(board):
    """The pen must draw history, not just what arrived since page load."""
    page, session = board
    page.wait_for_function(
        """() => {const p = document.querySelector(
              '[data-element="chart_recorder_1"] .chart-pen-1');
            return p && (p.getAttribute('d') || '').length > 200;}""",
        timeout=30000)
    info = page.evaluate("""() => ({
        d_len: document.querySelector(
          '[data-element="chart_recorder_1"] .chart-pen-1')
          .getAttribute('d').length,
        recorders: window.panel.charts.count(),
        t: window.panel.store.frame.t})""")
    print(f"\n  {info}")
    assert info["recorders"] == 2
    assert info["d_len"] > 200
    assert page.errors == []


def test_chart_query_reports_unknown_signals(board):
    """A bad pen assignment must be visible, not a blank chart."""
    page, _ = board
    got = page.evaluate("""() => new Promise(resolve => {
        const orig = window.panel.conn.handlers.chart_data;
        window.panel.conn.handlers.chart_data = (m) => {
            window.panel.conn.handlers.chart_data = orig;
            resolve(m);
        };
        window.panel.conn.chartQuery('probe', ['drum_level', 'not_a_signal'],
                                     0, 1e9, 100);
    })""")
    print(f"\n  unknown reported: {got['unknown']}")
    assert got["unknown"] == ["not_a_signal"]
    assert "drum_level" in got["series"]


def test_span_selector_changes_the_window(board):
    page, _ = board
    page.click('[data-element="chart_recorder_1"] [data-span="30"] .span-face')
    page.wait_for_timeout(600)
    axis = page.evaluate(
        """() => [...document.querySelectorAll(
             '[data-element="chart_recorder_1"] .chart-axis-text')]
             .map(n => n.textContent)""")
    print(f"\n  30-minute axis labels: {axis}")
    assert len(axis) == 3


# --------------------------------------------------- instructor station


def test_instructor_drawer_opens_and_shows_the_audit(board):
    page, _ = board
    assert "open" not in (page.get_attribute("#instructor", "class") or "")
    page.click(".ins-toggle")
    assert "open" in page.get_attribute("#instructor", "class")
    page.wait_for_function(
        "() => !document.getElementById('ins-audit').textContent.includes('—')",
        timeout=10000)
    audit = page.text_content("#ins-audit")
    seed = page.text_content("#ins-seed")
    print(f"\n  {audit}\n  {seed}")
    assert "mass drift" in audit and "energy residual" in audit
    assert "seed 42" in seed


def test_load_step_button_sends_a_mw_delta_converted_to_watts(board):
    """§9 offers a MW delta; hotwell's set_load takes absolute watts."""
    page, session = board
    page.click(".ins-toggle")
    before = session.sim.plant.loads.nonvital.p0
    page.fill("#ins-load-delta", "6")
    page.click("#ins-load-btn")
    page.wait_for_function(
        f"() => window.panel.store.frame.loops.loads_mw.nonvital > "
        f"{before / 1e6 + 5.5}", timeout=10000)
    after = session.sim.plant.loads.nonvital.p0
    print(f"\n  non-vital {before/1e6:.1f} -> {after/1e6:.1f} MW")
    assert after == pytest.approx(before + 6.0e6)
    # The session log holds the RESOLVED absolute value, so replay does not
    # depend on what the block happened to be at the time.
    rec = [r for r in session.log.records if r.kind == "set_load"]
    assert rec and rec[-1].payload["p0"] == pytest.approx(after)


def test_casualty_buttons_reach_the_simulator(board):
    page, session = board
    page.click(".ins-toggle")
    page.select_option("#ins-trip-pump", "cp1")
    page.click("#ins-trip-btn")
    page.wait_for_function(
        "() => window.panel.store.frame.indications.cp1_tripped === true",
        timeout=10000)
    assert session.sim.disc.pump_modes["cp1"] == "tripped"

    page.select_option("#ins-inhibit-pump", "cp2")
    page.click("#ins-inhibit-btn")
    page.wait_for_timeout(400)
    assert "cp2" in session.sim.disc.start_inhibited

    page.fill("#ins-air", "0.05")
    page.click("#ins-air-btn")
    page.wait_for_timeout(400)
    print(f"\n  air ingress now {session.sim.disc.air_ingress}")
    assert session.sim.disc.air_ingress == pytest.approx(0.05)


def test_sensor_fault_form_injects_a_bias(board):
    page, session = board
    page.click(".ins-toggle")
    page.select_option("#ins-fault-instr", "drum_pressure")
    page.select_option("#ins-fault-kind", "bias")
    page.fill("#ins-fault-bias", "-200000")
    page.click("#ins-fault-btn")
    page.wait_for_timeout(600)
    fault = session.sim.sensors.faults.get("drum_pressure")
    print(f"\n  injected fault: {fault}")
    assert fault is not None and fault.kind == "bias"
    assert fault.bias == pytest.approx(-200000.0)


def test_freeze_and_run_from_the_drawer(board):
    page, session = board
    page.click(".ins-toggle")
    page.click("#ins-freeze")
    page.wait_for_timeout(300)
    assert session.state == "paused"
    tick_a = session.frame().tick
    page.wait_for_timeout(500)
    assert session.frame().tick == tick_a, "a frozen sim must not advance"
    page.click("#ins-run")
    page.wait_for_function(
        f"() => window.panel.store.frame.tick > {tick_a}", timeout=10000)
    print(f"\n  froze at tick {tick_a}, resumed to {session.frame().tick}")


def test_export_session_writes_a_file_and_reports_the_hash(board, tmp_path):
    page, session = board
    page.click(".ins-toggle")
    page.wait_for_timeout(500)
    page.click("#ins-export-btn")
    page.wait_for_function(
        "() => document.getElementById('ins-export').textContent.includes('wrote')",
        timeout=10000)
    text = page.text_content("#ins-export")
    print(f"\n  {text}")
    path = Path(text.split("wrote ")[1].split(" —")[0])
    assert path.is_file()
    assert session.log.state_history_hash[:16] in text


def test_fidelity_selector_reloads_with_the_two_state_drum(board):
    """§9: fidelity applies on the next LOAD, because it constructs the sim."""
    page, session = board
    page.click(".ins-toggle")
    assert session.fidelity["drum_model"] == "astrom_bell"
    page.select_option("#ins-drum", "two_state")
    page.select_option("#ins-element", "1")
    page.click("#ins-load")
    page.wait_for_function(
        "() => window.panel.store.hello.fidelity.drum_model === 'two_state'",
        timeout=15000)
    print(f"\n  reloaded with {session.fidelity}")
    assert session.fidelity == {"drum_model": "two_state", "three_element": False}
    assert session.sim.cfg["drum"]["model"] == "two_state"
    assert page.text_content("#fidelity") == "TWO_STATE / 1E"


def test_pen_assignment_is_a_dropdown_over_every_instrument(board):
    """§8.1: 'Pen assignment selectable from any instrument (dropdown)'."""
    page, _ = board
    page.wait_for_function(
        """() => document.querySelectorAll(
             '[data-element="chart_recorder_1"] .pen-select')[0].options.length > 5""",
        timeout=20000)
    info = page.evaluate("""() => {
        const s = document.querySelectorAll(
          '[data-element="chart_recorder_1"] .pen-select');
        return {count: s.length, options: s[0].options.length,
                selected: [...s].map(x => x.value)};
    }""")
    print(f"\n  {info}")
    assert info["count"] == 3
    assert info["options"] == len(page.evaluate("Object.keys(window.panel.store.units)"))
    assert info["selected"] == ["drum_level", "feed_flow", "steam_flow"]

    # Reassigning a pen refetches its history rather than starting blank.
    page.select_option(
        '[data-element="chart_recorder_1"] .pen-select >> nth=2', "da_level")
    page.wait_for_timeout(1500)
    after = page.evaluate("""() => document.querySelectorAll(
        '[data-element="chart_recorder_1"] .pen-select')[2].value""")
    d = page.evaluate("""() => document.querySelector(
        '[data-element="chart_recorder_1"] .chart-pen-3').getAttribute('d')""")
    print(f"  pen 3 -> {after}, trace {len(d or '')} chars")
    assert after == "da_level"
    assert d and len(d) > 20, "reassigned pen must backfill, not start empty"
