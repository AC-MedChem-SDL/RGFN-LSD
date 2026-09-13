# The method

What hub-batching is, what it reads, and the arithmetic that prices the result. Source
docstrings throughout `src/hubbatching/` cite this file by section.

---

## 1. The idea

Labs do not make one molecule. They make a library, and the cost of a library is not the sum of
its molecules' costs — because molecules that share an intermediate can be made from it
together. One flask of a shared scaffold, then a plate of one-step diversifications, is a
fundamentally cheaper object than the same number of independently-assembled compounds. Chemists
already know this; it is why late-stage diversification exists.

The claim here is that **a trained reaction-grounded GFlowNet has already worked out which
intermediates to batch around**, and you can read it off without retraining, without changing
the reward, and without asking the model anything it was not already trained to answer.

Concretely: a *hub* is a pre-terminal state — a real, makeable intermediate — from which many
distinct high-reward products are one reaction away. The flow the model assigns to that state is
an estimate of how much good chemistry lies downstream of it. Rank hubs by that, enumerate the
good ones, and assemble a library greedily under a budget.

The comparison throughout is against **best-candidate**: take the highest-scoring molecules one
at a time, subject to the same diversity constraint. That is what a generator is normally used
for, and it is the honest thing to beat.

---

## 2. Flow recovery

For a hub `h` and a terminal product `x` reachable from `h` by one reaction and then `stop`,
detailed balance at that edge, rearranged, gives

```
F̂(h ; x) = R(x) · P_B(h | x) / ( P_F(x | h) · P_F(stop | x) )
```

This is a **lemma**, not a theorem — a one-line rearrangement of a known condition. It is worth
stating precisely because every term in it is load-bearing:

| term | what it is | what goes wrong without it |
|---|---|---|
| `R(x)` | reward at the terminal product | reward is the only source term; there is no estimate without it |
| `P_B(h \| x)` | backward probability of undoing the final reaction | must be the model's **own trained** policy — a uniform stand-in measures something else |
| `P_F(x \| h)` | forward probability of the diversifying reaction | for phased models, the product of the micro-step softmaxes composing one molecule→molecule move |
| `P_F(stop \| x)` | the terminating factor | equals 1 only for a true leaf; dropping it biases `F̂` **upward** for products eager to react further |

Everything is computed in **log space**:

```
log F̂(h ; x) = log R(x) + log P_B(h|x) − log P_F(x|h) − log P_F(stop|x)
```

Log space is not a numerical convenience, it is required: the estimates are heavy-tailed, and a
raw-space variance is dominated by a single outlier.

`hubbatching.flow` implements this and nothing else. It is pure — it takes already-extracted
scalars and knows nothing about any model's internals.

### Aggregating to one number per hub

Each terminal child independently estimates the *same* `F(h)`. Under a converged model they
agree. Two aggregations are used, for two different questions:

- **`consensus_log_flow`** — the **median** across children. The hub's single flow estimate, and
  what `highest_flow` ranks by. Median rather than mean, for the same heavy-tail reason.
- **`total_terminating_log_flow`** — the `logsumexp`. Total flow terminating one reaction
  downstream, which rewards *diversification parents* — hubs many distinct good products
  terminate from — rather than good general building blocks.

### The uncertainty signal

```
U(h) = Var_i [ log F̂(h ; x_i) ]
```

The local flow-matching residual: an epistemic-uncertainty signal with no ensemble, no dropout,
and no second model. It is shipped as a hub-ranking strategy and as a diagnostic.

**A caveat that a careful reader should have.** `U(h)` as defined is dominated by the variance
of `log P_F`, and it is undefined for a hub with fewer than two finite estimates — which is most
hubs in a typical sample. Treat it as a diagnostic; a `P_F`-weighted variant is the better
formulation and is not what ships.

### The reward-free cross-check

A trained GFlowNet visits states in proportion to their flow, so the empirical fraction of
trajectories passing through `h` is a **reward-free** estimate of `F(h)/Z`. Adding `log Z` puts
it on the same absolute scale as the identity above.

The two estimates share no terms. Disagreement between them, after the `log Z` shift, is a
direct test of whether trajectory balance holds — which matters for any model whose backward
policy has been modified, for instance by cost guidance.

---

## 3. Selection

Three nested choices, each independently swappable
([`docs/extending/strategies.md`](extending/strategies.md)):

**Which hubs, in what order** (`hubbatching.hubs`). A strategy scores hubs; the base class gates
and sorts. The resulting order *is* the strategy — hub-batching walks it top to bottom.

An ablation over the two knobs found that the reward pre-filter is **not** load-bearing (taking
every observed hub and letting flow do the selecting is marginally better), while the order very
much is: reversing or randomising it costs 1.5–1.7×. Good orderings agree with each other within
about 9%, which is the more interesting finding — the flow field picks the *neighbourhood*, not
the precise rank.

**Which children** (`hubbatching.child_select`). `reward` keeps everything reward-first with no
cost awareness — the control. `free_frag` keeps only children needing no new fragment built, so
each costs exactly one marginal reaction.

**What counts as new** (`hubbatching.mode_select`). Reward gate, then a Tanimoto diversity
filter against everything already accepted.

