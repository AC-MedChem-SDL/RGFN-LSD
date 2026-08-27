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


# The four arms that answer the question. Everything else is a control on a control --
# "is this an artifact of the hub pool rather than the ordering?" -- which belongs in an
# appendix, not in the panel that has to land in one look. --all-arms restores them.
MAIN_ARMS = ("flow_top", "cand_order", "random", "flow_bottom")


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
            # The primary readout: modes delivered on a fixed 100-reaction budget.
            # On this axis reverse-flow is simply worse rather than a failure, because
            # the budget binds long before the pool runs out.
            "modes_at_budget": num(r.get("modes_at_100rxn")),
            # An arm that never reached the mode budget did not "cost more" -- it
            # failed. Those two outcomes must not be plotted as the same thing.
            "finished": modes is not None and modes >= 300,
            "rxn_per_mode": num(r["reactions_per_mode"]),
        })
    return sorted(out, key=lambda d: d["reactions"])


def pareto(points):
    """Arms not dominated: nothing delivers MORE modes for LESS compute."""
    front = []
    for p in points:
        if not any(q["modes_at_budget"] > p["modes_at_budget"]
                   and q["compute_s"] < p["compute_s"]
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
    front = {id(p) for p in pareto(floor)}
    BLUE = "#1f6f8b"

    # ---- left: the floor, on the primary readout ----
    # One colour for every arm. An earlier version coloured by "reads a signal", which
    # was not true of the data -- reverse-flow reads the flow and inverts it. Frontier
    # membership is carried by marker size and edge instead, which is a property of the
    # point rather than a claim about the arm.
    for idx, p in enumerate(floor):
        on_front = id(p) in front
        axl.scatter(p["modes_at_budget"], p["compute_s"],
                    s=125 if on_front else 66, marker="o",
                    facecolor=BLUE, edgecolor="#123f50" if on_front else "none",
                    linewidth=1.7, zorder=3)
        axl.annotate(p["label"], (p["modes_at_budget"], p["compute_s"]), fontsize=7.8,
                     xytext=(9, 5 if idx % 2 == 0 else -13),
                     textcoords="offset points", color="#2c3f42")
    axl.set_xlabel("number of modes")
    axl.set_ylabel("compute cost: wall-clock, s")
    axl.set_title("Floor: does the walk order matter?  (\u2198)", fontsize=10.5)
    axl.scatter([], [], s=125, facecolor=BLUE, edgecolor="#123f50", linewidth=1.7,
                label="on the frontier")
    axl.scatter([], [], s=66, facecolor=BLUE, edgecolor="none", label="dominated")
    axl.legend(frameon=False, fontsize=8, loc="lower left")
    axl.spines[["top", "right"]].set_visible(False)
    axl.margins(0.17)

    # ---- right: the ceiling, share of achievable gain per cell ----
    cells = [c["cell"] for c in ceil]
    shares = [c["share_of_achievable_gain"] for c in ceil]
    ypos = range(len(cells))
    axr.barh(list(ypos), shares, color="#1f6f8b", height=0.62, zorder=3)
    med = statistics.median(shares)
    axr.axvline(med, color="#c0603a", lw=1.4, ls="--", zorder=4)
    axr.annotate(f"median {med:.3f}", xy=(med, len(cells) - 0.15), fontsize=7.5,
                 color="#c0603a", ha="center", va="top", annotation_clip=False)
    axr.axvline(1.0, color="#666666", lw=1.0, zorder=4)
    axr.annotate("re-deciding at every step", xy=(1.02, -0.8), fontsize=7.5,
                 color="#666666", ha="left", va="bottom", annotation_clip=False)
    axr.set_yticks(list(ypos))
    axr.set_yticklabels(cells, fontsize=7)
    axr.set_xlim(0, 1.24)
    axr.set_ylim(len(cells) - 0.4, -1.2)
    axr.set_xlabel("share of improvement recovered")
    axr.set_title("Reaction savings recovered, compared to optimal  (\u2192)",
                  fontsize=10.5)
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
    ap.add_argument("--all-arms", action="store_true",
                    help="include the control arms held back from the main figure")
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
    if not args.all_arms:
        held = [p["label"] for p in floor if p["arm"] not in MAIN_ARMS]
        floor = [p for p in floor if p["arm"] in MAIN_ARMS]
        if held:
            print(f"held back from the main figure ({len(held)}, --all-arms to include): "
                  + "; ".join(held) + "\n")
    ceil = ceiling_table(read_csv(base / "greedy_ceiling" / "cells.csv"))
    if not floor or not ceil:
        sys.exit("no rows -- re-run tools/harvest/mechanism.py")

    for name, table in (("fig2_floor.csv", floor), ("fig2_ceiling.csv", ceil)):
        with (out / name).open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(table[0]))
            w.writeheader()
            w.writerows(table)

    # On the fixed-budget axis every arm has a readout, so nothing is pre-filtered:
    # an arm that could not reach 300 modes still delivers a number at 100 reactions.
    front = pareto(floor)
    print(f"FLOOR — ordering ablation at prebuild_k={args.prebuild_k}\n")
    print(f"  {'arm':<34}{'modes@100rxn':>13}{'compute_s':>11}"
          f"{'rxn->300modes':>15}  on frontier")
    for p in sorted(floor, key=lambda d: -d["modes_at_budget"]):
        mark = "  <-- frontier" if p in front else ""
        r = "never" if not p["finished"] else f"{p['reactions']:.0f}"
        print(f"  {p['label']:<34}{p['modes_at_budget']:>13.0f}{p['compute_s']:>11.0f}"
              f"{r:>15}{mark}")
    # State what is actually true of the points rather than re-asserting the old
    # colour encoding: reverse-flow DOES read the flow, it just inverts it.
    dominated = [p["label"] for p in floor if p not in front]
    print(f"\n  on the frontier: {', '.join(p['label'] for p in front)}")
    if dominated:
        print(f"  dominated on both axes: {', '.join(dominated)}")

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
