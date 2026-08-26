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
    ours = int(headline["modes_lower"])

    print(f"Table 1 — modes delivered at 100 reactions (sEH, gate {headline['gate']})\n")
    print(f"| {'pipeline':<50} | {'modes @ 100 rxn (\u2191)':>19} | {'vs ours':>10} |")
    print(f"|{'-'*52}|{'-'*21}|{'-'*12}|")
    table = []
    for r in rows:
        lo, hi = int(r["modes_lower"]), int(r["modes_upper"])
        if r["side"] == "ours":
            ratio = "—" if r is headline else f"{ours/lo:.2f}x" if lo else "—"
        elif lo == hi:
            ratio = f"{ours/lo:.2f}x" if lo else "—"
        else:
            # Interval in the denominator inverts: the competitor's UPPER bound gives
            # our LOWER ratio, which is the conservative end and the one to lead with.
            ratio = f"{ours/hi:.2f}-{ours/lo:.2f}x"
        star = " *" if r is headline else ""
        print(f"| {r['arm'][:50]:<50} | {str(r['modes_at_100rxn']):>19} | {ratio:>10} |{star}")
        table.append({**r, "ratio_vs_headline": ratio})
    print(f"\n  * the headline configuration ({headline['config']})")

    exact = [r for r in rows if r["side"] == "competitor" and r["exact"] == "True"]
    inexact = [r for r in rows if r["side"] == "competitor" and r["exact"] != "True"]
    print()
    for r in exact:
        print(f"  vs {r['arm']}: {ours}/{r['modes_lower']} = "
              f"{ours/int(r['modes_lower']):.2f}x   "
              f"({r['solver']}, spent {r['used_rxns']} reactions)")
    if len(exact) > 1:
        worst = max(exact, key=lambda r: int(r["modes_lower"]))
        print(f"\n  Lead with the conservative one: "
              f"{ours/int(worst['modes_lower']):.2f}x against their strongest arm.")
    for r in inexact:
        print(f"  {r['arm']} is an interval [{r['modes_lower']}, {r['modes_upper']}] — "
              f"frontier granularity, not uncertainty. Lead with the conservative end.")
    # The verification sentence: SPARROW pricing OUR selection, not competing with it.
    prov = json.loads((src.parent / "provenance.json").read_text())
    v = prov.get("verification")
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
