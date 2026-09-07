# Figure captions — verified against the data, not written from memory

Every number here was read out of `build/figures/*.csv` or traced to a run's own
metadata. Regenerate the figures and re-check before submission: if a number in a
caption cannot be found in the CSV beside its figure, it is wrong.

---

## Figure 2, right panel — the ceiling

**Full version.**

> **The one-shot flow ranking captures most of what re-deciding at every step could
> achieve.** For each cell we compare three selections under a fixed 100-reaction
> budget: the best-candidate baseline, hub-batching's one-shot flow ranking, and an
> oracle greedy that re-ranks every remaining intermediate by measured marginal gain at
> each step. Bars show the share of the baseline-to-oracle-greedy improvement that the
> one-shot ranking already captures. Across 14 cells — four generators (RGFN, SCENT,
> RxnFlow, FragGFN) crossed with four reward generators (sEH, DRD2, ClpP, 6TD3), less two
> RGFN cells that were not trained — the median is **0.946** (range 0.821–0.989), one
> seed per cell, 200 intermediates each, Tanimoto cutoff 0.5, and per-target gates of 7.0
> (sEH), 0.5 (DRD2), −8.0 (ClpP) and −2.0 (6TD3). The oracle greedy is unaffordable by
> construction — it cannot rank an intermediate it has not scored, so it pays
> **1.5–26.8× more molecule scorings** and **5.6–79.8× more selection wall-clock**. Two
> cells (`rgfn_seh`, `rxnflow_seh`) are pool-limited, with neither arm reaching the mode
> budget; they are shown but excluded from those ranges, and over the 12 budget-bound
> cells the median is **0.952**.

**Trimmed, if space is tight.** Keep the quantity, the scope, the median, and the price;
everything else can go to the text.

> **The one-shot flow ranking captures most of the achievable improvement.** Share of the
> best-candidate-to-oracle-greedy improvement recovered by hub-batching's one-shot
> ranking at a fixed 100-reaction budget, across 14 cells (four generators × four reward
> generators, less two untrained RGFN cells), one seed each. Median **0.946**, range
> 0.821–0.989. The oracle greedy re-ranks every remaining intermediate at each step and is
> unaffordable by construction: 1.5–26.8× more molecule scorings, 5.6–79.8× more selection
> wall-clock. Two pool-limited cells are shown but excluded from those ranges; over the 12
> budget-bound cells the median is 0.952.

### Which clauses are load-bearing, and why

| clause | why it cannot be cut |
|---|---|
| "one seed per cell" | The whole panel is n=1 per cell. Omitting it invites a reader to assume error bars exist. |
| "less two RGFN cells" | 14, not 16. A reader who counts the bars will notice. |
| the four gates | Four different reward generators on four different scales; a single unqualified "gate" would be meaningless. |
| "unaffordable by construction" | This is the reason the ceiling is a ceiling rather than a method. Without it, a reviewer asks why we do not simply use the greedy. |
| the two pool-limited cells | Their scoring ratio degenerates to 1.0× and the greedy can even come out faster. Quoting the wider range without saying which cells produce it would be quoting a defect as a result. |

### Two things to decide before submitting

**The 6TD3 cells use the −2.0 gate**, which is the un-calibrated one the severe-testing
section is built around, and they are 3 of the 14. Unlike Figure 1, this does not threaten
the result — the median barely moves under any slicing:

| scope | n | median | range |
|---|---|---|---|
| all cells | 14 | 0.946 | 0.821–0.989 |
| budget-bound only | 12 | 0.952 | 0.821–0.989 |
| excluding 6TD3 | 11 | 0.948 | 0.821–0.989 |
| excluding both | 9 | 0.961 | 0.821–0.989 |

So a single sentence covers it: the median is 0.946–0.961 under every slicing. That is a
stronger statement than picking one and is cheaper than defending a choice.

**The child policy is not uniform across cells.** SCENT runs `free_frag` with
`prebuild_k=20`; RGFN, RxnFlow and FragGFN run the naive `reward` policy at K=0. This is
correct rather than sloppy — only SCENT has a dynamic library, so `free_frag` has nothing
to act on elsewhere — but a reader comparing cells should be told, or they will read
cross-cell differences as generator effects when part is configuration.

### An implementation check worth one sentence in the text

Running the same greedy machinery in *static* order over the flow ranking reproduces the
shipped strategy **bit-for-bit in 14 of 14 cells**. So the ceiling comparison is not
confounded by two code paths computing "the same" library differently — the arms differ in
ordering alone. This belongs in the methods, not the caption.

