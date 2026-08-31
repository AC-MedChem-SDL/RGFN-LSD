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
