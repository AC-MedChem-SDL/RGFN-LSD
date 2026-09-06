#!/usr/bin/env python3
"""Appendix A2 — is the advantage an artifact of where we set the two thresholds?

Every headline number in this paper is quoted at one setting of two knobs a reader
can reasonably argue with:

  * the **reward bar** -- how good a molecule has to be to count at all;
  * the **diversity cutoff** -- how different two molecules have to be to count twice.

Pick them generously and everything looks like a mode; pick them strictly and nothing
does. So the fair question is not "are these the right values" but "does the result
survive the other values". This figure answers that by measuring the entire grid --
9 reward bars x 13 cutoffs, on all four generators, at the paper's own 100-reaction
budget -- instead of defending a single point.

Each cell is the ratio of the two arms' cost:

    advantage = (reactions/mode, best-candidate) / (reactions/mode, hub-batching)

so 1.0 is parity and >1 means hub-batching bought its distinct molecules more cheaply.
Because the budget is fixed, this is monotone in "modes at 100 reactions", the paper's
primary readout -- the surface is the headline metric swept, not a different one.

**Two cell classes are deliberately not colored**, because counting them would flatter
us. Hatched cells are *pool-limited*: one arm ran out of library before it could spend
the budget, so its cost is measured over a shorter run and is not comparable to a cell
where the budget bound. Grey cells are *no modes*: nothing in that generator's pool
clears that reward bar at all, for either arm, so there is no selection to compare --
that is a fact about the pool, not about any strategy. Both appear at the strict end,
which is exactly where an unflagged surface would look most impressive.

The two markers on each panel are the only two gates the paper itself quotes: 5.0
(Figure 1) and 7.0 (Figure 3, Table 1), both at cutoff 0.5. The 5%-FPR standard for
sEH, 5.68, falls between two measured bars that are both wins.

    python3 reproduce/figA2_two_knob_surface.py
    python3 reproduce/figA2_two_knob_surface.py --layout row     # 1x4, full-page landscape
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

# Diverging, two hues with a neutral midpoint at parity: orange below 1.0, blue above.
# Ratio data is polarity data -- the reader's question is "which side of parity", and a
# sequential ramp would hide the sign. The midpoint is neutral grey, never a hue.
BLUE, ORANGE, NEUTRAL = "#1f6f8b", "#c2622d", "#f2f0ec"
GREY_NOMODE, INK, MUTED = "#d8dcdc", "#0f1e20", "#5b6b6d"

# The gates the paper actually quotes, both at cutoff 0.5. Figure 1 gates sEH at 5.0;
# Figure 3 and Table 1 at 7.0. Marking both is the point -- the figure has to show that
# the disagreement between them is immaterial.
PAPER_GATES = [(5.0, 0.5, "Fig 1"), (7.0, 0.5, "Fig 3 / Table 1")]


def load(path: Path):
    rows = list(csv.DictReader(path.open()))
    if not rows:
        raise SystemExit(f"no rows in {path}")
    gens, by = [], {}
    for r in rows:
        g = r["generator"]
        if g not in by:
            by[g] = {}
            gens.append(g)
        by[g][(float(r["reward_bar"]), float(r["diversity_cutoff"]))] = r
    return gens, by


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    repo = Path(__file__).resolve().parents[1]
    ap.add_argument("--artifacts", default=repo / "artifacts" / "two_knob")
    ap.add_argument("--out", type=Path, default=None,
                    help="output DIRECTORY (default build/figures/, as the other reproduce scripts)")
    # 2x2 by default: a 1x4 row is ~14in wide, which only fits a paper as a full-page
    # landscape plate. The grid spans two columns at a readable type size.
    ap.add_argument("--layout", choices=("grid", "row"), default="grid",
                    help="grid = 2x2 (default, fits a two-column appendix); row = 1x4")
    a = ap.parse_args()

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
    from matplotlib.patches import Patch

    art = Path(a.artifacts)
    gens, by = load(art / "surface.csv")
    prov = json.loads((art / "provenance.json").read_text())
    budget = prov.get("budget_reactions")
    tot = prov.get("totals", {})

    bars = sorted({k[0] for k in by[gens[0]]})
    cuts = sorted({k[1] for k in by[gens[0]]})
    # Cutoff descending left-to-right: the axis then reads permissive -> strict, so the
    # eye travels toward the harder problem rather than away from it.
    cuts_plot = list(reversed(cuts))

    cmap = LinearSegmentedColormap.from_list("adv", [ORANGE, NEUTRAL, BLUE])
    vmax = max(5.0, max((float(r["advantage"]) for g in gens for r in by[g].values()
                         if r["advantage"] != ""), default=5.0))
    # Centered on parity so the sign of the result reads off the color alone; the orange
    # half is kept live even with no losses, so a future regression would show.
    norm = TwoSlopeNorm(vmin=0.5, vcenter=1.0, vmax=vmax)

    if a.layout == "grid" and len(gens) == 4:
        ncols, nrows, figsize = 2, 2, (8.4, 7.6)
        # Title/legend offsets are in FIGURE fractions, so they must scale with the
        # aspect: values tuned on the 3.9in-tall row open a band of dead space on the
        # 7.6in-tall grid.
        y_title, y_sub, y_leg, y_note, top, bottom = 1.062, 1.014, -0.035, -0.062, 0.925, 0.075
    else:
        ncols, nrows, figsize = len(gens), 1, (3.15 * len(gens) + 1.5, 3.9)
        y_title, y_sub, y_leg, y_note, top, bottom = 1.155, 1.062, -0.085, -0.125, 0.84, 0.16
    fig, axes_arr = plt.subplots(nrows, ncols, figsize=figsize, sharey=True, sharex=True)
    axes = list(np.ravel(axes_arr)) if len(gens) > 1 else [axes_arr]
    fig.subplots_adjust(top=top, bottom=bottom, hspace=0.20, wspace=0.08)

    for ax, g in zip(axes, gens):
        grid = np.full((len(bars), len(cuts_plot)), np.nan)
        for i, b in enumerate(bars):
            for j, c in enumerate(cuts_plot):
                r = by[g][(b, c)]
                if r["cell_class"] == "comparable":
                    grid[i, j] = float(r["advantage"])
        ax.set_facecolor("white")
        ax.imshow(grid, origin="lower", aspect="auto", cmap=cmap, norm=norm,
                  extent=(-0.5, len(cuts_plot) - 0.5, -0.5, len(bars) - 0.5),
                  interpolation="nearest")

        # Non-comparable cells: texture for pool-limited, flat grey for no-modes. Texture
        # rather than a second color, so the distinction survives greyscale printing and
        # colorblind readers -- these are the cells a skeptical reader looks for first.
        for i, b in enumerate(bars):
            for j, c in enumerate(cuts_plot):
                cls = by[g][(b, c)]["cell_class"]
                if cls == "pool_limited":
                    ax.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1, facecolor=NEUTRAL,
                                               edgecolor=MUTED, hatch="xxx", lw=0.4, alpha=0.95))
                elif cls == "no_modes":
                    ax.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1, facecolor=GREY_NOMODE,
                                               edgecolor="white", lw=0.4))

        for bar_v, cut_v, _ in PAPER_GATES:
            if bar_v in bars and cut_v in cuts_plot:
                ax.plot(cuts_plot.index(cut_v), bars.index(bar_v), marker="o", ms=6.5,
                        mfc="none", mec=INK, mew=1.6, zorder=5)

        n = prov["cells"].get(
            next((k for k, v in prov["cells"].items() if v["label"] == g), ""), {})
        c = n.get("counts", {})
        ax.set_title(g, fontsize=12, fontweight="600", color=INK, pad=17)
        if c:
            ax.text(0.5, 1.012, f"{c['win']}/{c['comparable']} cells cheaper",
                    transform=ax.transAxes, ha="center", va="bottom",
                    fontsize=8.5, color=MUTED)
        ax.set_xticks(range(len(cuts_plot)))
        ax.set_xticklabels([f"{c:.2f}".rstrip("0") if (i % 2 == 0) else ""
                            for i, c in enumerate(cuts_plot)], fontsize=8)
        ax.set_xlabel("diversity cutoff (Tanimoto)", fontsize=9.5, color=INK)
        for s in ax.spines.values():
            s.set_color("#c9d1d2")
        ax.tick_params(colors=MUTED, length=2)

    for k, ax in enumerate(axes):
        if k % ncols == 0:
            ax.set_yticks(range(len(bars)))
            ax.set_yticklabels([f"{b:g}" for b in bars], fontsize=8)
            ax.set_ylabel("reward bar", fontsize=9.5, color=INK)
        # Only the bottom row carries the x label, else it repeats under every panel.
        if k < len(axes) - ncols:
            ax.set_xlabel("")

    cb = fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=cmap), ax=axes,
                      fraction=0.022, pad=0.015, extend="max")
    cb.set_label("× cheaper per distinct molecule  (1.0 = parity)",
                 fontsize=9, color=INK)
    cb.ax.tick_params(labelsize=8, colors=MUTED)
    cb.outline.set_edgecolor("#c9d1d2")

    fig.suptitle("The advantage does not depend on where the two thresholds are set",
                 fontsize=13.5, fontweight="600", color=INK, y=y_title)
    sub = (f"sEH · budget {budget} reactions · {len(bars)}×{len(cuts)} grid per generator — "
           f"hub-batching is cheaper in {tot.get('win','?')} of {tot.get('comparable','?')} "
           f"comparable cells, ties {tot.get('tie','?')}, loses {tot.get('loss','?')}")
    fig.text(0.5, y_sub, sub, ha="center", va="bottom", fontsize=9.5, color=MUTED)

    handles = [
        Patch(facecolor=NEUTRAL, edgecolor=MUTED, hatch="xxx",
              label="pool-limited — an arm ran out of library before spending the budget"),
        Patch(facecolor=GREY_NOMODE, edgecolor="white",
              label="no modes — nothing in the pool clears this bar, for either arm"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=2, frameon=False,
               fontsize=8.5, bbox_to_anchor=(0.5, y_leg), labelcolor=INK)
    fig.text(0.5, y_note, "○ = the two gates this paper quotes: 5.0 (Fig 1) and 7.0 "
             "(Fig 3 / Table 1), both at cutoff 0.5.  The 5%-FPR standard for sEH, 5.68, "
             "falls between two measured bars that are both wins.",
             ha="center", va="bottom", fontsize=8, color=MUTED)

    outdir = a.out or (repo / "build" / "figures")
    outdir.mkdir(parents=True, exist_ok=True)
    stem = "figA2_two_knob_surface" + ("_row" if a.layout == "row" and len(gens) == 4 else "")
    out = outdir / f"{stem}.png"
    fig.savefig(out, dpi=200, bbox_inches="tight", facecolor="white")
    fig.savefig(out.with_suffix(".pdf"), bbox_inches="tight", facecolor="white")
    print(f"wrote {out} and {out.with_suffix('.pdf')}")

    print(f"\ntwo-knob surface, budget {budget} reactions:")
    for g in gens:
        key = next(k for k, v in prov["cells"].items() if v["label"] == g)
        c = prov["cells"][key]["counts"]
        vals = sorted(float(r["advantage"]) for r in by[g].values() if r["advantage"] != "")
        med = vals[len(vals) // 2] if vals else float("nan")
        print(f"  {g:8s} {c['win']:3d} win / {c['tie']} tie / {c['loss']} loss   "
              f"median {med:.2f}x   (range {vals[0]:.2f}-{vals[-1]:.2f})   "
              f"{c['pool_limited']:2d} pool-limited, {c['no_modes']:2d} no-modes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
