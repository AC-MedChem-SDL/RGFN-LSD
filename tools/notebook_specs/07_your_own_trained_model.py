TITLE = "Your own trained model, end to end"
SUMMARY = "Drive a real RGFN checkpoint: sample, recover flow, rank hubs, enumerate, campaign."

CELLS = [
    (
        "md",
        """
# Your own trained model, end to end

Every other notebook here reads a file contract. This one drives an actual trained checkpoint:
loads it, samples trajectories, recovers the flow field from the model's own policies,
enumerates a selected hub's children for real, and runs the campaign on the result.

**This is the only notebook with heavy requirements.**

```bash
pip install -e ".[generators,notebooks]"    # torch, gin, the vendored rgfn
python3 setup/fetch_models.py --list        # what checkpoints are available
```

A GPU makes it faster and is not required — a small checkpoint samples on CPU.

If you have no checkpoint, the cells below **skip cleanly** and tell you what to do. Nothing
here fails just because you have not downloaded anything, which means you can read the notebook
through before deciding whether it is worth the install.
""",
    ),
    (
        "py",
        """
import os
from pathlib import Path

from hubbatching.paths import repo_root

# Set CHECKPOINT / CONFIG to your own, or fetch one with setup/fetch_models.py.
CHECKPOINT = Path(os.environ.get("HB_CHECKPOINT", repo_root() / "data/checkpoints/toy_rgfn_seh.pt"))
CONFIG     = Path(os.environ.get("HB_CONFIG", repo_root() / "third_party/rgfn_configs/rgfn_seh_proxy.gin"))

HAVE_CHECKPOINT = CHECKPOINT.exists()
try:
    import torch  # noqa: F401
    HAVE_TORCH = True
except ImportError:
    HAVE_TORCH = False

READY = HAVE_CHECKPOINT and HAVE_TORCH
print(f"torch installed : {HAVE_TORCH}")
print(f"checkpoint      : {CHECKPOINT}  {'found' if HAVE_CHECKPOINT else 'NOT FOUND'}")
print(f"config          : {CONFIG}  {'found' if CONFIG.exists() else 'NOT FOUND'}")
if not READY:
    print("\\nThe cells below will skip. To run them:")
    if not HAVE_TORCH:
        print("  pip install -e '.[generators]'")
    if not HAVE_CHECKPOINT:
        print("  python3 setup/fetch_models.py --list")
        print("  python3 setup/fetch_models.py toy_rgfn_seh")
        print("  ...or point HB_CHECKPOINT at a checkpoint you trained yourself")
""",
    ),
    (
        "md",
        """
## 1. Load the model

The adapter rebuilds the trained objective from a gin config plus a checkpoint, and builds a
**pure-policy** sampler from it.

That last detail matters more than it looks. Training usually samples from an *exploratory*
policy — say 95% trained plus 5% uniform — while the log-probabilities are scored against the
pure trained policy. If you sample with one and score with the other, the sampled distribution
and the recovered `P_F` disagree, and the per-hub spread stops being a clean flow-matching
residual. The adapter uses the pure policy for exactly this reason.
""",
    ),
    (
        "py",
        """
if READY:
    from hubbatching.adapters.registry import get_adapter

    adapter = get_adapter(
        "rgfn",
        config_path=str(CONFIG),
        checkpoint_path=str(CHECKPOINT),
        reward_name="seh",
        device="auto",          # falls back to CPU
    )
    print(f"loaded {adapter.model_name}")
else:
    print("skipped -- no checkpoint")
""",
    ),
    (
        "md",
        """
### Verify the backward policy actually loaded

Worth thirty seconds, because the failure is silent. If your backward policy lives somewhere the
checkpoint does not serialise — held outside the module tree, for instance — it loads as its
*initialisation*, every flow estimate is wrong, and nothing raises. We lost a set of checkpoints
to exactly this and had to add a sidecar file to recover them.

The check: its weights should not look freshly initialised.
""",
    ),
    (
        "py",
        """
if READY:
    import torch

    backward = getattr(adapter, "backward_policy", None) or getattr(
        getattr(adapter, "objective", None), "backward_policy", None
    )
    if backward is None:
        print("no separate backward policy exposed -- check your model's structure")
    else:
        stats = [(n, float(p.std())) for n, p in backward.named_parameters() if p.numel() > 1]
        print(f"{len(stats)} backward-policy parameter tensors")
        for name, std in stats[:5]:
            print(f"  std={std:.4f}  {name}")
        print("\\nAll std values suspiciously uniform => possibly un-loaded initialisation.")
else:
    print("skipped")
""",
    ),
    (
        "md",
        """
## 2. Sample, and recover the flow field

Sampling produces the four log-terms per terminal transition. **Rewards come free** — they were
computed during sampling, so there is no oracle cost here.
""",
    ),
    (
        "py",
        """
N_TRAJECTORIES = 200   # raise for a real run; 200 keeps this notebook quick

if READY:
    sample = adapter.sample_flow_records(N_TRAJECTORIES)
    print(f"{len(sample.records)} terminal transitions from {sample.n_trajectories} trajectories")
    print(f"log Z = {sample.log_z:.3f}   higher_is_better = {sample.higher_is_better}")
    print(f"routes captured: {len(sample.routes)}")
else:
    print("skipped")
""",
    ),
    (
        "md",
        """
**Check `routes captured` is non-zero.** Routes are what turn a selected library into something
a chemist can make, and they are **not recoverable** after sampling ends — the trajectory is
gone. A run that captures none completes, prints plausible numbers, and quietly cannot produce a
bench plan.
""",
    ),
    (
        "py",
        """
if READY:
    from hubbatching.dag import LiteHubDAG
    from hubbatching.hubs.registry import get_hub_strategy

    dag = LiteHubDAG.from_records(
        sample.records,
        total_trajectories=sample.n_trajectories,
        log_z=sample.log_z,
        higher_is_better=sample.higher_is_better,
        visit_counts=sample.visit_counts,
    )
    ranked = get_hub_strategy("highest_flow", min_children=2).rank(dag)
    print(f"{len(dag)} hubs observed, {len(ranked)} eligible (>=2 distinct children)\\n")
    for i, hub in enumerate(ranked[:10], 1):
        print(f"{i:2d}. logF={hub.log_flow_consensus():7.2f}  U(h)={hub.uncertainty():7.3f}  "
              f"depth={hub.depth}  {hub.n_children:3d} children")
else:
    print("skipped")
""",
    ),
    (
        "md",
        """
### The reward-free cross-check

A trained GFlowNet visits states in proportion to their flow, so empirical visitation is a
**reward-free** estimate of the same quantity. The two estimates share no terms, so disagreement
between them — after the `log Z` shift — is a direct test of whether trajectory balance holds.

This is worth running on any model whose backward policy has been modified (by cost guidance,
say). Large systematic disagreement means the flow field you are reading is not the one the
identity assumes.
""",
    ),
    (
        "py",
        """
if READY and sample.visit_counts:
    import statistics

    pairs = []
    for hub in ranked[:40]:
        db = hub.log_flow_consensus()
        mc = dag.log_visitation(hub)
        if db == db and mc not in (float("-inf"), float("inf")) and mc == mc:
            pairs.append((db, mc, db - mc))
    if pairs:
        diffs = [d for _, _, d in pairs]
        print(f"n={len(pairs)}   median(logF_DB - logF_visitation) = {statistics.median(diffs):+.2f}")
        print(f"  IQR {statistics.quantiles(diffs, n=4)[0]:+.2f} .. "
              f"{statistics.quantiles(diffs, n=4)[2]:+.2f}")
        print("\\nA large, systematic offset means the two estimators disagree -- worth")
        print("investigating before trusting the ranking.")
    else:
        print("no hub had both estimates finite")
else:
    print("skipped -- needs visit counts")
""",
    ),
    (
        "md",
        """
## 3. Enumerate a hub's children, for real

This is where the oracle bill lands. Everything above reused rewards from sampling; enumeration
scores molecules that were never sampled, and it is the dominant cost for an expensive oracle.

Start with one hub.
""",
    ),
    (
        "py",
        """
if READY and ranked:
    hub = ranked[0]
    children = adapter.enumerate_hub_children(hub.key)
    print(f"hub  {hub.key}")
    print(f"  {len(children)} applicable one-reaction children enumerated and scored\\n")
    top = sorted(children, key=lambda c: c.reward, reverse=sample.higher_is_better)[:8]
    for c in top:
        print(f"  reward={c.reward:7.3f}  {c.smiles}")
else:
    print("skipped")
""",
    ),
    (
        "md",
        """
Note the ratio: one hub yields tens to hundreds of children, each needing a score. Scaled across
a few hundred hubs that is the oracle budget, and it is why the `free_frag` child policy and
pre-select-K exist — both reduce the number of *hubs walked* for the same library.

## 4. Write the contract, then use the ordinary tools

Rather than driving everything in-process, the usual move is to emit the file contract once and
then use the CLI — which means the expensive sampling and enumeration happen once and every
subsequent selection experiment is cheap CPU work over cached results.
""",
    ),
    (
        "py",
        """
if READY:
    import json, tempfile
    from pathlib import Path

    from hubbatching.adapters import artifacts

    out = Path(tempfile.mkdtemp(prefix="mymodel_"))
    rows = [
        {
            "hub_key": r.hub_key, "child_key": r.child_key,
            "reward": r.reward, "log_reward": r.log_reward,
            "log_pf_move": r.log_pf_move, "log_pb_move": r.log_pb_move,
            "log_pf_stop": r.log_pf_stop, "hub_depth": r.hub_depth,
            "hub_stereo_key": r.hub_stereo_key, "child_stereo_key": r.child_stereo_key,
        }
        for r in sample.records
    ]
    artifacts.write_records(out / "records.csv", rows)
    artifacts.write_json(out / "routes.json", sample.routes)
    artifacts.write_json(out / "compositions.json", artifacts.compositions_from_records(rows))
    artifacts.write_json(out / "meta.json", {
        "model": sample.model, "reward_name": sample.reward_name,
        "log_z": sample.log_z, "higher_is_better": sample.higher_is_better,
        "n_trajectories": sample.n_trajectories,
    })
    print(out)
    print(sorted(p.name for p in out.iterdir()))
else:
    print("skipped")
""",
    ),
    (
        "py",
        """
if READY:
    from hubbatching.adapters.file_adapter import FileAdapter

    report = FileAdapter(str(out)).validate()
    for k in ("can_rank_hubs", "can_hub_batch", "can_export_bench_plan"):
        print(f"{'yes' if report[k] else 'NO ':>4}  {k}")
    print("\\nblockers:", report["blockers"] or "none")
else:
    print("skipped")
""",
    ),
    (
        "md",
        """
`can_hub_batch` is still `NO` until you write `enum_children.json` — enumerate each row of
`hubs.csv` the way section 3 did for one hub, and write the result in that ranking's order.

From there everything is ordinary CPU work:

```bash
hubbatching pick-hubs --records <out>/records.csv --out hubs.csv --pool all --order flow_desc
# ... enumerate each row -> enum_children.json ...
hubbatching campaign --analysis-dir <out> --enum-children <enum>/enum_children.json \\
                     --reward-threshold <your gate> --tag mymodel
hubbatching sweep    ...     # how the margin moves with the diversity cutoff
```

## Cluster notes

If you are running this on a shared cluster rather than a laptop, two things bite:

- **Libraries that cache under `$HOME`.** Triton, matplotlib and HuggingFace all default there,
  and `$HOME` is read-only on many compute nodes. Export their cache directories to scratch in
  your job script. A login-node test cannot catch this.
- **A GPU oracle called from inside a training process.** PyTorch's allocator holds device
  memory, so a docking subprocess can be starved of VRAM and fail in a way that looks exactly
  like a hardware fault. Free the allocator's cache before calling out.
""",
    ),
]
