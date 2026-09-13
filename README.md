# hub-batching

**Library cost, not per-molecule synthesizability.** A trained reaction-grounded GFlowNet's flow
field already identifies which intermediates a screening library should be batched around.
Reading it post-hoc — no retraining, no reward change — produces libraries that deliver more
distinct high-reward molecules per unit of bench chemistry than post-hoc retrosynthetic planning
over a route-less generator's output recovers.

*"LSD" in some names here is late-stage diversification — the chemistry, not the other thing.*

<!-- IDENTITY:BEGIN -->
**Authors:** Mark Stevens and contributors (author list not final).
**Repository:** <https://github.com/AC-MedChem-SDL/RGFN-LSD>
<!-- IDENTITY:END -->

---

## Start here

```bash
pip install -e .
hubbatching demo
```

A few seconds, no GPU, no downloads. It runs the whole pipeline on 432 real molecules and prints
what each stage produced.

Then pick a door:

| | |
|---|---|
| **Reproducing a number from the paper?** | [`reproduce/`](reproduce/) — one script per figure and table, reads committed artifacts, no accelerator |
| **Using this on your own molecules?** | [`docs/INPUT_CONTRACT.md`](docs/INPUT_CONTRACT.md), then [`notebooks/`](notebooks/) |
| **Extending it?** | [`docs/extending/`](docs/extending/) — generators, rewards, strategies, chemistry, export |

And if you want to know what the method *is* before any of that:
[`docs/METHOD.md`](docs/METHOD.md).

---

## The idea in one paragraph

Labs do not make one molecule, they make a library — and a library's cost is not the sum of its
molecules' costs, because molecules sharing an intermediate can be made from it together. A
*hub* is a pre-terminal state: a real, makeable intermediate from which many distinct
high-reward products are one reaction away. A trained reaction GFlowNet has already learned how
much good chemistry lies downstream of each such state, and the flow identity lets you read that
off a frozen checkpoint. Rank hubs by it, enumerate the good ones, and assemble a library
greedily under a fixed reaction budget.

The readout is deliberately the budget a chemist actually has:

> *"I have 100 reactions. How many distinct high-reward molecules do I get?"*

---

## What you can change

Five extension points, each with a page and a runnable notebook.

| | |
|---|---|
| **Your generator** | Write the file contract from your own environment. Nothing needs to co-import. |
| **Your reward** | Any scorer; the number is attached to the molecule before hub-batching sees it. |
| **Your selection strategy** | Subclass, implement `score()`, register. Three independent layers: hubs, children, modes. |
| **Your chemistry** | Your building blocks and your reaction templates, as three files. |
| **A bench plan out** | Molecules, batches, routes, buy lists, protocols, reaction schemes. |

The core is generator-agnostic: only `hubbatching/adapters/` imports torch or rgfn, and
`hubbatching.cost` imports nothing but the standard library — so the number a paper quotes can
be audited without installing a deep-learning stack. Both properties are enforced in CI.

---

## Layout

```
src/hubbatching/    the method: flow recovery, hub/child/mode selection, cost model, CLI
  adapters/           the ONLY place a specific generator is touched
  eval/               the pricing seam: LibrarySet -> Evaluator -> reactions
third_party/rgfn/   vendored upstream RGFN, unmodified (docs/PATCHES.md says how to check)
benchmarks/         comparing against other selection methods and planners
reproduce/          one script per published figure and table
artifacts/          the committed intermediates those scripts read
examples/toy/       a complete, valid input contract -- 432 real molecules
notebooks/          worked examples, one per extension point
data/libraries/     swappable chemistry: fragments + reaction templates
setup/              fetch scripts for checkpoints and third-party tools
docs/               method, contracts, extension guides
```

---

## Reproducibility tiers

Full replication is not laptop-scale — the published evaluation includes hundreds of GPU-hours
of docking. So reproduction is stratified, and each tier stands alone.

| tier | what it does | cost | who wants it |
|---|---|---|---|
| **T0** | install, then run the whole pipeline on toy inputs | seconds, CPU | anyone, first |
| **T1** | regenerate **every** published figure and table from committed `artifacts/` | minutes, CPU | a reviewer |
| **T2** | re-run selection and evaluation from archived checkpoints and enumerations | hours, GPU | someone extending |
| **T3** | retrain the generators from scratch | GPU-weeks; documented, not expected | a replication effort |

T1 is the one that matters: it is the claim that the numbers in the paper come from the code in
this repository, and it needs no accelerator. T0 and T1 both run in CI, so the claim is checked
rather than asserted.

---

## Why there are two repositories

The research tree is optimised for finding things out — experiment logs, scheduler scripts,
superseded numbers, per-cell result directories. This one is optimised for a reader confirming a
claim in twenty minutes, and for someone using the method on their own problem.

| | research tree | this repository |
|---|---|---|
| optimised for | discovery over months | verification in minutes, and reuse |
| contains | every experiment ever run, cluster wiring, full provenance | the method, the evaluation, one command per published number |
| compute assumed | GPU cluster | a laptop, for everything except retraining |

<!-- IDENTITY:BEGIN -->
## Anonymity

Author identity is confined to `NOTICE`, `CITATION.cff`, and the block at the top of this file.
`tools/check_identity.py` enforces that; `tools/make_anon_snapshot.sh` builds the double-blind
review artifact and refuses to emit one if any identity survives. See
[`docs/ANONYMITY.md`](docs/ANONYMITY.md).
<!-- IDENTITY:END -->

## Licence

Apache-2.0 (`LICENSE`). Vendored and fetched third-party components keep their own licences —
see [`NOTICE`](NOTICE) and [`THIRD_PARTY.md`](THIRD_PARTY.md).
