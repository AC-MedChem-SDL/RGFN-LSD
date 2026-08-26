#!/usr/bin/env python3
"""Figure 2 — the floor and the ceiling of hub ordering, in one panel.

Two questions a reviewer will ask about a method that ranks intermediates by flow,
answered from opposite directions:

**Is the flow field doing anything?** (the floor) Hold everything fixed -- the same
hubs, gate, cost model, child policy -- and change only the order they are walked in.
Reverse the sort and the method cannot finish the library at all. Randomise it and it
costs far more reactions. Every ordering that reads *any* signal, flow or reward,
lands close together, which is the honest claim: **flow finds the right
neighbourhood, not the exact rank.**

**How much is left on the table?** (the ceiling) An oracle greedy re-ranks hubs by
measured marginal gain at every step -- the best any ordering could achieve, at a
selection cost nobody would pay, since it must score the whole pool before it can
rank anything. The gap between the one-shot flow ranking and that ceiling is a
*measured* optimality gap, which is both stronger and shorter to state than a
worst-case approximation bound.

Reads only ``artifacts/mechanism/``. No cluster, no GPU, no generator.

    python3 reproduce/fig2_floor_and_ceiling.py
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
from pathlib import Path


def root() -> Path:
    return Path(__file__).resolve().parents[1] / "artifacts" / "mechanism"


def read_csv(path: Path) -> list[dict]:
    with path.open() as fh:
        return list(csv.DictReader(fh))


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def floor_table(rows, prebuild_k: int):
    """Ordering arms at one prebuild-K setting, on the two cost axes."""
    out = []
    for r in rows:
        if int(r["prebuild_k"]) != prebuild_k:
            continue
        rxn, comp, modes = num(r["reactions"]), num(r["compute_s"]), num(r["modes"])
        if rxn is None or comp is None:
            continue
        out.append({
            "arm": r["arm"], "label": r["label"],
            "informed": r["flow_or_reward_informed"] == "True",
            "reactions": rxn, "compute_s": comp, "modes": modes,
            # An arm that never reached the mode budget did not "cost more" -- it
            # failed. Those two outcomes must not be plotted as the same thing.
            "finished": modes is not None and modes >= 300,
            "rxn_per_mode": num(r["reactions_per_mode"]),
        })
    return sorted(out, key=lambda d: d["reactions"])


def pareto(points):
    """Arms not dominated on both axes (fewer reactions AND less compute)."""
    front = []
    for p in points:
        if not any(q["reactions"] < p["reactions"] and q["compute_s"] < p["compute_s"]
                   for q in points if q is not p):
            front.append(p)
    return front


def ceiling_table(rows):
    out = []
    for r in rows:
        bc, flow, gr = (num(r.get(f"{a}_rxn_per_mode"))
                        for a in ("best_candidate", "hub_batching", "greedy_oracle"))
        if None in (bc, flow, gr) or bc == gr:
            continue
        # Achievable gain is what the oracle greedy buys over the baseline; the share
        # is how much of it the one-shot ranking already captures.
        share = (bc - flow) / (bc - gr)
        calls_flow = num(r.get("hub_batching_reward_gen_calls"))
        calls_gr = num(r.get("greedy_oracle_reward_gen_calls"))
        wall_flow = num(r.get("hub_batching_selection_wall_s"))
        wall_gr = num(r.get("greedy_oracle_selection_wall_s"))
        out.append({
            "cell": r["cell"], "target": r["target"],
            "pool_limited": r.get("pool_limited") == "True",
            "bc_rxn_per_mode": bc, "flow_rxn_per_mode": flow, "greedy_rxn_per_mode": gr,
            "share_of_achievable_gain": round(share, 3),
            "flow_excess_pct": round(100 * (flow / gr - 1), 2),
            "scoring_ratio_greedy_over_flow":
                round(calls_gr / calls_flow, 2) if calls_flow else None,
            "wallclock_ratio_greedy_over_flow":
                round(wall_gr / wall_flow, 1) if wall_flow else None,
            "flow_modes_at_100rxn": num(r.get("hub_batching_modes_at_100rxn")),
            "greedy_modes_at_100rxn": num(r.get("greedy_oracle_modes_at_100rxn")),
        })
    return sorted(out, key=lambda d: d["share_of_achievable_gain"])


def draw(floor, ceil, out_path: Path) -> str:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return "matplotlib not installed - CSVs written, figure skipped"

    fig, (axl, axr) = plt.subplots(1, 2, figsize=(11, 4.4))
    front = {id(p) for p in pareto([p for p in floor if p["finished"]])}

    # ---- left: the floor, on the two cost axes ----
    # Two arms can sit almost on top of each other (357/5648 vs 365/5685), so
    # alternate the label offset rather than letting them overprint.
    for idx, p in enumerate(floor):
        informed, done = p["informed"], p["finished"]
        color = "#1f6f8b" if informed else "#c0603a"
        axl.scatter(p["reactions"], p["compute_s"], s=90 if id(p) in front else 55,
                    marker="o" if done else "X",
                    color=color, alpha=1.0 if done else 0.55,
                    edgecolor="black" if id(p) in front else "none",
                    linewidth=0.9, zorder=3)
        note = p["label"] if done else f"{p['label']} — only {int(p['modes'])}/300 modes"
        axl.annotate(note, (p["reactions"], p["compute_s"]), fontsize=7,
                     xytext=(7, 4 if idx % 2 == 0 else -11),
                     textcoords="offset points")
    axl.set_xlabel("bench cost  (reactions to 300 modes)")
    axl.set_ylabel("selection cost  (enumeration wall-clock, s)")
    axl.set_title("Floor: what the ordering is worth\n"
                  "blue = reads flow or reward · orange = no signal · X = never finished",
                  fontsize=9)
    axl.spines[["top", "right"]].set_visible(False)

    # ---- right: the ceiling, share of achievable gain per cell ----
    cells = [c["cell"] for c in ceil]
    shares = [c["share_of_achievable_gain"] for c in ceil]
    ypos = range(len(cells))
    axr.barh(list(ypos), shares, color="#1f6f8b", height=0.62, zorder=3)
    med = statistics.median(shares)
    axr.axvline(med, color="#c0603a", lw=1.4, ls="--", zorder=4,
                label=f"median {med:.3f}")
    axr.axvline(1.0, color="#666666", lw=1.0, zorder=4)
    axr.text(1.002, len(cells) - 0.4, "oracle greedy", fontsize=7,
             color="#666666", rotation=90, va="top")
    axr.set_yticks(list(ypos))
    axr.set_yticklabels(cells, fontsize=7)
    axr.set_xlim(0, 1.08)
    axr.set_xlabel("share of the achievable gain recovered\nby the one-shot flow ranking")
    axr.set_title("Ceiling: how much is left on the table", fontsize=9)
    axr.legend(frameon=False, fontsize=8, loc="lower right")
    axr.spines[["top", "right"]].set_visible(False)

    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(out_path.parent / f"{out_path.stem}.{ext}", dpi=200,
                    metadata={"Creator": None, "Producer": None, "CreationDate": None})
    plt.close(fig)
    return f"wrote {out_path.stem}.png and .pdf"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prebuild-k", type=int, default=20,
                    help="which prebuild-K setting to draw the floor at (default 20)")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    base = root()
    if not base.is_dir():
        sys.exit(f"missing artifacts: {base}")
    out = args.out or (Path(__file__).resolve().parents[1] / "build" / "figures")
    out.mkdir(parents=True, exist_ok=True)

    floor = floor_table(read_csv(base / "hub_ordering" / "arms.csv"), args.prebuild_k)
    ceil = ceiling_table(read_csv(base / "greedy_ceiling" / "cells.csv"))
    if not floor or not ceil:
        sys.exit("no rows -- re-run tools/harvest/mechanism.py")

    for name, table in (("fig2_floor.csv", floor), ("fig2_ceiling.csv", ceil)):
        with (out / name).open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(table[0]))
            w.writeheader()
            w.writerows(table)

    front = pareto([p for p in floor if p["finished"]])
    print(f"FLOOR — ordering ablation at prebuild_k={args.prebuild_k}\n")
    print(f"  {'arm':<34}{'reactions':>10}{'compute_s':>11}{'modes':>7}  on frontier")
    for p in floor:
        mark = "  <-- frontier" if p in front else ""
        finished = "" if p["finished"] else f"  FAILED ({int(p['modes'])}/300)"
        print(f"  {p['label']:<34}{p['reactions']:>10.0f}{p['compute_s']:>11.0f}"
              f"{p['modes']:>7.0f}{mark}{finished}")
    informed_off = [p for p in front if not p["informed"]]
    print(f"\n  frontier arms reading a signal: {len(front) - len(informed_off)}/{len(front)}"
          + ("  (both no-signal controls are dominated)" if not informed_off else ""))

    print(f"\nCEILING — {len(ceil)} cells")
    for label, subset in (("all cells", ceil),
                          ("budget-bound only", [c for c in ceil if not c["pool_limited"]])):
        if not subset or len(subset) == len(ceil) and label != "all cells":
            continue
        shares = [c["share_of_achievable_gain"] for c in subset]
        calls = [c["scoring_ratio_greedy_over_flow"] for c in subset
                 if c["scoring_ratio_greedy_over_flow"]]
        walls = [c["wallclock_ratio_greedy_over_flow"] for c in subset
                 if c["wallclock_ratio_greedy_over_flow"]]
        print(f"  {label} (n={len(subset)}):")
        print(f"    share of achievable gain  median {statistics.median(shares):.3f}"
              f"  (range {min(shares):.3f}-{max(shares):.3f})")
        print(f"    greedy pays              {min(calls):.1f}x-{max(calls):.1f}x scorings, "
              f"{min(walls):.1f}x-{max(walls):.1f}x wall-clock")
    n_pl = sum(1 for c in ceil if c["pool_limited"])
    if n_pl:
        print(f"  {n_pl} pool-limited cell(s) excluded from the second row: "
              + ", ".join(c["cell"] for c in ceil if c["pool_limited"]))
    print()
    print(draw(floor, ceil, out / "fig2_floor_and_ceiling"))
    print(f"tables: {out/'fig2_floor.csv'}, {out/'fig2_ceiling.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
