TITLE = "Bring your own reward"
SUMMARY = "Swap the scorer and the gate, and see what each does to the library."

CELLS = [
    (
        "md",
        """
# Bring your own reward

A reward enters hub-batching at two points, and they are not the same point:

| | where | what it costs |
|---|---|---|
| **During sampling** | your generator's loop, written into `records.csv` | already paid |
| **During enumeration** | scoring each selected hub's children | **this is the bill** |

Hub-batching never calls an oracle itself. It reads a number already attached to a molecule.
That is why there is no oracle abstraction to implement: you score, you write the number down.

The consequence worth internalising: **the enumeration pass is where your oracle budget goes.**
Selecting 40 molecules might mean scoring twenty thousand enumerated children.

Reference: [`docs/extending/rewards.md`](../docs/extending/rewards.md).
""",
    ),
    (
        "py",
        """
import json
from hubbatching.paths import repo_root
from hubbatching.adapters.file_adapter import FileAdapter

TOY = repo_root() / "examples" / "toy"
adapter = FileAdapter(str(TOY))
enum_hubs = adapter.enumerated_hubs()

meta = json.loads((TOY / "meta.json").read_text())
print("reward:", meta["reward_name"], "--", meta["reward_description"])
print("higher_is_better:", meta["higher_is_better"])
""",
    ),
    (
        "md",
        """
## 1. Re-score with a different oracle

The toy data ships scored with QED. Here we re-score every enumerated child with something else
entirely — a crude polarity preference — and watch the library change. Substitute your own
scorer and nothing else about this notebook changes.
""",
    ),
    (
        "py",
        """
from dataclasses import replace
from rdkit import Chem, RDLogger
from rdkit.Chem import Crippen, Descriptors, QED

RDLogger.DisableLog("rdApp.*")

def my_oracle(smiles: str) -> float:
    \"\"\"A stand-in: prefer polar, mid-sized molecules. Replace with your real scorer.\"\"\"
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return 0.0
    tpsa = Descriptors.TPSA(mol)
    logp = Crippen.MolLogP(mol)
    return max(0.0, min(1.0, tpsa / 140.0 - 0.15 * abs(logp - 1.5)))

# Re-score in place. This is the enumeration bill: one call per enumerated child.
calls = 0
rescored = []
for hub in enum_hubs:
    children = []
    for c in hub.children:
        children.append(replace(c, reward=my_oracle(c.smiles)))
        calls += 1
    rescored.append(replace(hub, children=children))

print(f"{calls} oracle calls to re-score {len(rescored)} hubs")
""",
    ),
    (
        "md",
        """
## 2. Choosing the gate

`reward_threshold` is the bar above which a molecule counts as a hit. It is the single number
that most changes the answer, so it is worth **choosing** rather than picking.

The rule this project settled on, after several ad-hoc alternatives:

> **The gate is the score at which 5% of property-matched decoys pass.**

Calibrate against known actives and decoys **matched on molecular properties** — size, logP,
charge — not random molecules. Then the threshold means "5% false-positive rate" in every
target's own units, and one sentence justifies every gate instead of four separately-argued
numbers.

Three warnings, each of which cost real work here:

- **Property-matched decoys, not random ones.** One gate looked like 82.9× enrichment against
  warhead-matched decoys and 2.1× against property-matched ones. The second is the true number;
  the first was measuring molecular weight.
- **A gate in an oracle's optimised tail is not an activity claim.** One proxy separated actives
  from decoys at AUROC 0.76, and *zero of 2,315 real actives* reached the bar being quoted.
- **Never apply different gates to the two arms.** Both are always measured at the same
  threshold.

Here is the shape of that calibration, with synthetic "actives" and "decoys" standing in for
your real sets.
""",
    ),
    (
        "py",
        """
import random

rng = random.Random(0)
all_smiles = [c.smiles for h in rescored for c in h.children]

# Stand-ins. Replace with YOUR known actives and property-matched decoys.
actives = rng.sample(all_smiles, 40)
decoys  = rng.sample([s for s in all_smiles if s not in set(actives)], 200)

def gate_at_fpr(actives, decoys, oracle, fpr=0.05):
    \"\"\"The score at which `fpr` of decoys pass. One rule, every target, its own units.\"\"\"
    decoy_scores = sorted((oracle(s) for s in decoys), reverse=True)
    idx = max(0, int(round(fpr * len(decoy_scores))) - 1)
    return decoy_scores[idx]

gate = gate_at_fpr(actives, decoys, my_oracle)
tpr = sum(my_oracle(s) >= gate for s in actives) / len(actives)
print(f"5%-FPR gate: {gate:.3f}")
print(f"  {tpr:.0%} of actives pass at that gate")
print("  (synthetic sets -- substitute your own before quoting anything)")
""",
    ),
    (
        "md",
        """
## 3. What the gate does to the library
""",
    ),
    (
        "py",
        """
from hubbatching.campaign import HubBatchingStrategy

BUDGET, CUTOFF = 30, 0.5

print(f"{'gate':>7}  {'molecules':>10}  {'reactions':>10}  stop reason")
for g in (0.0, 0.1, 0.2, gate, 0.4, 0.6):
    res = HubBatchingStrategy(
        rescored, None, reward_threshold=g, similarity=CUTOFF, higher_is_better=True,
    ).run(budget=("reactions", BUDGET))
    mark = "  <- 5%-FPR" if abs(g - gate) < 1e-9 else ""
    print(f"{g:7.3f}  {len(res.accepted):10d}  {res.total_reactions:10d}  "
          f"{res.stop_reason}{mark}")
""",
    ),
    (
        "md",
        """
A stricter gate admits fewer molecules, so the count falls — and at some point the arm stops
being *budget-binding* and starts being *pool-exhausted*. Those are different situations and the
second one is not comparable: the arm did not choose to stop, it ran out.

Always read `stop_reason` beside the count.
""",
    ),
    (
        "md",
        """
## 4. Reward direction

`higher_is_better` is not a display setting. Docking scores are usually more negative when
better, and getting this wrong produces a perfectly plausible-looking, completely inverted
library.
""",
    ),
    (
        "py",
        """
worse_is_better = [
    replace(h, children=[replace(c, reward=-c.reward) for c in h.children])
    for h in rescored
]
res = HubBatchingStrategy(
    worse_is_better, None, reward_threshold=-gate, similarity=CUTOFF,
    higher_is_better=False,     # <- the flag that makes negated scores mean the same thing
).run(budget=("reactions", BUDGET))
print(f"negated reward, higher_is_better=False -> {len(res.accepted)} molecules "
      f"(should match the 5%-FPR row above)")
""",
    ),
    (
        "md",
        """
## 5. Making an expensive oracle affordable

If your oracle is slow — docking, co-folding, anything on a GPU — enumeration dominates. Four
levers, in rough order of effort:

1. **Score in batches.** Per-call overhead dominates for GPU oracles; batching a whole hub's
   children into one invocation is often several times faster for free.
2. **Use the `free_frag` child policy.** It keeps only children needing no new fragment built,
   so each costs one marginal reaction — usually meaning fewer hubs walked for the same library.
3. **Pre-select K fragments** (`--prebuild-k K`). Pay for K high-value fragments up front, then
   fill for free. K is the dial between reactions spent and oracle calls made.
4. **Cheap surrogate to enumerate, expensive oracle to confirm.** Changes what the selection is
   optimising, so say so — but it is the regime most real campaigns run in.

One encouraging measurement: the compute split **flips** with oracle cost. For a millisecond
surrogate, enumeration is 64–79% of the bill and reward evaluation ~5%; for real GPU docking,
reward evaluation is 87.5–99.7%. The more expensive your oracle, the smaller hub-batching's
relative overhead.
""",
    ),
    (
        "py",
        """
from hubbatching.child_select import make_child_policy

for policy in ("reward", "free_frag"):
    res = HubBatchingStrategy(
        rescored, None, reward_threshold=gate, similarity=CUTOFF, higher_is_better=True,
        child_policy=make_child_policy(policy),
    ).run(budget=("reactions", BUDGET))
    print(f"  {policy:<11} {len(res.accepted):3d} molecules   "
          f"{res.total_reward_gen_calls:6d} reward-gen calls")
""",
    ),
    (
        "md",
        """
(On the toy data every building block is purchasable, so there are no promoted fragments and
`free_frag` has nothing to filter — it collapses to reward order. On a generator with a dynamic
library the two diverge sharply.)

## 6. If you are training rather than reading

Then the reward is an RGFN component, not a hub-batching one. Subclass upstream's
`CachedProxyBase`, make it `@gin.configurable`, reference it from a gin config:

```python
import gin
from rgfn.api.proxy_base import CachedProxyBase

@gin.configurable()
class MyProxy(CachedProxyBase):
    is_non_negative = True
    higher_better = True

    def _compute_proxy_output(self, states):
        return [my_oracle(s.molecule.smiles) for s in states]
```

Two practical notes. Cache aggressively — the same molecule is scored many times. And if your
oracle is a subprocess needing GPU memory, free the training allocator's cache before calling
it, or it will fail in a way that looks like a hardware fault.
""",
    ),
]
