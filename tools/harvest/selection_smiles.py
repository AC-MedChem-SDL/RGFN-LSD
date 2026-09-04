#!/usr/bin/env python3
"""Harvest the molecules each arm actually selected, for the similarity panel.

The similarity distribution needs the picks themselves, not a summary of them. Those
were previously written to a temp directory and lost with it, so this harvest pulls them
into artifacts/ where they survive: a few hundred SMILES, a few tens of kilobytes.

**Candidate pools, not mode pools.** For the SPARROW arms these differ sharply -- it buys
~99 compounds that collapse to 24-33 distinct molecules -- and the candidate pool is what
explains the collapse. For hub-batching they are the same set by construction, since the
greedy cannot accept a molecule that duplicates one already taken. That asymmetry is the
point of the panel.

Usage:
    python3 tools/harvest/selection_smiles.py --seed 43 \\
        --ours <campaign out dir> --sparrow-root <bc_sb dir>
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import md5  # noqa: E402


def modes_within_budget(curve_csv: Path, budget: int) -> int:
    """How many accepted modes fit inside the reaction budget.

    The dump lists every mode accepted over the whole run (300 of them); only the prefix
    that fits the budget is what the figure is about. Reading it off the curve rather
    than assuming keeps this consistent with every other readout in the paper.
    """
    n = 0
    with curve_csv.open() as fh:
        for r in csv.DictReader(fh):
            if int(r["cum_reactions"]) <= budget:
                n = int(r["cum_modes"])
            else:
                break
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=43)
    ap.add_argument("--budget", type=int, default=100)
    ap.add_argument("--ours", type=Path, required=True,
                    help="campaign out dir holding selection_hub_batching.json")
    ap.add_argument("--sparrow-root", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    out = args.out or (Path(__file__).resolve().parents[2] / "artifacts" / "similarity")
    out.mkdir(parents=True, exist_ok=True)
    arms, sources = [], []

    sel = args.ours / "selection_hub_batching.json"
    curve = args.ours / "curve_hub_batching.csv"
    if not (sel.is_file() and curve.is_file()):
        sys.exit(f"missing {sel} or {curve}")
    d = json.loads(sel.read_text())
    n = modes_within_budget(curve, args.budget)
    arms.append({
        "arm": "hub-batching", "label": "hub-batching",
        "seed": args.seed, "lambda_div": None,
        "n_candidates": n, "n_distinct": n,
        "note": "candidates and distinct molecules are the same set: the greedy cannot "
                "accept a duplicate",
        "smiles": d["accepted_smiles"][:n],
        "gate": d.get("reward_threshold"), "tau": d.get("similarity"),
    })
    sources.append({"arm": "hub-batching", "file": sel.name, "md5": md5(sel)})

    for lam, tag in ((0.0, "L0"), (1.0, "L1")):
        run = args.sparrow_root / f"enumR100_seed{args.seed}_{tag}_N50000"
        milp = run / f"milp_{tag}_R100.json"
        front = run / "select_frontier.csv"
        if not milp.is_file():
            print(f"  skip lambda={lam:g}: {milp} missing")
            continue
        m = json.loads(milp.read_text())
        smis = m.get("selected_target_smiles") or []
        distinct = None
        if front.is_file():
            with front.open() as fh:
                for r in csv.DictReader(fh):
                    if str(r.get("budget_rxns")) == str(args.budget):
                        distinct = int(r.get("n_modes_kept") or 0)
        arms.append({
            "arm": f"sparrow_lambda_{lam:g}", "label": f"SPARROW λ={lam:g}",
            "seed": args.seed, "lambda_div": lam,
            "n_candidates": len(smis), "n_distinct": distinct,
            "note": "candidates chosen by the optimizer; distinct is how many survive "
                    "the diversity filter",
            "smiles": smis,
            "gate": None, "tau": None,
        })
        sources.append({"arm": f"lambda={lam:g}", "file": f"{run.name}/{milp.name}",
                        "md5": md5(milp)})

    if len(arms) < 2:
        sys.exit("need at least two arms")

    (out / "selections.json").write_text(json.dumps(
        {"seed": args.seed, "budget_reactions": args.budget, "arms": arms}, indent=2))
    (out / "provenance.json").write_text(json.dumps({
        "harvested_from_subdir": "rgfn_runs/lsdflow_sparrow",
        "note": "All arms read the SAME enumeration (t45_seh_seed43), verified by the "
                "routes_artifact each run records. Same candidate pool, different "
                "choosers.",
        "sources": sources,
    }, indent=2))
    print(f"harvested {len(arms)} arms, seed {args.seed}, budget {args.budget}")
    for a in arms:
        print(f"  {a['label']:<18} {a['n_candidates']:>3} candidates -> "
              f"{a['n_distinct']} distinct")
    return 0


if __name__ == "__main__":
    sys.exit(main())
