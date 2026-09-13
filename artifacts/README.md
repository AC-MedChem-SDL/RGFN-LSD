# artifacts/

The committed intermediates every `reproduce/` script reads. Small, CSV and JSON only, no
accelerator needed — this directory is what makes T1 a laptop-scale claim.

`MANIFEST.csv` is the index: every file, its size, its SHA-256, which harvest script produced
it, which published exhibit reads it, and which **measurement generation** it belongs to. It is
generated, never hand-maintained:

```bash
python3 tools/build_manifest.py            # rebuild
python3 tools/build_manifest.py --check    # fail if stale
```

## Where these came from

Each group carries a `provenance.json` naming the source directory in the research tree and the
md5 of every file it was built from. Nothing here is hand-copied: `tools/harvest/*.py` is the
only path from a machine-specific tree into this repository, and it redacts absolute paths on
the way through — the md5s remain, so a copy is still checkable against its source.

| group | read by |
|---|---|
| `reaction_budget/` | `reproduce/fig1_reaction_budget.py` |
| `mechanism/` | `reproduce/fig2_floor_and_ceiling.py` |
| `similarity/`, `sparrow_diversity/` | `reproduce/fig3_selection_vs_enumeration.py` |
| `external/` | `reproduce/table1_external.py` |
| `yield_risk/`, `rewards/` | `reproduce/figA1_yield_risk.py` |
| `two_knob/` | `reproduce/figA2_two_knob_surface.py` |

A group that nothing reads is flagged by `build_manifest.py` — it is either dead weight or a
figure that has gone missing, and both are worth noticing.

## The `generation` column, and why it exists

These results were assembled over several months, during which the training budget, the hit
gates, one reward definition, and the generator taxonomy all changed. Nothing on disk is
*wrong*. Some of it is no longer *commensurable* with the rest — and a figure that silently
mixes generations is a real hazard here rather than a hypothetical one.

Three states, and the last distinction is the one that matters:

| state | meaning | can re-harvesting fix it? |
|---|---|---|
| `v1` | measured under v1 standards; a newer measurement will exist once the re-run reaches this cell | eventually |
| `v1-stale` | its source has **already** been regenerated | **yes, now** |
| `invalidated` | the quantity itself was **redefined** — no newer measurement of the same thing exists or will | **no** |

Collapsing `invalidated` into "superseded" would be the dangerous direction: it implies a newer
number exists somewhere, and someone would go looking for it.

Currently flagged (run `python3 tools/build_manifest.py` to see the live list):

- **27 files `invalidated`** — every 6TD3 cell. The 6TD3-B CNN_VS oracle *replaced* the
  Tier2−Tier1 differential these were docked with, and the old differential was measured to be
  exploitable by the generator itself. A different reward is a re-dock, not a re-gate.
  `reproduce/fig1_reaction_budget.py` already excludes 6TD3 from the headline for this reason
  and reports it alongside rather than pooling it silently.
- **2 files `v1-stale`** — the external head-to-head, whose S3-GFN seed-43 pool was retrained
  on 2026-09-12 and has since passed verification. A refresh is available now, not pending.

### Refreshing

A clean re-run under one consistent set of standards is under way in the research tree, and its
runbook (§10.1) carries the trigger. When a phase completes:

1. re-run the harvest script named in `MANIFEST.csv` for that group, pointed at the new tree,
2. update `GENERATION` / `GENERATION_OVERRIDES` in `tools/build_manifest.py`,
3. `python3 tools/build_manifest.py`.

The harvest layer is the seam that makes this a re-point rather than a rewrite: no `reproduce/`
script changes, because each reads a fixed artifact path and the harvest decides what lands
there.

**Until then, do not mix generations in one table or one figure.** If you add a group from a
different generation, say so in its `generation` field and in the caption.

## Adding an artifact

Harvest it — do not copy it by hand. If it is too large to commit, it belongs in the archived
deposit with a fetch script and a checksum row here, **not** in a one-off `.gitignore`
exception. The note in `.gitignore` says why: a previous repository accumulated a tail of those
and silently lost a publication figure that way.
