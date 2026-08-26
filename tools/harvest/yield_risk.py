#!/usr/bin/env python3
"""Harvest the yield / risk-concentration result (appendix figure).

The cost metric counts reactions *attempted*, not reactions that worked. These files
are what happens when yield is put back in, and the finding is not the expected value
-- that barely moves -- it is the variance. Hub-batching's savings come from many
molecules descending from one shared intermediate, so when that intermediate fails the
whole batch below it fails together.

Usage:
    python3 tools/harvest/yield_risk.py --campaign-root <research>/experiments/lsd_hubs/campaign
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import md5  # noqa: E402

KEEP = ["tag", "target", "arm", "child_policy", "modes", "used_rxns", "stop_reason",
        "mean_route_yield", "median_route_yield", "mean_step_yield", "mean_route_len",
        "expected_molecules", "sd_if_independent", "sd_with_shared_prefixes",
        "n_shared_batches", "pct_in_multi_batches", "largest_batch",
        "expected_lost_to_shared_prefix", "worst_batch_loss_prob"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--campaign-root", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    root = args.campaign_root
    if root is None:
        env = os.environ.get("LSDFLOW_CAMPAIGN_ROOT")
        if not env:
            sys.exit("pass --campaign-root or set $LSDFLOW_CAMPAIGN_ROOT")
        root = Path(env)
    src = (root / "results" / "yield_preference").resolve()
    if not src.is_dir():
        sys.exit(f"not found: {src}")
    out = args.out or (Path(__file__).resolve().parents[2] / "artifacts" / "yield_risk")
    out.mkdir(parents=True, exist_ok=True)

    rows, sources = [], []
    for f in sorted(src.glob("strategy_yield_*.csv")):
        if "detail" in f.name:
            continue          # per-molecule routes; the summary carries the readout
        with f.open() as fh:
            for r in csv.DictReader(fh):
                rows.append({k: r.get(k, "") for k in KEEP})
        sources.append({"file": f.name, "md5": md5(f)})
    if not rows:
        sys.exit(f"no strategy_yield_*.csv under {src}")

    # Normalise the cell label: one file writes its target twice into the tag.
    for r in rows:
        tag = r["tag"]
        tgt = r["target"]
        r["cell"] = tag.replace(f"{tgt}_{tgt}_", f"{tgt}_")

    with (out / "strategy_yield.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["cell"] + KEEP)
        w.writeheader()
        w.writerows(rows)
    (out / "provenance.json").write_text(json.dumps({
        "harvested_from_subdir": "experiments/lsd_hubs/campaign/results/yield_preference",
        "n_rows": len(rows), "sources": sources,
        "note": "Per-molecule route detail (strategy_yield_detail_*.csv) intentionally not "
                "harvested: the summary carries every quantity the figure reads.",
    }, indent=2) + "\n")
    print(f"harvested {len(rows)} arm-rows from {len(sources)} cells -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
