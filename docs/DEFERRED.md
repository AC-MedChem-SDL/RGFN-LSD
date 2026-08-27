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

## Table 1's competitor was trained at a much larger budget

`OLDBUDGET_` on the S3-GFN pool directories means what it says: those checkpoints were
trained with a **much larger iteration budget** than the generators we compare them
against. Training has since been standardised to comparable budgets across models.

**Why it is still what Table 1 uses.** It is the only S3-GFN sEH pool that exists with
retrosynthesis completed. Newer, budget-matched S3-GFN checkpoints exist but have not
been routed, and without routes there is nothing for SPARROW to select over.

**Direction of the bias, which is the part that matters.** A competitor trained *longer*
than us is a competitor at its best. So the current numbers — 3.42× against
SPARROW-selects, 2.16× against greedy selection — are measured against a stronger
opponent than a budget-matched comparison would give, and are therefore **conservative**.
That is the right direction for a bias to run, and it should be stated in the caption
rather than discovered by a reviewer.

**What refreshing needs:** retrosynthesis on the budget-matched S3-GFN checkpoints, then
re-running `sparrow_select_frontier.py` for both the `--selection sparrow` and
`--selection greedy` arms. The harvest and both readouts pick the new numbers up with no
code change.
