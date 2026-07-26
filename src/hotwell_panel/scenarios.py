"""Scenario discovery: `hotwell`'s packaged canonical set plus this repo's own.

The picker merges two sources and labels each by origin (§3.3). References are
opaque strings (``builtin:load_step``, ``local:blackstart``) so the client never
handles filesystem paths.
"""
from __future__ import annotations

from pathlib import Path

from hotwell import data
from hotwell.scenario import Scenario, load_scenario

BUILTIN, LOCAL = "builtin", "local"


def _entry(source: str, name: str, ref_path) -> dict:
    sc: Scenario = load_scenario(ref_path)
    return {
        "ref": f"{source}:{name}",
        "name": sc.name,
        "source": source,
        "seed": sc.seed,
        "load_mw": sc.load_mw,
        "max_t": sc.max_t,
        "n_events": len(sc.events),
        # A scenario whose events include scripted operator actions plays
        # itself; the panel shows this so a player knows what they loaded.
        "self_playing": any(e.type == "action" for e in sc.events),
    }


def discover(local_dir: Path | None = None) -> list[dict]:
    """All loadable scenarios, builtins first, each labeled by origin."""
    out = [_entry(BUILTIN, name, path)
           for name, path in data.builtin_scenarios().items()]
    if local_dir and local_dir.is_dir():
        for path in sorted(local_dir.glob("*.yaml")):
            out.append(_entry(LOCAL, path.stem, path))
    return out


def resolve(ref: str, local_dir: Path | None = None):
    """``source:name`` -> a resource `hotwell.scenario.load_scenario` accepts."""
    source, _, name = ref.partition(":")
    if source == BUILTIN:
        builtins = data.builtin_scenarios()
        if name not in builtins:
            raise KeyError(f"no built-in scenario {name!r}")
        return builtins[name]
    if source == LOCAL:
        if local_dir is None:
            raise KeyError("no local scenario directory configured")
        path = local_dir / f"{name}.yaml"
        if not path.is_file():
            raise KeyError(f"no local scenario {name!r}")
        return path
    raise KeyError(f"bad scenario reference {ref!r} (want 'builtin:x' or 'local:x')")
