# Divergences from vendored upstream

`third_party/rgfn/` is RGFN, vendored. `NOTICE` claims it is vendored **unmodified**, and this
file exists so that claim is checkable rather than asserted.

## Current state: no divergences

As of this writing `third_party/rgfn/` is byte-identical to upstream `main`. Verify it yourself:

```bash
git clone https://github.com/koziarskilab/RGFN /tmp/rgfn-upstream
diff -r /tmp/rgfn-upstream/rgfn third_party/rgfn
```

The only expected difference is `third_party/rgfn/LICENSE`, which is upstream's MIT licence
copied in beside the code it covers.

## Why there are none, when the research tree has three

The research tree this work came from carries three small operational overrides to upstream
files. **None of them is carried here, deliberately**, because all three are site-specific to
one cluster and every one of them would silently change behaviour for someone running this
repository:

| upstream file | the override there | why it is not here |
|---|---|---|
| `rgfn/trainer/logger/wandb_logger.py` | drops `dir=` from `wandb.init` | works around a conflict with cluster-set `WANDB_DIR`; on a normal machine it just removes a useful argument |
| `configs/loggers/wandb.gin` | `mode = 'offline'` | compute nodes there have no network. Forcing offline on a user who has one would silently stop their run reporting anywhere |
| `configs/rgfn_seh_docking.gin` | appends `Trainer.n_iterations = 400` | caps a docking run to fit a 20-hour walltime. **This one is the sharpest**: silently training for 8% of upstream's 5002 iterations, with no error, is exactly the kind of invisible difference that makes a result irreproducible |

The third is worth dwelling on, because restoring upstream's value has a real consequence you
should know before starting a run: **GPU docking is roughly 160 s/iteration against ~10 s for
the neural proxy, so upstream's 5002 iterations is about nine days.** That is upstream's
default, and capping it silently is worse than saying so. If you need a cap, set it explicitly:

```bash
python train.py --cfg configs/rgfn_seh_docking.gin --bindings "Trainer.n_iterations=400"
```

## If you need site-specific overrides

Put them in a config overlay or a binding, not in `third_party/`. Anything under `third_party/`
should stay something a reader can diff against its upstream in one command — the moment it
does not, nobody can tell which behaviour they are observing.

If a divergence becomes genuinely unavoidable, add it to the table below with the diff and the
reason, and keep the `NOTICE` wording in step.

| file | diff | why | added |
|---|---|---|---|
| *(none)* | | | |

## One thing upstream fetches rather than ships

`rgfn/gfns/reaction_gfn/proxies/cache/` holds proxy models that upstream downloads on first use
(the sEH proxy is ~2.5 MB). It is **not** vendored here — it is a downloaded artifact, not
source, and shipping it would break the byte-identical claim above.

The practical consequence: the first sEH run needs network access. On an air-gapped compute
node that fails at an awkward moment, so warm the cache from a login node first, or stage the
directory across yourself.
