"""FastAPI app: static assets, the WebSocket endpoint, and the real-time loop.

One process, one simulator, one asyncio task (§1). WebSocket handlers never
touch the simulator — they enqueue onto `SimSession` and subscribe to
broadcasts, so every operator action lands on a tick boundary and is stamped
with a sim tick rather than a wall-clock time.
"""
from __future__ import annotations

import asyncio
import contextlib
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from hotwell_panel import hello as hello_builder
from hotwell_panel.protocol import ChartData, ProtocolError, encode, parse_client
from hotwell_panel.session import ENDED, RUNNING, SimSession

WALL_HZ = 20.0
STATIC = Path(__file__).parent / "static"


class Broadcaster:
    """Fan-out to every connected browser. Localhost tool: no auth, no roles —
    any connection may observe and any may act (§2)."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()

    def add(self, ws: WebSocket) -> None:
        self._clients.add(ws)

    def discard(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    async def send(self, messages: list[dict[str, Any]]) -> None:
        if not messages or not self._clients:
            return
        dead = []
        for ws in list(self._clients):
            try:
                for m in messages:
                    await ws.send_json(m)
            except Exception:            # client vanished mid-send
                dead.append(ws)
        for ws in dead:
            self._clients.discard(ws)


class RealTimeLoop:
    """20 Hz wall clock with drift-corrected scheduling (§3.1).

    Next-tick times are absolute, not accumulated sleeps, so a slow tick does
    not push every later one. A missed deadline is counted and the schedule
    resynchronises; simulation determinism is unaffected because dt never
    changes and the sim advances by tick count, not wall time.
    """

    def __init__(self, session: SimSession, bus: Broadcaster,
                 wall_hz: float = WALL_HZ) -> None:
        self.session = session
        self.bus = bus
        self.period = 1.0 / wall_hz
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _run(self) -> None:
        next_at = time.perf_counter()
        while True:
            next_at += self.period
            await self.pump()
            delay = next_at - time.perf_counter()
            if delay > 0:
                await asyncio.sleep(delay)
            else:
                self.session.note_missed_deadline()
                next_at = time.perf_counter()
                await asyncio.sleep(0)

    async def pump(self) -> None:
        """One wall tick. Frames are only produced when the sim steps, so a
        paused panel goes quiet except for client-side animation (§3.2)."""
        frame, events, results = self.session.tick()
        out: list[dict[str, Any]] = []
        if frame is not None:
            out.append(encode(frame))
        out += [encode(e) for e in events]
        out += [encode(r) for r in results]
        await self.bus.send(out)


def create_app(session: SimSession | None = None, *, wall_hz: float = WALL_HZ,
               autostart: bool = True, scenario: str | None = None) -> FastAPI:
    """Build the app. `autostart=False` leaves the loop stopped for tests."""
    session = session or SimSession(local_scenarios=Path("scenarios"))
    bus = Broadcaster()
    loop = RealTimeLoop(session, bus, wall_hz=wall_hz)

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI):
        if scenario:
            session.load(scenario)
        if autostart:
            loop.start()
        yield
        await loop.stop()

    app = FastAPI(title="hotwell-panel", lifespan=lifespan)
    app.state.session = session
    app.state.bus = bus
    app.state.loop = loop

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    if STATIC.is_dir():
        app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        bus.add(ws)
        try:
            await ws.send_json(encode(hello_builder.build(
                session, session.local_scenarios)))
            frame = session.frame()
            if frame is not None:
                await ws.send_json(encode(frame))
            while True:
                await _handle(ws, await ws.receive_json(), session, bus)
        except WebSocketDisconnect:
            pass
        finally:
            bus.discard(ws)

    return app


async def _handle(ws: WebSocket, raw: Any, session: SimSession,
                  bus: Broadcaster) -> None:
    """Dispatch one client message. Protocol errors are reported, never fatal."""
    try:
        mtype, body = parse_client(raw)
    except ProtocolError as exc:
        await ws.send_json({"type": "error", "reason": str(exc)})
        return
    if mtype == "action":
        session.submit_action(body["command"])
    elif mtype == "chart_query":
        await ws.send_json(encode(_chart(session, body)))
    elif mtype == "instructor":
        await _instructor(session, bus, body["command"], body["params"])


def _chart(session: SimSession, body: dict[str, Any]) -> ChartData:
    """Historian passthrough (§4). NaNs become JSON null."""
    sim = session.sim
    if sim is None or sim.historian is None:
        return ChartData(request_id=body["request_id"], t=[], series={},
                         unknown=list(body["signals"]))
    known = [s for s in body["signals"] if s in sim.historian.signals]
    unknown = [s for s in body["signals"] if s not in sim.historian.signals]
    t, series = sim.historian.query(known, body["t0"], body["t1"],
                                    body["max_points"])

    def clean(arr):
        return [None if v != v else float(v) for v in arr]

    return ChartData(request_id=body["request_id"], t=[float(x) for x in t],
                     series={k: clean(v) for k, v in series.items()},
                     unknown=unknown)


async def _instructor(session: SimSession, bus: Broadcaster, command: str,
                      params: dict[str, Any]) -> None:
    """Instructor station commands (§9). State-changing ones push a frame
    immediately so a paused panel still updates (§3.2)."""
    if command == "load_scenario":
        session.load(params["ref"], params.get("fidelity"))
        await bus.send([encode(hello_builder.build(
            session, session.local_scenarios))])
    elif command == "run":
        session.run()
    elif command == "pause":
        session.pause()
    elif command == "speed":
        session.set_speed(params["speed"])
    elif command == "reset":
        session.reset()
        await bus.send([encode(hello_builder.build(
            session, session.local_scenarios))])
    elif command == "inject_event":
        session.inject_event(params["event"], params.get("params", {}))
    elif command == "export_session":
        path = session.export()
        await bus.send([{"type": "session_exported", "path": str(path),
                         "hash": session.log.state_history_hash}])
        return
    # §3.2: push one frame immediately so a *frozen* panel reflects the change.
    # While running, the loop is already the sole frame producer and will send
    # one within a wall tick — pushing here too would race it and could deliver
    # a stale tick after a newer one.
    if session.state != RUNNING:
        frame = session.frame()
        if frame is not None:
            await bus.send([encode(frame)])
    if session.state == ENDED:
        await bus.send([{"type": "info", "text": "scenario ended"}])
