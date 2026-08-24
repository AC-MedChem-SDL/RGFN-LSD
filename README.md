# LSD-Flow

**Library cost, not per-molecule synthesizability.** A trained reaction-grounded
GFlowNet's flow field already identifies which intermediates a screening library
should be batched around. Reading it post-hoc — no retraining, no reward change —
produces libraries that deliver more distinct high-reward molecules per unit of
bench chemistry than post-hoc retrosynthetic planning over a route-less
generator's output recovers.

<!-- IDENTITY:BEGIN -->
**Authors:** Mark Stevens and contributors (author list not final).
**Repository:** <https://github.com/AC-MedChem-SDL/RGFN-LSD>
<!-- IDENTITY:END -->

---

## Status

**This repository is under construction.** It is the clean publication artifact,
migrated from a larger research working tree. Code, configs, and committed
artifacts land here progressively; anything not yet present is still in the
research repo. What *is* here is expected to work.

Present today: the anonymity toolchain (`tools/`, `docs/ANONYMITY.md`), licensing,
and project metadata.

## Why there are two repositories

The research tree is optimised for finding things out — experiment logs, scheduler
scripts, superseded numbers, per-cell result directories. This one is optimised
for a reader confirming a claim in twenty minutes. Keeping them separate is what
lets this repo stay small enough to be read.

| | Research tree | This repository |
|---|---|---|
| Optimised for | discovery over months | verification in minutes |
| Contains | every experiment ever run, cluster wiring, full provenance | the method, the evaluation, and one command per published number |
| Compute assumed | GPU cluster | a laptop, for everything except retraining |

## Planned layout

```
src/lsdflow/       the method: flow estimation, hub selection, child/mode
                   policies, the count-once cost model
third_party/rgfn/  vendored upstream RGFN, unmodified (see docs/PATCHES.md)
benchmarks/        baseline generators and competing planners, as thin adapters
reproduce/         one script per published figure and table
artifacts/         the small committed intermediates those scripts read
setup/             fetch scripts for non-vendored third-party code
cluster/           site-specific job submission (not needed to reproduce)
tools/             release engineering, including the anonymity gate
docs/              method notes, definitions, limitations, CLAIMS.md
```

## Reproducibility tiers

Full replication is not laptop-scale — the published evaluation includes hundreds
of GPU-hours of docking. So reproduction is stratified, and each tier stands alone:

| Tier | What it does | Cost |
|---|---|---|
| **T0** | install, then run the whole pipeline end to end on toy inputs | ~2 min, CPU |
| **T1** | regenerate **every** published figure and table from committed `artifacts/` | minutes, CPU |
| **T2** | re-run selection and evaluation from archived checkpoints and enumerations | hours, GPU |
| **T3** | retrain the generators from scratch | GPU-weeks; documented, not expected |

T1 is the one that matters: it is the claim that the numbers in the paper come
from the code in this repository, and it needs no accelerator.

<!-- IDENTITY:BEGIN -->
## Anonymity

Author identity is confined to `NOTICE`, `CITATION.cff`, and the block at the top
of this file. `tools/check_identity.py` enforces that; `tools/make_anon_snapshot.sh`
builds the double-blind review artifact and refuses to emit one if any identity
survives. See [`docs/ANONYMITY.md`](docs/ANONYMITY.md).
<!-- IDENTITY:END -->

## Licence

Apache-2.0 (`LICENSE`). Vendored and fetched third-party components keep their own
licences — see `NOTICE` and `THIRD_PARTY.md`.
