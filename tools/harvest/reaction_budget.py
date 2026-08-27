#!/usr/bin/env python3
"""Harvest Fig 1's inputs (the reaction-axis curves) out of the research tree.

Fig 1 reads modes-delivered-at-a-fixed-reaction-budget off per-cell curves. Those
curves live in the research repo and are almost entirely UNCOMMITTED there, because
its .gitignore blanket-ignores ``*.csv`` -- 102 curve files on disk, 2 tracked. This
script copies them here, where they are committed, so ``reproduce/fig1_*`` needs
nothing but this repository.

Also emits ``gates.csv``: the per-target reward gate, its direction, and whether it
is calibrated. Fig 1's headline is computed over calibration-passing targets only, so
that flag is part of the figure's definition and belongs beside the data rather than
inside the plotting code.

Usage:
    python3 tools/harvest/reaction_budget.py --matrix-root <research>/experiments/lsd_hubs/matrix16
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import md5, redact_paths  # noqa: E402

SEED_DIRS = {"results": 42, "results_seed43": 43, "results_seed44": 44}
ARMS = ("hub_batching", "best_candidate")
# Cell tags carrying these markers are sensitivity-sweep variants, not cells of the
# matrix proper. This list must match the research tree's readout EXACTLY -- a longer
# list here would silently drop cells and move the published median.
VARIANT_MARKERS = ("thr", "cap9", "naive")

# Per-target gate, direction, and calibration status. `calibrated` is what Fig 1's
# headline filters on, and each value is a claim with evidence behind it:
#   seh   5.0  Logs/034 (weak enrichment above ~6) + Logs/051 (diversity collapse past ~7)
#   drd2  0.5  Logs/028 gate fix; Logs/066 validated on held-out actives (AUROC 0.949)
#   clpp -8.0  Logs/045 Youden-optimal vs property-matched decoys (AUROC 0.895)
#   6td3 -2.0  PROVISIONAL, never AUROC-calibrated -- and Logs/072 then measured the
#              generator exploiting it (78% clear the trained gate, 0% of 400 clear the
#              untrained one), so the differential is gameable rather than merely noisy.
GATES = [
    {"target": "seh",  "gate": 5.0,  "higher_is_better": True,  "calibrated": True,
     "basis": "Logs/034, Logs/051; 7.0 kept as the paper-comparable variant"},
    {"target": "drd2", "gate": 0.5,  "higher_is_better": True,  "calibrated": True,
     "basis": "Logs/028 gate fix; Logs/066 held-out AUROC 0.949"},
    {"target": "clpp", "gate": -8.0, "higher_is_better": False, "calibrated": True,
     "basis": "Logs/045 Youden-optimal, AUROC 0.895 vs matched decoys"},
    {"target": "6td3", "gate": -2.0, "higher_is_better": False, "calibrated": False,
     "basis": "PROVISIONAL, no AUROC calibration; Logs/072 measured reward exploitation"},
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--matrix-root", type=Path, default=None,
                    help="the research tree's matrix16 dir "
                         "(default: $HUBBATCH_MATRIX_ROOT)")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    root = args.matrix_root
    if root is None:
        env = os.environ.get("HUBBATCH_MATRIX_ROOT")
        if not env:
            sys.exit("pass --matrix-root or set $HUBBATCH_MATRIX_ROOT")
        root = Path(env)
    root = root.resolve()
    if not root.is_dir():
        sys.exit(f"not a directory: {root}")

    out = args.out or (Path(__file__).resolve().parents[2] / "artifacts" / "reaction_budget")
    out.mkdir(parents=True, exist_ok=True)

    sources, cells, skipped = [], 0, []
    for sd, seed in SEED_DIRS.items():
        sdir = root / sd
        if not sdir.is_dir():
            continue
        for summary in sorted(sdir.glob("*/summary.json")):
            cdir = summary.parent
            tag = json.loads(summary.read_text()).get("tag", cdir.name)
            if any(m in tag for m in VARIANT_MARKERS):
                skipped.append(f"{sd}/{tag} (variant)")
                continue
            present = [a for a in ARMS if (cdir / f"curve_{a}.csv").is_file()]
            if not present:
                skipped.append(f"{sd}/{tag} (no curves)")
                continue
            dest = out / f"seed{seed}" / tag
            dest.mkdir(parents=True, exist_ok=True)
            for name in [f"curve_{a}.csv" for a in present] + ["summary.json"]:
                src = cdir / name
                if name == "summary.json":
                    payload = redact_paths(json.loads(src.read_text()))
                    (dest / name).write_text(json.dumps(payload, indent=2) + "\n")
                else:
                    shutil.copy2(src, dest / name)
                sources.append({
                    "seed": seed, "cell": tag, "file": name,
                    "src": f"{sd}/{cdir.name}/{name}", "md5": md5(src),
                    "redacted": name == "summary.json",
                })
            cells += 1

    if not cells:
        sys.exit(f"no matrix cells found under {root}")

    # ---- sEH threshold variants, for the "report both bars" secondary readout ----
    # These cells are excluded from the matrix proper (VARIANT_MARKERS) because they are
    # sensitivity sweeps, not matrix cells. They are harvested separately so the paper can
    # show the advantage at BOTH the calibrated bar (5.0) and the paper-comparable one (7.0)
    # without either standing in for the other.
    variants = 0
    for sd, seed in SEED_DIRS.items():
        sdir = root / sd
        if not sdir.is_dir():
            continue
        for summary in sorted(sdir.glob("*_seh_thr*/summary.json")):
            tag = json.loads(summary.read_text()).get("tag", summary.parent.name)
            if "cap9" in tag:          # the mis-set FragGFN cap, superseded (Logs/046)
                continue
            cdir = summary.parent
            present = [a for a in ARMS if (cdir / f"curve_{a}.csv").is_file()]
            if not present:
                continue
            dest = out / "gate_variants" / f"seed{seed}" / tag
            dest.mkdir(parents=True, exist_ok=True)
            for name in [f"curve_{a}.csv" for a in present] + ["summary.json"]:
                src = cdir / name
                if name == "summary.json":
                    (dest / name).write_text(
                        json.dumps(redact_paths(json.loads(src.read_text())), indent=2) + "\n")
                else:
                    shutil.copy2(src, dest / name)
                sources.append({"seed": seed, "cell": tag, "file": name,
                                "src": f"{sd}/{cdir.name}/{name}", "md5": md5(src),
                                "redacted": name == "summary.json", "variant": True})
            variants += 1

    with (out / "gates.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(GATES[0]))
        w.writeheader()
        w.writerows(GATES)

    (out / "provenance.json").write_text(json.dumps({
        "harvested_from_subdir": "experiments/lsd_hubs/matrix16",
        "n_cells": cells,
        "n_files": len(sources),
        "skipped": skipped,
        "sources": sources,
    }, indent=2) + "\n")

    print(f"harvested {cells} cells / {len(sources)} files")
    if variants:
        print(f"  + {variants} sEH threshold-variant cell(s) under gate_variants/")
    for seed in SEED_DIRS.values():
        n = len(list((out / f"seed{seed}").glob("*"))) if (out / f"seed{seed}").is_dir() else 0
        print(f"  seed{seed}: {n} cells")
    print(f"  skipped {len(skipped)} (variants / no curves)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