Both halves of that last definition are load-bearing. Dropping either makes the headline look
~1.13× better while costing 9.8×, 6.8× and 29× more per *qualified* molecule — the library
collapses and the metric stops noticing.

---

## 4. Cost

One model, applied identically to both arms. This is the part most worth reading carefully,
because the obvious way to compute it is wrong in our favour.

A library's reaction cost decomposes into two **count-once** parts:

1. **Assembly couplings** — the steps that join pre-built pieces. Per molecule,
   `couplings = num_reactions − Σ(nested build cost of every promoted fragment it attaches)`.
   A shared hub has its couplings charged **once**, and each molecule descending from it then
   pays only its marginal couplings.
2. **Promoted-fragment builds** — each distinct dynamic-library fragment is built and charged
   **exactly once** across the campaign, closed under its own recipes (a promoted fragment built
   from another promoted fragment pulls the inner one in).

Both arms amortize both parts identically. The **only** difference is the selection.

### Best-candidate gets credit for accidental sharing

Hub-batching shares scaffolds by design. Best-candidate shares them *accidentally*, whenever its
top-reward picks happen to descend from a common parent — and it is credited for that, via a
swappable assignment policy.

This is not a courtesy. Without it, an early version of this analysis reported roughly a 2×
advantage that was mostly a fragment **double-count**: the generator's `num_reactions` was
already fully nested, and the campaign was adding the promoted-fragment builds a second time.
The corrected, fair number is about 1.13× on that comparison. If you are extending this, keep
the credit; the honest number is the one worth having.

### Compute is a third axis, and it is measured

Reactions are bench cost. `reward_gen_calls` is a count of oracle invocations. Neither is
wall-clock, so wall-clock is measured separately and per component — never modelled.

The interesting part is that the split **flips** with the cost of the reward. For a millisecond
surrogate, enumeration is 64–79% of the compute bill and reward evaluation ~5%; for real GPU
docking, reward evaluation is 87.5–99.7%. So the more expensive the oracle, the smaller
hub-batching's relative overhead — which is the regime a real campaign runs in.

---

## 5. Reading the result

**The primary readout is a fixed REACTION budget.**

> *"I have 100 reactions. How many distinct high-reward molecules do I get?"*

Not "I need 100 molecules, what do they cost?" Both are read off the same ordering, so this is a
reporting convention rather than a different experiment — but it is the constraint a chemist
actually has, and ~100 reactions is about one plate.

It also behaves better. A mode target simply **excludes** any pool that cannot reach it. A
reaction budget always yields a number — but the number is only *comparable* if the budget was
actually spent, so every cell must be classified and reported with the reactions it used:

- **budget-binding** — qualifying candidates remain, but the cheapest next molecule does not
  fit. The only like-for-like case.
- **pool-exhausted** — nothing qualifying is left. Reporting this as "N molecules at R
  reactions" implies the arm could have spent R and declined, which is false. Flag it; never
  count it as a win or a loss on cost.
- **solver-truncated** — a competitor's optimiser hit a time limit. That is *compute*-limited,
  an entirely different claim, and conflating it with pool-exhausted reads a solver failure as a
  property of the generator. A truncated row is a lower bound on the competitor, i.e. it
  flatters us.

Report `n_modes_available` alongside, which separates genuine *collapse* (only 18 distinct
molecules exist in the pool) from mere *redundancy* (171 distinct among 459 routed).

### Thresholds

Every gate is the 5%-false-positive point on its own oracle's actives-versus-**property-matched**
decoys set. One rule covers every target instead of four separately-argued numbers.

Two disciplines go with it. **Both arms are always measured at the same threshold** — applying
different ones is the exact fault an appendix would exist to disprove. And where a threshold is
non-binding for one arm's pool and binding for the other's, say so: that is a sharper and more
accurate statement than calling it "conservative".

---

## 6. What this does not claim

- **Not a retrosynthesis claim.** A route here is the *logged assembly route* — the sequence of
  reactions the model actually used, grounded in templates that fired. A chemist may well know a
  shorter one.
- **Not a yield model.** The budget counts reactions, not successful reactions. A four-step
  route at 75% per step delivers about a third of what a one-step route does, and the headline
  metric does not notice.
- **Not an activity claim.** A gate is calibrated separation between actives and decoys on a
  given oracle. It is a statement about the oracle, not about binding.
- **Not conditions.** Connectivity-level plans. No solvents, temperatures, or stereochemical
  outcomes.

---

## Where the code is

| section | module |
|---|---|
| 2 flow recovery | `hubbatching.flow`, `hubbatching.uncertainty` |
| 2 aggregation | `hubbatching.dag`, `hubbatching.records` |
| 3 hub selection | `hubbatching.hubs` |
| 3 child / mode selection | `hubbatching.child_select`, `hubbatching.mode_select` |
| 3 the greedy walk | `hubbatching.campaign` |
| 4 cost | `hubbatching.cost` (standard library only) |
| 4 compute | `hubbatching.compute_time` |
| 5 pricing seam | `hubbatching.eval` |
| model-specific | `hubbatching.adapters` — the only place torch or rgfn is imported |
