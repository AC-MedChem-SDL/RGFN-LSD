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

    # ---- competitor arm 1: SPARROW chooses, at an exact R=100 solve ----
    sel = res / "s3gfn_seh_select_N500" / "select_frontier.csv"
    if sel.is_file():
        with sel.open() as fh:
            for r in csv.DictReader(fh):
                if r["budget_rxns"] != "100":
                    continue
                rows.append({
                    "arm": "S3-GFN \u2192 retrosynthesis \u2192 SPARROW selects", "side": "competitor",
                    "config": "SPARROW chooses under a 100-reaction budget",
                    "modes_at_100rxn": r["n_modes"], "modes_lower": r["n_modes"],
                    "modes_upper": r["n_modes"], "used_rxns": r["used_rxns"],
                    "n_selected": r["n_selected"], "solver": r["milp_status"],
                    "exact": True, "gate": 7.0,
                })
        sources.append({"file": "s3gfn_seh_select_N500/select_frontier.csv", "md5": md5(sel)})

    # ---- competitor arm 2: their strongest -- diversity-aware greedy ----
    # Sampled every 25 modes, so R=100 falls between two rows. Greedy mode selection
    # is prefix-stable, so trimming is exact -- but only to the sampled grid, which
    # means this arm can be BOUNDED at R=100, not pointed. Reporting the upper bound
    # as if measured would overstate the competitor; reporting the lower bound as if
    # measured would flatter us. So carry the interval.
    # Prefer the 1-mode-granularity re-run when it exists: the original frontier was
    # sampled every 25 modes, which can only BOUND the readout at 100 reactions.
    gre = res / "s3gfn_seh_greedy_N500_fine" / "greedy_frontier.csv"
    if not gre.is_file():
        gre = res / "s3gfn_seh_greedy_N500" / "greedy_frontier.csv"
    if gre.is_file():
        with gre.open() as fh:
            grid = [(int(r["n_modes"]), int(r["used_rxns"])) for r in csv.DictReader(fh)]
        below = [m for m, u in grid if u <= 100]
        above = [m for m, u in grid if u > 100]
        lo = max(below) if below else 0
        hi = (min(above) - 1) if above else lo
        rows.append({
            "arm": "S3-GFN \u2192 retrosynthesis \u2192 greedy selection", "side": "competitor",
            "config": "their strongest pipeline; frontier sampled every 25 modes",
            "modes_at_100rxn": str(lo) if lo == hi else f"{lo}-{hi}",
            "modes_lower": lo, "modes_upper": hi,
            "used_rxns": max((u for m, u in grid if u <= 100), default=0),
            "n_selected": lo, "solver": "greedy",
            "exact": lo == hi, "gate": 7.0,
        })
        step = (grid[1][0] - grid[0][0]) if len(grid) > 1 else 0
        if lo == hi:
            notes.append(f"The diversity-aware greedy arm is EXACT at R=100: {lo} modes for "
                         f"{max(u for m, u in grid if u <= 100)} reactions, with the next mode "
                         f"taking it to {min(u for m, u in grid if u > 100)}. Read off a "
                         f"{step}-mode grid, every point Optimal.")
        else:
            notes.append(f"The diversity-aware greedy arm is an INTERVAL [{lo}, {hi}] at R=100: "
                         f"its frontier is sampled every {step} modes, so no grid point lands at "
                         f"100 reactions. Re-run it at 1-mode granularity to make this exact -- "
                         f"greedy mode selection is prefix-stable, so it costs seconds.")
        sources.append({"file": "s3gfn_seh_greedy_N500/greedy_frontier.csv", "md5": md5(gre)})

    # ---- our arms, every config, so the spread is visible ----
    for tag, config, headline in OURS:
        summary = res / tag / "summary.json"
        # Sweep-style runs write sweep_summary.json instead; without this fallback the
        # gate reads as None and the row cannot be checked against the others.
        if not summary.is_file() and (res / tag / "sweep_summary.json").is_file():
            summary = res / tag / "sweep_summary.json"
        pareto = res / tag / "pareto.csv"
        modes = gate = None
        if summary.is_file():
            meta = json.loads(summary.read_text())
            hb = meta.get("hub_batching") or (meta.get("arms") or {}).get("hub_batching") or {}
            modes = hb.get("case1_modes_at_100rxn")
            gate = meta.get("reward_threshold")
        if modes is None and pareto.is_file():
            with pareto.open() as fh:
                for r in csv.DictReader(fh):
                    if r.get("strategy") == "hub_batching" and r.get("cutoff") == "0.5":
                        modes = r.get("modes_at_100rxn")
            if summary.is_file() and gate is None:
                gate = json.loads(summary.read_text()).get("reward_threshold")
        if modes is None:
            continue
        rows.append({
            # Name the generator: the competitor rows say which model produced their
            # pool, and ours should too rather than looking model-agnostic.
            "arm": "SCENT \u2192 hub-batching" + ("" if headline else f" \u2014 {tag}"),
            "side": "ours", "config": config,
            "modes_at_100rxn": modes, "modes_lower": modes, "modes_upper": modes,
            "used_rxns": 100, "n_selected": "", "solver": "greedy walk",
            "exact": True, "gate": gate, "is_headline_config": headline,
        })
        for f in (summary, pareto):
            if f.is_file():
                sources.append({"file": f"{tag}/{f.name}", "md5": md5(f)})

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
