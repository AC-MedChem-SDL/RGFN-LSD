#!/usr/bin/env python3
"""Figure 3 — buying compounds is not the same as buying distinct molecules.

The obvious challenge to this work is: *your generator made the molecules, so why do
we need your selection?* This is the answer. SPARROW -- somebody else's optimizer,
given a diversity term its authors say it does not ship (``--lambda-div``) -- chooses
from an enumerated pool under the same 100-reaction budget we spend.

**Left.** How many compounds each arm buys, and how many of those are genuinely
different molecules. The optimizer buys nearly a hundred compounds either way; the
grey is what those compounds amount to once near-duplicates are collapsed. Our arm has
no grey at all, because the greedy accepts a child only if it clears the gate *and* is
far from everything already taken -- every pick is distinct by construction.

**Right.** The same fact as two efficiency numbers. Per *compound* the optimizer is
slightly cheaper than us. Per *distinct molecule* it is far more expensive. Those two
bars are equal for us and far apart for it, and that gap is the entire point: cheap
compounds are easy, cheap distinct molecules are not.

Bars are the mean over seeds, whiskers the full range. Rows that hit the solver's time
limit are excluded, since an uncertified objective is a lower bound rather than a
measurement; so is the single-seed lambda=0.1 point.

    python3 reproduce/fig3_selection_vs_enumeration.py
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path

GREY, BLUE = "#9aa5a7", "#1f6f8b"
# The gate and tau these runs were actually measured at. NOT the 5.0 headline bar that
# Figure 1's surrogate cells use -- this comparison is at the paper-comparable 7.0, and
# labelling it 5.0 would misstate what the bars mean.
GATE, TAU = 7.0, 0.5


def num(v, default=float("nan")):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def pairwise_similarities(root: Path):
    """Every within-pool pairwise Tanimoto, per arm, over the CANDIDATE pools.

    Morgan r=3 / 2048 bits -- the same fingerprint the mode definition uses, so the
    distribution shown here is the one the diversity filter actually acts on rather
    than a second opinion computed differently.

    Candidates, not modes: for the SPARROW arms these differ sharply (~99 compounds
    collapsing to 24-33 distinct), and it is the candidate pool that explains the
    collapse. For hub-batching they are the same set, because the greedy cannot accept
    a duplicate.
    """
    f = root / "similarity" / "selections.json"
    if not f.is_file():
        return []
    try:
        from rdkit import Chem, DataStructs
        from rdkit.Chem import AllChem
        from rdkit import RDLogger
        RDLogger.DisableLog("rdApp.*")
    except ImportError:
        return []
    out = []
    for a in json.loads(f.read_text())["arms"]:
        fps = []
        for smi in a["smiles"]:
            m = Chem.MolFromSmiles(smi)
            if m is not None:
                fps.append(AllChem.GetMorganFingerprintAsBitVect(m, 3, nBits=2048))
        sims = []
        for i in range(len(fps)):
            # BulkTanimoto against the tail only: each unordered pair counted once.
            if i + 1 < len(fps):
                sims.extend(DataStructs.BulkTanimotoSimilarity(fps[i], fps[i + 1:]))
        if sims:
            out.append({"label": a["label"], "sims": sims, "n": len(fps),
                        "n_distinct": a.get("n_distinct"),
                        "ours": a["arm"] == "hub-batching"})
    return out


def collect(root: Path):
    """One entry per arm: the per-seed rows that survive the exclusion rules."""
    comp = [r for r in csv.DictReader((root / "r100.csv").open())
            if r["arm"] == "BC-Enum-SB" and r["subset"].startswith("R100")]
    ours = list(csv.DictReader((root / "ours_r100.csv").open()))

    dropped = []
    keep = []
    for r in comp:
        lam = num(r["lambda_div"])
        if r["milp_status"] != "Optimal":
            dropped.append(f"BC-Enum-SB λ={lam:g} seed {r['seed']} ({r['milp_status']})")
            continue
        if abs(lam - 0.1) < 1e-9:
            dropped.append(f"BC-Enum-SB λ=0.1 seed {r['seed']} (single seed)")
            continue
        if lam > 1.0:
            dropped.append(f"BC-Enum-SB λ={lam:g} seed {r['seed']} (λ>1 saturates)")
            continue
        keep.append(r)

    arms = []
    ours_entry = {
        "label": "hub-batching\n(ours)",
        "selected": [num(r["n_selected"]) for r in ours],
        "distinct": [num(r["n_modes_kept"]) for r in ours],
        "rxn_per_cand": [num(r["used_rxns"]) / num(r["n_selected"]) for r in ours],
        # Budget spent divided by distinct molecules -- NOT cost_kept_rxns/distinct.
        # cost_kept prices only the survivors, so for an arm that spends its whole
        # budget buying near-duplicates it charges a fraction of what was actually
        # spent and reads as cheaper than us. Every row here has used_rxns == 100
        # (budget-binding), which is exactly the regime where the budget is the
        # honest numerator.
        "rxn_per_mode": [num(r["used_rxns"]) / num(r["n_modes_kept"]) for r in ours],
        "n": len(ours),
    }
    for lam in sorted({num(r["lambda_div"]) for r in keep}):
        rows = [r for r in keep if abs(num(r["lambda_div"]) - lam) < 1e-9]
        arms.append({
            "label": f"SPARROW\nλ={lam:g}",
            "selected": [num(r["n_selected"]) for r in rows],
            "distinct": [num(r["n_modes_kept"]) for r in rows],
            "rxn_per_cand": [num(r["used_rxns"]) / num(r["n_selected"]) for r in rows],
            "rxn_per_mode": [num(r["used_rxns"]) / num(r["n_modes_kept"]) for r in rows],
            "n": len(rows),
        })
    # Ours first: the reference the competitor bars are read against.
    arms.insert(0, ours_entry)
    return arms, dropped


def whisk(ax, x, vals, color="#20343a", spread=0.10):
    """Plot the individual seeds, not a summary of them.

    At n=2-3, a bar with an error bar implies a distribution that cannot be estimated
    from that many points, and it hides the shape that matters here: lambda=0's seeds
    are 2, 24 and 26, which is not a spread around a mean, it is one seed collapsing.
    Dots show that; a whisker averages it away.
    """
    if not vals:
        return
    n = len(vals)
    for j, v in enumerate(sorted(vals)):
        dx = 0.0 if n == 1 else (j - (n - 1) / 2) * spread
        ax.scatter(x + dx, v, s=13, color=color, zorder=6, linewidths=0)


def draw(arms, sims, out_path: Path) -> str:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return "matplotlib not installed - table written, figure skipped"

    n_panels = 3 if sims else 2
    widths = [1, 1, 0.52] if sims else [1, 1]
    fig, axes = plt.subplots(1, n_panels, figsize=(13.2 if sims else 10.5, 4.3),
                             gridspec_kw={"width_ratios": widths})
    axl, axr = axes[0], axes[1]
    axv = axes[2] if sims else None
    xs = range(len(arms))

    # ---- left: stacked. distinct on the bottom, the near-duplicate remainder above.
    for i, a in enumerate(arms):
        d, s = statistics.mean(a["distinct"]), statistics.mean(a["selected"])
        axl.bar(i, d, 0.56, color=BLUE, zorder=3,
                label=f"modes (reward > {GATE:g}, T < {TAU:g})" if i == 0 else None)
        axl.bar(i, max(s - d, 0), 0.56, bottom=d, color=GREY, zorder=3,
                label=f"candidates (reward > {GATE:g})" if i == 0 else None)
        whisk(axl, i, a["distinct"])
    # The budget caps the count. Every candidate in this pool is a synthesised product,
    # so an additional compound costs at least one reaction -- measured at ~1.01-1.23
    # reactions per compound across these arms -- and 100 reactions therefore cannot
    # buy more than 100 molecules. The cap is the budget, not the chemistry.
    axl.axhline(100, color="#c0603a", lw=1.2, ls=(0, (5, 3)), zorder=4)
    # Below the line, not above: the axis stops at 100, so anything above is clipped.
    # Sits over the gap between our bar and the cap, which is otherwise empty.
    axl.annotate("theoretical maximum", xy=(0, 100), fontsize=7.5, color="#c0603a",
                 ha="center", va="top", xytext=(0, -4), textcoords="offset points")
    axl.set_xticks(list(xs))
    axl.set_xticklabels([a["label"] for a in arms], fontsize=8.5)
    axl.set_ylabel("number of molecules")
    axl.set_title("Modes found with selection algorithms "
                  "under 100 reaction budget  (\u2191)", fontsize=10.5)
    axl.legend(frameon=False, fontsize=8, loc="upper center",
               bbox_to_anchor=(0.5, -0.13), ncol=1)
    axl.spines[["top", "right"]].set_visible(False)
    axl.set_ylim(0, 100)

    # ---- right: the two efficiency numbers side by side.
    w = 0.36
    for i, a in enumerate(arms):
        for j, (key, color, lab) in enumerate(
                # Blue listed first in BOTH panels: the two legends describe the same
                # pairing, so the colour order has to agree or the reader re-learns it.
                ((("rxn_per_mode"), BLUE,
                  f"reactions per mode (reward > {GATE:g}, T < {TAU:g})"),
                 (("rxn_per_cand"), GREY,
                  f"reactions per candidate (reward > {GATE:g})"))):
            m = statistics.mean(a[key])
            axr.bar(i + (j - 0.5) * w, m, w * 0.92, color=color, zorder=3,
                    label=lab if i == 0 else None)
            whisk(axr, i + (j - 0.5) * w, a[key])
    axr.set_xticks(list(xs))
    axr.set_xticklabels([a["label"] for a in arms], fontsize=8.5)
    # Log scale: the lambda=0 range spans 3.8 to 50 reactions per distinct molecule
    # (one seed bought 98 compounds that collapsed to 2), and on a linear axis that
    # single whisker flattens every other bar into the baseline.
    axr.set_yscale("log")
    axr.set_ylim(0.8, 80)
    axr.set_yticks([1, 2, 5, 10, 20, 50])
    axr.set_yticklabels(["1", "2", "5", "10", "20", "50"])
    axr.set_ylabel("reactions per molecule")
    axr.set_title("Reactions per molecule with different synthesis protocols  (\u2193)",
                  fontsize=10.5)
    axr.legend(frameon=False, fontsize=8, loc="upper center",
               bbox_to_anchor=(0.5, -0.13), ncol=1)
    axr.spines[["top", "right"]].set_visible(False)

    # ---- third: how alike the chosen compounds are, within each pool ----
    if axv is not None:
        data = [d["sims"] for d in sims]
        parts = axv.violinplot(data, positions=range(len(sims)), widths=0.82,
                               showextrema=False, showmedians=False)
        for body, d in zip(parts["bodies"], sims):
            body.set_facecolor(BLUE if d["ours"] else GREY)
            body.set_alpha(0.95)
            body.set_edgecolor("none")
        for i, d in enumerate(sims):
            q1, med, q3 = (statistics.quantiles(d["sims"], n=4)[0],
                           statistics.median(d["sims"]),
                           statistics.quantiles(d["sims"], n=4)[2])
            axv.vlines(i, q1, q3, color="#20343a", lw=3.2, zorder=4)
            axv.scatter(i, med, s=16, color="white", zorder=5, linewidths=0)
        axv.set_xticks(range(len(sims)))
        axv.set_xticklabels([d["label"].replace(" ", "\n", 1) for d in sims],
                            fontsize=8.5)
        axv.set_ylabel("pairwise Tanimoto similarity")
        axv.set_title("How alike the chosen\ncompounds are  (\u2193)", fontsize=10.5)
        axv.set_ylim(0, 1)
        axv.spines[["top", "right"]].set_visible(False)

    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(out_path.parent / f"{out_path.stem}.{ext}", dpi=200,
                    bbox_inches="tight",
                    metadata={"Creator": None, "Producer": None, "CreationDate": None})
    plt.close(fig)
    return f"wrote {out_path.stem}.png and .pdf"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1] / "artifacts" / "sparrow_diversity"
    if not root.is_dir():
        sys.exit(f"missing artifacts: {root}")
    arms, dropped = collect(root)
    sims = pairwise_similarities(root.parent)
    out = args.out or (Path(__file__).resolve().parents[1] / "build" / "figures")
    out.mkdir(parents=True, exist_ok=True)

    print("Figure 3 — selection vs enumeration at a 100-reaction budget\n")
    print(f"  {'arm':<26}{'n':>3}{'selected':>10}{'distinct':>10}"
          f"{'rxn/cand':>10}{'rxn/mode':>10}")
    table = []
    for a in arms:
        lab = a["label"].replace("\n", " ")
        row = dict(arm=lab, n_seeds=a["n"],
                   selected_mean=round(statistics.mean(a["selected"]), 1),
                   distinct_mean=round(statistics.mean(a["distinct"]), 1),
                   distinct_min=min(a["distinct"]), distinct_max=max(a["distinct"]),
                   rxn_per_candidate=round(statistics.mean(a["rxn_per_cand"]), 3),
                   rxn_per_distinct=round(statistics.mean(a["rxn_per_mode"]), 3),
                   note="rxn_per_distinct = budget spent / distinct molecules")
        table.append(row)
        print(f"  {lab:<26}{a['n']:>3}{row['selected_mean']:>10.1f}"
              f"{row['distinct_mean']:>10.1f}{row['rxn_per_candidate']:>10.2f}"
              f"{row['rxn_per_distinct']:>10.2f}")
    ours = table[0]
    for row in table[1:]:
        print(f"\n  vs {row['arm']}: {ours['distinct_mean']/row['distinct_mean']:.2f}x "
              f"more distinct molecules for the same budget")
    if dropped:
        print(f"\n  excluded ({len(dropped)}): " + "; ".join(dropped))
    if sims:
        print(f"\n  within-pool pairwise Tanimoto (candidate pools, Morgan r=3/2048):")
        for d in sims:
            q = statistics.quantiles(d["sims"], n=4)
            print(f"    {d['label']:<18} n={d['n']:>3} compounds, "
                  f"{len(d['sims']):>5} pairs   median {statistics.median(d['sims']):.3f}"
                  f"   IQR {q[0]:.3f}-{q[2]:.3f}   -> {d['n_distinct']} distinct")

    with (out / "fig3_selection_vs_enumeration.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(table[0]))
        w.writeheader()
        w.writerows(table)
    print()
    print(draw(arms, sims, out / "fig3_selection_vs_enumeration"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
