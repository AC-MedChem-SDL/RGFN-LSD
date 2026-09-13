# Getting a bench plan out

This is the end of the pipeline and the point of it. Everything upstream produces a *number*;
this produces a directory a synthetic chemist can work from without reading any of our code.

```bash
hubbatching export --analysis-dir <sample-dir> \
                   --enum-children <enum-dir>/enum_children.json \
                   --reward-threshold <your gate> --seed 43
```

---

## What you get

```
<out-root>/<generator>_<target>_seed<N>/
  README.md                 gate, budget, every input by path and checksum, the caveats
  hub_batching/
    molecules.csv           one row per molecule
    batches.csv             one row per batch
    routes.json             AiZynth-compatible route trees — the interoperable view
    steps.csv               one row per reaction step — the flat view
    batch_01/
      buy_list.csv          what to order for this batch
      protocol.md           ordered, human-readable steps
      scheme.png            the rendered reaction scheme
    batch_02/ ...
  best_candidate/ ...
```

A **batch** is a set of molecules sharing a synthetic intermediate — made together off one common
prefix, which is the thing a chemist would run as one plate.

**Both strategies are always exported.** They run on identical chemistry — same enumeration, same
gate, same budget, only the chooser differs — so the two directories are directly comparable, and
that contrast is the deliverable rather than a by-product. On one real cell at 100 reactions:
75 molecules in 6 batches against 27 molecules in 25 batches.

### `protocol.md` reads like this

```markdown
**Shared intermediate** (made once, then split 3 ways):
`O=C(O)c1ccc(NC(=O)C2CC2)cc1`

3 molecules | 1 shared reaction(s) + 3 final = 4 reactions (1.33 per molecule).

## Shared prefix — run ONCE for the whole batch
1. **amide coupling** — `Nc1ccc(C(=O)O)cc1` (buy) + `O=C(O)C1CC1` (buy) -> ...

## Diversification — one entry per molecule
### M0005 — qed 0.8932
2. **amide coupling** — `...` (make) + `NC1CCCCC1` (buy) -> ...
```

Every reactant is tagged **buy** or **make**, and every route bottoms out in purchasable stock.

---

## What it needs from you

`routes.json` — and this is the one that catches people out. Hub ranking, the campaign and the
cost model all work without routes, so a run with none completes and prints plausible numbers.
It just cannot produce any of the above, and **routes are not recoverable afterwards**: the
trajectory is gone once sampling ends.

Check before you commit to a long run:

```bash
hubbatching inspect <sample-dir>
```

Two things improve the output a lot for almost no effort:

- **`reaction_name` on each step.** The exporter infers a readable name from RGFN-format
  templates, but your SMARTS will not match that table and every protocol would print a SMARTS
  string where a reaction name belongs. If your generator knows it is doing an amide coupling,
  say so on the step and the exporter uses it.
- **`catalog_id` in your chemistry library.** It is carried into `buy_list.csv`, which turns a
  list of SMILES into something someone can actually order from.

### Routes for intermediates, not just products

A hub is a **built** intermediate. If `routes.json` has no route for it, it appears as a *leaf*
of its children's route trees, and the exporter correctly reports it as unpurchasable — telling
a chemist to order a compound the library itself makes. Emit a route for every hub as well as
every product. (The toy dataset does; `tools/make_toy_dataset.py` shows the shape.)

---

## Three things verified, not asserted

Each names its failing case, which is what makes it a check rather than a restatement:

**Every leaf is purchasable.** A route that says *buy X* for an unbuyable X is a broken cell, not
a footnote. The failing case is a fragment snapshot belonging to a *different* run: internally
complete, so its own coverage reads 100%, while this run's promoted fragments are silently bought
instead of built.

**The route tree and the flat step table agree.** They are built by different code paths — a
recursive expansion versus a linear walk — so the check can genuinely fail: an intermediate
reachable twice, or a final step whose product is not the molecule, breaks it.

**The stereo-aware SMILES matches the sampler's own record.** `records.csv`'s
`child_stereo_key` is an independent record of the same fact, which is what makes this a check.

If no catalogue is supplied, the purchasable set is inferred from the routes' own leaves, every
leaf is purchasable *by construction*, and the cell README says the check was not independently
verified. An audit that fires on everything is as useless as one that cannot fire.

---

## Interoperability

`routes.json` is written in AiZynthFinder's route-tree schema and parses with
`ReactionTree.from_dict` — verified on a real cell, 102 of 102 trees, all `is_solved`. So the
output drops into existing retrosynthesis tooling rather than needing a bespoke reader.

---

## What it does not claim

The cell README repeats these, so a directory opened in isolation is not misread:

- **Logged assembly routes, not optimal retrosynthesis.** The exact sequence the model used,
  grounded in templates that fired. A chemist may well know a shorter or more robust route.
- **Connectivity-level plans, not procedures.** No solvents, temperatures, stoichiometry, or
  stereochemical outcomes.
- **Reaction counts, not yields.** A shared prefix concentrates risk as well as cost: one bad
  step in a prefix loses the whole plate. Yields are carried in the chemistry library so this can
  be analysed, but the budget counts reactions, not successful ones.
- **Selection ran on stereo-stripped structures**, so two enantiomers can be counted as one
  molecule. The exporter measures how often that happened for your cell and reports it rather
  than restating it as a generic caveat.

---

## Programmatically

```python
from hubbatching.export import build_library, write_strategy

lib = build_library(result, source, purchasable, reward_name="seh", budget_reactions=100)
write_strategy(out_dir, lib, "my_cell / hub_batching")
```

`hubbatching.export` takes **objects, not paths** — a `CampaignResult` and a route source — so
the schema is independent of where anything happens to live. Only the CLI knows about
directories. That is what lets the same exporter serve a different data layout without changing.

Worked example: `notebooks/06_export_a_bench_plan.ipynb`.
