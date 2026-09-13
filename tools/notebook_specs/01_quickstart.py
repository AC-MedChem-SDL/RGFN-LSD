TITLE = "Quickstart"
SUMMARY = "Run both strategies on the bundled toy data and read the budget answer."

CELLS = [
    (
        "md",
        """
# Quickstart: how many molecules does 30 reactions buy?

This notebook runs the whole method on the bundled toy dataset — 432 real molecules, built by
real RDKit chemistry — and answers the question the method exists to answer.

**No GPU, no downloads, no configuration.** A few seconds end to end.

### What is real here, and what is not

The molecules, the reaction templates, the products and the synthesis routes are **real**:
RDKit actually fired every template. The *reward* is RDKit's QED standing in for a
target-specific oracle, and the policy log-probabilities were generated from a self-consistent
model of a trained GFlowNet rather than recovered from one.

So the numbers below illustrate the **mechanism**. They are not a result, and they are not the
paper's numbers — for those, run `reproduce/`.
""",
    ),
    (
        "py",
        """
from pathlib import Path
import json, csv

from hubbatching.paths import repo_root

TOY = repo_root() / "examples" / "toy"
meta = json.loads((TOY / "meta.json").read_text())
meta
""",
    ),
    (
        "md",
        """
## 1. What do we have?

Before running anything long, ask what the data can support. The check that matters is
`routes.json`: without it everything still runs and prints plausible numbers, but you cannot
produce a bench plan — and routes are **not recoverable** after sampling ends.
""",
    ),
    (
        "py",
        """
from hubbatching.adapters.file_adapter import FileAdapter

adapter = FileAdapter(str(TOY))
report = adapter.validate()

for key in ("can_rank_hubs", "can_hub_batch", "can_export_bench_plan"):
    print(f"{'yes' if report[key] else 'NO ':>4}  {key}")
print()
print("blockers:", report["blockers"] or "none")
""",
    ),
    (
        "md",
        """
## 2. The flow field

A *hub* is a pre-terminal intermediate — something you could put in a flask — from which several
distinct high-reward products are one reaction away.

For each hub, every observed terminal child gives an independent estimate of the same quantity
`F(h)`:

$$\\log \\hat{F}(h; x) = \\log R(x) + \\log P_B(h|x) - \\log P_F(x|h) - \\log P_F(\\text{stop}|x)$$

Under a converged model those estimates agree. Their **median** is the hub's flow estimate;
their **variance** is `U(h)`, the flow-matching residual.
""",
    ),
    (
        "py",
        """
from hubbatching.dag import LiteHubDAG

sample = adapter.sample_flow_records()
dag = LiteHubDAG.from_records(
    sample.records,
    total_trajectories=sample.n_trajectories,
    log_z=sample.log_z,
    higher_is_better=sample.higher_is_better,
)

print(f"{len(dag)} hubs from {len(sample.records)} observed transitions\\n")
for hub in list(dag.hubs_iter())[:5]:
    print(f"  logF={hub.log_flow_consensus():6.2f}  U(h)={hub.uncertainty():6.3f}  "
          f"{hub.n_children:2d} children   {hub.key}")
""",
    ),
    (
        "md",
        """
## 3. Rank the hubs

A strategy scores hubs; the base class handles eligibility gating and sorting. `highest_flow`
ranks by the median estimate above.

The resulting **order is the strategy** — hub-batching walks it top to bottom.
""",
    ),
    (
        "py",
        """
from hubbatching.hubs.registry import available, get_hub_strategy

print("available strategies:", available(), "\\n")

ranked = get_hub_strategy("highest_flow").rank(dag)
for i, hub in enumerate(ranked[:8], 1):
    print(f"{i:2d}. logF={hub.log_flow_consensus():6.2f}  {hub.n_children:2d} children  {hub.key}")
""",
    ),
    (
        "md",
        """
## 4. Run both strategies

Two strategies, identical chemistry, identical gate, identical diversity rule. **Only the
chooser differs.**

- **best-candidate** — take the highest-scoring molecules one at a time. This is what a
  generator is normally used for, and it is the honest thing to beat.
- **hub-batching** — walk the ranked hubs, build each scaffold once, diversify off it.

Both are priced by the *same* count-once cost model, and best-candidate is credited for
scaffolds its picks happen to share. That credit matters: without it the margin below would
look considerably larger than it is.
""",
    ),
    (
        "py",
        """
from hubbatching.campaign import BestCandidateStrategy, Candidate, HubBatchingStrategy

GATE   = 0.80   # QED: the toy reward
CUTOFF = 0.50   # Tanimoto: closer than this and it is not a new molecule
BUDGET = 30     # reactions

comps = json.loads((TOY / "compositions.json").read_text())
enum_hubs = adapter.enumerated_hubs()

# Rebuild the candidate pool the sampled run saw, with each molecule's parent hubs attached so
# best-candidate can be credited for accidental sharing.
best, parents = {}, {}
for r in sample.records:
    if r.child_key not in best or r.reward > best[r.child_key]:
        best[r.child_key] = r.reward
    parents.setdefault(r.child_key, set()).add(r.hub_key)

pool = [
    Candidate(
        smiles=s, reward=rw,
        num_reactions=comps.get(s, {}).get("num_reactions", 1),
        promoted=tuple(comps.get(s, {}).get("promoted", ())),
        parents=tuple(sorted(parents.get(s, ()))),
    )
    for s, rw in best.items()
]
print(f"{len(pool)} candidate molecules, {len(enum_hubs)} enumerated hubs")
""",
    ),
    (
        "py",
        """
common = dict(reward_threshold=GATE, similarity=CUTOFF, higher_is_better=True)

bc = BestCandidateStrategy(pool, None, hub_compositions=comps, **common).run(
    budget=("reactions", BUDGET))
hb = HubBatchingStrategy(enum_hubs, None, **common).run(budget=("reactions", BUDGET))

print(f"At a fixed budget of {BUDGET} reactions:\\n")
print(f"  best-candidate   {len(bc.accepted):3d} distinct molecules  "
      f"({bc.total_reactions} reactions used)")
print(f"  hub-batching     {len(hb.accepted):3d} distinct molecules  "
      f"({hb.total_reactions} reactions used)")
print(f"\\n  ratio  {len(hb.accepted) / max(len(bc.accepted), 1):.2f}x")
""",
    ),
    (
        "md",
        """
### Read that carefully

A budget comparison is only like-for-like if **both arms actually spent the budget**. If one ran
out of qualifying molecules it did not *choose* to stop, and reporting it as "N molecules at R
reactions" would imply it could have spent R and declined.

So always check the stop reason alongside the count.
""",
    ),
    (
        "py",
        """
for name, res in (("best-candidate", bc), ("hub-batching", hb)):
    print(f"  {name:<16} stop_reason={res.stop_reason:<16} used={res.total_reactions}")
""",
    ),
    (
        "md",
        """
## 5. The whole curve

One run gives the entire modes-versus-reactions curve, not just one point — so the budget
readout is a lookup rather than a separate experiment.
""",
    ),
    (
        "py",
        """
import matplotlib.pyplot as plt

full_bc = BestCandidateStrategy(pool, None, hub_compositions=comps, **common).run()
full_hb = HubBatchingStrategy(enum_hubs, None, **common).run()

def curve(result):
    return ([p.cum_reactions for p in result.accepted],
            [p.cum_modes for p in result.accepted])

fig, ax = plt.subplots(figsize=(6.5, 4.2))
for result, label, color in ((full_bc, "best-candidate", "#888"),
                             (full_hb, "hub-batching", "#0b7285")):
    xs, ys = curve(result)
    ax.step(xs, ys, where="post", label=label, color=color, lw=2)

ax.axvline(BUDGET, ls=":", color="#c92a2a", lw=1.2)
ax.annotate(f"{BUDGET} reactions", (BUDGET, 2), color="#c92a2a",
            fontsize=9, rotation=90, va="bottom", ha="right")
ax.set_xlabel("reactions spent"); ax.set_ylabel("distinct high-reward molecules")
ax.set_title("More molecules per reaction (toy data — mechanism, not a result)", fontsize=10)
ax.legend(frameon=False); ax.spines[["top", "right"]].set_visible(False)
plt.tight_layout()
""",
    ),
    (
        "md",
        """
## Where next

| | |
|---|---|
| `02_bring_your_own_strategy` | write a hub-selection strategy and compare it |
| `03_bring_your_own_generator` | run this on *your* model's output |
| `04_bring_your_own_reward` | swap QED for your own scorer |
| `05_bring_your_own_chemistry` | your building blocks, your reaction templates |
| `06_export_a_bench_plan` | buy lists, protocols, reaction schemes |

Or from a shell:

```bash
hubbatching demo             # everything above, narrated
hubbatching sweep  --help    # how the margin moves with the diversity cutoff
hubbatching inspect <dir>    # can my data support what I want?
```
""",
    ),
]
