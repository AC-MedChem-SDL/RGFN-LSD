#!/usr/bin/env python3
"""Harvest the external head-to-head: hub-batching vs S3-GFN + MultiAiZ + SPARROW.

Table 1's job is to show this is not an internal-comparison paper. Three rows do
that, but only if each row names the configuration it was measured at -- because our
own modes-at-100-reactions on sEH ranges from 27 to 82 depending on the child policy
and the prebuild-K, and one of the committed run directories is *named*
``sparrow_headline`` while not being the headline configuration.

Usage:
    python3 tools/harvest/external.py --campaign-root <research>/experiments/lsd_hubs/campaign
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import md5, redact_paths  # noqa: E402

# Our own arms, with the configuration that distinguishes them. `is_headline` marks
# the one the paper's external comparison is written against (free-frag child policy,
# no pre-selected fragments); the others are kept so the spread is visible rather
# than hidden behind a single quoted number.
# Only the headline configuration is a table row. The other runs that exist for this
# cell are not competitors and were misleading as rows:
#   scent_seh_1kx200_freefrag  - a hub-pool construction variant of the same method
#   scent_seh                  - the naive child policy, superseded
#   scent_seh_sparrow_headline - NOT a competitor at all. That run does our own
#       selection and uses SPARROW only to PRICE it; SPARROW never chooses anything.
#       It is verification, and it belongs in a sentence (see VERIFICATION below),
#       not in a row where a reader would read it as a rival pipeline.
# Lines that belong UNDER the table, not in it.
FOOTNOTES = [
    "We are also exploring giving the retrosynthesis pipeline a diversity-enforced "
    "candidate pool rather than the highest-scoring one; those results are not yet "
    "included.",
    "A selection-only control on DRD2 isolates the chooser from the candidates: handing "
    "SPARROW our own enumerated children -- a byte-identical pool, verified by digest -- "
    "it recovers 28 and 15 distinct molecules across two seeds against our 78, both "
    "solves optimal. Our arm sees only already-stocked fragments while SPARROW sees the "
    "whole enumeration, so that margin is a lower bound.",
]

OURS = [
    ("scent_seh_freefrag", "free-frag child policy, no pre-selected fragments", True),
]

# Independent pricing of our own selection, from the reconciliation audit. Logs/049
# reported 3.12%, but that was measured on the NAIVE child policy; the re-audit against
# the headline configuration is the number that belongs beside a headline row.
VERIFICATION = {
    "headline_gap_pct": 0.75,
    "headline_config": "sEH, free-frag, K=20",
    "direction": "count-once charges what we actually spent; SPARROW charges only what "
                 "hindsight needed, so our published cost is conservative",
    "source": "Logs/049 + its re-audit recorded in RESEARCH_CONTEXT",
    "caveat": "DRD2 at K=20 reads 12.69%, traced entirely to pre-select-K's 26 up-front "
              "reactions (~17 unused by a 100-mode selection); at K=0 it is exactly "
              "0.00% (110/110)",
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--campaign-root", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    root = args.campaign_root
    if root is None:
        env = os.environ.get("HUBBATCH_CAMPAIGN_ROOT")
        if not env:
            sys.exit("pass --campaign-root or set $HUBBATCH_CAMPAIGN_ROOT")
        root = Path(env)
    res = (root / "results").resolve()
    out = args.out or (Path(__file__).resolve().parents[2] / "artifacts" / "external")
    out.mkdir(parents=True, exist_ok=True)

    rows, sources, notes = [], [], []

    # ---- the competitor, on the budget-matched pool ----
    # PAIRED ON SEED 43, because that is the seed whose budget-matched pool has both
    # solves. The earlier seed-42 numbers (24 and 38) came from the OLDBUDGET pool --
    # an S3-GFN trained far longer than the generators it is compared against, and
    # sampled too thinly to route 500 molecules -- and are superseded, not merely older.
    #
    # NAIVE POOL ONLY. A diversity-enforced ("pruned") variant exists and produces a
    # different picture; it is being checked before it is quoted, and the table says so
    # rather than silently reporting whichever is kinder.
    # All three seeds, not one. This was never a cost limit -- the expensive stage
    # (MultiAiZ retrosynthesis, ~2.25 h/seed) is done for all three enlarged pools and
    # so are both selection arms. The table read n=1 because this script discovered
    # cells from a hard-coded seed.
    SEEDS = (42, 43, 44)
    for SEED in SEEDS:
     sel = res / f"s3gfn_seh_seed{SEED}_big_select_N500" / "select_frontier.csv"
     if sel.is_file():
         with sel.open() as fh:
             for r in csv.DictReader(fh):
                 if str(r.get("budget_rxns")) != "100":
                     continue
                 n = r.get("n_modes") or r.get("n_modes_kept")
                 rows.append({
                     "arm": "S3-GFN \u2192 retrosynthesis \u2192 SPARROW selects",
                     "side": "competitor", "seed": SEED,
                     "config": "SPARROW chooses under a 100-reaction budget; no diversity term",
                     "modes_at_100rxn": n, "modes_lower": n, "modes_upper": n,
                     "used_rxns": r.get("used_rxns"), "n_selected": r.get("n_selected"),
                     "solver": r.get("milp_status"), "exact": True, "gate": 7.0,
                 })
         sources.append({"file": sel.parent.name + "/select_frontier.csv", "md5": md5(sel)})

     # Prefer the 1-mode re-price when present: the 5-mode grid could only bound R=100.
     gre = res / f"s3gfn_seh_seed{SEED}_big_greedy_FINE" / "greedy_frontier.csv"
     if not gre.is_file():
         gre = res / f"s3gfn_seh_seed{SEED}_big_greedy_N500" / "greedy_frontier.csv"
     if gre.is_file():
         with gre.open() as fh:
             grid = [(int(r["n_modes"]), int(r["used_rxns"]), r.get("milp_status"))
                     for r in csv.DictReader(fh)]
         step = (grid[1][0] - grid[0][0]) if len(grid) > 1 else 0
         below = [(m, u) for m, u, _ in grid if u <= 100]
         above = [(m, u) for m, u, _ in grid if u > 100]
         lo = max(m for m, _ in below) if below else 0
         hi = (min(m for m, _ in above) - 1) if above else lo
         rows.append({
             "arm": "S3-GFN \u2192 retrosynthesis \u2192 greedy selection",
             "side": "competitor", "seed": SEED,
             "config": f"their strongest pipeline; frontier priced every {step} modes",
             "modes_at_100rxn": str(lo), "modes_lower": lo, "modes_upper": hi,
             "used_rxns": max((u for _, u in below), default=0),
             "n_selected": lo, "solver": "greedy", "exact": lo == hi, "gate": 7.0,
         })
         if lo != hi:
             notes.append(
                 f"The greedy-selection arm is priced every {step} modes, so R=100 falls "
                 f"between grid points: {lo} modes fit in "
                 f"{max(u for _, u in below)} reactions and the next point needs "
                 f"{min(u for _, u in above)}. The readout is therefore [{lo}, {hi}] and "
                 f"{lo} is quoted, which UNDERSTATES the competitor and therefore "
                 f"OVERSTATES our ratio; the conservative end for us is {hi}. A 1-mode "
                 f"re-price makes it exact and costs seconds, since greedy mode selection "
                 f"is prefix-stable.")
         sources.append({"file": gre.parent.name + "/greedy_frontier.csv", "md5": md5(gre)})

    # ---- our arm, on the SAME seed, from the harvested per-seed values ----
    ours_csv = (Path(__file__).resolve().parents[2] / "artifacts" / "sparrow_diversity"
                / "ours_r100.csv")
    if ours_csv.is_file():
        ours_rows = [r for r in csv.DictReader(ours_csv.open())
                     if int(r["seed"]) in SEEDS]
        # Seed 42's prebuild_k was never recorded (its source run is the scent_seh_freefrag
        # tree). All three rows are the same configuration, so take the value from the
        # seeds that do record it rather than emitting a provenance string ending "K=".
        ks = {r.get("prebuild_k", "").strip() for r in ours_rows}
        ks.discard("")
        k_common = ks.pop() if len(ks) == 1 else None
        for r in ours_rows:
                n = int(r["n_modes_kept"])
                rows.append({
                    "arm": "SCENT \u2192 hub-batching", "side": "ours",
                    "seed": int(r["seed"]),
                    "config": (f"{r.get('child_policy')} child policy, "
                               f"K={r.get('prebuild_k', '').strip() or k_common}"
                               if (r.get('prebuild_k', '').strip() or k_common)
                               else f"{r.get('child_policy')} child policy"),
                    "prebuild_k": r.get("prebuild_k", "").strip() or (k_common or ""),
                    "modes_at_100rxn": n, "modes_lower": n, "modes_upper": n,
                    "used_rxns": r.get("used_rxns"), "n_selected": n,
                    "solver": "greedy walk", "exact": True, "gate": r.get("gate"),
                    "is_headline_config": True,
                })
        sources.append({"file": "artifacts/sparrow_diversity/ours_r100.csv",
                        "md5": md5(ours_csv)})

    if not rows:
        sys.exit(f"nothing harvested from {res}")

    keys = sorted({k for r in rows for k in r},
                  key=lambda k: (k not in ("arm", "side", "config", "modes_at_100rxn"), k))
    with (out / "head_to_head_r100.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    (out / "provenance.json").write_text(json.dumps({
        "harvested_from_subdir": "experiments/lsd_hubs/campaign/results",
        "n_rows": len(rows), "notes": notes, "sources": sources,
        "verification": VERIFICATION,
        "footnotes": FOOTNOTES,
    }, indent=2) + "\n")

    print(f"harvested {len(rows)} arms")
    for r in rows:
        print(f"  [{r['side']:<10}] {r['arm']:<52} {str(r['modes_at_100rxn']):>7} modes"
              f"  gate={r['gate']}")
    for n in notes:
        print(f"\nNOTE: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
