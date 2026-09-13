# Bring your own generator

You have a trained molecular generator. You want hub-batching to read its flow field and build
you a library. There are two routes, and the first is the one you want.

---

## Route 1: files on disk (recommended)

Run your model **in its own environment**, write a handful of CSV and JSON files, point
hub-batching at the directory. Nothing needs to co-import.

```bash
hubbatching inspect  path/to/sample-dir        # what does this support?
hubbatching pick-hubs --records path/to/sample-dir/records.csv --out hubs.csv --pool all
# ... your generator enumerates each hub's children -> enum_children.json ...
hubbatching campaign --analysis-dir path/to/sample-dir \
                     --enum-children path/to/enum_children.json \
                     --reward-threshold <your gate> --tag mymodel
```

The file formats are specified in [`docs/INPUT_CONTRACT.md`](../INPUT_CONTRACT.md). Read that
page; this one only covers the shape of the work.

**This is not a fallback.** It is how the published comparison was actually run. The generators
in the paper live in mutually incompatible conda environments and no two of them co-import —
one of them ships its own fork of a package another one needs. A file contract is what made them
comparable, and it will almost certainly be less painful for you than it was for us.

### The writer is standard-library only

`hubbatching.adapters.artifacts` deliberately imports nothing but `csv`, `json` and `math`, so
it loads inside whatever environment your model needs:

```python
import sys
sys.path.insert(0, "/path/to/hubbatching/src")
from hubbatching.adapters import artifacts

artifacts.write_records(out / "records.csv", rows)
artifacts.write_json(out / "meta.json", meta)
artifacts.write_json(out / "routes.json", routes)
artifacts.write_json(
    out / "compositions.json",
    artifacts.compositions_from_records(rows),   # gets the hub entries right for you
)
```

If even that is awkward, copy `artifacts.py` and `route_steps.py` next to your worker — that is
a supported layout and the loader handles it.

### The three steps

**1. Sample, and record the log-terms as you go.** For every trajectory that ends
`h --[one reaction]--> x --[stop]`, write a row with `log R(x)`, `log P_B(h|x)`,
`log P_F(x|h)`, `log P_F(stop|x)`. These have to be captured *during* sampling; they cannot be
reconstructed afterwards.

**2. Capture routes in the same pass.** `routes.json` is the difference between a number and a
bench plan, and it is **unrecoverable** once sampling ends. The contract page explains what this
cost us. Do it now.

**3. Enumerate the chosen hubs.** `pick-hubs` gives you `hubs.csv`; for each row, exhaustively
apply every applicable reaction, score the products with your oracle, and write
`enum_children.json` in the order `hubs.csv` gave you.

### Reading it back

```python
from hubbatching.adapters.registry import get_adapter

adapter = get_adapter("files", sample_dir="path/to/sample-dir")
print(adapter.validate())            # what this data supports
sample = adapter.sample_flow_records()
hubs = adapter.enumerated_hubs()
```

---

## Route 2: in-process

If your model imports cleanly alongside `hubbatching`, subclass the adapter directly:

```python
from hubbatching.adapters.contract import FlowSample, GFNAdapter
from hubbatching.adapters.registry import register
from hubbatching.records import FlowRecord

@register
class MyModelAdapter(GFNAdapter):
    model_name = "mymodel"

    def __init__(self, checkpoint_path: str, reward_name: str = "mytarget"):
        self.model = load_my_model(checkpoint_path)
        self.reward_name = reward_name

    def sample_flow_records(self, n_trajectories: int) -> FlowSample:
        records, routes = [], {}
        for traj in self.model.sample(n_trajectories):
            records.append(FlowRecord(
                hub_key=key(traj.penultimate_smiles),
                child_key=key(traj.terminal_smiles),
                reward=traj.reward,
                log_reward=traj.log_reward,
                log_pf_move=traj.log_pf_final_move,
                log_pb_move=traj.log_pb_final_move,
                log_pf_stop=traj.log_pf_stop,
                hub_depth=traj.penultimate_num_reactions,
            ))
            routes[key(traj.terminal_smiles)] = traj.route_dict()
        return FlowSample(
            records=records, visit_counts={}, n_trajectories=n_trajectories,
            log_z=float(self.model.log_z), higher_is_better=True,
            model=self.model_name, reward_name=self.reward_name, routes=routes,
        )
```

`sample_flow_records` is the only required method. The five others on `GFNAdapter` — `reward`,
`enumerate_children`, `forward_logprob`, `backward_logprob`, `stop_logprob` — are for the
enumeration pass, and the base class raises `NotImplementedError` naming the capability. That is
deliberate: an un-wired capability should fail loudly rather than silently return wrong numbers.

`hubbatching/adapters/rgfn_adapter.py` is a complete, working implementation to read alongside
this.

---

## Four things that will cost you if you get them wrong

**Score with the policy you sampled with.** Many training loops sample from an exploratory
policy — say 95% trained plus 5% uniform — while `assign_log_probs` scores against the pure
trained policy. If those differ, the sampled distribution and the recovered `P_F` disagree, and
the per-hub spread stops being a clean flow-matching residual. Sample with the pure policy.

**Use the trained backward policy.** The method reads a field your model learned. A uniform
`P_B` stand-in measures something else. A *deterministic* backward step genuinely contributes 0
— that is different from ignoring a learned one.

**Watch for checkpoints that drop the backward policy.** If your backward policy lives somewhere
the checkpoint does not serialise — a `ModuleList` held outside the module tree, say — it will
load silently as its initialisation, and every flow estimate will be wrong in a way nothing
flags. We lost a set of checkpoints to exactly this and had to add a sidecar. Verify after
loading that the backward policy's weights are not at their init values.

**Keys, once.** One key function for records, routes, and compositions. This is stated three
times across these docs because it is the failure that produces no error at all.

---

## Does hub-batching apply to my model?

It needs two things:

1. **A backward policy over a state graph.** The flow identity is detailed balance at one edge,
   rearranged. Without `P_B` there is nothing to rearrange.
2. **States that are makeable intermediates.** A hub has to be a real molecule you could put in
   a flask. For a reaction-grounded generator every state is; for an atom- or fragment-attachment
   model the intermediates are skeletons, not compounds, and "build the hub once" has no bench
   meaning even though the arithmetic still runs.

A model that fails (2) can still be *compared against* — that is what the route-less path in
[`benchmarks/`](../../benchmarks/README.md) is for, where routes are recovered by
retrosynthesis rather than logged. It just cannot be hub-batched natively.
