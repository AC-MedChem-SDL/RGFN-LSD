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


def draw(rows, out_path: Path, gates, budget: int) -> str:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return "matplotlib not installed - CSV written, figure skipped"

    cal = {t for t, g in gates.items() if g["calibrated"].lower() == "true"}
    at_R = [r for r in rows if r["budget_rxns"] == budget and r["comparable"]]
    cells = sorted({r["cell"] for r in at_R},
                   key=lambda c: (target_of(c) not in cal, target_of(c) or "", c))
    if not cells:
        return "no comparable cells to draw"

    fig, ax = plt.subplots(figsize=(9, 4.2))
    for i, cell in enumerate(cells):
        pts = [r for r in at_R if r["cell"] == cell]
        uncal = target_of(cell) not in cal
        for r in pts:  # seed scatter, jittered so overlapping seeds stay visible
            off = (r["seed"] - 43) * 0.13
            ax.scatter(i + off - 0.16, r["bc_modes"], s=26, marker="s",
                       color="#b0b0b0" if not uncal else "#dcdcdc",
                       edgecolor="none", zorder=3)
            ax.scatter(i + off + 0.16, r["hub_modes"], s=30, marker="o",
                       color="#1f6f8b" if not uncal else "#a8c6d2",
                       edgecolor="none", zorder=3)
        ax.axvline(i + 0.5, color="#eeeeee", lw=0.8, zorder=1)
    n_cal = sum(1 for c in cells if target_of(c) in cal)
    if 0 < n_cal < len(cells):
        ax.axvline(n_cal - 0.5, color="#cc6666", lw=1.2, ls="--", zorder=2)
        ax.text(n_cal - 0.4, ax.get_ylim()[1], " un-calibrated gate ",
                color="#cc6666", fontsize=7, va="top")
    ax.set_xticks(range(len(cells)))
    ax.set_xticklabels(cells, rotation=45, ha="right", fontsize=7)
    ax.set_ylabel(f"distinct high-reward molecules\nat {budget} reactions")
    ax.set_title(f"Modes delivered at a fixed {budget}-reaction budget "
                 f"(~one plate), per cell, all seeds", fontsize=10)
    ax.scatter([], [], s=30, marker="o", color="#1f6f8b", label="hub-batching")
    ax.scatter([], [], s=26, marker="s", color="#b0b0b0", label="best-candidate")
    ax.legend(frameon=False, fontsize=8, loc="upper right")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    for ext in ("png", "pdf"):
        # Strip figure metadata: matplotlib stamps a creator and a timestamp, which
        # is both a weak fingerprint and the reason figures are not byte-reproducible.
        fig.savefig(out_path.parent / f"{out_path.stem}.{ext}", dpi=200,
                    metadata={"Creator": None, "Producer": None, "CreationDate": None})
    plt.close(fig)
    return f"wrote {out_path.stem}.png and .pdf"


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

    table, lines = summarise(rows, budgets, gates, args.include_uncalibrated)
    with (out / "fig1_summary.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(table[0]))
        w.writeheader()
        w.writerows(table)

    cells = {(r["cell"], r["seed"]) for r in rows}
    print(f"Figure 1 — {len(cells)} cell-seeds, {len(rows)} rows\n")
    print("\n".join(lines))
    print()
    print(draw(rows, out / "fig1_reaction_budget", gates, args.headline_budget))
    print(f"tables: {out/'fig1_reaction_budget.csv'}, {out/'fig1_summary.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