---

## Figure 2, left panel — the floor

Scope differs sharply from the right panel and the caption must say so: the floor is a
**deep single-cell ablation** (SCENT on the sEH surrogate proxy, one frozen checkpoint,
one seed, 200 intermediates, gate 7.0, τ 0.5, `free_frag` child policy at K=20) while the
ceiling spans 14 cells. All arms share one checkpoint and one enumeration, so the only
thing varying is the walk order — that is what licenses the comparison.

It is **not** the same checkpoint the matrix cells use (Figure 1 draws on the
`scent_seh_5k` series; this ablation predates it), so their similar values at gate 7.0 are
a coincidence of two checkpoints and must not be presented as a cross-validation.

See `artifacts/mechanism/hub_ordering/PROVENANCE.md`.

---

## Appendix A2 — the two-knob surface

Draft caption:

> **The advantage does not depend on where the two thresholds are set.** Every headline
> number is quoted at one reward threshold and one Tanimoto threshold. Sweeping both — 9
> × 13, all four generators on sEH, at the paper's own 100-reaction budget — leaves
> hub-batching cheaper per distinct molecule in **397 of 400 comparable cells**, with 3
> exact ties and no losses. Colour is the ratio of the two arms' reactions-per-mode, so
> 1.0 is parity. Hatched cells are pool-limited (one arm exhausted its library before
> spending the budget, so its cost is measured over a shorter run); grey cells hold no
> modes at all for either arm. The filled marker is the operating point (reward threshold
> 5.68, the 5%-FPR gate on sEH's own actives-vs-decoys set); hollow markers are the two
> other thresholds existing numbers sit at, 5.0 and 7.0. ↗ marks the direction of
> increasing stringency, not of improvement — the advantage narrows toward that corner.

### Three things the caption must not overstate

**The ties are ties, not wins.** Three cells sit at exactly 1.00 — FragGFN at bar 8.0 with
cutoffs 0.3 and 0.35, RxnFlow at bar 6.5 / cutoff 0.3. Both arms land on the same small set
and price it identically. Counting them as wins would have been free and wrong; the harvest
classifies anything within 5e-4 of parity as a tie for that reason.

**RGFN's 7.0 cell is hatched, and that is an argument against 7.0.** At bar 7.0 / cutoff
0.5 the best-candidate arm on RGFN is pool-exhausted (9 modes for 36 of its 100 reactions),
and RGFN's whole 7.0 row is hatched. `targets.py` already records the same starvation for
both RxnFlow cells on all three seeds. At the 5.68 operating point all four generators are
comparable, at 2.26 / 2.71 / 2.19 / 4.00×. The ratio at 7.0 is taken over a starved
baseline, so it *understates* hub-batching — dropping 7.0 costs us nothing.

**This is one target and one seed.** sEH only, and the surface re-scores a single cached
enumeration per generator — it sweeps thresholds, not seeds. It answers "is the result an
artifact of the thresholds", and nothing else. Seed variance is Figure 3's question.

### Why it is measured at 100 and not 300

An earlier surface exists at a 300-reaction budget (`results/surface/`, 4 generators, a
9-bar grid) and agrees: 381/381 comparable cells, median advantage 2.60–4.47×. It was not reused,
because defending the thresholds at a budget the paper never quotes invites the obvious
question. Re-measuring is pure CPU re-scoring of an existing enumeration, about five minutes
a generator, so there was no reason to inherit the old budget.

**A coincidence worth not leaning on:** SCENT at bar 5.0 / cutoff 0.5 reads 77 modes against
best-candidate's 28, close to Figure 1's headline SCENT cell. These are the same matrix
checkpoint and enumeration, so it is a consistency check on the pipeline, not independent
corroboration of the result.

See `artifacts/two_knob/provenance.json` for per-cell counts and source digests.

### Two layouts, one figure

`--layout row` (1×4, ~14.1 in wide) and `--layout grid` (2×2, ~8.4 in). Both render from
the same code, so every content decision above applies to either; only the figure size and
the title/legend offsets differ. The row reads better — four panels on one baseline, one
shared y-axis — but only fits as a full-page landscape plate or a two-column span at small
type. The grid drops into an ordinary column-spanning slot. Pick on the page budget, not on
the content; the review board shows the row.

### Why the figure shows 9 reward thresholds and the artifact holds 10

The grid was measured at 4.0–8.0 in steps of 0.5 **plus 5.68**, the 5%-FPR operating point.
The figure suppresses 5.5, so 5.68 replaces its nearest neighbour rather than sitting 0.18
away from it, which reads as a rendering artefact rather than a measurement. Counts in the
figure are computed over what is **drawn** (397 of 400), never off the harvest totals (449
of 452) — otherwise the caption would quote a grid the reader cannot see. `SUPPRESSED_BARS`
in the reproduce script is the single place this is decided, and `artifacts/two_knob/` keeps
the 5.5 row for anyone who wants the even ladder.

---


## Appendix A1, third panel — what each arm picked, against what it picked from

Draft caption:

> **Are the extra molecules worse ones?** Pale violins are each arm's source pool, solid
> violins its selection under the 100-reaction budget; SCENT, seeds 43 and 44, at the same
> 5%-FPR thresholds as the rest of the paper. The arms draw from **different pools** —
> best-candidate from the sampled candidates, hub-batching from the enumerated children of
> its hubs — so each is shown against its own. Best-candidate takes a sliver at the extreme
> top of its pool (sEH median **8.31**); hub-batching takes a band spanning most of its own
> (median **6.53**). Both clear the same threshold, so every molecule in both selections is
> a hit by our own definition.

### The panel goes against us on the median, and that is why it is here

Best-candidate's selections score higher on both targets. That is what it is built to do —
it takes the top of its pool by reward. Do not bury it and do not dress it up. What the pool
violins add is *where* that top lies, and at the 5%-FPR thresholds the answer is categorical:

- On sEH, **all 54 of its selected molecules score above 8.0** — a level Logs/034 measured
  that **0 of 2,315 real actives** reach, with proxy AUROC 0.76/0.68 against decoys.
  Hub-batching puts 2 of 189 there.
- On DRD2, **all 54 sit at exactly 1.000**, the saturation Logs/066 documented. Hub-batching
  puts 22 of 179 there.

The defensible claim, narrower than "our molecules are better":

> Both arms deliver hits. Best-candidate's entire selection lies in a region where the
> oracle has not been shown to track activity, so its higher reward is not evidence of
> better molecules.

It does **not** establish that hub-batching's molecules are more active. Nothing here
measures activity, and 6.53 is not shown to beat 8.31 within the calibrated range.

### What was fixed to make this panel possible

All three A1 panels were re-run together on 2026-09-06, at the 5%-FPR thresholds and against
the enumerations every other figure reads. Both changes were needed:

- The previous panels 1–2 used sEH **7.0** and DRD2 **0.5**, pre-dating the threshold rule.
- More seriously, they were built against enumerations that have since been regenerated:
  only **8–71%** of their hub-batching molecules still existed on disk (drd2_seed43 was 8 of
  96). They were therefore not reproducible from the artifacts, which is how the problem was
  found — a join against them failed.

The two selection paths now agree: `yield_by_strategy.py` and `run_campaign.py` return
identical hub-batching counts on three of four cells and differ by one molecule on
best-candidate, which is a budget-boundary convention (the former allows the slight
overshoot its `used_rxns` column shows, the latter truncates at ≤100), not a disagreement
about molecules.

Source: `artifacts/rewards/selection_rewards.csv` and `artifacts/yield_risk/strategy_yield.csv`
(pools subsampled to 1,200 points per cell and arm).

### Why panels 1–2 show dots and not error bars

There are **two seeds**. A whisker over two points implies a distribution that cannot be
estimated from them, and it fails in a specific way here: when the seeds agree closely it
collapses to nothing, which reads as *"no variation"* rather than *"the two runs agreed"*.
Each seed is drawn as its own dot instead — the same device Figure 3 uses, for the same
reason.

Two of the four route-length bars used to show no marker at all. That was a **storage
artifact**: `mean_route_len` was rounded to 2 decimal places at write time while
`mean_route_yield` got 4, so a seed spread below 0.01 wrote as identical values. Fixed to 4
d.p. (`yield_by_strategy.py`), which recovers DRD2 hub-batching's real spread of 0.0039
steps. sEH hub-batching genuinely is 2.0 in both seeds — every selected molecule is exactly
two steps. Coincident seeds are nudged apart horizontally so two runs never print as one
point; the mark itself is Figure 3's, so the two figures do not use different conventions
for the same n.

Observed seed spreads, as a fraction of the mean: route yield 0.15%–5.4%, route length
0.0%–3.8%. The bars are close together because the runs agree, not because the figure is
hiding anything.
