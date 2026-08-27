#!/usr/bin/env python3
"""Figure 1 — distinct high-reward molecules delivered at a fixed reaction budget.

    "I have 100 reactions. How many distinct high-reward molecules do I get?"

100 reactions is roughly one plate, which is why the budget is the readout rather
than a mode target: a chemist has a budget, not a shopping list. Hub-batching is
compared against best-candidate on the same trained checkpoints, the same gate, and
the same cost model.

Reads only ``artifacts/reaction_budget/`` -- committed CSVs, no cluster, no GPU, no
generator. Runs in seconds.

    python3 reproduce/fig1_reaction_budget.py
    python3 reproduce/fig1_reaction_budget.py --include-uncalibrated

Three definitions carry the figure, and all three can flatter a result if applied
loosely:

**modes at R.** The cumulative modes at the last point whose cumulative reactions do
not exceed R. Never interpolated.

**Status.** A cell is *budget-binding* when the next mode would not fit -- the only
case where two arms are spending the same budget. *pool-exhausted* means the arm ran
out of qualifying candidates with budget to spare; *mode-capped* means it hit the
300-mode ceiling early. Quoting either as "modes at R reactions" implies the arm
could have spent R and declined, which is false.

**Comparable.** Both arms budget-binding. Only comparable cells enter the median, so
no ratio is inflated by one side running out of material.

**Median convention.** ``statistics.median`` -- the mean of the two middle values on
even samples. The research tree's readout takes the upper-middle element instead;
the two agree on odd n, which includes the R=100 headline (31 comparable cells), and
differ by at most 0.023 elsewhere. ``fig1_summary.csv`` carries both columns.

The headline is computed over targets whose gate is *calibrated* against
property-matched decoys (``gates.csv``). 6TD3's -2.0 gate never was, and was later
measured to be exploitable by the generator itself, so it is excluded by default and
reported alongside rather than silently pooled.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path

ARMS = ("hub_batching", "best_candidate")
DEFAULT_BUDGETS = (50, 100, 150, 200)


def artifact_root() -> Path:
    return Path(__file__).resolve().parents[1] / "artifacts" / "reaction_budget"


def load_gates(root: Path) -> dict[str, dict]:
    with (root / "gates.csv").open() as fh:
        return {r["target"]: r for r in csv.DictReader(fh)}


def read_curve(path: Path) -> list[tuple[int, int, int]]:
    with path.open() as fh:
        return [(int(r["cum_reactions"]), int(r["cum_modes"]),
                 int(r["cum_reward_gen_calls"] or 0)) for r in csv.DictReader(fh)]


def read_at_budget(rows, budget: int, mode_cap: int) -> dict | None:
    """Modes at a fixed reaction budget, plus the label saying whether it bound."""
    if not rows:
        return None
    kept = [r for r in rows if r[0] <= budget]
    if not kept:
        return dict(modes=0, used=0, calls=0, status="budget-binding",
                    modes_available=rows[-1][1])
    used, modes, calls = kept[-1]
    total_rxn, total_modes = rows[-1][0], rows[-1][1]
    if total_modes >= mode_cap and total_rxn <= budget:
        status = "mode-capped"
    elif total_rxn <= budget:
        status = "pool-exhausted"
    else:
        status = "budget-binding"
    return dict(modes=modes, used=used, calls=calls, status=status,
                modes_available=total_modes)


def target_of(cell: str) -> str | None:
    return next((t for t in ("6td3", "clpp", "drd2", "seh") if cell.endswith(t)), None)


def collect(root: Path, budgets) -> list[dict]:
    """One row per (cell, seed, budget), both arms side by side."""
    out = []
    for seed_dir in sorted(root.glob("seed*")):
        seed = int(seed_dir.name.removeprefix("seed"))
        for cdir in sorted(p for p in seed_dir.iterdir() if p.is_dir()):
            summary = cdir / "summary.json"
            if not summary.is_file():
                continue
            meta = json.loads(summary.read_text())
            cell = meta.get("tag", cdir.name)
            target = target_of(cell)
            if target is None:
                continue
            mode_cap = int(meta.get("budget_modes") or 300)
            curves = {}
            for arm in ARMS:
                path = cdir / f"curve_{arm}.csv"
                if path.is_file():
                    curves[arm] = read_curve(path)
            if len(curves) < 2:
                continue
            for R in budgets:
                hb = read_at_budget(curves["hub_batching"], R, mode_cap)
                bc = read_at_budget(curves["best_candidate"], R, mode_cap)
                if hb is None or bc is None:
                    continue
                out.append(dict(
                    cell=cell, generator=cell.rsplit("_", 1)[0], target=target, seed=seed,
                    budget_rxns=R,
                    hub_modes=hb["modes"], bc_modes=bc["modes"],
                    hub_used=hb["used"], bc_used=bc["used"],
                    hub_status=hb["status"], bc_status=bc["status"],
                    ratio=round(hb["modes"] / bc["modes"], 3) if bc["modes"] else "",
                    comparable=hb["status"] == "budget-binding" == bc["status"],
                    gate=meta.get("reward_threshold", ""),
                ))
    return out


def summarise(rows, budgets, gates, include_uncal: bool):
    cal = {t for t, g in gates.items() if g["calibrated"].lower() == "true"}
    lines, table = [], []
    for R in budgets:
        at_R = [r for r in rows if r["budget_rxns"] == R]
        for label, subset in (("calibrated", [r for r in at_R if r["target"] in cal]),
                              ("all cells", at_R)):
            if label == "all cells" and not include_uncal and cal >= {r["target"] for r in at_R}:
                continue  # nothing uncalibrated present; the two views coincide
            comp = [r for r in subset if r["comparable"] and r["ratio"] != ""]
            if not comp:
                continue
            vals = sorted(float(r["ratio"]) for r in comp)
            table.append(dict(budget_rxns=R, scope=label, n_comparable=len(comp),
                              n_total=len(subset), median_ratio=round(statistics.median(vals), 3),
                              # The research tree's readout reports the upper-middle
                              # element rather than the mean of the two middle values.
                              # Identical on odd n -- including the R=100 headline --
                              # and at most 0.023 apart on even n. Both are emitted so
                              # a reviewer recomputing either way finds no surprise.
                              median_upper_middle=round(vals[len(vals) // 2], 3),
                              min_ratio=min(vals), max_ratio=max(vals),
                              n_bc_wins=sum(1 for v in vals if v <= 1.0)))
            lines.append(f"  R={R:<4} {label:<11} {statistics.median(vals):.2f}x   "
                         f"{len(comp)}/{len(subset)} comparable   "
                         f"range {min(vals):.2f}-{max(vals):.2f}   "
                         f"best-candidate wins or ties: {sum(1 for v in vals if v <= 1.0)}")
    return table, lines


MODEL_ORDER = ["rgfn", "scent", "rxnflow", "fraggfn"]
MODEL_LABEL = {"rgfn": "RGFN", "scent": "SCENT", "rxnflow": "RxnFlow", "fraggfn": "FragGFN"}
TARGET_ORDER = ["seh", "drd2", "clpp", "6td3"]
TARGET_LABEL = {"seh": "sEH", "drd2": "DRD2", "clpp": "ClpP", "6td3": "6TD3"}
HUB_C, BC_C = "#1f6f8b", "#9aa5a7"


def draw(rows, out_path: Path, gates, budget: int) -> str:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return "matplotlib not installed - CSV written, figure skipped"

    cal = {t for t, g in gates.items() if g["calibrated"].lower() == "true"}
    at_R = [r for r in rows if r["budget_rxns"] == budget and r["comparable"]]
    if not at_R:
        return "no comparable cells to draw"

    # One slot per (model, target); models separated by a gap so the four sections read
    # as sections. Within a slot the two arms sit adjacent, which is the comparison the
    # eye should make first.
    GAP = 1.0
    slots, xs = [], {}
    for mi, model in enumerate(MODEL_ORDER):
        for ti, target in enumerate(TARGET_ORDER):
            pts = [r for r in at_R if r["generator"] == model and r["target"] == target]
            if not pts:
                continue
            x = mi * (len(TARGET_ORDER) + GAP) + ti
            xs[(model, target)] = x
            slots.append((model, target, x, pts))
    if not slots:
        return "no cells matched the model/target order"

    fig, ax = plt.subplots(figsize=(11.5, 4.6))
    w = 0.40
    for model, target, x, pts in slots:
        uncal = target not in cal
        for sign, key, color in ((-1, "bc_modes", BC_C), (+1, "hub_modes", HUB_C)):
            vals = [r[key] for r in pts]
            mean = sum(vals) / len(vals)
            ax.bar(x + sign * w / 2, mean, w * 0.94, color=color, zorder=2,
                   hatch="//" if uncal else None,
                   edgecolor="white" if uncal else "none", linewidth=0.0)
            # Full range, not a standard deviation: at 2-3 seeds a range is the only
            # honest summary, and it makes the stability visible without claiming a
            # distribution we cannot estimate.
            if len(vals) > 1:
                lo, hi = min(vals), max(vals)
                ax.plot([x + sign * w / 2] * 2, [lo, hi], color="#20343a", lw=1.1,
                        zorder=5, solid_capstyle="butt")
                for y in (lo, hi):
                    ax.plot([x + sign * w / 2 - 0.07, x + sign * w / 2 + 0.07], [y, y],
                            color="#20343a", lw=1.1, zorder=5)
        ax.text(x, -3.0, TARGET_LABEL[target], ha="center", va="top", fontsize=8.5)

    # Model section labels and separators
    top = max(r["hub_modes"] for r in at_R) * 1.16
    for mi, model in enumerate(MODEL_ORDER):
        present = [x for (m, t), x in xs.items() if m == model]
        if not present:
            continue
        ax.text(sum(present) / len(present), -13.5, MODEL_LABEL[model], ha="center",
                va="top", fontsize=11, fontweight="semibold")
        if mi:
            ax.axvline(min(present) - (GAP + 1) / 2, color="#d8e2e2", lw=1, zorder=1)

    ax.set_ylim(0, top)
    ax.set_xlim(-1.1, max(xs.values()) + 1.1)
    ax.set_xticks([])
    # No arrow on the axis: direction lives in the title only, and the budget is
    # stated in the caption rather than duplicated here.
    ax.set_ylabel("distinct high-reward molecules")
    # Direction arrows go in the title, never on an axis label: the title is always
    # upright, while a rotated y-label makes the reader re-orient the glyph.
    ax.set_title("hub-batching produces substantially more modes "
                 "on a fixed reaction budget  (\u2191)", fontsize=11.5, pad=30)
    ax.bar(0, 0, color=HUB_C, label="hub-batching")
    ax.bar(0, 0, color=BC_C, label="best-candidate")
    if any(t not in cal for _, t, _, _ in slots):
        # White fill with a black edge and black hatch: on a light background a white
        # stripe over light grey is invisible, so the swatch failed to explain itself.
        # Drawn differently from the bars ON PURPOSE: a white stripe reads on a
        # coloured bar but vanishes on the page ground, so the key uses black-on-white
        # to explain the same encoding legibly.
        ax.bar(0, 0, facecolor="white", hatch="//", edgecolor="black", linewidth=0.9,
               label="uncalibrated reward generator")
    # Above the axes, not inside: several bars reach the top of the panel and any
    # in-plot corner collides with one of them.
    ax.legend(frameon=False, fontsize=9, ncol=3, handlelength=1.4, columnspacing=1.6,
              loc="lower center", bbox_to_anchor=(0.5, 1.02))
    ax.spines[["top", "right", "bottom"]].set_visible(False)
    ax.tick_params(axis="y", length=3)
    ax.margins(x=0.01)

    fig.subplots_adjust(bottom=0.17)
    for ext in ("png", "pdf"):
        fig.savefig(out_path.parent / f"{out_path.stem}.{ext}", dpi=200,
                    bbox_inches="tight",
                    metadata={"Creator": None, "Producer": None, "CreationDate": None})
    plt.close(fig)
    return f"wrote {out_path.stem}.png and .pdf"


def gate_variant_readout(root: Path, budget: int) -> list[dict]:
    """sEH at each swept bar, from the threshold-variant cells.

    The workshop reports BOTH bars rather than unifying: 5.0 is the calibrated one
    (Logs/034 measured only weak proxy enrichment above ~6; Logs/051 found diversity
    collapsing past ~7), while 7.0 is the value the RGFN paper's own sEH numbers are
    quoted at, and the value the external comparison happens to be measured at. Neither
    stands in for the other, and the advantage holds at both -- which is a stronger
    statement than picking one.
    """
    vdir = root / "gate_variants"
    if not vdir.is_dir():
        return []
    out = []
    for seed_dir in sorted(vdir.glob("seed*")):
        seed = int(seed_dir.name.removeprefix("seed"))
        for cdir in sorted(p for p in seed_dir.iterdir() if p.is_dir()):
            meta = json.loads((cdir / "summary.json").read_text())
            gate = meta.get("reward_threshold")
            cap = int(meta.get("budget_modes") or 300)
            curves = {a: read_curve(cdir / f"curve_{a}.csv") for a in ARMS
                      if (cdir / f"curve_{a}.csv").is_file()}
            if len(curves) < 2:
                continue
            hb = read_at_budget(curves["hub_batching"], budget, cap)
            bc = read_at_budget(curves["best_candidate"], budget, cap)
            if hb is None or bc is None:
                continue
            out.append(dict(
                cell=cdir.name, seed=seed, gate=gate,
                generator=cdir.name.split("_")[0],
                hub_modes=hb["modes"], bc_modes=bc["modes"],
                hub_status=hb["status"], bc_status=bc["status"],
                comparable=hb["status"] == "budget-binding" == bc["status"],
                ratio=round(hb["modes"] / bc["modes"], 3) if bc["modes"] else "",
            ))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--budgets", default=",".join(str(b) for b in DEFAULT_BUDGETS))
    ap.add_argument("--headline-budget", type=int, default=100)
    ap.add_argument("--include-uncalibrated", action="store_true",
                    help="also report the all-cells median even where it coincides")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    root = artifact_root()
    if not root.is_dir():
        sys.exit(f"missing artifacts: {root}")
    budgets = [int(b) for b in args.budgets.split(",")]
    out = args.out or (Path(__file__).resolve().parents[1] / "build" / "figures")
    out.mkdir(parents=True, exist_ok=True)

    gates = load_gates(root)
    rows = collect(root, budgets)
    if not rows:
        sys.exit(f"no cells found under {root}")

    with (out / "fig1_reaction_budget.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    # ---- secondary readout: sEH at every swept bar ----
    variants = gate_variant_readout(root, args.headline_budget)
    if variants:
        with (out / "fig1_seh_gate_variants.csv").open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(variants[0]))
            w.writeheader(); w.writerows(variants)

    table, lines = summarise(rows, budgets, gates, args.include_uncalibrated)
    with (out / "fig1_summary.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(table[0]))
        w.writeheader()
        w.writerows(table)

    cells = {(r["cell"], r["seed"]) for r in rows}
    print(f"Figure 1 — {len(cells)} cell-seeds, {len(rows)} rows\n")
    print("\n".join(lines))
    print()
    if variants:
        print(f"\nsEH AT EVERY SWEPT BAR (secondary readout, R={args.headline_budget})\n")
        print(f"  {'bar':>5}{'seeds':>7}{'comparable':>12}{'median':>9}{'range':>14}"
              f"   cells dropped")
        for g in sorted({v["gate"] for v in variants}):
            at_g = [v for v in variants if v["gate"] == g]
            comp = [v for v in at_g if v["comparable"] and v["ratio"] != ""]
            if not comp:
                continue
            vals = sorted(float(v["ratio"]) for v in comp)
            dropped = [v["generator"] for v in at_g if not v["comparable"]]
            n_seeds = len({v["seed"] for v in at_g})
            comp_s = f"{len(comp)}/{len(at_g)}"
            rng = f"{min(vals):.2f}-{max(vals):.2f}"
            print(f"  {g:>5.1f}{n_seeds:>7}{comp_s:>12}"
                  f"{statistics.median(vals):>8.2f}x{rng:>14}"
                  f"   {', '.join(dropped) if dropped else '-'}")
        print("\n  Both bars are reported rather than unified. A cell drops out where an arm\n"
              "  is pool-exhausted rather than budget-binding: it did not spend the budget,\n"
              "  so quoting it as modes-at-a-budget would imply it chose not to.")

    print(draw(rows, out / "fig1_reaction_budget", gates, args.headline_budget))
    print(f"tables: {out/'fig1_reaction_budget.csv'}, {out/'fig1_summary.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
