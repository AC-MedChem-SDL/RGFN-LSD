# The reward-threshold decision — what to change in the manuscript

Written 2026-09-06 for whoever is editing the paper. Everything here is measured, not
proposed; the run that produced each number is named. Read the first section before
writing a single sentence about thresholds, because there is one way to phrase this that
is fatal and it is close to the natural phrasing.

---

## 0. The one thing that must not appear in the paper

> ❌ "We gate our arm at 7.0 and the competitor at 5.68."

Both arms are **always measured at the same threshold**. Applying a different threshold to
each arm is not conservatism, it is the exact fault the appendix exists to disprove, and a
reviewer would be right to reject on it.

What we actually do:

> ✅ Every gate is the **5%-FPR point on its own oracle's actives-vs-decoys set** — sEH
> 5.68, DRD2 0.345, ClpP −9.1. On sEH we report the comparison at **both** 5.68 and 7.0,
> with both arms at each, and we **lead with the 7.0 numbers because they are the smaller
> ones**.

The sentence to aim for: *"5.68 is the principled threshold — it is where the sEH oracle
separates known actives from decoys at 5% false-positive rate. We report it, and we also
report the stricter 7.0 that prior numbers used. Our margin is smaller at 7.0, so that is
the one we quote."*

---

## 1. Why 5.68 rather than 5.0 or 7.0

| threshold | what it is | status |
|---|---|---|
| **5.68** | the 5%-FPR point on sEH's own actives-vs-decoys set | **the rule.** `targets.py:116` has carried it since 2026-08-21 |
| 5.0 | the older calibrated bar | 16% FPR — `targets.py` says so inline |
| 7.0 | "paper-comparable" variant | sits in the proxy's **optimised tail**: Logs/034 measured AUROC 0.76/0.68 and **0 of 2,315 real actives reach 8.0**; Logs/051 puts the meaningful range at ~5–6 with diversity collapsing past ~7 |

The rule generalises, which is the actual win: one sentence covers all targets instead of
four separately-argued numbers. Note that **Figure 1 currently uses four gates chosen four
different ways** — sEH 5.0 (Logs/034/051), DRD2 0.5 (a gate fix), ClpP −8.0 (Youden-optimal),
6TD3 −2.0 (**marked "PROVISIONAL, no AUROC calibration"**). That inconsistency is a larger
review risk than the sEH 5.0-vs-7.0 split and should be fixed in the same pass.

---

## 2. The numbers

### Table 1 — external comparison (sEH, R=100)

Competitor rows are **identical at both thresholds**. Our rows are not.

| arm | seed | @ 7.0 | @ 5.68 |
|---|---|---|---|
| S3-GFN → retro → SPARROW | 42 / 43 / 44 | 54 / 46 / 41 | **54 / 46 / 41** (unchanged) |
| S3-GFN → retro → greedy | 42 / 43 / 44 | 55 / 55 / 65 | **55 / 55 / 65** (unchanged) |
| SCENT → hub-batching (ours) | 42 / 43 / 44 | 82 / 81 / 82 | — / 95 / 94 |

**Headline to quote: 1.41× mean, worst seed 1.26×, at threshold 7.0**, against their
strongest arm (greedy). Within-seed: s42 82/55 = 1.49×, s43 81/55 = 1.47×, s44 82/65 = 1.26×.
Against SPARROW it is 1.76× mean (1.52–2.00×).

At 5.68 the same comparison is ~1.59×. **Do not lead with it.** Report it as the value at
the principled threshold and say why it is larger (§3).

### Figure 3 — selection vs enumeration (sEH, R=100)

**Keep this figure at 7.0.** At 5.68 both competitor arms become unquotable:

All four solves are now in (job 75758, 61 min on `debug`). Distinct molecules kept at
R=100, against our 81 / 95 (seed 43) and 82 / 94 (seed 44) at 7.0 / 5.68:

| seed | λ | @ 7.0 | @ 5.68 | solver @ 5.68 | ratio @ 7.0 | ratio @ 5.68 |
|---|---|---|---|---|---|---|
| 43 | 0 | 24 | **4** | Optimal | 3.38× | 23.75× |
| 43 | 1 | 33 | 34 | **TimeLimit** | 2.45× | *2.79× — not quotable* |
| 44 | 0 | 26 | **9** | Optimal | 3.15× | 10.44× |
| 44 | 1 | 32 | **23** | Optimal | 2.56× | 4.09× |

- **λ=0 collapses** (24→4, 26→9). Real mechanism, not a bug: the enumerated pool is
  ~26,000 candidates, so a looser threshold floods the diversity-blind optimizer with
  near-duplicates. Ratios of 10–24× are not a result anyone should print.
- **λ=1 gets worse for the competitor too** (32→23 on seed 44, Optimal), and on seed 43 it
  hits the solver time limit at 1,702 s. A capped row is a **lower bound on the
  competitor**, so the ratio beside it is an **upper bound on us** and cannot be quoted.

At 7.0 both arms return `Optimal`. Quote **λ=1 at 2.51×** as the headline and λ=0 at 3.26×
as the diversity-blind reference.

