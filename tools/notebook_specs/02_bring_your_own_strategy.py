TITLE = "Bring your own selection strategy"
SUMMARY = (
    "Write a hub-selection strategy, register it, and compare it fairly against the shipped ones."
)

CELLS = [
    (
        "md",
        """
# Bring your own selection strategy

Hub-batching is three nested choices, and all three are swappable independently:

1. **Which hubs, in what order?** — `hubbatching.hubs`
2. **Which of a chosen hub's children do we offer?** — `hubbatching.child_select`
3. **Which offered molecules count as genuinely new?** — `hubbatching.mode_select`

Most new ideas are a change to exactly one. This notebook writes a new one of each and measures
whether it helped.

Reference: [`docs/extending/strategies.md`](../docs/extending/strategies.md).
""",
    ),
    (
        "py",
        """
import json
from hubbatching.paths import repo_root
from hubbatching.adapters.file_adapter import FileAdapter
from hubbatching.dag import LiteHubDAG

TOY = repo_root() / "examples" / "toy"
adapter = FileAdapter(str(TOY))
sample = adapter.sample_flow_records()
dag = LiteHubDAG.from_records(
    sample.records, total_trajectories=sample.n_trajectories,
    log_z=sample.log_z, higher_is_better=sample.higher_is_better,
)
print(f"{len(dag)} hubs")
""",
    ),
    (
        "md",
        """
## 1. A new hub-selection strategy

Subclass, implement `score`, register. That is the whole contract. `score` returns a float where
**higher is better**; `nan` sorts to the tail. The base class does eligibility gating and
sorting.
""",
    ),
    (
        "py",
        """
from hubbatching.hubs.base import HubSelectionStrategy
from hubbatching.hubs.registry import register, get_hub_strategy, available

@register
class FlowPerReactionStrategy(HubSelectionStrategy):
    \"\"\"Flow per unit of build cost, rather than flow alone.

    The intuition: a deep hub has to earn its construction. A hub one step from stock that
    yields eight good products may be worth more than a four-step hub yielding ten.
    \"\"\"

    name = "flow_per_reaction"

    def score(self, hub, dag) -> float:
        return hub.log_flow_consensus() / max(hub.depth, 1)

print(available())
""",
    ),
    (
        "py",
        """
for name in ("highest_flow", "flow_per_reaction", "parent_of_topk"):
    ranked = get_hub_strategy(name).rank(dag)
    top = ", ".join(h.key[:28] for h in ranked[:2])
    print(f"{name:<20} top 2: {top}")
""",
    ),
    (
        "md",
        """
### Fields your `score` can read

Strategies are **protocol-pure** — they read only duck-typed fields, so the same strategy works
on the lightweight in-loop DAG and on a richer persisted one.
""",
    ),
    (
        "py",
        """
hub = next(iter(dag.hubs_iter()))
for attr in ("key", "depth", "n_children", "visit_count"):
    print(f"  hub.{attr:<14} = {getattr(hub, attr)!r}")
for meth in ("log_flow_consensus", "log_flow_terminating", "uncertainty", "effective_n"):
    print(f"  hub.{meth + '()':<22} = {getattr(hub, meth)():.4f}")
""",
    ),
    (
        "md",
        """
### Do the maths in `hubbatching.flow`

If you need a flow quantity, take it from `hubbatching.flow`. Every shipped strategy does, and
the reason is that the aggregation choices are already argued: the estimates are heavy-tailed,
so everything is in log space, and the consensus statistic is the **median** rather than the
mean so one outlying child cannot move a hub's rank.

A strategy that re-derives these gets to be subtly different from every other strategy for no
stated reason.
""",
    ),
    (
        "md",
        """
## 2. A new child policy

Given a chosen hub, which of its children get offered, and in what order?
""",
    ),
    (
        "py",
        """
from hubbatching.child_select import ChildSelectionPolicy, _POLICIES, available_child_policies

class SmallestFirstPolicy(ChildSelectionPolicy):
    \"\"\"Prefer smaller products -- a crude stand-in for a property filter.\"\"\"

    name = "smallest_first"

    def order(self, children, *, higher_is_better=True, cost_table=None, available=None):
        return sorted(children, key=lambda c: (len(c.smiles), -c.reward))

_POLICIES[SmallestFirstPolicy.name] = SmallestFirstPolicy
print(available_child_policies())
""",
    ),
    (
        "md",
        """
## 3. Did it actually help?

The comparison is only meaningful if **everything else is held fixed**: same enumeration, same
gate, same diversity cutoff, same cost model. Only the chooser differs.
""",
    ),
    (
        "py",
        """
from hubbatching.campaign import HubBatchingStrategy
from hubbatching.child_select import make_child_policy

GATE, CUTOFF, BUDGET = 0.80, 0.50, 30
enum_hubs = adapter.enumerated_hubs()

def run(child_policy_name):
    return HubBatchingStrategy(
        enum_hubs, None,
        reward_threshold=GATE, similarity=CUTOFF, higher_is_better=True,
        child_policy=make_child_policy(child_policy_name),
    ).run(budget=("reactions", BUDGET))

for policy in ("reward", "smallest_first"):
    res = run(policy)
    print(f"  {policy:<16} {len(res.accepted):3d} molecules   "
          f"{res.total_reactions:3d} reactions   stop={res.stop_reason}")
""",
    ),
    (
        "md",
        """
## 4. The control that makes a claim mean something

An ablation over hub *ordering* found something worth knowing before you claim your scorer is
better: the reward pre-filter turns out **not** to be load-bearing, while the order very much is
— reversing or randomising it costs 1.5–1.7×. But good orderings agree with each other within
about 9%.

The implication: the flow field picks the *neighbourhood*, not the precise rank. So if your
strategy beats `highest_flow` by a few percent, the honest question is whether it picked better
hubs or merely a better order over the same ones.

`pick-hubs --restrict-to` separates those at zero enumeration cost — it applies your order to a
**fixed** hub set:

```bash
hubbatching pick-hubs --records examples/toy/records.csv --out mine.csv \\
    --pool all --order flow_desc
hubbatching pick-hubs --records examples/toy/records.csv --out reordered.csv \\
    --restrict-to mine.csv --order random --seed 0
```

Compare against `random` as your floor. If your strategy cannot beat a shuffle of its own hub
set, it is selecting rather than ordering — which is a fine result, but a different one.
""",
    ),
    (
        "md",
        """
## 5. Redefining a mode

A *mode* is a molecule that clears the reward gate **and** is not within a Tanimoto cutoff of
anything already accepted.

**Both halves are load-bearing, and dropping either flatters you.** Removing the reward gate or
the diversity filter makes the headline look ~1.13× better while costing 9.8×, 6.8× and 29× more
per *qualified* molecule: the library collapses and the metric stops noticing.

So if you redefine a mode, report both arms under your definition, and say what it does to the
baseline as well as to your method.
""",
    ),
    (
        "py",
        """
from hubbatching.mode_select import DiverseThresholdModeSelector

for cutoff in (0.3, 0.5, 0.7, 0.9):
    res = HubBatchingStrategy(
        enum_hubs, None, reward_threshold=GATE, similarity=cutoff, higher_is_better=True,
    ).run(budget=("reactions", BUDGET))
    print(f"  cutoff {cutoff:.1f}  ->  {len(res.accepted):3d} molecules at {BUDGET} reactions")
""",
    ),
    (
        "md",
        """
A looser cutoff admits near-duplicates and the count rises. That is not the method improving —
it is the definition of "distinct" loosening. Whatever cutoff you choose, both arms get the
same one, and report the sweep rather than the single point.

To get your strategy priced against ours on a neutral evaluator rather than on our cost model,
see [`benchmarks/README.md`](../benchmarks/README.md).
""",
    ),
]
