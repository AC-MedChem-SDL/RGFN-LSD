# Bring your own chemistry

A reaction-grounded generator builds molecules from exactly two inputs: a **building-block set**
and a **reaction-template set**. Together they define the action space — what the model is even
able to make. They do not define the reward, and swapping them changes what can be built without
changing what is wanted.

This matters for benchmarking as much as for chemistry. If two generators use different
libraries, a comparison between them is partly a comparison of their catalogues. Holding the
chemistry fixed is what isolates the generator.

It is also the most direct way to make this useful to your own lab: point it at *your* stock
and *your* validated reactions, and everything downstream — flow recovery, hub selection, the
cost model, the bench plan — is about chemistry you can actually run.

---

## The format

A library is one directory of three files:

```
<library>/
  fragments.csv     smiles[, group, cost, catalog_id]
  reactions.csv     reaction[, family, comments, yield]
  manifest.json     name, version, source, counts, defaults, checksums
```

### `fragments.csv`

| column | required | meaning |
|---|---|---|
| `smiles` | yes | the building block |
| `group` | no | a label you can filter on |
| `cost` | no | price per unit, your units (defaults to `default_cost`) |
| `catalog_id` | no | supplier catalogue number — carried into buy lists |

```csv
smiles,group,cost,catalog_id
BrCC1CCCCC1,,0.24083424,
BrCc1ccccc1,,0.033865326,
```

Fill in `catalog_id` if you have it. It costs nothing now and turns an exported buy list into
something someone can actually order from.

### `reactions.csv`

| column | required | meaning |
|---|---|---|
| `reaction` | yes | reaction SMARTS, `reactants >> product` |
| `family` | no | a human-readable class name, e.g. `Buchwald` |
| `comments` | no | free text — conditions, caveats |
| `yield` | no | expected yield 0–1 (defaults to `default_yield`) |

```csv
reaction,family,comments,yield
"[C:1](=[O:2])[OH].[N;H2,H1;!$(N-C=O):3]>>[C:1](=[O:2])[N:3]",amide coupling,HATU/DIPEA/DMF,0.75
```

Fill in `family`. It is what makes an exported protocol say "amide coupling" instead of printing
a SMARTS string at a chemist, and it is what groups a library into plates of like reactions.

### `manifest.json`

Provenance, and it is not decoration — it is how someone six months from now works out which
library a result came from:

```json
{
  "name": "my_library", "version": "1.0",
  "source": "our internal stock list, 2026-09",
  "n_fragments": 418, "n_reactions": 112,
  "default_cost": 1.0, "default_yield": 0.5,
  "cost_units": "USD/mmol",
  "fragments_sha256": "...", "reactions_sha256": "..."
}
```

---

## Using it

```python
from hubbatching.chemistry import ChemLibrary

lib = ChemLibrary.from_canonical_dir("data/libraries/my_library")
print(len(lib.fragments), len(lib.reactions))
```

`ChemLibrary` needs only rdkit — no gin, no torch — so you can build, inspect and validate a
library without a deep-learning stack.

To train a generator on it, one gin binding selects it:

```gin
data_factory/gin.singleton.constructor = @GlueReactionDataFactory
GlueReactionDataFactory.library_dir = 'data/libraries/my_library'
```

`GlueReactionDataFactory` subclasses upstream RGFN's `ReactionDataFactory` and builds the *same*
attributes with the *same* upstream classes, so the action-space semantics are unchanged — only
the source of the lists differs. The vendored `third_party/rgfn/` stays pristine.

This is the one part of this page that needs the heavy stack (`pip install
'hubbatching[generators]'`), which is why it is imported lazily: reading and writing a library
must not require torch.

---

## What ships

`data/libraries/glue_standard_v1/` — 418 priced building blocks and 112 reaction templates with
yields, repackaged from an existing public set. It exists so that *library* is an explicit
benchmark axis alongside generator, oracle, seed and budget, rather than an uncontrolled
difference between models.

---

## Building your own

Four things to get right.

**Canonicalise.** `ChemLibrary` canonicalises SMILES on load and will tell you which rows failed
to parse. Do not skip the report — a silently dropped block is a silently smaller action space.

**Reaction SMARTS canonicalisation is not well defined in RDKit**, so templates are keyed on the
whitespace-normalised string. Two templates that differ only in spacing are two templates. Keep
them consistent.

**Anchoring matters.** A single chemical transformation is often encoded several times with the
reactant patterns in different orders, so it can fire from either side. That is correct for
generation and wrong for reporting: grouping by raw template id splits chemically identical
groups and understates how parallelisable a library is. Group by `family` instead. In the
library that ships, 168 templates collapse to 42 named classes.

**Cost and yield are annotations, not structure.** A generator with a cost-aware policy can use
them during generation; everything else prices routes after the fact with the same numbers and
the same formula. Either way they are optional — omit them and the defaults in `manifest.json`
apply.

### A caveat on yield

The reaction budget counts *reactions*, not *successful* reactions. A four-step route at 75%
per step delivers about a third of what a one-step route does, and nothing in the headline
metric notices. Yields are carried in the library so this can be analysed, and a route-length
distribution should accompany any cost claim — but be clear that a reaction count is a count,
not a prediction of what comes out of the flask.

---

## A worked example

Notebook `05_bring_your_own_chemistry.ipynb` builds a small library from scratch, loads it,
inspects the action space it implies, and runs a campaign on it. `tools/make_toy_dataset.py`
shows the same chemistry used directly: six bifunctional cores, six caps, twelve amines, two
reaction steps, 432 real molecules.
