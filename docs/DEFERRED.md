# Deferred to the conference / journal version

Results that are real and measured but deliberately out of scope for the 5-page
workshop paper. Each entry says what it is, where the evidence lives, and why it was
held back — so the decision is recoverable rather than looking like an omission.

## Compute-time accounting

**What it is.** Hub-batching's reaction savings are bought with selection compute:
roughly 150× more than the best-candidate baseline (~170 s against ~1 s at τ=0.5) to
save ~113 bench reactions. The component split is the interesting part and it *flips*
with the cost of the reward: for a millisecond surrogate, enumeration is 64–79% of the
bill and reward evaluation only ~5%; for real GPU docking, reward evaluation is
87.5–99.7%. So the more expensive the oracle, the smaller hub-batching's relative
overhead — which is the regime a real campaign runs in.

**Evidence.** Logs/039, Logs/044, Logs/055, Logs/058. Measured in-run wall-clock per
component, never modelled. `artifacts/mechanism/hub_ordering/` already carries the
per-arm compute axis, and Figure 2's floor panel plots it.

**Why held back.** It is an ML-audience argument about where the method spends its
budget. A workshop convened to put experimental chemists in the room is weighing
whether the plan is makeable, not how many seconds the selector took. The one-line
version — that the overhead shrinks as the oracle gets more expensive — can sit in a
sentence if space allows.

**What the fuller treatment needs.** The surrogate-versus-docking contrast drawn as a
single panel, and the per-stage attribution stated for both regimes. Neither needs new
compute; both need space.

## Others held back for the workshop

- **Two-knob threshold surfaces** (reward bar × diversity cutoff, 380/380 comparable
  cells with no crossover). Logs/052, Logs/055. Strong generality evidence, needs a
  full figure.
- **Filter ablation** (both halves of the mode definition are load-bearing; dropping
  either looks ~12–13% cheaper while the library collapses). Logs/054. One sentence
  plus an appendix pointer in the workshop version.
- **Construct-validity ladder** (walking the metric's low end recovers fragment
  screening, then parallel synthesis, then late-stage diversification). Reads better to
  a chemistry audience than an ML one, so it is a candidate to *promote* rather than cut
  if the journal version is the target.
- **Chemistry gallery** (closest still-distinct pair at each τ, with route trees).
  Makes τ interpretable to a chemist. Appendix asset.

---

# Needs refreshing before publication (not deferred — dated)

## ~~Table 1's competitor was trained at a much larger budget~~ RESOLVED 2026-08-28

The `OLDBUDGET_` pools held S3-GFN checkpoints trained far longer than the generators
they were compared against, and sampled too thinly to route 500 molecules. Both are now
fixed: budget-matched checkpoints with sampling raised until the routed pool reaches 500.

**The headline moved, substantially, and in the competitor's favour.** On seed 43 at
gate 7.0, both solves optimal:

| arm | OLDBUDGET pool | budget-matched pool |
|---|---|---|
| SPARROW selects | 24 modes (3.42x) | **46 modes (1.76x)** |
| greedy selection | 38 modes (2.16x) | **55 modes (1.47x)** |

A properly-sampled, budget-matched S3-GFN is a far stronger opponent, and 1.47x against
its best configuration is the number to quote. The old figures are superseded, not merely
older, and must not be cited.

**Still open on this arm:**

- ~~**Seeds 42 and 44** have no select/greedy solves yet, so Table 1 is n=1.~~ **CLOSED
  2026-09-12.** All three seeds now solve on both competitor arms, and
  `reproduce/table1_external.py` reports n=3: 1.41x mean against greedy (range 1.26-1.49),
  1.76x against SPARROW-selects (1.52-2.00). The concern that motivated this bullet -- that
  seed variance could move a margin this small -- is answered by the observed range rather
  than assumed away.
- **The diversity-enforced pool.** A "pruned" variant -- 500 mutually different molecules
  rather than the 500 highest-scoring -- exists for seed 43 and gives a different picture.
  It is under review rather than quoted, and the table carries a line saying so. Deciding
  which pool is the fair comparison is a real methodological question, not a formatting
  one: pruning changes what the competitor is optimising over, and Logs/067 exists
  precisely because the answer is not obvious.

## Open: sEH is gated at two different thresholds across exhibits

| exhibit | sEH gate | why |
|---|---|---|
| Figure 1 | **5.0** | the calibrated headline bar (decided 2026-08-18): Logs/034 measured only weak enrichment above ~6 and Logs/051 found diversity collapsing past ~7 |
| Figure 3, Table 1 | **7.0** | what the competitor pipeline and the SPARROW runs were actually measured at; also the value the RGFN paper's own sEH numbers are quoted at, so it is the paper-comparable bar |

Each is defensible on its own and neither is wrong. But a reader who notices sEH
appearing at 5.0 in one figure and 7.0 in another will ask, and the answer needs to be
in the paper rather than in a repository note.

**Three ways to close it**, in increasing cost:

1. **State it.** One sentence: Figure 1 uses the calibrated bar, the external comparison
   uses the paper-comparable bar, and the advantage is threshold-robust (Logs/052 and
   Logs/055: 380 of 380 comparable cells, no crossover on either knob). Cheapest, and
   already supported by evidence we have.
2. **Add a 7.0 column to Figure 1.** `threshold_variants` already includes 7.0 for sEH
   and the gate sweep machinery exists, so this is a re-read rather than a re-run.
3. **Re-measure the competitor at 5.0.** Correct but expensive: it means re-solving the
   SPARROW selections against a 5.0-gated pool, and the pool changes size, so it is a
   new measurement rather than a re-slice.

Recommendation: (1) for the workshop, (2) if a reviewer pushes, (3) only for the journal
version.
