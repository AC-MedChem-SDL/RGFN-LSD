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

**The bundled checkpoint is committed**, so if you have torch installed this notebook runs with
no download at all. It is deliberately tiny -- 48 building blocks, 12 reaction templates, a few
hundred iterations against QED -- and trained by `tools/train_toy_checkpoint.py`, which you can
re-run in about half an hour on a CPU. It exists to prove the adapter path works end to end;
no number it produces means anything about chemistry.

If the checkpoint is missing, the cells below **skip cleanly** and say what to do, so you can
read the notebook through before deciding whether the install is worth it.
""",
    ),
    (
        "py",
        """
import os
from pathlib import Path

from hubbatching.paths import repo_root

# Set CHECKPOINT / CONFIG to your own, or fetch one with setup/fetch_models.py.
CHECKPOINT = Path(os.environ.get("HB_CHECKPOINT", repo_root() / "examples/toy_model/toy_rgfn_qed.pt"))
CONFIG     = Path(os.environ.get("HB_CONFIG", repo_root() / "configs/hubbatching/toy_rgfn_qed.gin"))

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
        print("  python3 tools/train_toy_checkpoint.py    # ~30 min, CPU, no download")
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
        reward_name="qed",
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

        # An actual verdict, not a caption. Freshly-initialised layers of the same shape come out
        # of one initialiser and their spreads cluster tightly; a trained policy's do not. This
        # is a heuristic and it says so -- but a heuristic that computes something beats a
        # warning printed unconditionally, which is just a sentence that always looks alarming.
        spreads = [s for _, s in stats]
        ratio = max(spreads) / max(min(spreads), 1e-12)
        print(f"\\nspread of per-tensor std: {min(spreads):.4f} .. {max(spreads):.4f}  "
              f"(ratio {ratio:.1f}x)")
        if ratio < 1.5:
            print("  SUSPICIOUS: nearly uniform, consistent with weights that never loaded.")
        else:
            print("  OK: varied, consistent with a policy that was actually trained.")
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
N_TRAJECTORIES = 600   # ~25 s on a CPU. See the note below on why this matters.

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
### How many hubs you get, and why it is fewer than you expect -- and unstable

From 600 trajectories the toy model finds 400+ distinct hubs and only a handful that are
*rankable*. Across runs of this very notebook that number came out as 8, 34 and 7. **Sampling is
not seeded, and with a flow field this thin the count is genuinely that volatile** -- so do not
be surprised when your figure differs from the sentence above, and do not tune anything based on
one draw of it.

A hub becomes rankable only once it has been reached with **more than one distinct terminal
child**: one child gives one flow estimate, and `min_children=2` refuses a ranking built on a
single sample. With 48 building blocks, 24 anchored reactions and up to 4 reactions per
molecule, the reachable state space is far larger than a few hundred trajectories can revisit,
so most hubs are seen once and drop out. Which ones survive is close to a coin toss.

**Two lessons, and the second is the one that transfers.** Hub-batching reads a flow field, and
a flow field needs traffic -- if your ranking comes back nearly empty, the question is not "is
the method working" but "have I sampled enough for hubs to be revisited", which scales with your
action space rather than your model's quality. And a statistic computed from an unseeded sample
this sparse is not a measurement yet: quote a range, or seed it. A published run here samples
tens of thousands of trajectories, which is what makes its hub counts stable enough to report.

### The reward-free cross-check

A trained GFlowNet visits states in proportion to their flow, so empirical visitation is a
**reward-free** estimate of the same quantity. The two estimates share no terms, so disagreement
between them — after the `log Z` shift — is a direct test of whether trajectory balance holds.

This is worth running on any model whose backward policy has been modified (by cost guidance,
say). Large systematic disagreement means the flow field you are reading is not the one the
identity assumes.

**On this toy model expect a large offset -- around -7 -- and do not read it as a defect.** The
visitation estimator assumes the sampler visits states in proportion to their flow, which holds
only for a *converged* model. Six hundred iterations on a 48-block library is nowhere near
converged, so the two estimators genuinely disagree. What the diagnostic is for is the same
measurement on a properly trained model, where a large offset would point at something real.
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
    # Takes (smiles, depth) PAIRS, and returns (flow_records, per_hub_stats). The records are
    # the same FlowRecord type sampling produced, so an enumeration merges into the same DAG.
    records, stats = adapter.enumerate_hub_children([(hub.key, hub.depth)])

    print(f"hub  {hub.key}")
    print(f"  {stats[0]['n_enumerated_paths']} applicable one-reaction paths")
    print(f"  {stats[0]['n_records']} distinct children enumerated AND scored\\n")

    best = sorted(records, key=lambda r: r.reward, reverse=sample.higher_is_better)[:8]
    for r in best:
        print(f"  qed={r.reward:6.3f}  {r.child_key}")
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
