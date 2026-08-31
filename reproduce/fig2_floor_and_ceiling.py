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
            "baseline": num(r.get("baseline_modes_at_100rxn")),
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
    BLUE = "#1f6f8b"

    # ---- left: the floor, on the primary readout ----
    # One colour for every arm. An earlier version coloured by "reads a signal", which
    # was not true of the data -- reverse-flow reads the flow and inverts it. Frontier
    # membership is carried by marker size and edge instead, which is a property of the
    # point rather than a claim about the arm.
    # Every point drawn identically. Marking a Pareto frontier implied a ranking the
    # figure does not need to make: these are configurations to compare, and a reader
    # can see which sit down-and-right without being told which "won".
    for idx, p in enumerate(floor):
        axl.scatter(p["modes_at_budget"], p["compute_s"], s=100, marker="o",
                    facecolor=BLUE, edgecolor="none", zorder=3)
        axl.annotate(p["label"], (p["modes_at_budget"], p["compute_s"]), fontsize=8.2,
                     xytext=(10, 5 if idx % 2 == 0 else -13),
                     textcoords="offset points", color="#2c3f42")
    # The baseline these orderings are all being compared against. Identical in every
    # run, because best-candidate does not walk hubs at all -- so it is a line, not a
    # point, and it answers "more than what?" without distorting the compute axis.
    base = [p["baseline"] for p in floor if p["baseline"]]
    if base:
        b = base[0]
        axl.axvline(b, color="#9aa5a7", lw=1.3, ls=(0, (5, 3)), zorder=1)
        axl.annotate(f"best-candidate baseline ({b:.0f})", xy=(b, 0.03),
                     xycoords=("data", "axes fraction"), fontsize=7.5,
                     color="#6b7a7c", ha="left", va="bottom", rotation=90,
                     xytext=(4, 0), textcoords="offset points")
    axl.set_xlabel("number of modes")
    axl.set_ylabel("compute cost: wall-clock, s")
    axl.set_title("Floor: hub-batching under different walk orders  (\u2198)",
                  fontsize=10.5)
    axl.spines[["top", "right"]].set_visible(False)
    axl.margins(0.17)
    axl.set_xlim(left=min(base + [p["modes_at_budget"] for p in floor]) - 6)

    # ---- right: the ceiling, share of achievable gain per cell ----
    # Grouped by model, then a fixed reward-generator order inside each group -- the
    # same structure as Figure 1, so a reader carries one mental layout between them.
    # Sorting by value instead would make the two figures disagree about where a cell is.
    MODELS = ["rgfn", "scent", "rxnflow", "fraggfn"]
    TARGETS = ["seh", "drd2", "clpp", "6td3"]
    def cell_key(c):
        m, _, t = c.rpartition("_")
        return (MODELS.index(m) if m in MODELS else 99,
                TARGETS.index(t) if t in TARGETS else 99)
    ceil = sorted(ceil, key=lambda r: cell_key(r["cell"]))
    cells = [c["cell"] for c in ceil]
    shares = [c["share_of_achievable_gain"] for c in ceil]
    ypos = range(len(cells))
    axr.barh(list(ypos), shares, color="#1f6f8b", height=0.62, zorder=3)
    med = statistics.median(shares)
    axr.axvline(med, color="#c0603a", lw=1.4, ls="--", zorder=4)
    axr.annotate(f"median {med:.3f}", xy=(med, -0.9), fontsize=7.5,
                 color="#c0603a", ha="right", va="bottom", xytext=(-4, 0),
                 textcoords="offset points", annotation_clip=False)
    axr.axvline(1.0, color="#666666", lw=1.0, zorder=4)
    axr.annotate("re-deciding at every step", xy=(1.0, 0.03),
                 xycoords=("data", "axes fraction"), fontsize=7.5, color="#666666",
                 ha="left", va="bottom", rotation=90, xytext=(4, 0),
                 textcoords="offset points")
    prev = None
    for i, c in enumerate(cells):
        m = c.rpartition("_")[0]
        if prev is not None and m != prev:
            axr.axhline(i - 0.5, color="#d8e2e2", lw=0.9, zorder=1)
        prev = m
    axr.set_yticks(list(ypos))
    axr.set_yticklabels(cells, fontsize=7)
    axr.set_xlim(0, 1.10)
    axr.set_ylim(len(cells) - 0.4, -1.2)
    axr.set_xlabel("share of improvement recovered")
    # "Ceiling:" pairs with the left panel's "Floor:" -- the two titles are what tell a
    # reader the panels answer the same question from opposite ends.
    axr.set_title("Ceiling: reaction savings recovered, compared to optimal  (\u2192)",
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
