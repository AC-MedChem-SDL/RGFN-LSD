#!/usr/bin/env python3
"""Harvest the SPARROW diversity-sweep results out of a run tree into artifacts/.

Why this exists as a separate step. The runs behind Table 2 produced ~570 MB of
MILP solutions on a cluster scratch filesystem, which is periodically purged and
which no reader will ever have. The numbers the table actually needs are a few
dozen rows. This script is the bridge: it runs where the scratch tree lives, emits
small tidy CSVs plus a provenance record, and after that nothing downstream needs
the cluster again.

It is release tooling, not part of the artifact -- a reviewer cannot run it and does
not need to, because its *output* is committed.

Usage:
    python3 tools/harvest/sparrow_diversity.py                 # $LSDFLOW_SCRATCH or $SCRATCH
    python3 tools/harvest/sparrow_diversity.py --scratch-root /path/to/runs
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Run-tag grammar. The tags encode arm, seed, lambda and pool size positionally;
# parsing them here keeps that knowledge in one place instead of in the figure code.
ARMS = {
    "bcsbR100": ("BC-SB", "R100 sweep"),
    "bcsb_div": ("BC-SB", "lambda sweep"),
    "bcsb_div2": ("BC-SB", "lambda sweep (2h re-solve)"),
    "bcsb_hi2": ("BC-SB", "high-lambda re-solve"),
    "bc_sb_seh": ("BC-SB", "pool-size sweep"),
    "enumR100": ("BC-Enum-SB", "R100 sweep"),
    "enumdiv": ("BC-Enum-SB", "lambda sweep"),
    "enumdiv2": ("BC-Enum-SB", "lambda sweep (2h re-solve)"),
    "bc_enum_sb_seh42": ("BC-Enum-SB", "pool-size sweep"),
}
SKIP = ("smoke", "_dbg", "metrics_smoke", "lam_dbg")


def parse_tag(tag: str) -> dict | None:
    if any(s in tag for s in SKIP):
        return None
    pool = None
    body = tag
    if "_N" in tag:
        body, _, pool_s = tag.rpartition("_N")
        pool = int(pool_s) if pool_s.isdigit() else None
    arm = subset = None
    for prefix, (a, s) in sorted(ARMS.items(), key=lambda kv: -len(kv[0])):
        if body == prefix or body.startswith(prefix + "_"):
            arm, subset = a, s
            break
    if arm is None:
        return None
    seed = None
    for part in body.split("_"):
        if part.startswith("seed") and part[4:].isdigit():
            seed = int(part[4:])
        elif part.startswith("seh") and part[3:].isdigit():
            seed = int(part[3:])
    # Tags with no seed marker are the original seed-42 runs; the later replicates
    # are the ones that got an explicit suffix. Confirmed against Logs/062 Result 12,
    # where the unsuffixed BC-Enum-SB row is the seed-42 TimeLimit row (24 distinct).
    seed_inferred = seed is None
    if seed_inferred:
        seed = 42
    return {"run_tag": tag, "arm": arm, "subset": subset, "seed": seed,
            "seed_inferred": seed_inferred, "pool_n": pool}


def md5(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.md5()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scratch-root", type=Path, default=None,
                    help="run tree root (default: $LSDFLOW_SCRATCH, else $SCRATCH)")
    ap.add_argument("--subdir", default="rgfn_runs/lsdflow_sparrow/bc_sb",
                    help="path to the bc_sb run tree under the root")
    ap.add_argument("--out", type=Path, default=None,
                    help="output dir (default: <repo>/artifacts/sparrow_diversity)")
    args = ap.parse_args()

    root = args.scratch_root
    if root is None:
        env = os.environ.get("LSDFLOW_SCRATCH") or os.environ.get("SCRATCH")
        if not env:
            sys.exit("no --scratch-root and neither $LSDFLOW_SCRATCH nor $SCRATCH is set")
        root = Path(env)
    base = (root / args.subdir).resolve()
    if not base.is_dir():
        sys.exit(f"run tree not found: {base}")

    out = args.out or (Path(__file__).resolve().parents[2] / "artifacts" / "sparrow_diversity")
    out.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    sources: list[dict] = []
    skipped: list[str] = []
    for run in sorted(p for p in base.iterdir() if p.is_dir()):
        meta = parse_tag(run.name)
        if meta is None:
            skipped.append(run.name)
            continue
        csv_path = run / "select_frontier.csv"
        if not csv_path.is_file():
            skipped.append(run.name + " (no select_frontier.csv)")
            continue
        with csv_path.open() as fh:
            for rec in csv.DictReader(fh):
                rows.append({**meta, **rec})
        stat = csv_path.stat()
        sources.append({
            "run_tag": run.name,
            "file": str(csv_path.relative_to(base)),
            "md5": md5(csv_path),
            "mtime_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            "bytes": stat.st_size,
        })

    if not rows:
        sys.exit(f"no frontier rows found under {base}")

    # Column order: identity first, then the readout, then solver provenance.
    # The schema is NOT uniform across runs -- the earliest ones predate the
    # --lambda-div flag and have no such column -- so take the union, and let the
    # writer emit empty cells rather than dropping a run for having fewer fields.
    lead = ["arm", "subset", "seed", "seed_inferred", "pool_n", "run_tag",
            "lambda_div", "budget_rxns", "used_rxns", "n_selected", "n_modes_kept",
            "cost_kept_rxns", "rxn_per_mode_kept", "clusters_touched",
            "mean_pairwise_sim", "mean_pairwise_sim_kept",
            "milp_status", "time_capped", "solve_s"]
    seen_cols: list[str] = []
    for r in rows:
        for k in r:
            if k not in lead and k not in seen_cols:
                seen_cols.append(k)
    cols = lead + seen_cols

    missing_lambda = sorted({r["run_tag"] for r in rows if "lambda_div" not in r})
    if missing_lambda:
        print(f"note: {len(missing_lambda)} run(s) predate --lambda-div "
              f"(diversity-blind): {', '.join(missing_lambda[:4])}"
              + (" ..." if len(missing_lambda) > 4 else ""))

    full = out / "frontier_all.csv"
    with full.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    r100 = [r for r in rows if str(r.get("budget_rxns")) == "100"]
    p100 = out / "r100.csv"
    with p100.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(r100, key=lambda r: (r["arm"], r.get("seed") or 0,
                                                float(r.get("lambda_div") or 0))))

    prov = {
        # Record the tree-relative subdir, never the absolute root: the root is
        # site-specific and would carry a username into a committed artifact. The
        # per-file md5s are what actually identify the inputs.
        "harvested_from_subdir": args.subdir,
        "n_runs": len(sources),
        "n_rows": len(rows),
        "n_rows_r100": len(r100),
        "skipped": skipped,
        "sources": sources,
        "note": "Provenance for Table 2. See artifacts/sparrow_diversity/PROVENANCE.md "
                "for which numbers in Logs/062 stand and which are withdrawn.",
    }
    (out / "provenance.json").write_text(json.dumps(prov, indent=2) + "\n")

    print(f"harvested {len(rows)} rows from {len(sources)} runs")
    print(f"  {full.name}: all budgets")
    print(f"  {p100.name}: {len(r100)} rows at R=100")
    print(f"  provenance.json: md5 + mtime per source file")
    if skipped:
        print(f"  skipped {len(skipped)} dir(s): {', '.join(skipped[:6])}"
              + (" ..." if len(skipped) > 6 else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
