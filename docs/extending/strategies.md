# Bring your own selection strategy

Hub-batching is really three nested choices, and all three are swappable independently:

1. **Which hubs, in what order?** — `hubbatching.hubs`
2. **Which of a chosen hub's children do we offer?** — `hubbatching.child_select`
3. **Which offered molecules count as genuinely new?** — `hubbatching.mode_select`

Most new ideas are a change to exactly one of them. Changing one does not require touching the
other two, or the cost model, or anything generator-specific.

---

## 1. A new hub-selection strategy

Subclass, implement `score`, register. The base class handles eligibility gating and sorting.

```python
from hubbatching.hubs.base import HubSelectionStrategy
from hubbatching.hubs.registry import register

@register
class MostChildrenStrategy(HubSelectionStrategy):
    """Rank hubs purely by how many distinct terminal children were observed."""

    name = "most_children"          # the key the CLI and configs use

    def score(self, hub, dag) -> float:
        return float(hub.n_children)
```

That is the whole contract. `score` returns a float where **higher is better**, and `nan` sorts
to the tail. Then:

```bash
hubbatching pick-hubs --records sample/records.csv --out hubs.csv --order flow_desc
```

…or in Python:

```python
from hubbatching.hubs.registry import get_hub_strategy
ranked = get_hub_strategy("most_children").rank(dag)
```

### What your `score` can read

Strategies are **protocol-pure**: they read only the duck-typed fields in
`hubbatching.records`, so the same strategy works on the lightweight in-loop DAG and on a
richer persisted one. On `hub`:

| | |
|---|---|
| `hub.key` | canonical, stereo-stripped SMILES |
| `hub.depth` | minimum reactions to build it |
| `hub.children` | the distinct terminal children observed |
| `hub.n_children` | how many |
| `hub.visit_count` | trajectories through it (needs `visit_counts.json`) |
| `hub.child_log_flows()` | per-child `log F̂(h ; x)` |
| `hub.log_flow_consensus()` | the median of those — the hub's single flow estimate |
| `hub.log_flow_terminating()` | logsumexp of them — total flow terminating one step downstream |
| `hub.uncertainty()` | variance of them — the flow-matching residual |
| `hub.best_reward(higher_is_better)` | best child reward |

And on `dag`: `dag.log_z`, `dag.total_trajectories`, `dag.higher_is_better`,
`dag.log_visitation(hub)`.

### Do the maths in `hubbatching.flow`, not in your strategy

If you need a flow quantity, take it from `hubbatching.flow`. Every shipped strategy does, and
the reason is that the aggregation choices are subtle and already argued: estimates are
heavy-tailed, so everything is in log space; the consensus statistic is the **median** rather
than the mean, because one outlying child should not move a hub's rank. A strategy that
re-derives these gets to be subtly different from every other strategy for no stated reason.

### Gating

The base class drops ineligible hubs before scoring:

```python
MyStrategy(min_children=2, min_effective_n=3)
```

`min_children` because a one-child hub is not a *diversifying* neighbourhood, and
`min_effective_n` because a flow estimate from two children is far noisier than one from twenty
and rankings that flip on resampling are not rankings. Override `is_eligible` for something
more specific.

### What ships

| name | ranks by |
|---|---|
| `highest_flow` | median per-child `log F̂(h)` — the default |
| `highest_terminating_flow` | logsumexp of them; rewards hubs many good products terminate from |
| `most_modes` | distinct clusters among a hub's children |
| `parent_of_topk` | the reward of a hub's best child |
| `highest_visitation` | empirical trajectory visitation — reward-free |
| `lowest_uncertainty` | smallest flow-matching residual |
| `ucb` | flow plus an uncertainty bonus, for active learning |

### The other half of the strategy: order

A subtlety worth knowing before you write a scorer. `pick-hubs` exposes two orthogonal knobs,
and an ablation over them found that **the reward pre-filter is not load-bearing** while the
*order* very much is — reversing or randomising it costs 1.5–1.7×:

```bash
hubbatching pick-hubs --pool {topk_candidates,all} --order {flow_desc,flow_asc,random,candidate_reward}
```

`--restrict-to hubs.csv` applies an order to a *fixed* hub set, which separates "did the ranking
pick better hubs?" from "did it pick a better order?" at zero enumeration cost. If you are
claiming your strategy is better, this is the control that makes the claim mean something.

---

## 2. A new child policy

Given a chosen hub, which of its children get offered to the mode selector, and in what order?

```python
from hubbatching.child_select import ChildSelectionPolicy, _POLICIES

class SmallestFirstPolicy(ChildSelectionPolicy):
    name = "smallest_first"

    def order(self, children, *, higher_is_better=True, cost_table=None, available=None):
        return sorted(children, key=lambda c: len(c.smiles))

_POLICIES[SmallestFirstPolicy.name] = SmallestFirstPolicy
```

Each child exposes `.smiles`, `.reward`, and `.added_promoted` (dynamic-library fragments
attached in the final reaction — empty when every block is purchasable).

Two ship. `reward` is reward-first, keep everything, no cost awareness — the control.
`free_frag` keeps only children whose final reaction attaches an **already-available** fragment,
so every kept child costs exactly one marginal reaction. With a pre-built fragment stock
(`HubBatchingStrategy(prebuilt_fragments=...)`) that becomes pre-select-K: pay for K
high-value fragments up front, then fill for free. K trades a few fragment builds against far
fewer oracle calls at roughly constant reactions per molecule.

---

## 3. A new mode definition

What counts as a genuinely new molecule? The default gates on reward and then rejects anything
within a Tanimoto cutoff of something already accepted.

```python
from hubbatching.mode_select import ModeSelector

class MyModeSelector(ModeSelector):
    def offer(self, smiles: str, reward: float) -> bool:
        ...  # True if this is a new mode; record it if so
```

Pass it via `mode_selector_factory=` to either strategy.

**Both halves are load-bearing, and dropping either flatters you.** An ablation found that
removing the reward gate or the diversity filter makes the headline look ~1.13× better while
costing 9.8×, 6.8× and 29× more per *qualified* molecule — the library collapses and the metric
stops noticing. If you redefine a mode, report both arms under your definition, and say what it
does to the baseline as well as to your method.

---

## Comparing fairly

Whatever you change, the comparison is only meaningful if everything else is held fixed. Both
arms must read the same enumeration, the same gate, the same diversity cutoff, and the same cost
model — the only thing that differs is the chooser. `hubbatching campaign` does this by
construction, which is the main reason to run your idea through it rather than scoring a
selection by hand.

If you want your strategy priced against ours on a neutral evaluator, see
[`benchmarks/README.md`](../../benchmarks/README.md): emit a `LibrarySet` and any `Evaluator`
will score it.
