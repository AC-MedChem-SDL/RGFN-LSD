#!/usr/bin/env python3
"""Harvest the REWARDS of the molecules each arm actually selected, for Appendix A1.

Why this exists. Hub-batching buys more distinct molecules per reaction. The obvious
follow-up is whether they are *worse* molecules, and it is a fair question with an
uncomfortable answer: best-candidate selects the top of the pool by reward **by
construction**, so it wins a reward comparison almost by definition. Showing that anyway
is the point -- what makes the panel worth printing is the range the two arms sit in, not
which median is higher (see `docs/CAPTIONS.md`).

Both arms clear the same gate, so every molecule in both distributions is a hit under the
project's own definition. What differs is how far into the proxy's tail the selection
reaches.

Scope: the three **reaction-aware** generators (RGFN, SCENT, RxnFlow) on sEH and DRD2.
FragGFN is excluded on purpose -- it is a cost-model control whose fragment attachments
are not synthesis steps, so pooling its rewards would mix two different quantities.

Only the prefix of each accepted sequence that fits the reaction budget is kept; the dump
holds the whole run (300 modes), which is a different readout from the one the paper
reports.

Usage:
    python3 tools/harvest/selection_rewards.py --dump-root <scratch>/lsdflow/reward_dump
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

GENERATORS = ("rgfn", "scent", "rxnflow")
TARGETS = {"seh": "sEH", "drd2": "DRD2"}
ARMS = {"best_candidate": "best-candidate", "hub_batching": "hub-batching"}


def modes_within_budget(curve_csv: Path, budget: int) -> int:
    """How many accepted modes fit inside the reaction budget, read off the curve."""
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
    ap.add_argument("--dump-root", default=os.environ.get("HUBBATCH_REWARD_DUMP"),
                    help="dir holding <gen>_<target>/selection_<arm>.json")
    ap.add_argument("--budget", type=int, default=100)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    if not a.dump_root:
        ap.error("--dump-root or $HUBBATCH_REWARD_DUMP is required")
    root = Path(a.dump_root).expanduser().resolve()

    out = Path(a.out) if a.out else Path(__file__).resolve().parents[2] / "artifacts" / "rewards"
    out.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    prov = {"generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "budget_reactions": a.budget, "cells": {}}

    for tgt in TARGETS:
        for gen in GENERATORS:
            cell = f"{gen}_{tgt}"
            for arm, label in ARMS.items():
                sel = root / cell / f"selection_{arm}.json"
                curve = root / cell / f"curve_{arm}.csv"
                if not sel.is_file() or not curve.is_file():
                    print(f"  skip {cell}/{arm}: missing", file=sys.stderr)
                    continue
                d = json.loads(sel.read_text())
                n = modes_within_budget(curve, a.budget)
                vals = [float(x) for x in d["accepted_rewards"][:n]]
                if not vals:
                    continue
                for v in vals:
                    rows.append({"target": TARGETS[tgt], "generator": gen,
                                 "arm": label, "reward": v})
                prov["cells"][f"{cell}/{arm}"] = {
                    "n_within_budget": n, "n_accepted_total": len(d["accepted_rewards"]),
                    "gate": d.get("reward_threshold"), "tau": d.get("similarity"),
                    "child_policy": d.get("child_policy"), "prebuild_k": d.get("prebuild_k"),
                    "selection_md5": md5(sel),
                }
                print(f"  {cell:14s} {label:15s} n={n:3d} of {len(d['accepted_rewards'])} accepted")

    if not rows:
        print("nothing harvested", file=sys.stderr)
        return 1
    with (out / "selection_rewards.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    (out / "provenance.json").write_text(json.dumps(prov, indent=2) + "\n")
    print(f"\nwrote {out}/selection_rewards.csv ({len(rows)} molecules)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
