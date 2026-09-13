# Claims, and how to check each one

Every claim the paper makes, the command that regenerates its evidence, and **what would
falsify it**. If a claim is not in this table it is not being made.

All commands are CPU-only and read committed artifacts. None needs a GPU, a cluster, or a
download.

```bash
pip install -e ".[figures]"
for s in reproduce/*.py; do python "$s"; done      # every number below, a few minutes
```

---

## The claim architecture

One sentence, three sub-claims:

> **Reading a trained reaction-GFlowNet's flow field post-hoc selects intermediates to batch a
> library around, delivering more distinct high-reward molecules per reaction than either
> best-candidate selection or retrosynthetic planning over a route-less generator.**

| | sub-claim |
|---|---|
| **A. The axis** | library cost — reactions per distinct molecule — is the right unit, and it is not the sum of per-molecule costs |
| **B. The mechanism** | the flow field is what delivers it, not the reward gate or the diversity filter |
| **C. Generality** | it holds across generators, targets, seeds, and both quality knobs |

---

## A. The axis

### A1 — Hub-batching delivers more distinct molecules at a fixed reaction budget

```bash
python reproduce/fig1_reaction_budget.py
```

**2.82× median at R=100** over calibrated-gate cells, 31 of 32 comparable, range 1.70–4.80,
**zero cells where best-candidate wins or ties**. Also reported at R=50/150/200.

*What would falsify it:* a cell where best-candidate delivers more at the same budget with both
arms budget-binding. The script counts those explicitly and currently reports 0.

*Do not over-read:* the median is over *comparable* cells only — both arms budget-binding. A
cell that ran out of material did not choose to stop, and is excluded rather than counted.

### A2 — The advantage is not an artefact of route length

```bash
python reproduce/figA1_yield_risk.py
```

Mean **step** yield is 0.730–0.765 for **both arms on every cell**, so the route-yield difference
is length, not chemistry. Hub-batching's routes are shorter on DRD2 (2.66 vs 3.37 steps) and
slightly longer on sEH (2.00 vs 1.82).

*This one cuts against us and is reported anyway:* on sEH, hub-batching's mean **route** yield is
*lower* (0.563 vs 0.597, 0.533 vs 0.627). The reaction budget is yield-blind — it counts
reactions, not successful ones — and this is where that shows.

---

## B. The mechanism

### B1 — The flow ordering is load-bearing

```bash
python reproduce/fig2_floor_and_ceiling.py
```

| hub order | molecules @ 100 rxn | reactions → 300 |
|---|---|---|
| highest flow | **73** | 357 |
| best child score | 70 | 389 |
| random | 50 | 546 |
| lowest flow | 42 | never reaches 300 |

Highest-flow and best-child-score are both on the Pareto frontier (reactions × compute); random
and lowest-flow are dominated on both axes.

*What would falsify it:* random ordering matching flow ordering. It does not — it costs ~1.5×.

*The honest nuance:* highest-flow and best-child-score agree closely. The flow field picks the
**neighbourhood**, not the precise rank. The claim is Pareto dominance over uninformed
ordering, not that this specific scorer is uniquely correct.

### B2 — Greedy selection is near the achievable ceiling

Same script. **Median 0.946 of achievable gain** (range 0.821–0.989) across 14 cells; 0.952 over
the 12 budget-bound ones. The exhaustive alternative pays 1.0–26.8× more scorings and up to
79.8× more wall-clock.

*What this does not claim:* optimality. It bounds how much a better selector could win.

### B3 — Both halves of the mode definition are load-bearing

Dropping either the reward gate or the diversity filter makes the headline look ~1.13× *better*
while costing 9.8×, 6.8× and 29× more per **qualified** molecule. The library collapses and the
metric stops noticing. (Research-tree measurement; reported as an ablation, not a headline.)

---

## C. Generality

### C1 — Across a competing planner, not just a naive baseline

```bash
python reproduce/table1_external.py
python reproduce/fig3_selection_vs_enumeration.py
```

| pipeline | molecules @ 100 rxn | vs ours |
|---|---|---|
| S3-GFN → retrosynthesis → SPARROW selects | 47.0 (41–54) | 1.76× (1.52–2.00) |
| S3-GFN → retrosynthesis → greedy selection | 58.3 (55–65) | **1.41× (1.26–1.49)** |
| SCENT → hub-batching | 81.7 (81–82) | — |

n=3 seeds, ratios computed **within seed** then averaged. Parenthesised values are the observed
range, not a confidence interval.

**Lead with 1.41× mean / 1.26× worst seed**, against the competitor's *strongest* arm. Quoting
the 1.76× against its weaker arm would be choosing the opponent.

Figure 3 isolates selection from enumeration on a shared pool: 3.26× against diversity-blind
λ=0, **2.51×** against λ=1. The mechanism is visible in the pools themselves — median pairwise
Tanimoto 0.137 for ours against 0.351–0.366 for SPARROW, so 99 selected compounds collapse to
24–33 distinct.

*Seed 42 is excluded from Figure 3* because its two arms read different enumerations, and the
figure's whole claim is that both choose from the same pool. **Dropping it lowered λ=0 from
4.71× to 3.26×** — it moved against us.

### C2 — Across both quality knobs

```bash
python reproduce/figA2_two_knob_surface.py
```

9 reward thresholds × 13 diversity cutoffs, four generators, budget 100:
**397 of 400 comparable cells cheaper, 3 ties, 0 losses.** Medians 2.57–4.40×.

*What would falsify it:* a region of the (gate × cutoff) plane where best-candidate wins. There
is none on the swept grid. Pool-limited cells are hatched, never counted as wins.

---

## Where a claim is deliberately *not* made

- **Not a retrosynthesis claim.** Routes are the *logged assembly route* the model used, not an
  assertion of optimal synthesis.
- **Not a yield model.** See A2 — the budget counts reactions, not successful ones.
- **Not an activity claim.** A gate is calibrated separation on a given oracle, a statement about
  the oracle rather than about binding. One proxy separated actives from decoys at AUROC 0.76
  with *zero of 2,315 real actives* reaching a bar that was being quoted.
- **6TD3 is excluded from the headline.** Its gate was never calibrated against
  property-matched decoys, and the reward it was measured with has since been replaced. It is
  reported alongside (`--include-uncalibrated`), never pooled silently. Its artifacts are marked
  `invalidated` in `artifacts/MANIFEST.csv`.
- **Compute-time accounting** is measured and real but held back — see `docs/DEFERRED.md`.

## Thresholds

Every gate is the **5%-false-positive point on its own oracle's actives-versus-property-matched-
decoys set**. Both arms are *always* measured at the same threshold. Where sEH is reported at two
bars, both arms appear at each, and the **smaller** margin is the one quoted. See
`docs/THRESHOLD_DECISION.md`, including the disclosure that the threshold is non-binding for the
competitor's pool and binding for ours — which is a sharper statement than calling it
"conservative".

## Data currency

Everything in `artifacts/` is generation `v1`; 27 files are `invalidated` and 2 are `v1-stale`.
`artifacts/README.md` explains the distinction, which matters: an *invalidated* artifact has no
newer measurement of the same quantity and never will.
