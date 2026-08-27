#!/usr/bin/env python3
"""Harvest Figure 2's inputs: the floor (hub ordering) and the ceiling (oracle greedy).

Figure 2 answers "is the flow field doing anything?" from both directions at once.

The **floor** is the hub-ordering ablation: hold everything fixed except the order
hubs are walked in, and see what the ordering is worth. Reverse the sort and the
method cannot build the library at all; randomise it and it costs more.

The **ceiling** is an oracle greedy that re-ranks hubs by measured marginal gain at
every step -- the best any ordering could do, at a selection cost no one would pay.
It replaces a worst-case bound with a measured optimality gap, which is both stronger
and shorter to state.

Usage:
    python3 tools/harvest/mechanism.py --research-root <research repo>/experiments/lsd_hubs
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import md5, redact_paths  # noqa: E402

# Arm labels and draw order, copied from the research tree's compare_hub_order.py so
# the figure names arms the way the log that measured them does.
ORDER_ARMS = [
    ("incumbent",            "flow over reward-filtered pool", True),
    ("flow_top",             "highest flow first",             True),
    ("cand_order",           "best-molecule order",            True),
    ("cand_order_fixedset",  "best-molecule order (fixed set)", True),
    ("random",               "random order",                   False),
    ("flow_bottom",          "lowest flow first",              False),
    ("flow_bottom_600",      "lowest flow first (600 hubs)",    False),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--research-root", type=Path, default=None,
                    help="the research tree's experiments/lsd_hubs dir "
                         "(default: $HUBBATCH_RESEARCH_ROOT)")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    root = args.research_root
    if root is None:
        env = os.environ.get("HUBBATCH_RESEARCH_ROOT")
        if not env:
            sys.exit("pass --research-root or set $HUBBATCH_RESEARCH_ROOT")
        root = Path(env)
    root = root.resolve()
    out = args.out or (Path(__file__).resolve().parents[2] / "artifacts" / "mechanism")
    out.mkdir(parents=True, exist_ok=True)

    sources, missing = [], []

    # ---- the floor: hub-ordering arms -------------------------------------------
    rows = []
    for arm, label, signal in ORDER_ARMS:
        for suffix, k in (("", 20), ("_k0", 0)):
            d = root / "hub_order" / "results" / f"hubord_{arm}{suffix}"
            summary = d / "summary.json"
            if not summary.is_file():
                missing.append(f"hub_order/{d.name}")
                continue
            meta = json.loads(summary.read_text())
            hb = meta.get("hub_batching") or {}
            ct = (meta.get("compute_time") or {}).get("head_to_head") or {}
            rows.append({
                "arm": arm, "label": label, "flow_or_reward_informed": signal,
                "prebuild_k": k,
                "reactions": hb.get("total_reactions"),
                # The primary readout, already recorded by every arm's own campaign --
                # no re-run needed to move the figure onto the fixed-budget axis.
                "modes_at_100rxn": hb.get("case1_modes_at_100rxn"),
                "modes": hb.get("total_modes"),
                "reactions_per_mode": hb.get("reactions_per_mode"),
                "hubs_used": hb.get("distinct_hubs_used"),
                "reward_gen_calls": hb.get("total_reward_gen_calls"),
                "compute_s": ct.get("hub_total_s"),
                "best_candidate_reactions": (meta.get("best_candidate") or {}).get("total_reactions"),
                "stop_reason": hb.get("stop_reason"),
            })
            dest = out / "hub_ordering" / d.name
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "summary.json").write_text(
                json.dumps(redact_paths(meta), indent=2) + "\n")
            sources.append({"half": "floor", "arm": d.name, "file": "summary.json",
                            "md5": md5(summary), "redacted": True})

    if rows:
        with (out / "hub_ordering" / "arms.csv").open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)

    # ---- the ceiling: oracle greedy vs flow vs best-candidate -------------------
    ceil = []
    gdir = root / "greedy_oracle" / "results"
    for summary in sorted(gdir.glob("*/summary.json")) if gdir.is_dir() else []:
        meta = json.loads(summary.read_text())
        cell = meta.get("tag", summary.parent.name)
        arms = meta.get("arms") or {}
        if not {"best_candidate", "hub_batching", "greedy_oracle"} <= set(arms):
            missing.append(f"greedy_oracle/{cell} (incomplete arms)")
            continue
        # A cell where neither arm can reach the mode budget is pool-limited: its
        # ratios are measured over a truncated run, so they are reported but must not
        # be pooled with cells where the budget actually bound. Logs/060 flags
        # rgfn_seh and rxnflow_seh this way.
        fvg = meta.get("flow_vs_greedy") or {}
        at_budget = fvg.get("reactions_at_mode_budget") or {}
        pool_limited = at_budget.get("flow") is None or at_budget.get("greedy") is None
        rec = {"cell": cell, "target": next(
            (t for t in ("6td3", "clpp", "drd2", "seh") if cell.endswith(t)), ""),
            "gate": meta.get("reward_threshold"), "pool_limited": pool_limited}
        for name, arm in arms.items():
            rec[f"{name}_rxn_per_mode"] = arm.get("reactions_per_mode")
            rec[f"{name}_modes_at_100rxn"] = arm.get("case1_modes_at_100rxn")
            rec[f"{name}_reward_gen_calls"] = arm.get("total_reward_gen_calls")
            rec[f"{name}_selection_wall_s"] = arm.get("selection_wall_s")
        ceil.append(rec)
        dest = out / "greedy_ceiling" / cell
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "summary.json").write_text(json.dumps(redact_paths(meta), indent=2) + "\n")
        sources.append({"half": "ceiling", "arm": cell, "file": "summary.json",
                        "md5": md5(summary), "redacted": True})

    if ceil:
        keys = sorted({k for r in ceil for k in r},
                      key=lambda k: (k not in ("cell", "target", "gate"), k))
        with (out / "greedy_ceiling" / "cells.csv").open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=keys)
            w.writeheader()
            w.writerows(ceil)

    (out / "provenance.json").write_text(json.dumps({
        "harvested_from_subdir": "experiments/lsd_hubs",
        "n_order_arms": len(rows), "n_ceiling_cells": len(ceil),
        "missing": missing, "sources": sources,
    }, indent=2) + "\n")

    print(f"floor  : {len(rows)} ordering arms")
    print(f"ceiling: {len(ceil)} cells")
    if missing:
        print(f"missing: {len(missing)} -> {', '.join(missing[:5])}"
              + (" ..." if len(missing) > 5 else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
