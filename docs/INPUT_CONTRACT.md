# The input contract

**What your generator must write so hub-batching can read it.**

This is the integration surface. If your model can produce these files, hub-batching works on
it — no shared Python environment, no dependency negotiation, no changes to your code beyond
writing some CSV and JSON at the end of a sampling run.

That design is not a convenience. The generators in the published comparison live in mutually
incompatible conda environments and no two of them co-import; a file contract is the only thing
that made them comparable. Yours is unlikely to be worse behaved than those, but the same route
is open either way.

---

## The short version

```
<sample-dir>/
  records.csv          REQUIRED   one row per observed hub -> child transition
  meta.json            REQUIRED   log Z, reward direction, provenance
  routes.json          strongly recommended — and NOT recoverable later
  compositions.json    if your generator promotes intermediates into a dynamic library
  visit_counts.json    optional   enables the reward-free hub estimator
  enum_children.json   required for hub-batching; written by a second, enumeration pass
```

Check what you have before running anything long:

```bash
hubbatching inspect path/to/sample-dir
```

It prints which stages your data can feed and names what is missing for the rest.

## Writing the files

Use `hubbatching.adapters.artifacts`. It is **pure standard library** precisely so it imports
inside whatever environment your model needs — no rdkit, no torch, no version conflicts:

```python
import sys
sys.path.insert(0, "/path/to/hubbatching/src")
from hubbatching.adapters import artifacts

artifacts.write_records(out / "records.csv", rows)
artifacts.write_json(out / "meta.json", meta)
```

If even that import is awkward, copy `artifacts.py` and `route_steps.py` next to your worker.
They are written to tolerate it: `artifacts.py` locates `route_steps.py` either beside itself or
in an installed `hubbatching`.

---

## 1. `records.csv` — REQUIRED

One row per observed transition `h --[one reaction]--> x --[stop]--> terminal`. This is what hub
ranking reads, and it is the only file that is truly mandatory.

| column | type | meaning |
|---|---|---|
| `hub_key` | str | the hub (intermediate), canonical SMILES, **stereochemistry stripped** |
| `child_key` | str | the terminal product, same key function |
| `reward` | float | your oracle's raw value for the child |
| `log_reward` | float | `log R(x)` — the **shaped** log reward your objective trains against |
| `log_pf_move` | float | `log P_F(x \| h)` — forward log-prob of the one reaction |
| `log_pb_move` | float | `log P_B(h \| x)` — your model's **own trained** backward policy |
| `log_pf_stop` | float | `log P_F(stop \| x)` — the terminating factor |
| `hub_depth` | int | minimum reactions to build `h` from purchasable stock |
| `hub_stereo_key` | str | stereo-aware hub SMILES (optional; defaults to `hub_key`) |
| `child_stereo_key` | str | stereo-aware child SMILES (optional; defaults to `child_key`) |

All logs are natural logs. Extra columns are fine — every reader parses by name, so you can add
your own without breaking anything.

### Four things that will bite you

**Do not drop `log_pf_stop`.** It is zero in log space only for a true leaf. Omitting it biases
the recovered flow *upward* for exactly those products that are eager to react further — which
are disproportionately the interesting ones. The flow identity is

```
log F̂(h ; x) = log R(x) + log P_B(h|x) − log P_F(x|h) − log P_F(stop|x)
```

and every term is load-bearing.

**`log_pb_move` must be your model's own trained backward policy**, not a uniform stand-in. The
whole method reads a field the model learned; substituting a uniform `P_B` measures something
else. If your backward policy is deterministic, its contribution is genuinely 0 — that is fine
and is not the same thing as ignoring it.

**Score with the same policy you sampled with.** If you sample from an exploratory policy
(say 95% trained, 5% uniform) but score with the pure trained policy, the sampled distribution
and the recovered `P_F` disagree, and the per-hub spread stops being a clean flow-matching
residual. Sample with the pure policy, or score with the one you sampled with.

**One key function, everywhere.** `hub_key`, `child_key`, and every key in `routes.json` and
`compositions.json` must come from the same function. A route keyed differently from its hub is
worse than no route at all: the lookup returns nothing, the caller prices the hub instead of the
child, and nothing raises. The convention here is RDKit canonical SMILES with stereochemistry
removed:

```python
from rdkit import Chem

def key(smiles: str) -> str:
    mol = Chem.MolFromSmiles(smiles)
    Chem.RemoveStereochemistry(mol)
    return Chem.MolToSmiles(mol)
```

---

## 2. `meta.json` — REQUIRED

```json
{
  "model": "mymodel",
  "reward_name": "seh",
  "log_z": 74.76,
  "higher_is_better": true,
  "n_trajectories": 50000,
  "strip_stereo": true
}
```

`log_z` and `higher_is_better` are required because they **change the answer** rather than
label it: `log_z` puts the reward-free visitation estimator on the same absolute scale as the
flow estimate, and getting the reward direction wrong inverts every ranking. They are not
defaulted for that reason — a missing `meta.json` is an error, not a shrug.