**Seed 42 is excluded from Figure 3** — its two arms never read the same enumeration (ours
`scent_seh_freefrag`, SPARROW's `bc_enum_seh_seed42`; seeds 43/44 both read
`t45_seh_seed{43,44}`, verified in each run's `select_frontier_summary.json`). The figure's
whole claim is that both arms choose from the same pool. Dropping it **lowers** λ=0 from
4.71× to 3.26×, because seed 42's collapse-to-2 was carrying most of that ratio. n=2.

### Figure 1 — the other three targets move for free

Re-read at their 5%-FPR gates, budget 100, cutoff 0.5. All twelve cells stay comparable;
none becomes pool-limited or empty.

| target | gate change | ratios before → after (fraggfn / rgfn / rxnflow / scent) |
|---|---|---|
| sEH | 5.0 → 5.68 | 4.15 / 2.44 / 2.39 / 2.75 → **4.00 / 2.28 / 2.21 / 2.71** |
| DRD2 | 0.5 → 0.345 | 4.40 / 3.28 / 1.67 / 2.96 → **4.40 / 3.28 / 1.76 / 3.00** |
| ClpP | −8.0 → −9.1 | 4.80 / 3.33 / 2.45 / 2.93 → **4.80 / 2.44 / 2.03 / 2.74** |

Mostly **down**. Adopting the rule costs a little advantage and buys a uniform
justification. **6TD3 is excluded**: its 5%-FPR gate (6.718) belongs to the 6TD3-B CNN_VS
oracle, a different reward from the −2.0 differential those cells were docked with. That is
a re-dock, not a re-gate.

### Appendix A2 — the two-knob surface

Already at the rule. 9 reward thresholds × 13 diversity thresholds, four generators, budget
100: **hub-batching cheaper in 397 of 400 comparable cells, 3 exact ties, 0 losses.**
Medians 2.57–4.40×. The operating point 5.68 is marked filled; 5.0 and 7.0 hollow.

---

## 3. The disclosure that has to be in the paper

**Lowering the threshold helps us and not them, and the reason is pool size.**

Measured: the competitor's pool holds **499 molecules above the gate at 7.0 and 499 at
5.68** — identical, on all three seeds. The threshold is entirely **non-binding** for them,
because their pool was built as the top-500 by score and essentially all of it already
clears 7.0. Our enumerated pool is ~26,000 candidates, so a looser threshold admits a great
many more.

So the ~16% gain in our numbers between 7.0 and 5.68 is an artefact of pool size, not of
method quality. **State this explicitly.** A reviewer who compares the two thresholds will
find it in thirty seconds, and it is far better as a disclosed limitation than as a
discovery. It is also the reason leading with 7.0 is the right call: at the threshold that
binds neither arm's pool differently, we still win.

---

## 4. Text changes, concretely

1. **Methods, thresholds.** One sentence for the rule, with the four values and the 5%-FPR
   definition. Cite the calibration set, not the convenience.
2. **Table 1 caption.** "seeds 42/43/44" (was seed 43). Headline **1.41× (worst seed 1.26×)**
   at threshold 7.0. Add: the enlarged S3-GFN pools cost **10,271 / 41,346 / 10,342**
   eval-phase oracle calls for seeds 42/43/44 against a 10,048-call training budget —
   **per seed, no average, no error bar**.
3. **Table 1 exactness — re-priced 2026-09-06, and the brackets resolve to their LOWER
   ends.** Seeds 42 and 44 were re-priced on a 1-mode grid at gate 7.0
   (`results/s3gfn_seh_seed{42,44}_big_greedy_FINE`, 36 points each, every solve
   `Optimal`). Both land exactly on the bracket's lower end, and the boundary is not close:

   | seed | quoted modes | cost | next mode up | cost |
   |---|---|---|---|---|
   | 42 | **55** | 99 rxn | 56 | **103** rxn |
   | 44 | **65** | 100 rxn | 66 | **101** rxn |

   So 55 and 65 are measurements, not the optimistic end of a range. The old bracket note
   can go, and the headline stands at **1.41× mean / 1.26× worst**.

   **Why this needed checking rather than assuming.** With a 5-mode grid the competitor's
   true count lies in [lo, hi], meaning it delivers *at least* lo — so quoting lo
   **understates the competitor and inflates our ratio**. Had the brackets stood, the
   honest headline would have been 1.35× mean / 1.19× worst (82/59, 81/55, 82/69), not
   1.41×/1.26×. Two strings in the code said the opposite — that quoting lo was "the
   conservative end for us" — and both are corrected. The direction is worth holding onto:
   *a lower competitor count always flatters us.*
4. **Figure 3 caption.** n=2, seeds 43/44. Say seed 42 is excluded for reading a different
   enumeration, and that removing it **lowered** λ=0 from 4.71× to 3.26×.
5. **A limitations sentence** carrying §3 above.
6. **Appendix A2** as the threshold-robustness answer; the ↗ in its title means *stricter*,
   not *better* — the advantage narrows toward that corner.
7. **Do not** describe 7.0 as "conservative for both arms". It is non-binding for the
   competitor and binding for us, which is a sharper and more accurate statement.

---

## 5. Open items

- **Table 1 at 5.68 is n=2 for our arm** — seed 42's hub-batching run has no `t45`
  directory (same asymmetry that removed it from Figure 3). At 7.0 it is n=3.
- **6TD3** needs its column reconciled against the 6TD3-B oracle; `targets.py:175` carries
  6.718 while a docstring in `calibrate_gates.py:24` still says 7.97.
- Figure 3's seed-44 λ solves at 5.68 were still running when this was written; they do not
  change the recommendation, since the figure stays at 7.0 either way.

Source runs: `results_g568/` and `bc_sb_g568/` under
`lsdflow_sparrow/` (gate 5.68), `results/` and `bc_sb/` (gate 7.0),
`matrix16/results/fpr_gate_r100/` (Figure 1), `artifacts/two_knob/` (A2).
