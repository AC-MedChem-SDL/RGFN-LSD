# Benchmarks

Comparing hub-batching against other ways of choosing what to make.

There are two very different things people mean by that, and they cost very different amounts.
**Read this section before installing anything** — most people want the first one, and it needs
nothing beyond what you already have.

---

## A. "I have my own way of picking molecules. Is it better?"

No extra installs. No conda environments. Runs on a laptop.

The pricing seam is a pair of dataclasses. Your selection method emits an **ordered** library;
an evaluator prices it. Neither knows anything about the other.

```python
from hubbatching.eval import CountOnceEvaluator, LibrarySet

library = LibrarySet(
    smiles=[...],        # your chosen molecules, IN SELECTION ORDER
    rewards=[...],
    routes={...},        # each molecule's synthesis route
    provenance={"method": "my_selector", "target": "seh", "gate": 5.68},
)
result = CountOnceEvaluator().score(library)
print(result.total_reactions)
```

**The ordering is the point.** An evaluator prices *prefixes*, so one selection yields the whole
(molecules, reactions) curve rather than a single number — and the reaction-budget readout is a
lookup into that curve rather than a separate run.

Selection and evaluation are decoupled deliberately: your method *tries* to be cheap using
whatever logic it likes; the evaluator *independently* prices whatever set it actually chose. It
never assumes the set is reward-optimal or reaction-minimal.

To compare against us on identical footing, run `hubbatching campaign` on the same enumeration
with the same gate and the same diversity cutoff, and price both with the same evaluator. That
is the whole protocol.

### Writing your own evaluator

```python
class MyEvaluator:
    name = "my_pricer"

    def score(self, library: LibrarySet) -> EvaluationResult:
        ...
```

Anything structurally matching `hubbatching.eval.Evaluator` works. `hubbatching.eval.base`
imports nothing heavy on purpose, so an evaluator loads in any environment.

---

## B. "I want to re-run the published head-to-head."

This one is heavy, and it is for verifying our numbers rather than for using the method. It
needs several mutually incompatible conda environments and a MILP solver.

```bash
setup/fetch_sparrow.sh          # the competing planner
setup/fetch_aizynth.sh          # retrosynthesis, for route-less generators
setup/fetch_generators.sh       # the other entrants
```

Then the evaluators in `hubbatching.eval` reach the workers here by **subprocess** — never by
import, because no two of these co-import:

| worker | environment | what it does |
|---|---|---|
| `workers/sparrow_worker.py` | `sparrow` | the MILP that selects a library over a shared reaction network |
| `workers/route_recovery_worker.py` | `aizynth` | recovers routes for generators that log none |
| `workers/multiaiz_worker.py` | `aizynth` | broader route discovery feeding the same MILP |

### Three readings of cost, one seam

| | what it does | applies to |
|---|---|---|
| **from-scratch** (headline) | re-route **every** molecule independently, ignoring logged routes | everything, including route-less generators |
| **native-route** | price the generator's own by-construction routes | reaction-grounded generators only |
| **count-once** | the strategy's own DAG estimate — the campaign metric | reaction DAGs only |

All three are the same `Evaluator` interface, so `--evaluator {count_once,sparrow,multiaiz}`
swaps them. From-scratch is the headline because it is the one unit that applies to every
method: a route-less generator has no DAG to count, so count-once cannot score it, and a
comparison that silently used different units for different arms would not be a comparison.

---

## Reading a competitor's number honestly

Four rules. Each exists because breaking it produced a wrong number here first.

**Check whether the budget actually bound.** A cell is comparable only if both arms were
*budget-binding* — qualifying candidates remained and the next one did not fit. An arm that ran
out of material did not choose to stop, and reporting it as "N molecules at R reactions" implies
it could have spent R and declined.

**Check `time_capped` before calling a MILP result optimal.** A solver reports `Optimal` for
whatever it happens to hold when a time limit stops it. At a two-hour cap, 25 of 36 points in
one sweep were still unconverged. A truncated row is a **lower bound on the competitor**, which
flatters us — so it must never be quoted as their result.

**Do not trim a solved selection to a smaller budget.** That is exact for greedy selection,
which is prefix-stable, and **not** exact for a jointly-optimised MILP: trimming gives a
feasible but suboptimal set, i.e. a lower bound on the competitor. Re-solve.

**Give competitors the larger catalogue when there is a choice.** Free purchasable leaves are
their best case, not a confound. A comparison you win against a hobbled opponent is not worth
running.

---

## What the competitor gets, and why it is fair

The comparison is deliberately not rigged in an easy direction:

- The competing planner optimises jointly over shared intermediates, which is a strictly harder
  thing to beat than per-molecule retrosynthesis.
- Competitors are given the larger public building-block catalogue.
- Where a competitor's pool has been enlarged or its checkpoints budget-matched, the result
  moved **in its favour** and the new number is the one quoted.

If you find a configuration where a competitor does better than we report, that is a result and
we would rather hear it. The rules above are there to make such a finding legible rather than
arguable.