---

## 3. `routes.json` — strongly recommended, and unrecoverable if skipped

```json
{
  "<child_key>": {
    "seed": "<purchasable starting block SMILES>",
    "num_reactions": 2,
    "steps": [
      {
        "reaction": "<reaction SMARTS or template id>",
        "reactants": ["<co-reactant SMILES>"],
        "input": "<input molecule SMILES>",
        "product": "<product SMILES>"
      }
    ]
  }
}
```

Steps are in synthesis order, the last step's `product` is the molecule, and every route bottoms
out in purchasable stock.

> **Read this paragraph before deciding to skip routes.**
>
> Hub ranking, the campaign, and the cost model all work without routes. A run with none will
> complete, print plausible numbers, and look fine. What you cannot then do is produce a bench
> plan — and you cannot go back and add them, because the trajectory is gone once sampling ends
> and `compositions.json` keeps only a reaction count.
>
> In this project, three of four generators wrote a well-formed *empty* `routes.json`, exited
> zero, and were promoted. The loss surfaced months later when the comparison needed routes, and
> cost a full re-sample of 36 of 40 cell-seeds.
>
> If your generator genuinely has no synthesis routes — a fragment-attachment model, for
> instance — **declare it** (`FileAdapter(..., routes_expected=False)`) rather than leaving the
> file empty and hoping the reader notices.

---

## 4. `compositions.json` — needed whenever intermediates cost anything

```json
{ "<key>": { "num_reactions": 3, "promoted": ["<fragment smiles>", "..."] } }
```

`num_reactions` is the **fully nested** build cost: if your generator promotes intermediates
into a dynamic library and attaches them in one step, this must include the cost of building
those fragments too. `promoted` lists the dynamic-library fragments the molecule attaches, so
the cost model can charge each distinct one exactly once across a campaign.

**It must contain an entry for every hub, not just every product.** A hub absent from this file
prices at zero, which silently gives the best-candidate baseline its shared scaffolds for free
and inflates hub-batching's apparent advantage. The run does not fail; it reports a better
number. If your generator has no dynamic library, do not hand-write this — call the helper,
which gets the hub entries right by construction:

```python
from hubbatching.adapters.artifacts import compositions_from_records
compositions = compositions_from_records(rows)   # child: depth+1, hub: depth
```

---

## 5. `enum_children.json` — required for hub-batching

Written by a **second pass**: pick the hubs you want, then exhaustively enumerate and score each
one's one-reaction children.

```json
{
  "hubs": [
    {
      "hub_key": "<stereo-stripped>",
      "hub_input": "<stereo-aware; disambiguates stereoisomeric hubs>",
      "depth": 1,
      "promoted": [],
      "uncertainty": 0.019,
      "n_effective": 12,
      "children": [
        {
          "smiles": "<product>",
          "reward": 0.87,
          "added_promoted": [],
          "reaction": [ { "reaction": "...", "reactants": ["..."], "input": "...", "product": "..." } ]
        }
      ]
    }
  ]
}
```

**The order of `hubs` is the strategy.** Hub-batching walks the list top to bottom, so the
ranking your hub-selection step produced is carried by the file itself. Nothing downstream
re-sorts it — re-sorting would silently substitute a different strategy for the one you ran.

`added_promoted` lists dynamic-library fragments attached in the *final* reaction; it is what
the `free_frag` child policy reads to tell a free diversification from one that needs a new
fragment built. Leave it empty if every block you use is purchasable.

To produce the hub list in the first place:

```bash
hubbatching pick-hubs --records sample/records.csv --out sample/hubs.csv \
    --pool all --order flow_desc --n-hubs 200
```

Then enumerate each row of `hubs.csv` in your own environment and write the file above.

---

## 6. `visit_counts.json` — optional

```json
{ "<hub_key>": 412 }
```

How many sampled trajectories passed through each hub. It enables a **reward-free** estimate of
the same quantity the flow identity recovers, which is worth having: the two estimates share no
terms, so disagreement between them (after the `log Z` shift) is a direct diagnostic that
something has broken trajectory balance.

---

## A worked example

`examples/toy/` is a complete, valid contract directory — 36 hubs, 432 real molecules, every
file above. Read it alongside this page; it is small enough to open. It is produced by
`tools/make_toy_dataset.py`, which is a working reference implementation of a writer.

## Checklist

- [ ] `records.csv` has all eight required columns, natural logs throughout
- [ ] `log_pf_stop` is present and not assumed zero
- [ ] `log_pb_move` comes from the trained backward policy
- [ ] one key function for records, routes, and compositions
- [ ] `meta.json` carries `log_z` and `higher_is_better`
- [ ] `routes.json` is non-empty, or `routes_expected=False` is a deliberate declaration
- [ ] `compositions.json` has an entry for every **hub** as well as every product
- [ ] `enum_children.json` is in your ranking's order
- [ ] `hubbatching inspect <dir>` reports no blockers
