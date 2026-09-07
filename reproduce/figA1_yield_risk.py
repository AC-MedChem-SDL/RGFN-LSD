#!/usr/bin/env python3
"""Appendix figure — how much material survives a route, and why.

A reaction count treats every reaction as equal. Real ones are not: each has a
**yield**, the fraction of material that survives the step. Compound those along a
route and you get the route yield -- the share of theoretical material that reaches
the final compound. SCENT's library ships a per-reaction yield (0.65-0.95) and this
is what the delivered libraries look like through it.

The result is not the one we expected, and the mechanism is unambiguous. Mean *step*
yield is essentially identical between the two arms (0.73-0.77 for both, on every
cell) -- so hub-batching is not choosing better chemistry. What differs is route
LENGTH: its routes are shorter, so less yield compounds away. On DRD2 that makes its
libraries carry a substantially *higher* route yield than picking the best candidates
one at a time (0.54 vs 0.36, at 2.0 vs 3.4 steps); on sEH, where its routes are
slightly longer, a slightly lower one. A reaction count cannot see either.

**On what this figure deliberately does not show.** An earlier version drew error bars
from a batch-failure model that treats each route yield as a coin-flip probability of
success (``yield_by_strategy.py``: ``X_b ~ Bern(q)``). That is a modelling assumption,
not a measurement -- yield is a mass fraction, not a success rate -- and drawing it as
an error bar lends it a precision it has not earned. The structural point behind it is
real and worth a sentence of prose: molecules built off one shared intermediate share
its route prefix, so their outcomes are correlated in a way independent molecules' are
not. Quantifying that honestly needs a failure model somebody is willing to defend.

Reads only ``artifacts/yield_risk/``. No cluster, no GPU.

    python3 reproduce/figA1_yield_risk.py
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ARMS = ("best_candidate", "hub_batching")
LABEL = {"best_candidate": "best-candidate", "hub_batching": "hub-batching"}
GREY, BLUE = "#9aa5a7", "#1f6f8b"
VCOL = {"best-candidate": GREY, "hub-batching": BLUE}
# The 5%-FPR hit thresholds. Every molecule in BOTH violins clears these, which is what
# makes the panel a statement about distance from the bar rather than about hits vs misses.
# The 5%-FPR rule, same as every other figure. All three A1 panels were re-run together
# at these gates and against the enumerations currently on disk.
GATES = {"sEH": 5.68, "DRD2": 0.345}


def load(root: Path) -> dict[str, dict[str, dict]]:
    with (root / "strategy_yield.csv").open() as fh:
        rows = list(csv.DictReader(fh))
    out: dict[str, dict[str, dict]] = {}
    for r in rows:
        out.setdefault(r["cell"], {})[r["arm"]] = r
    return out


def f(r, key):
    try:
        return float(r[key])
    except (KeyError, TypeError, ValueError):
        return float("nan")


def draw(cells, out_path: Path) -> str:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return "matplotlib not installed - table written, figure skipped"

    # Merge seeds: two seeds per target is not two conditions, and drawing them as
    # separate bars implies a distinction that is not there. Bars are the mean; each seed
    # is drawn as its own dot rather than summarised by a whisker (see bar()).
    TARGET = {"drd2": "DRD2", "seh": "sEH"}
    merged: dict[str, dict[str, list]] = {}
    for cell, arms in cells.items():
        tgt = TARGET.get(cell.split("_")[0], cell.split("_")[0])
        for arm, r in arms.items():
            merged.setdefault(tgt, {}).setdefault(arm, []).append(r)
    names = sorted(merged, key=lambda n: n != "sEH")
    COL = {"hub_batching": "#1f6f8b", "best_candidate": "#9aa5a7"}

    def seed_values(tgt, arm, key):
        return [f(r, key) for r in merged[tgt].get(arm, [])]

    def stat(tgt, arm, key):
        vals = seed_values(tgt, arm, key)
        return (sum(vals) / len(vals), min(vals), max(vals)) if vals else (0, 0, 0)

    def bar(ax, i, j, tgt, arm, key, label=None):
        """Bar at the mean, with each SEED drawn as its own dot.

        Not an error bar. There are two seeds; a whisker over two points implies a
        distribution that cannot be estimated from them, and when the two agree closely it
        collapses to nothing and reads as "no variation measured" rather than "the two runs
        agreed". Dots say what was actually observed, and match the device Figure 3 uses
        for the same reason. Where the seeds coincide exactly -- sEH hub-batching route
        length is 2.0 in both -- the dots overlap, which is the honest picture.
        """
        m, _lo, _hi = stat(tgt, arm, key)
        x = i + (j - 0.5) * w
        ax.bar(x, m, w * 0.92, color=COL[arm], zorder=2, label=label)
        for v in seed_values(tgt, arm, key):
            ax.plot(x, v, marker="o", ms=3.6, mfc="white", mec="#20343a", mew=0.9,
                    zorder=6, clip_on=False)
    rw = load_rewards(Path(__file__).resolve().parents[1] / "artifacts" / "rewards")
    ncol = 2 + (1 if rw else 0)
    fig, axes = plt.subplots(1, ncol, figsize=(9.5 if ncol == 2 else 13.0, 4.3),
                             gridspec_kw={"width_ratios": [1, 1] if ncol == 2 else [1, 1, 1.05]})
    axl, axr = axes[0], axes[1]
    w = 0.36

    # ---- left: mean route yield. Product of step yields per molecule, averaged. ----
    for i, tgt in enumerate(names):
        for j, arm in enumerate(ARMS):
            bar(axl, i, j, tgt, arm, "mean_route_yield", LABEL[arm] if i == 0 else None)
    axl.set_xticks(range(len(names)))
    axl.set_xticklabels(names, fontsize=9.5)
    axl.set_ylabel("mean route yield")
    axl.set_title("Fraction of material surviving a full route  (\u2191)", fontsize=10.5)
    axl.legend(frameon=False, fontsize=8.5, loc="upper right")
    axl.spines[["top", "right"]].set_visible(False)
    axl.set_ylim(0, max(f(r, "mean_route_yield")
                        for c in cells.values() for r in c.values()) * 1.30)

    # ---- right: the explanation -- route length ----
    for i, tgt in enumerate(names):
        for j, arm in enumerate(ARMS):
            bar(axr, i, j, tgt, arm, "mean_route_len")
    axr.set_xticks(range(len(names)))
    axr.set_xticklabels(names, fontsize=9.5)
    axr.set_ylabel("mean steps per molecule")
    axr.set_title("...which is mostly route length  (\u2193)", fontsize=10.5)
    axr.spines[["top", "right"]].set_visible(False)

    # ---- third: are the molecules we pick WORSE? ----
    if rw:
        draw_reward_violins(axes[2], rw)

    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(out_path.parent / f"{out_path.stem}.{ext}", dpi=200,
                    metadata={"Creator": None, "Producer": None, "CreationDate": None})
    plt.close(fig)
    return f"wrote {out_path.stem}.png and .pdf"


def load_rewards(root: Path):
    """Selected-molecule rewards and the pools they were drawn from.

    Scope matches this figure's other two panels exactly: SCENT, seeds 43 and 44, sEH and
    DRD2. Seeds are pooled, as they are in the bars beside it.
    """
    f = root / "selection_rewards.csv"
    if not f.is_file():
        return None
    out: dict = {}
    with f.open() as fh:
        for r in csv.DictReader(fh):
            out.setdefault(r["target"], {}).setdefault(r["arm"], {}) \
               .setdefault(r["kind"], []).append(float(r["reward"]))
    return out or None


def draw_reward_violins(ax, rw) -> None:
    """What each arm picked, against what it picked FROM.

    The pale violin at each position is that arm's SOURCE pool, the solid one its
    selection. The two pools are different sets -- best-candidate draws from the sampled
    candidates, hub-batching from the enumerated children of its hubs -- so each arm is
    shown against its own, which is the only comparison that means anything.

    Two sub-axes rather than four violins on one: sEH reward is a proxy score (~4-9) and
    DRD2 a probability (0-1), so a shared y-axis would collapse one of them.
    """
    import numpy as np

    targets = [t for t in ("sEH", "DRD2") if t in rw]
    ax.axis("off")
    inner = ax.get_subplotspec().subgridspec(1, len(targets), wspace=0.42)
    for k, tgt in enumerate(targets):
        sub = ax.get_figure().add_subplot(inner[0, k])
        arms = [a for a in ("best-candidate", "hub-batching") if a in rw[tgt]]
        for i, arm in enumerate(arms):
            pool = rw[tgt][arm].get("pool", [])
            sel = rw[tgt][arm].get("selected", [])
            if pool:
                b = sub.violinplot([pool], positions=[i], widths=0.86,
                                   showextrema=False, showmedians=False)["bodies"][0]
                b.set_facecolor(VCOL[arm]); b.set_alpha(0.22); b.set_edgecolor("none")
            if sel:
                b = sub.violinplot([sel], positions=[i], widths=0.50,
                                   showextrema=False, showmedians=False)["bodies"][0]
                b.set_facecolor(VCOL[arm]); b.set_alpha(0.92); b.set_edgecolor("none")
                sub.plot(i, float(np.median(sel)), marker="_", ms=13,
                         color="#20343a", mew=2.0, zorder=7)
        gate = GATES.get(tgt)
        if gate is not None:
            sub.axhline(gate, color="#c2622d", lw=1.1, ls=(0, (4, 2)), zorder=3)
            sub.text(-0.62, gate, f"hit threshold {gate}", va="bottom", ha="left",
                     fontsize=6.8, color="#c2622d")
        # sEH only: the level above which the proxy stops being evidence of activity.
        # Without it, best-candidate's higher selection reads as "better molecules".
        if tgt == "sEH":
            sub.axhline(8.0, color="#5b6b6d", lw=1.0, ls=(0, (1.5, 2)), zorder=3)
            sub.text(-0.62, 8.0, "no known active reaches 8.0", va="bottom", ha="left",
                     fontsize=6.8, color="#5b6b6d")
        sub.set_xticks(range(len(arms)))
        sub.set_xticklabels(["best-\ncandidate", "hub-\nbatching"], fontsize=7.5)
        sub.set_xlim(-0.68, 1.62)
        sub.set_title(tgt, fontsize=9.5, color="#0f1e20")
        sub.tick_params(labelsize=8)
        sub.spines[["top", "right"]].set_visible(False)
        if k == 0:
            sub.set_ylabel("reward")
    ax.set_title("What each arm picked, against what it picked from",
                 fontsize=10.5, pad=14)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1] / "artifacts" / "yield_risk"
    if not root.is_dir():
        sys.exit(f"missing artifacts: {root}")
    cells = load(root)
    out = args.out or (Path(__file__).resolve().parents[1] / "build" / "figures")
    out.mkdir(parents=True, exist_ok=True)

    table = []
    print("Appendix figure — yield and risk concentration\n")
    print(f"  {'cell':<14}{'arm':<16}{'modes':>6}{'route yield':>12}"
          f"{'steps':>7}{'step yield':>11}")
    for cell in sorted(cells):
        for arm in ARMS:
            r = cells[cell].get(arm)
            if r is None:
                continue
            ind, shr = f(r, "sd_if_independent"), f(r, "sd_with_shared_prefixes")
            infl = shr / ind if ind else float("nan")
            print(f"  {cell:<14}{LABEL[arm]:<16}{int(f(r,'modes')):>6}"
                  f"{f(r,'mean_route_yield'):>12.3f}{f(r,'mean_route_len'):>7.2f}"
                  f"{f(r,'mean_step_yield'):>11.3f}")
            table.append({"cell": cell, "arm": arm, "modes": int(f(r, "modes")),
                          # what the figure now plots, first
                          "mean_route_yield": f(r, "mean_route_yield"),
                          "mean_route_len": f(r, "mean_route_len"),
                          "mean_step_yield": f(r, "mean_step_yield"),
                          "expected_molecules": f(r, "expected_molecules"),
                          "sd_if_independent": ind, "sd_with_shared_prefixes": shr,
                          "spread_inflation": round(infl, 3),
                          "pct_in_multi_batches": f(r, "pct_in_multi_batches"),
                          "largest_batch": int(f(r, "largest_batch")),
                          "worst_batch_loss_prob": f(r, "worst_batch_loss_prob")})

    ylds, lens = [], []
    for cell, arms in cells.items():
        if not {"hub_batching", "best_candidate"} <= set(arms):
            continue
        h, b = arms["hub_batching"], arms["best_candidate"]
        ylds.append((cell, f(h, "mean_route_yield"), f(b, "mean_route_yield")))
        lens.append((cell, f(h, "mean_route_len"), f(b, "mean_route_len")))
    print("\n  mean route yield (hub vs best-candidate):")
    for cell, hv, bv in sorted(ylds):
        arrow = "higher" if hv > bv else "lower"
        print(f"    {cell:<14} {hv:.3f} vs {bv:.3f}   ({arrow} for hub-batching)")
    steps = [(c, f(a["hub_batching"], "mean_step_yield"),
              f(a["best_candidate"], "mean_step_yield"))
             for c, a in cells.items()
             if {"hub_batching", "best_candidate"} <= set(a)]
    lo = min(min(h, b) for _, h, b in steps)
    hi = max(max(h, b) for _, h, b in steps)
    print(f"  mean STEP yield is {lo:.3f}-{hi:.3f} for BOTH arms on every cell, so the")
    print("  route-yield difference is length, not chemistry:")
    for cell, hv, bv in sorted(lens):
        print(f"    {cell:<14} {hv:.2f} vs {bv:.2f}")
    print("\n  NOTE: the batch-failure columns (sd_*, worst_batch_loss_prob) are carried in")
    print("  the CSV but NOT plotted -- they rest on treating a route yield as a coin-flip")
    print("  success probability, which is an assumption rather than a measurement.")

    with (out / "figA1_yield_risk.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(table[0]))
        w.writeheader()
        w.writerows(table)
    print()
    print(draw(cells, out / "figA1_yield_risk"))
    print(f"table: {out/'figA1_yield_risk.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
