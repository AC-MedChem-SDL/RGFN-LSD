#!/usr/bin/env python3
"""Appendix figure — batching wins on expected molecules and concentrates the risk.

The cost metric counts reactions *attempted*. Every reaction has a yield, so the
library that gets planned is not the library that arrives. Putting yield back in gives
two results, and the second is the one a chemist cares about.

**The expected count still favours batching, by a lot** -- 2.7-5.3x more molecules
actually delivered.

**But the failures stop being independent.** Hub-batching's savings come from many
final molecules descending from one shared intermediate. When that intermediate fails,
everything below it fails with it. So the spread in what arrives widens 1.8-4.9x
relative to treating each molecule as an independent coin flip -- while the baseline's
spread barely moves at all (1.00-1.06x), because it barely shares anything. The
correlated risk is a property of batching, not of the chemistry.

This is a risk caveat on a real win, not a reversal, and it belongs in the paper
rather than in a footnote: it is the first thing an experimentalist would ask.

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

    names = sorted(cells)
    fig, (axl, axr) = plt.subplots(1, 2, figsize=(11, 4.3),
                                   gridspec_kw={"width_ratios": [1.25, 1]})
    COL = {"hub_batching": "#1f6f8b", "best_candidate": "#9aa5a7"}
    width = 0.34

    # ---- left: expected molecules, with BOTH error bars ----
    for i, cell in enumerate(names):
        for j, arm in enumerate(ARMS):
            r = cells[cell].get(arm)
            if r is None:
                continue
            x = i + (j - 0.5) * width
            exp = f(r, "expected_molecules")
            axl.bar(x, exp, width * 0.92, color=COL[arm], zorder=2,
                    label=LABEL[arm] if i == 0 else None)
            # thin bar = if failures were independent; thick = with shared prefixes.
            axl.errorbar(x, exp, yerr=f(r, "sd_if_independent"), fmt="none",
                         ecolor="#3b4a4c", elinewidth=2.4, capsize=7, zorder=4)
            axl.errorbar(x, exp, yerr=f(r, "sd_with_shared_prefixes"), fmt="none",
                         ecolor="#c0603a", elinewidth=1.1, capsize=3.5, zorder=3)
    axl.set_xticks(range(len(names)))
    axl.set_xticklabels(names, fontsize=8)
    axl.set_ylabel("molecules actually delivered\n(expected, after yield)")
    axl.set_title("Batching still delivers 2.7–5.3× more molecules —\n"
                  "but the orange spread is the honest one", fontsize=9.5)
    axl.legend(frameon=False, fontsize=8, loc="upper left")
    axl.spines[["top", "right"]].set_visible(False)
    # Below the axis, not inside the plot: the tall drd2 bars leave no clear space.
    axl.set_xlabel("dark caps: failures treated as independent   ·   "
                   "orange caps: shared prefixes accounted for",
                   fontsize=7.5, color="#3b4a4c", labelpad=8)

    # ---- right: the inflation factor, i.e. the mechanism ----
    ys, labels, colors, notes = [], [], [], []
    for cell in names:
        for arm in ARMS:
            r = cells[cell].get(arm)
            if r is None:
                continue
            ind, shr = f(r, "sd_if_independent"), f(r, "sd_with_shared_prefixes")
            ys.append(shr / ind if ind else float("nan"))
            labels.append(f"{cell} · {LABEL[arm]}")
            colors.append(COL[arm])
            notes.append(f"largest batch {int(f(r,'largest_batch'))}"
                         f" · {f(r,'pct_in_multi_batches'):.0f}% shared")
    ypos = list(range(len(ys)))
    axr.barh(ypos, ys, color=colors, height=0.6, zorder=3)
    axr.axvline(1.0, color="#3b4a4c", lw=1.2, zorder=4)
    # Horizontal, above the plot: rotated at the baseline it collided with the axis label.
    axr.annotate("1× = no correlated risk", xy=(1.09, -0.72), fontsize=7.5,
                 color="#3b4a4c", ha="left", va="bottom", annotation_clip=False)
    for y, v, n in zip(ypos, ys, notes):
        axr.text(v + 0.08, y, n, fontsize=6.6, va="center", color="#5f7275")
    axr.set_yticks(ypos)
    axr.set_yticklabels(labels, fontsize=7)
    axr.set_xlim(0, max(ys) * 1.62)   # room for the per-bar annotations
    axr.set_ylim(len(ys) - 0.4, -1.0)  # headroom for the baseline note
    axr.set_xlabel("spread inflation once shared steps are counted\n(× the independent-failure spread)")
    axr.set_title("The risk is concentrated by batching,\nnot by the chemistry", fontsize=9.5)
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
    print(f"  {'cell':<14}{'arm':<16}{'modes':>6}{'E[mol]':>8}{'sd ind':>8}"
          f"{'sd shared':>10}{'inflation':>10}{'worst p':>9}")
    for cell in sorted(cells):
        for arm in ARMS:
            r = cells[cell].get(arm)
            if r is None:
                continue
            ind, shr = f(r, "sd_if_independent"), f(r, "sd_with_shared_prefixes")
            infl = shr / ind if ind else float("nan")
            print(f"  {cell:<14}{LABEL[arm]:<16}{int(f(r,'modes')):>6}"
                  f"{f(r,'expected_molecules'):>8.1f}{ind:>8.2f}{shr:>10.2f}"
                  f"{infl:>10.2f}{f(r,'worst_batch_loss_prob'):>9.2f}")
            table.append({"cell": cell, "arm": arm, "modes": int(f(r, "modes")),
                          "expected_molecules": f(r, "expected_molecules"),
                          "sd_if_independent": ind, "sd_with_shared_prefixes": shr,
                          "spread_inflation": round(infl, 3),
                          "pct_in_multi_batches": f(r, "pct_in_multi_batches"),
                          "largest_batch": int(f(r, "largest_batch")),
                          "worst_batch_loss_prob": f(r, "worst_batch_loss_prob")})

    ratios, infl_hub, infl_bc = [], [], []
    for cell, arms in cells.items():
        if not {"hub_batching", "best_candidate"} <= set(arms):
            continue
        h, b = arms["hub_batching"], arms["best_candidate"]
        ratios.append(f(h, "expected_molecules") / f(b, "expected_molecules"))
        infl_hub.append(f(h, "sd_with_shared_prefixes") / f(h, "sd_if_independent"))
        infl_bc.append(f(b, "sd_with_shared_prefixes") / f(b, "sd_if_independent"))
    print(f"\n  expected molecules delivered : {min(ratios):.2f}x-{max(ratios):.2f}x in our favour")
    print(f"  spread inflation, hub-batching: {min(infl_hub):.2f}x-{max(infl_hub):.2f}x")
    print(f"  spread inflation, baseline    : {min(infl_bc):.2f}x-{max(infl_bc):.2f}x"
          f"   <- essentially none, so the correlated risk is batching's, not the chemistry's")

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
