#!/usr/bin/env python3
"""Convert a session log to a plain scenario YAML, and optionally verify it.

    python scripts/session_to_scenario.py sessions/X.session.yaml -o out.yaml
    python scripts/session_to_scenario.py sessions/X.session.yaml -o out.yaml --replay

`--replay` re-runs the derived scenario headlessly and compares the
state-history hash against the one recorded during the live session (§3.4,
§12.2). Exit status is non-zero on a mismatch, so this is usable as a gate.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from hotwell_panel.replay import verify_session
from hotwell_panel.sessionlog import SessionLog, write_scenario


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("session", type=Path)
    ap.add_argument("-o", "--out", type=Path, default=None,
                    help="scenario YAML to write (default: alongside the session)")
    ap.add_argument("--replay", action="store_true",
                    help="replay the derived scenario and check the hash")
    args = ap.parse_args()

    log = SessionLog.read(args.session)
    out = args.out or args.session.with_suffix("").with_suffix(".scenario.yaml")

    if args.replay:
        r = verify_session(args.session, out)
        print(f"scenario   : {r['scenario']}")
        print(f"records    : {r['n_records']}")
        print(f"end tick   : expected {r['expected_end_tick']}, "
              f"replayed {r['actual_end_tick']}")
        print(f"plant_dead : expected {r['expected_plant_dead']}, "
              f"replayed {r['actual_plant_dead']}")
        print(f"hash       : expected {r['expected_hash']}")
        print(f"             replayed {r['actual_hash']}")
        print("MATCH" if r["match"] else "MISMATCH")
        return 0 if r["match"] else 1

    write_scenario(log, out)
    print(f"wrote {out} ({len(log.records)} events)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
