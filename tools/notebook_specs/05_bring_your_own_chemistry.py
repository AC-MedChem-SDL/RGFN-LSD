TITLE = "Bring your own chemistry"
SUMMARY = "Your building blocks and your reaction templates, as three files."

CELLS = [
    (
        "md",
        """
# Bring your own chemistry

A reaction-grounded generator builds molecules from exactly two inputs: a **building-block set**
and a **reaction-template set**. Together they define the action space — what the model is even
able to make. They do not define the reward.

Two reasons to care:

- **For benchmarking.** If two generators use different libraries, a comparison between them is
  partly a comparison of their catalogues. Holding the chemistry fixed isolates the generator.
- **For your lab.** Point it at *your* stock and *your* validated reactions, and everything
  downstream — flow recovery, hub selection, the cost model, the bench plan — is about chemistry
  you can actually run.

Reference: [`docs/extending/chemistry.md`](../docs/extending/chemistry.md).
""",
    ),
    (
        "md",
        """
## 1. The format

Three files in a directory.

```
<library>/
  fragments.csv     smiles[, group, cost, catalog_id]
  reactions.csv     reaction[, family, comments, yield]
  manifest.json     name, version, source, counts, defaults, checksums
```

`ChemLibrary` needs only rdkit — no gin, no torch — so you can build, inspect and validate a
library without a deep-learning stack.
""",
    ),
    (
        "py",
        """
from hubbatching.chemistry import ChemLibrary
from hubbatching.paths import repo_root

lib = ChemLibrary.from_canonical_dir(repo_root() / "data" / "libraries" / "glue_standard_v1")
print(f"{len(lib.fragments)} building blocks, {len(lib.reactions)} reaction templates")
""",
    ),
    (
        "py",
        """
# cost and yield_ are Optional -- a library need not be priced at all.
for frag in lib.fragments[:5]:
    cost = f"{frag.cost:>10.4f}" if frag.cost is not None else f"{'unpriced':>10}"
    print(f"  cost={cost}  {frag.smiles}")
print()
for rxn in lib.reactions[:3]:
    y = f"{rxn.yield_:.2f}" if rxn.yield_ is not None else "n/a "
    print(f"  yield={y}  {rxn.family or '(unnamed family)'}")
    print(f"      {rxn.smarts[:100]}...")
""",
    ),
    (
        "md",
        """
### Fill in `family`

It is optional and it matters more than it looks. `family` is what makes an exported protocol
say "amide coupling" instead of printing a SMARTS string at a chemist, and it is what groups a
library into plates of like reactions.

It also fixes a real reporting bug. A single transformation is usually encoded several times
with the reactant patterns in different orders, so it can fire from either side. That is correct
for generation and wrong for reporting: grouping by raw template id splits chemically identical
groups and **understates** how parallelisable a library is. In the shipped library, 168
templates collapse to 42 named classes.
""",
    ),
    (
        "py",
        """
from collections import Counter

families = Counter(r.family or "(unnamed)" for r in lib.reactions)
print(f"{len(lib.reactions)} templates -> {len(families)} named families\\n")
for name, n in families.most_common(8):
    print(f"  {n:3d}  {name}")
""",
    ),
    (
        "md",
        """
## 2. Build one of your own

Three files, written by hand or by a script. Below: a deliberately tiny library of the chemistry
most medicinal chemists have in a drawer.
""",
    ),
    (
        "py",
        """
import csv, hashlib, json, tempfile
from pathlib import Path

mylib = Path(tempfile.mkdtemp(prefix="mylib_")) / "my_library"
mylib.mkdir(parents=True)

FRAGMENTS = [
    # smiles, group, cost, catalog_id
    ("Nc1ccc(C(=O)O)cc1", "bifunctional", 0.42, "A-1001"),
    ("NC1CCC(C(=O)O)CC1", "bifunctional", 1.10, "A-1002"),
    ("NCc1ccccc1",        "amine",        0.08, "B-2001"),
    ("NC1CCOCC1",         "amine",        0.95, "B-2002"),
    ("OC(=O)C1CC1",       "acid",         0.31, "C-3001"),
    ("CC(=O)O",           "acid",         0.01, "C-3002"),
]
REACTIONS = [
    ("[C:1](=[O:2])[OH].[N;H2,H1;!$(N-C=O):3]>>[C:1](=[O:2])[N:3]",
     "amide coupling", "HATU, DIPEA, DMF, rt", 0.78),
    ("[c:1][Br].[c:2][B](O)O>>[c:1][c:2]",
     "Suzuki coupling", "Pd(dppf)Cl2, K2CO3, dioxane/water, 90C", 0.65),
]

with (mylib / "fragments.csv").open("w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["smiles", "group", "cost", "catalog_id"]); w.writerows(FRAGMENTS)

with (mylib / "reactions.csv").open("w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["reaction", "family", "comments", "yield"]); w.writerows(REACTIONS)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

(mylib / "manifest.json").write_text(json.dumps({
    "name": "my_library", "version": "1.0",
    "source": "hand-written for this notebook",
    "n_fragments": len(FRAGMENTS), "n_reactions": len(REACTIONS),
    "default_cost": 1.0, "default_yield": 0.5,
    "cost_units": "USD/mmol",
    "fragments_sha256": sha(mylib / "fragments.csv"),
    "reactions_sha256": sha(mylib / "reactions.csv"),
}, indent=2))

mine = ChemLibrary.from_canonical_dir(mylib)
print(f"loaded: {len(mine.fragments)} blocks, {len(mine.reactions)} templates")
""",
    ),
    (
        "md",
        """
### Canonicalisation, and what it silently drops

`ChemLibrary` canonicalises SMILES on load. **Do not skip the parse report** — a silently
dropped block is a silently smaller action space, and nothing downstream will tell you the model
could not have made the thing you were expecting.
""",
    ),
    (
        "py",
        """
from rdkit import Chem, RDLogger
RDLogger.DisableLog("rdApp.*")

candidates = ["NCc1ccccc1", "this-is-not-smiles", "OC(=O)C1CC1", "C1CC"]
for s in candidates:
    mol = Chem.MolFromSmiles(s)
    print(f"  {'ok  ' if mol else 'DROP'}  {s}")
""",
    ),
    (
        "md",
        """
## 3. Which reactions actually fire on which blocks?

The action space is not "all blocks × all templates" — it is the subset that matches. Checking
this before training is much cheaper than discovering it afterwards.
""",
    ),
    (
        "py",
        """
from rdkit.Chem import AllChem

def applicable(rxn_smarts, blocks):
    rxn = AllChem.ReactionFromSmarts(rxn_smarts)
    mols = {b: Chem.MolFromSmiles(b) for b in blocks}
    pairs = []
    for a in blocks:
        for b in blocks:
            if a == b or mols[a] is None or mols[b] is None:
                continue
            try:
                if rxn.RunReactants((mols[a], mols[b])):
                    pairs.append((a, b))
            except Exception:
                pass
    return pairs

blocks = [f[0] for f in FRAGMENTS]
for smarts, family, _, _ in REACTIONS:
    pairs = applicable(smarts, blocks)
    print(f"  {family:<18} {len(pairs):3d} applicable block pairs")
    for a, b in pairs[:2]:
        print(f"      {a}  +  {b}")
""",
    ),
    (
        "md",
        """
## 4. Using it to train

One gin binding selects a library, so *library* becomes an explicit benchmark axis alongside
generator, oracle, seed and budget:

```gin
data_factory/gin.singleton.constructor = @GlueReactionDataFactory
GlueReactionDataFactory.library_dir = 'data/libraries/my_library'
```

`GlueReactionDataFactory` subclasses upstream RGFN's `ReactionDataFactory` and builds the *same*
attributes with the *same* upstream classes — only the source of the lists changes, so the
action-space semantics are unchanged and `third_party/rgfn/` stays pristine.

This is the one part of this notebook needing the heavy stack
(`pip install 'hubbatching[generators]'`), which is why it is imported lazily: reading and
writing a library must not require torch.
""",
    ),
    (
        "md",
        """
## 5. Cost and yield are annotations, not structure

Both are optional; omit them and the `manifest.json` defaults apply. A generator with a
cost-aware policy can use them *during* generation; everything else prices routes after the fact
with the same numbers and the same formula.

**One caveat worth stating in any write-up.** The reaction budget counts *reactions*, not
*successful* reactions. A four-step route at 78% per step delivers about half of what a one-step
route does, and nothing in the headline metric notices. Yields are carried in the library so
this can be analysed — but a reaction count is a count, not a prediction of what comes out of
the flask.
""",
    ),
    (
        "py",
        """
y = REACTIONS[0][3]
print(f"per-step yield {y:.2f}\\n")
for steps in (1, 2, 3, 4):
    print(f"  {steps}-step route: {y ** steps:.2%} expected overall")
""",
    ),
]
