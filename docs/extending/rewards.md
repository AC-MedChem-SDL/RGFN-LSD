# Bring your own reward

A reward enters hub-batching at exactly two points, and they are not the same point.

| | where | what it costs |
|---|---|---|
| **During sampling** | your generator's training/sampling loop, written into `records.csv` | already paid |
| **During enumeration** | scoring each selected hub's children | this is the bill |

Hub-batching itself never calls an oracle. It reads a number that is already attached to a
molecule. That is why the core has no oracle abstraction to implement: you score, you write the
number down, hub-batching reads it.

The consequence worth internalising: **the enumeration pass is where your oracle budget goes.**
Selecting 40 molecules might mean scoring twenty thousand enumerated children. Everything below
is about making that affordable.

---

## The minimum

Put your oracle's raw value in the `reward` column and its shaped log in `log_reward`:

```python
rows.append({
    "hub_key": key(hub), "child_key": key(child),
    "reward": my_oracle(child),                 # raw, in your units
    "log_reward": beta * my_oracle(child),      # what your objective trains against
    ...
})
```

Two independent things then have to be right.

**`log_reward` must be the shaped reward your objective actually trained against.** It is a
term in the flow identity, not a display value. If your training used a temperature, a clip, or
a transform, the same one belongs here — otherwise the recovered flow is not the flow your
model learned.

**`higher_is_better` in `meta.json` must match your units.** Docking scores are usually more
negative when better. Getting this wrong inverts every ranking and produces a perfectly
plausible-looking, completely inverted library.

---

## Choosing the gate

`--reward-threshold` is the bar above which a molecule counts as a hit. It is the single number
that most changes the answer, so it is worth choosing rather than picking.

The rule this project settled on, after several ad-hoc alternatives:

> **The gate is the score at which 5% of property-matched decoys pass.**

Calibrate against a set of known actives and decoys **matched on molecular properties** — size,
logP, charge — not random molecules. Then the threshold means "5% false-positive rate" in every
target's own units, and one sentence justifies every gate instead of four separately-argued
numbers.

Three warnings, each of which cost real work here:

- **Property-matched decoys, not random ones.** One gate looked like 82.9× enrichment against
  warhead-matched decoys and 2.1× against property-matched ones. The second number is the true
  one; the first was measuring molecular weight.
- **A gate in an oracle's optimised tail is not an activity claim.** One proxy separated actives
  from decoys at AUROC 0.76, and *zero of 2,315 real actives* reached the bar that was being
  quoted. "Modes above 8.0" was a statement about the proxy, not about binding.
- **Never apply different gates to the two arms.** Both are always measured at the same
  threshold. If you report several thresholds, report both arms at each, and lead with the one
  least favourable to you.

Report your gate, the set you calibrated on, and its false-positive rate. A reviewer who cannot
reconstruct the threshold cannot check anything downstream of it.

---

## Making enumeration affordable

If your oracle is slow — docking, co-folding, anything on a GPU — the enumeration pass
dominates, and there are four levers.

**Score in batches.** Per-call overhead dominates for GPU oracles. Batching an entire hub's
children into one invocation is often several times faster for free.

**Use the `free_frag` child policy.** It keeps only children that need no new fragment built, so
each costs one marginal reaction — which usually means fewer hubs walked for the same library,
and oracle calls scale with hubs walked.

**Pre-select K fragments.** `--prebuild-k K --rank-by build_score` pays for K high-value
fragments up front and then fills for free. Because a stocked fragment is reused across many
hubs, each hub yields more free children, so fewer hubs are walked. K is the dial between
reactions spent and oracle calls made; sweep it.

**Use a cheap surrogate to enumerate and an expensive oracle to confirm.** Score enumerated
children with something fast, select, then re-score only the selected library. This changes what
the selection is optimising, so say so — but it is the regime most real campaigns run in, and
it is the regime where hub-batching's selection overhead is relatively smallest: for a
millisecond surrogate, enumeration is 64–79% of the compute bill and reward evaluation ~5%; for
real GPU docking, reward evaluation is 87.5–99.7%. The more expensive your oracle, the less the
selection costs you in relative terms.

---

## Rewards inside a training loop

If you are training a generator here rather than reading one, the reward is an RGFN component,
not a hub-batching one. Subclass upstream's `CachedProxyBase`, make it `@gin.configurable`, and
reference it from a gin config:

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

Two practical notes. Cache aggressively — the same molecule is scored many times, and the base
class exists to help. And if your oracle is a subprocess that needs GPU memory, free the
training allocator's cache before calling it: PyTorch's allocator will otherwise hold the memory
and the subprocess will fail in a way that looks like a hardware fault.

---

## A worked example

`examples/toy/` uses RDKit's QED as a stand-in oracle — real, deterministic, and recognisable —
with a gate at 0.80. `tools/make_toy_dataset.py` shows a complete reward-to-`records.csv` path
in about thirty lines. Notebook `04_bring_your_own_reward.ipynb` swaps QED for something else
and watches the library change.
