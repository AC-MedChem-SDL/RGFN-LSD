TITLE = "Bring your own generator"
SUMMARY = (
    "Write the file contract from any environment; run hub-batching on your own model's output."
)

CELLS = [
    (
        "md",
        """
# Bring your own generator

You have a trained molecular generator. You want hub-batching to read its flow field.

The recommended route does **not** involve importing your model into this environment. You run
your model wherever it already runs, write some CSV and JSON, and point hub-batching at the
directory.

That is not a fallback — it is how the published comparison was actually done. The generators in
the paper live in mutually incompatible conda environments and no two of them co-import; one
ships its own fork of a package another needs. A file contract is what made them comparable.

Reference: [`docs/INPUT_CONTRACT.md`](../docs/INPUT_CONTRACT.md) and
[`docs/extending/generators.md`](../docs/extending/generators.md).
""",
    ),
    (
        "md",
        """
## The contract

```
<sample-dir>/
  records.csv          REQUIRED   one row per observed hub -> child transition
  meta.json            REQUIRED   log Z, reward direction, provenance
  routes.json          strongly recommended — and NOT recoverable later
  compositions.json    build costs, keyed for hubs AND products
  enum_children.json   required for hub-batching (a second, enumeration pass)
```

Only the first two are needed to rank hubs. You can integrate with those alone, look at the flow
field, and decide whether the rest is worth wiring.
""",
    ),
    (
        "md",
        """
## 1. Write it

The writer is **standard library only** — `csv`, `json`, `math` — precisely so it imports inside
whatever environment your model needs. No rdkit, no torch, no version negotiation.

Below is a complete, working writer for a pretend generator. Substitute your own sampling loop
and it is the real thing.
""",
    ),
    (
        "py",
        """
import json, math, random, tempfile
from pathlib import Path

from hubbatching.adapters import artifacts   # pure stdlib -- safe in any env

rng = random.Random(0)
out = Path(tempfile.mkdtemp(prefix="mygen_"))

# --- pretend to sample. In reality this loop is your model's sampler. -------------------
# For every trajectory ending  h --[one reaction]--> x --[stop]  record the four log-terms.
HUBS = {"CC(=O)Nc1ccc(C(=O)O)cc1": 1, "O=C(O)C1CCN(C(=O)C2CC2)CC1": 1}
TAILS = ["NCc1ccccc1", "NC1CCOCC1", "NCC(F)(F)F", "NCc1ccncc1"]

rows, routes = [], {}
for hub, depth in HUBS.items():
    for tail in TAILS:
        child = f"{hub[:-1]}N{tail[1:]}"          # a stand-in for the real product
        reward = rng.uniform(0.6, 0.95)
        log_reward = 8.0 * reward
        log_pf_move = -math.log(len(TAILS))
        log_pf_stop = math.log(0.9)
        log_pb_move = -0.4
        rows.append({
            "hub_key": hub, "child_key": child,
            "reward": reward, "log_reward": log_reward,
            "log_pf_move": log_pf_move,
            "log_pb_move": log_pb_move,       # your model's OWN trained backward policy
            "log_pf_stop": log_pf_stop,       # never assume this is zero
            "hub_depth": depth,
            "hub_stereo_key": hub, "child_stereo_key": child,
        })
        routes[child] = {
            "seed": "Nc1ccc(C(=O)O)cc1",
            "num_reactions": depth + 1,
            "steps": [{"reaction": "amide coupling", "reactants": [tail],
                       "input": hub, "product": child}],
        }

artifacts.write_records(out / "records.csv", rows)
artifacts.write_json(out / "routes.json", routes)
artifacts.write_json(out / "compositions.json", artifacts.compositions_from_records(rows))
artifacts.write_json(out / "meta.json", {
    "model": "mygen", "reward_name": "demo",
    "log_z": 9.0,               # required: puts the visitation estimator on the same scale
    "higher_is_better": True,   # required: getting this wrong inverts every ranking
    "n_trajectories": len(rows),
})

print(out)
print(sorted(p.name for p in out.iterdir()))
""",
    ),
    (
        "md",
        """
### Note what `compositions_from_records` did

It wrote an entry for every **hub** as well as every product. A hub missing from that file
prices at zero, which silently gives the best-candidate baseline its shared scaffolds for free
and inflates hub-batching's apparent advantage. The run does not fail — it reports a better
number.

Call the helper rather than hand-rolling the dict.
""",
    ),
    (
        "py",
        """
comps = json.loads((out / "compositions.json").read_text())
for key, value in list(comps.items())[:4]:
    kind = "HUB    " if key in HUBS else "product"
    print(f"  {kind}  cost={value['num_reactions']}  {key[:44]}")
""",
    ),
    (
        "md",
        """
## 2. Check it before running anything long
""",
    ),
    (
        "py",
        """
from hubbatching.adapters.registry import get_adapter

adapter = get_adapter("files", sample_dir=str(out))
report = adapter.validate()
for k in ("can_rank_hubs", "can_hub_batch", "can_export_bench_plan"):
    print(f"{'yes' if report[k] else 'NO ':>4}  {k}")
print("\\nblockers:")
for b in report["blockers"] or ["none"]:
    print(" ", b)
""",
    ),
    (
        "md",
        """
`can_hub_batch` is `NO` because there is no `enum_children.json` yet — that comes from a second
pass, after you know which hubs are worth enumerating. `can_rank_hubs` is `yes`, which is enough
to look at the flow field.
""",
    ),
    (
        "py",
        """
from hubbatching.dag import LiteHubDAG
from hubbatching.hubs.registry import get_hub_strategy

sample = adapter.sample_flow_records()
dag = LiteHubDAG.from_records(
    sample.records, total_trajectories=sample.n_trajectories,
    log_z=sample.log_z, higher_is_better=sample.higher_is_better,
)
for hub in get_hub_strategy("highest_flow").rank(dag):
    print(f"  logF={hub.log_flow_consensus():6.2f}  {hub.n_children} children  {hub.key}")
""",
    ),
    (
        "md",
        """
## 3. The warning that exists for a reason

Delete `routes.json` and read the data back. Everything still works — the warning is the only
thing that tells you a bench plan is now impossible.
""",
    ),
    (
        "py",
        """
import warnings

(out / "routes.json").write_text("{}")

with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always")
    get_adapter("files", sample_dir=str(out)).sample_flow_records()

for w in caught:
    print("WARNING:", str(w.message)[:300], "...")
""",
    ),
    (
        "md",
        """
Routes are **not recoverable** after sampling ends: the trajectory is gone, and
`compositions.json` keeps only a reaction count.

In this project three of four generators wrote a well-formed *empty* `routes.json`, exited zero,
and were promoted. The loss surfaced months later when the comparison needed routes, and cost a
full re-sample of 36 of 40 cell-seeds.

If your generator genuinely has no synthesis routes — a fragment-attachment model, say —
**declare it** rather than leaving the file empty:

```python
get_adapter("files", sample_dir=..., routes_expected=False)
```
""",
    ),
    (
        "md",
        """
## 4. Four things that will cost you

**Score with the policy you sampled with.** Many training loops sample from an exploratory
policy (95% trained + 5% uniform) but score with the pure trained policy. If those differ, the
sampled distribution and the recovered `P_F` disagree and the per-hub spread stops being a clean
flow-matching residual.

**Use the trained backward policy.** The method reads a field your model learned; a uniform
`P_B` stand-in measures something else. A *deterministic* backward step genuinely contributes 0
— that is different from ignoring a learned one.

**Watch for checkpoints that silently drop the backward policy.** If it lives somewhere the
checkpoint does not serialise, it loads as its initialisation and every flow estimate is wrong
with nothing flagged. We lost checkpoints to exactly this. Verify the weights are not at init.

**One key function, everywhere.** Records, routes and compositions must use the same one. A
route keyed differently from its hub is worse than no route: the lookup returns nothing and the
caller prices the wrong molecule, with no error anywhere.
""",
    ),
    (
        "md",
        """
## 5. From the shell

```bash
hubbatching inspect   <sample-dir>
hubbatching pick-hubs --records <sample-dir>/records.csv --out hubs.csv --pool all --order flow_desc
# ... your generator enumerates each row of hubs.csv -> enum_children.json ...
hubbatching campaign  --analysis-dir <sample-dir> --enum-children <enum>/enum_children.json \\
                      --reward-threshold <your gate> --tag mymodel
```

### Does hub-batching apply to my model at all?

It needs a **backward policy over a state graph** (the flow identity is detailed balance at one
edge, rearranged — without `P_B` there is nothing to rearrange), and **states that are makeable
intermediates** (a hub has to be something you could put in a flask).

A model that fails the second can still be *compared against* — that is the route-less path in
[`benchmarks/`](../benchmarks/README.md), where routes are recovered by retrosynthesis rather
than logged. It just cannot be hub-batched natively.
""",
    ),
]
