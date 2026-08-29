"""``python -m hotwell_panel [--scenario REF] [--port 8000]``."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import uvicorn

from hotwell_panel import scenarios as scenario_catalog
from hotwell_panel.server import DIST, create_app
from hotwell_panel.session import SimSession


def main() -> None:
    ap = argparse.ArgumentParser(prog="hotwell_panel", description=__doc__)
    ap.add_argument("--scenario", default=None,
                    help="scenario reference to load at startup, "
                         "e.g. builtin:cp1_trip_unrecovered")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1",
                    help="localhost only by design (§15: no remote deployment)")
    ap.add_argument("--scenarios-dir", type=Path, default=Path("scenarios"))
    ap.add_argument("--sessions-dir", type=Path, default=Path("sessions"))
    ap.add_argument("--list-scenarios", action="store_true")
    args = ap.parse_args()

    if args.list_scenarios:
        for s in scenario_catalog.discover(args.scenarios_dir):
            flag = "  [self-playing]" if s["self_playing"] else ""
            print(f"{s['ref']:<40} {s['load_mw']:>5.1f} MW  "
                  f"max_t {s['max_t']:>6.0f} s{flag}")
        return

    if not (DIST / "index.html").is_file():
        sys.exit(
            "hotwell-panel: built client not found at "
            f"{DIST}\n"
            "Production serving needs the Svelte client built first:\n"
            "    cd client && npm install && npm run build\n"
            "(For development, run `vite dev` beside uvicorn instead — "
            "see README.)")

    session = SimSession(local_scenarios=args.scenarios_dir,
                         sessions_dir=args.sessions_dir)
    app = create_app(session, scenario=args.scenario)
    print(f"hotwell-panel on http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
