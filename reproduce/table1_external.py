#!/usr/bin/env python3
"""Table 1 — the external head-to-head at the primary readout.

Its job is narrow: show that the comparison is against an independent pipeline, not
an internal ablation. S3-GFN generates, MultiAiZ plans routes over its own catalogue,
and SPARROW -- someone else's optimizer -- chooses what to make. Three rows do that.

Two honesty constraints are wired in rather than left to the caption.

**Our own number depends on configuration, so every row names one.** Modes at 100
reactions on sEH ranges 27-82 across our arms; the child policy is the difference.
One committed directory is *named* ``sparrow_headline`` and is NOT the headline
configuration (it pre-selects 100 fragments, which costs modes at a small budget).
Quoting from the directory name rather than the config is a live trap.

**The competitor's stronger arm can only be bounded.** Its frontier is sampled every
25 modes, and no sample lands at 100 reactions. Greedy mode selection is prefix-
stable so trimming is exact -- but only to the grid. Reporting the interval's upper
end as measured would overstate them; the lower end would flatter us.

    python3 reproduce/table1_external.py
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--per-seed", action="store_true",
                    help="one row per seed instead of the collapsed mean+range")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    src = Path(__file__).resolve().parents[1] / "artifacts" / "external" / "head_to_head_r100.csv"
    if not src.is_file():
        sys.exit(f"missing artifact: {src}")
    rows = list(csv.DictReader(src.open()))
    out = args.out or (Path(__file__).resolve().parents[1] / "build" / "figures")
    out.mkdir(parents=True, exist_ok=True)

    headline = next((r for r in rows
                     if r.get("is_headline_config") == "True"), None)
    if headline is None:
        sys.exit("no row marked as the headline config")
    # Our value PER SEED. Every ratio below is within-seed: pairing our seed 42 against
    # their seed 44 compares two different draws and measures nothing. With a single
    # seed this reduces to the previous behaviour exactly.
    OURS = {r["seed"]: int(r["modes_lower"]) for r in rows if r["side"] == "ours"}
    ours = int(headline["modes_lower"])

    def ours_for(r):
        return OURS.get(r.get("seed"), ours)

    seeds = {r.get("seed") for r in rows if r.get("seed")}
    seed_s = f"seed {seeds.pop()}" if len(seeds) == 1 else f"seeds {sorted(seeds)}"
    print(f"Table 1 — modes delivered at 100 reactions "
          f"(sEH, gate {headline['gate']}, {seed_s})\n")
    # The glyph lives in a variable, not inside the f-string expression: Python 3.11
    # rejects a backslash escape there (PEP 701 only relaxed it in 3.12), and this
    # project supports 3.10+.
    head = "modes @ 100 rxn (\u2191)"
    # Collapsed by default: nine rows is a seed ledger, and the paper wants a comparison.
    # --per-seed keeps the expanded view for the appendix and for checking.
    if not args.per_seed:
        print(f"| {'pipeline':<44} | {head:>19} | {'vs ours':>18} |")
        print(f"|{'-'*46}|{'-'*21}|{'-'*20}|")
        table = []
        by_arm = {}
        for r in rows:
            by_arm.setdefault((r["side"], r["arm"]), []).append(r)
        for (side, arm), rs in sorted(by_arm.items(), key=lambda kv: kv[0][0] != "competitor"):
            counts = [int(r["modes_lower"]) for r in rs]
            mean_n = sum(counts) / len(counts)
            cells = f"{mean_n:.1f}  ({min(counts)}\u2013{max(counts)})"
            if side == "ours":
                ratio = "\u2014"
            else:
                # Mean of the WITHIN-SEED ratios, never the ratio of the means. Averaging
                # counts first pairs our seed 42 with their seed 44 by the back door; here
                # it happens to move 1.408 -> 1.400, but the two are different quantities
                # and only one of them is a measurement.
                w = [ours_for(r) / int(r["modes_lower"]) for r in rs if int(r["modes_lower"])]
                ratio = f"{sum(w)/len(w):.2f}x  ({min(w):.2f}\u2013{max(w):.2f})"
            print(f"| {arm[:44]:<44} | {cells:>19} | {ratio:>18} |")
            table.append({"arm": arm, "side": side, "n_seeds": len(counts),
                          "config": rs[0].get("config", ""),
                          "modes_at_100rxn": cells, "modes_mean": round(mean_n, 2),
                          "modes_min": min(counts), "modes_max": max(counts),
                          "modes_lower": min(counts),
                          "is_headline_config": rs[0].get("is_headline_config", ""),
                          "ratio_vs_headline": ratio})
        print(f"\n  n={len(counts)} seeds per row. Parenthesised values are the observed "
              f"RANGE across seeds, not a confidence interval.")
        print(f"  Ratios are computed within seed and then averaged.")
    else:
        print(f"| {'pipeline':<50} | {head:>19} | {'vs ours':>10} |")
        print(f"|{'-'*52}|{'-'*21}|{'-'*12}|")
        table = []
        for r in sorted(rows, key=lambda q: (q["side"] != "competitor", q["arm"], q.get("seed", ""))):
            lo, hi = int(r["modes_lower"]), int(r["modes_upper"])
            ours = ours_for(r)
            if r["side"] == "ours":
                ratio = "—"
            elif lo == hi:
                ratio = f"{ours/lo:.2f}x" if lo else "—"
            else:
                # Interval in the denominator inverts: the competitor's UPPER bound gives
                # our LOWER ratio, which is the conservative end and the one to lead with.
                ratio = f"{ours/hi:.2f}-{ours/lo:.2f}x"
            star = " *" if r is headline else ""
            print(f"| {r['arm'][:44]:<44} s{str(r.get('seed','')):<3} | "
                  f"{str(r['modes_at_100rxn']):>19} | {ratio:>10} |{star}")
            table.append({**r, "ours_same_seed": ours, "ratio_vs_headline": ratio})
    cfg = headline["config"]
    if cfg.rstrip().endswith("K="):
        # Seed 42's row has no prebuild_k recorded, so the headline printed "K=" with
        # nothing after it. A provenance string that trails off is worse than a short one:
        # borrow the value from a row of the same config that does record it, else drop
        # the clause rather than imply a blank.
        known = {r.get("prebuild_k") for r in rows
                 if r["side"] == "ours" and str(r.get("prebuild_k", "")).strip()}
        cfg = cfg + (known.pop() if len(known) == 1 else "?") if len(known) == 1 \
            else cfg[:cfg.rindex(",")]
    print(f"\n  * the headline configuration ({cfg})")

    print()
    per_arm = {}
    for r in rows:
        if r["side"] == "competitor":
            per_arm.setdefault(r["arm"], []).append(r)
    worst_arm = None
    for arm, rs in per_arm.items():
        rs = [r for r in rs if int(r["modes_lower"])]
        if not rs:
            continue
        vals = [ours_for(r) / int(r["modes_lower"]) for r in rs]
        mean = sum(vals) / len(vals)
        detail = "  ".join(f"s{r.get('seed')} {ours_for(r)}/{r['modes_lower']}={v:.2f}x"
                           for r, v in zip(rs, vals))
        print(f"  vs {arm}:")
        print(f"      n={len(vals)}  mean {mean:.2f}x  range {min(vals):.2f}-{max(vals):.2f}x")
        print(f"      within-seed: {detail}")
        if worst_arm is None or mean < worst_arm[1]:
            worst_arm = (arm, mean, min(vals))
    if worst_arm:
        print(f"\n  Lead with the conservative one: {worst_arm[1]:.2f}x mean, worst seed "
              f"{worst_arm[2]:.2f}x, against their strongest arm ({worst_arm[0]}).")
    for r in rows:
        if r["side"] == "competitor" and r["exact"] != "True":
            print(f"  {r['arm']} seed {r.get('seed')} is an interval "
                  f"[{r['modes_lower']}, {r['modes_upper']}] — frontier granularity, not "
                  f"uncertainty. The lower end is quoted, which UNDERSTATES the "
                  f"competitor and so OVERSTATES our ratio -- the conservative end for us "
                  f"is the upper one. Re-price at 1-mode spacing to remove the interval.")
    # The verification sentence: SPARROW pricing OUR selection, not competing with it.
    prov = json.loads((src.parent / "provenance.json").read_text())
    v = prov.get("verification")
    for i, note in enumerate(prov.get("footnotes") or [], start=1):
        # These go UNDER the table in the manuscript, not in it.
        print(f"\n  [{i}] {note}")
    if v:
        print(f"\n  Verification (a sentence, not a row): we independently priced "
              f"hub-batching's own\n  selection with SPARROW and the two agree to "
              f"{v['headline_gap_pct']}% on {v['headline_config']}.\n"
              f"  {v['direction']}.\n  Caveat: {v['caveat']}.")

    with (out / "table1_external.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(table[0]))
        w.writeheader()
        w.writerows(table)
    print(f"\ntable: {out/'table1_external.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
