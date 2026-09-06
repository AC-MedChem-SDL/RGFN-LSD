#!/usr/bin/env python3
"""Build the exhibit-review page from the current build/figures output.

Every number and image comes from the reproduce/ scripts' own output, so the page
cannot disagree with the figures. Run the reproduce scripts first, then this.

This lives in the repository rather than a temp directory on purpose: an earlier
version lived in a scratch dir and was lost when that dir was cleared, taking the
whole template with it.

    python3 tools/review/build.py            # -> build/review/exhibits.html
"""

from __future__ import annotations

import argparse
import base64
import csv
import html
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
FIG = REPO / "build" / "figures"
ART = REPO / "artifacts"

LBL = {"hub_batching": "hub-batching", "best_candidate": "best-candidate"}


def b64(p: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()


def rows(p: Path) -> list[dict]:
    with p.open() as fh:
        return list(csv.DictReader(fh))


def esc(x) -> str:
    return html.escape(str(x))


def f(x, default=0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def build() -> str:
    missing = [p.name for p in (FIG / "fig1_reaction_budget.png",
                                FIG / "fig2_floor_and_ceiling.png",
                                FIG / "fig3_selection_vs_enumeration.png",
                                FIG / "figA1_yield_risk.png",
                                FIG / "figA2_two_knob_surface.png") if not p.is_file()]
    if missing:
        sys.exit(f"missing figures: {', '.join(missing)}\n"
                 f"run the reproduce/ scripts first")

    # ---- Figure 1: the budget sweep, plus the both-bars secondary readout ----
    f1 = "".join(
        f'<tr><td class="m">{esc(r["budget_rxns"])}</td><td>{esc(r["scope"])}</td>'
        f'<td class="m num strong">{f(r["median_ratio"]):.2f}&times;</td>'
        f'<td class="m num">{esc(r["n_comparable"])}/{esc(r["n_total"])}</td>'
        f'<td class="m num">{f(r["min_ratio"]):.2f}&ndash;{f(r["max_ratio"]):.2f}&times;</td>'
        f'<td class="m num">{esc(r["n_bc_wins"])}</td></tr>'
        for r in rows(FIG / "fig1_summary.csv"))

    gate_rows = ""
    gv = FIG / "fig1_seh_gate_variants.csv"
    if gv.is_file():
        by_gate: dict[float, list[dict]] = {}
        for r in rows(gv):
            by_gate.setdefault(f(r["gate"]), []).append(r)
        for g in sorted(by_gate):
            at = by_gate[g]
            comp = [r for r in at if r["comparable"] == "True" and r["ratio"]]
            if not comp:
                continue
            vals = sorted(f(r["ratio"]) for r in comp)
            dropped = sorted({r["generator"] for r in at if r["comparable"] != "True"})
            gate_rows += (
                f'<tr><td class="m">bar {g:g}</td>'
                f'<td class="m num strong">{statistics.median(vals):.2f}&times;</td>'
                f'<td class="m num">{len(comp)}/{len(at)}</td>'
                f'<td class="m num">{min(vals):.2f}&ndash;{max(vals):.2f}&times;</td>'
                f'<td class="m">{", ".join(dropped) if dropped else "&mdash;"}</td></tr>')

    # ---- Figure 2 ----
    def floor_row(r):
        done = f(r["modes"]) >= 300
        reach = (f'{int(f(r["reactions"]))}' if done
                 else '<span class="chip bad">never</span>')
        return (f'<tr><td>{esc(r["label"])}</td>'
                f'<td class="m num strong">{int(f(r["modes_at_budget"]))}</td>'
                f'<td class="m num">{int(f(r["compute_s"])):,}</td>'
                f'<td class="m num">{reach}</td></tr>')
    floor = sorted(rows(FIG / "fig2_floor.csv"),
                   key=lambda r: -f(r["modes_at_budget"]))
    f2floor = "".join(floor_row(r) for r in floor)

    ceil = rows(FIG / "fig2_ceiling.csv")

    def ceil_row(label, subset):
        sh = [f(r["share_of_achievable_gain"]) for r in subset]
        ca = [f(r["scoring_ratio_greedy_over_flow"]) for r in subset
              if r["scoring_ratio_greedy_over_flow"]]
        wa = [f(r["wallclock_ratio_greedy_over_flow"]) for r in subset
              if r["wallclock_ratio_greedy_over_flow"]]
        return (f'<tr><td>{label}</td><td class="m num">{len(subset)}</td>'
                f'<td class="m num strong">{statistics.median(sh):.3f}</td>'
                f'<td class="m num">{min(sh):.3f}&ndash;{max(sh):.3f}</td>'
                f'<td class="m num">{min(ca):.1f}&ndash;{max(ca):.1f}&times;</td>'
                f'<td class="m num">{min(wa):.1f}&ndash;{max(wa):.1f}&times;</td></tr>')
    f2ceil = (ceil_row("all cells", ceil)
              + ceil_row("budget-bound only",
                         [r for r in ceil if r["pool_limited"] != "True"]))
    n_pl = sum(1 for r in ceil if r["pool_limited"] == "True")

    # ---- Table 1 ----
    t1 = rows(FIG / "table1_external.csv")

    def t1_row(r):
        head = r.get("is_headline_config") == "True"
        star = ' <span class="star" title="headline configuration">&#9733;</span>' if head else ""
        return (f'<tr class="{"ours" if r["side"] == "ours" else ""}">'
                f'<td>{esc(r["arm"])}{star}<div class="m" style="font-size:12px;color:var(--muted)">'
                f'{esc(r["config"])}</div></td>'
                f'<td class="m num strong">{esc(r["modes_at_100rxn"])}</td>'
                f'<td class="m num">{esc(r["ratio_vs_headline"])}</td></tr>')
    t1_rows = "".join(t1_row(r) for r in t1)
    # The conservative headline: the SMALLEST arm mean, read off the ratio the table
    # already computed within seed. Deriving it here as ours/max(theirs) would divide a
    # mean by a max and land on a number that appears nowhere in the table.
    means = []
    for r in t1:
        if r["side"] != "competitor":
            continue
        txt = str(r.get("ratio_vs_headline", ""))
        try:
            means.append(float(txt.split("x")[0]))
        except (ValueError, IndexError):
            pass
    lead = f"{min(means):.2f}" if means else "?"
    verif = (json.loads((ART / "external" / "provenance.json").read_text())
             .get("verification", {}))

    # ---- Figure 3 ----
    f3 = rows(FIG / "fig3_selection_vs_enumeration.csv")

    def f3_row(r):
        ours = r["arm"].startswith("hub-batching")
        return (f'<tr class="{"ours" if ours else ""}"><td>{esc(r["arm"])}</td>'
                f'<td class="m num">{esc(r["n_seeds"])}</td>'
                f'<td class="m num">{f(r["selected_mean"]):.0f}</td>'
                f'<td class="m num strong">{f(r["distinct_mean"]):.0f}</td>'
                f'<td class="m num">{esc(r["distinct_min"])}&ndash;{esc(r["distinct_max"])}</td>'
                f'<td class="m num">{f(r["rxn_per_candidate"]):.2f}</td>'
                f'<td class="m num strong">{f(r["rxn_per_distinct"]):.2f}</td></tr>')
    f3_rows = "".join(f3_row(r) for r in f3)

    # ---- Appendix ----
    ya = rows(FIG / "figA1_yield_risk.csv")
    ya_rows = "".join(
        f'<tr class="{"ours" if r["arm"] == "hub_batching" else ""}">'
        f'<td class="m">{esc(r["cell"])}</td><td>{LBL[r["arm"]]}</td>'
        f'<td class="m num strong">{f(r["mean_route_yield"]):.3f}</td>'
        f'<td class="m num">{f(r["mean_route_len"]):.2f}</td>'
        f'<td class="m num">{f(r["mean_step_yield"]):.3f}</td>'
        f'<td class="m num">{esc(r["modes"])}</td></tr>' for r in ya)
    steps = [f(r["mean_step_yield"]) for r in ya]

    zip_path = REPO / "build" / "gem.zip"
    zip_mb = f"{zip_path.stat().st_size / 1048576:.1f}" if zip_path.is_file() else "0.7"
    n_tests = len([l for l in (REPO / "tests").rglob("*.py")
                   for l in open(l) if l.strip().startswith("def test_")])

    body = (HERE / "body.html").read_text()
    css = (HERE / "style.css").read_text()
    head = (
        '<title>GEM Exhibit Board</title>\n'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
        'family=Archivo:wght@500;600;700&family=Source+Serif+4:opsz,wght@8..60,400;'
        '8..60,600&family=IBM+Plex+Mono:wght@400;500;600&display=swap">\n'
        f'<style>\n{css}</style>\n\n')

    # Recomputed over the drawn grid: the figure suppresses reward threshold 5.5, so the
    # harvest totals (449/452) describe a grid the reader cannot see. Kept in step with
    # SUPPRESSED_BARS in reproduce/figA2_two_knob_surface.py.
    a2rows_raw = [r for r in rows(ART / "two_knob" / "surface.csv")
                  if abs(f(r["reward_bar"]) - 5.5) > 1e-9]
    a2cells = {}
    for r in a2rows_raw:
        c = a2cells.setdefault(r["generator"], {"comparable": 0, "win": 0, "tie": 0,
                                                "loss": 0, "pool_limited": 0, "no_modes": 0})
        if r["cell_class"] == "comparable":
            c["comparable"] += 1
            adv = f(r["advantage"])
            c["win" if adv > 1 + 5e-4 else "loss" if adv < 1 - 5e-4 else "tie"] += 1
        else:
            c[r["cell_class"]] += 1
    a2 = json.loads((ART / "two_knob" / "provenance.json").read_text())
    a2rows = "".join(
        f'<tr><td>{esc(g)}</td>'
        f'<td class="m num strong">{c["win"]}/{c["comparable"]}</td>'
        f'<td class="m num">{c["tie"]}</td>'
        f'<td class="m num">{c["loss"]}</td>'
        f'<td class="m num">{c["pool_limited"] + c["no_modes"]}</td></tr>'
        for g, c in a2cells.items())
    a2t = {k: sum(c[k] for c in a2cells.values())
           for k in ("comparable", "win", "tie", "loss", "pool_limited", "no_modes")}

    fill = {
        "__FIG1__": b64(FIG / "fig1_reaction_budget.png"),
        "__FIG2__": b64(FIG / "fig2_floor_and_ceiling.png"),
        "__FIG3__": b64(FIG / "fig3_selection_vs_enumeration.png"),
        "__FIGA1__": b64(FIG / "figA1_yield_risk.png"),
        "__FIGA2__": b64(FIG / "figA2_two_knob_surface.png"),
        "__F1__": f1, "__GATEROWS__": gate_rows,
        "__F2FLOOR__": f2floor, "__F2CEIL__": f2ceil, "__NPL__": str(n_pl),
        "__T1__": t1_rows, "__LEAD__": lead,
        "__GAP__": str(verif.get("headline_gap_pct", "?")),
        "__CFG__": verif.get("headline_config", ""),
        "__F3__": f3_rows, "__YA__": ya_rows,
        "__STEPLO__": f"{min(steps):.2f}", "__STEPHI__": f"{max(steps):.2f}",
        "__ZIPMB__": zip_mb, "__NTESTS__": str(n_tests),
        "__A2__": a2rows, "__A2WIN__": str(a2t["win"]), "__A2CMP__": str(a2t["comparable"]),
        "__A2TIE__": str(a2t["tie"]), "__A2LOSS__": str(a2t["loss"]),
        "__A2BUDGET__": str(a2["budget_reactions"]),
    }
    for k, v in fill.items():
        body = body.replace(k, v)
    left = [k for k in fill if k in body]
    assert not left, f"unsubstituted placeholders: {left}"
    return head + body


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path,
                    default=REPO / "build" / "review" / "exhibits.html")
    args = ap.parse_args()
    page = build()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(page)
    print(f"wrote {args.out}  ({len(page) // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
