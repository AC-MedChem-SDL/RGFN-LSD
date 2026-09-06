#!/usr/bin/env python3
"""Harvest the two-knob robustness surface (reward bar x diversity cutoff) into artifacts/.

Why this exists. Every headline number in the paper is quoted at ONE setting of two
thresholds a reader could reasonably argue with: the reward bar that decides what
counts as good, and the Tanimoto cutoff that decides what counts as different. A
reviewer's fair question is whether the advantage is a property of the method or of
where those two knobs were set. The surface answers it by measuring the whole grid
rather than defending the single point.

The measurement is cheap and CPU-only -- it re-scores an enumeration that already
exists, with no model, no oracle and no GPU -- so it is run at the paper's own
100-reaction budget rather than inherited from an earlier 300-reaction sweep.

What a cell is. Fix the budget, run both selection strategies to it, and read

    reactions / mode = reactions_used / modes_reached      (lower is better)

then take the ratio best_candidate / hub_batching, so >1 means hub-batching is
cheaper. Because the budget is fixed, this is monotone in "modes at 100 reactions",
which is the paper's primary readout.

Three cell classes are kept distinct, because collapsing them would flatter us:

  * ``comparable``    -- both strategies spent the budget. The only case a ratio means
                        what it looks like.
  * ``pool_limited``  -- a strategy ran out of library before spending the budget, so
                        its ratio is measured over a shorter run. Hatched, never counted.
  * ``no_modes``      -- nothing in the pool clears the bar at all, for either strategy.
                        A property of the generator's pool, not of any selection.

Source: ``experiments/lsd_hubs/matrix16/results/surface_r100/<cell>/surface.{csv,json}``
in the research tree, produced by ``surface_all_generators.sh`` at ``BUDGET=100``.

It is release tooling, not part of the artifact -- a reviewer cannot run it and does
not need to, because its *output* is committed.

Usage:
    python3 tools/harvest/two_knob_surface.py --surface-root <research-repo>/experiments/lsd_hubs/matrix16/results/surface_r100
    HUBBATCH_SURFACE_ROOT=... python3 tools/harvest/two_knob_surface.py
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.harvest._common import md5  # noqa: E402

# Display names and the order panels appear in. Reaction-aware generators first, then
# the fragment-assembly one, because that is the order the paper introduces them.
GENERATORS = [
    ("rgfn_seh", "RGFN"),
    ("scent_seh", "SCENT"),
    ("rxnflow_seh", "RxnFlow"),
    ("fraggfn_seh", "FragGFN"),
]

# A ratio this close to 1 is an exact tie, not a win. Both strategies land on the same
# small set in the strict-cutoff corner and price it identically; calling that a win
# would inflate the headline count by three cells.
TIE_EPS = 5e-4


def classify(hub: dict, best: dict) -> str:
    if int(hub["modes"]) == 0 or int(best["modes"]) == 0:
        return "no_modes"
    if hub["pool_limited"] == "True" or best["pool_limited"] == "True":
        return "pool_limited"
    return "comparable"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--surface-root", default=os.environ.get("HUBBATCH_SURFACE_ROOT"),
                    help="dir holding <cell>/surface.csv, from surface_all_generators.sh")
    ap.add_argument("--out", default=None, help="artifacts subdir (default artifacts/two_knob)")
    a = ap.parse_args()

    if not a.surface_root:
        ap.error("--surface-root or $HUBBATCH_SURFACE_ROOT is required")
    root = Path(a.surface_root).expanduser().resolve()
    if not root.is_dir():
        ap.error(f"not a directory: {root}")

    out = Path(a.out) if a.out else Path(__file__).resolve().parents[2] / "artifacts" / "two_knob"
    out.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    prov: dict = {"generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  "source_dir_name": root.name, "cells": {}}
    budgets: set[int] = set()

    for cell, label in GENERATORS:
        csv_path, json_path = root / cell / "surface.csv", root / cell / "surface.json"
        if not csv_path.exists():
            print(f"  skip {cell}: no surface.csv", file=sys.stderr)
            continue
        raw = list(csv.DictReader(csv_path.open()))
        by = {(r["strategy"], float(r["tau"]), float(r["similarity"])): r for r in raw}
        taus = sorted({float(r["tau"]) for r in raw})
        sims = sorted({float(r["similarity"]) for r in raw})

        meta = json.loads(json_path.read_text()) if json_path.exists() else {}
        budgets.add(int(meta.get("budget_reactions", 0)))
        counts = {"comparable": 0, "pool_limited": 0, "no_modes": 0,
                  "win": 0, "tie": 0, "loss": 0}

        for t in taus:
            for s in sims:
                hub, best = by[("hub_batching", t, s)], by[("best_candidate", t, s)]
                cls = classify(hub, best)
                counts[cls] += 1
                ratio = ""
                if cls == "comparable":
                    ratio = float(best["reactions_per_mode"]) / float(hub["reactions_per_mode"])
                    counts["win" if ratio > 1 + TIE_EPS else
                           "loss" if ratio < 1 - TIE_EPS else "tie"] += 1
                    ratio = round(ratio, 4)
                rows.append({
                    "generator": label, "cell": cell,
                    "reward_bar": t, "diversity_cutoff": s,
                    "hub_modes": hub["modes"], "best_modes": best["modes"],
                    "hub_rxn_used": hub["reactions_used"], "best_rxn_used": best["reactions_used"],
                    "hub_rxn_per_mode": hub["reactions_per_mode"],
                    "best_rxn_per_mode": best["reactions_per_mode"],
                    "advantage": ratio, "cell_class": cls,
                    "hub_stop": hub["stop_reason"], "best_stop": best["stop_reason"],
                })

        prov["cells"][cell] = {
            "label": label, "surface_csv_md5": md5(csv_path),
            "budget_reactions": meta.get("budget_reactions"),
            "child_policy": meta.get("child_policy"), "prebuild_k": meta.get("prebuild_k"),
            "rank_by": meta.get("rank_by"), "wall_s": meta.get("wall_s"),
            "n_reward_bars": len(taus), "n_cutoffs": len(sims), "counts": counts,
        }
        print(f"  {label:8s} {counts['comparable']:3d} comparable "
              f"({counts['win']} win / {counts['tie']} tie / {counts['loss']} loss), "
              f"{counts['pool_limited']:2d} pool-limited, {counts['no_modes']:2d} no-modes")

    if not rows:
        print("nothing harvested", file=sys.stderr)
        return 1
    if len(budgets - {0}) > 1:
        print(f"REFUSING: cells were run at different budgets {sorted(budgets)} -- one "
              f"surface cannot mix them", file=sys.stderr)
        return 1
    prov["budget_reactions"] = sorted(budgets - {0})[0] if budgets - {0} else None

    tot = {k: sum(c["counts"][k] for c in prov["cells"].values())
           for k in ("comparable", "pool_limited", "no_modes", "win", "tie", "loss")}
    prov["totals"] = tot

    with (out / "surface.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    (out / "provenance.json").write_text(json.dumps(prov, indent=2) + "\n")

    print(f"\nTOTAL {tot['win']} win / {tot['tie']} tie / {tot['loss']} loss "
          f"over {tot['comparable']} comparable cells at {prov['budget_reactions']} reactions")
    print(f"wrote {out}/surface.csv ({len(rows)} rows) + provenance.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
