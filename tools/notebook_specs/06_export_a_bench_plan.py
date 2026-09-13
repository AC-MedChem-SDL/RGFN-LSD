TITLE = "Export a bench plan"
SUMMARY = "Turn a selected library into buy lists, protocols and reaction schemes."

CELLS = [
    (
        "md",
        """
# Export a bench plan

This is the end of the pipeline and the point of it. Everything so far produced a *number*.
Here we produce a directory a synthetic chemist can work from without reading any of our code:
what to buy, what reaction to run at each step, and which molecules are made together off one
shared intermediate.

Reference: [`docs/extending/export.md`](../docs/extending/export.md).
""",
    ),
    (
        "py",
        """
import json, shutil, tempfile
from pathlib import Path

from hubbatching.paths import repo_root
from hubbatching.adapters.file_adapter import FileAdapter

TOY = repo_root() / "examples" / "toy"
OUT = Path(tempfile.mkdtemp(prefix="benchplan_"))

GATE, CUTOFF, BUDGET = 0.80, 0.50, 30

adapter = FileAdapter(str(TOY))
report = adapter.validate()
print("can export a bench plan:", report["can_export_bench_plan"])
print("routes available:", report["n_routes"])
""",
    ),
    (
        "md",
        """
## 1. The check that decides whether any of this is possible

`routes.json` is the difference between a number and a bench plan, and it is **not recoverable**
after sampling ends — the trajectory is gone.

A run without routes still completes and still prints plausible numbers. It just cannot produce
anything below. In this project three of four generators wrote a well-formed *empty*
`routes.json`, exited zero, and were promoted; the loss surfaced months later and cost a
re-sample of 36 of 40 cell-seeds.

So this check is worth thirty seconds before any long run.
""",
    ),
    (
        "py",
        """
for blocker in report["blockers"] or ["(nothing missing)"]:
    print(" ", blocker)
""",
    ),
    (
        "md",
        """
## 2. Build both libraries

Both strategies, identical chemistry, identical gate, identical diversity rule. The contrast
between the two exported directories is the deliverable, not a by-product.
""",
    ),
    (
        "py",
        """
from hubbatching.campaign import BestCandidateStrategy, Candidate, HubBatchingStrategy

sample = adapter.sample_flow_records()
comps = json.loads((TOY / "compositions.json").read_text())
hubs = adapter.enumerated_hubs(with_reactions=True)   # reactions needed to write routes

best, parents = {}, {}
for r in sample.records:
    if r.child_key not in best or r.reward > best[r.child_key]:
        best[r.child_key] = r.reward
    parents.setdefault(r.child_key, set()).add(r.hub_key)

pool = [
    Candidate(smiles=s, reward=rw,
              num_reactions=comps.get(s, {}).get("num_reactions", 1),
              promoted=tuple(comps.get(s, {}).get("promoted", ())),
              parents=tuple(sorted(parents.get(s, ()))))
    for s, rw in best.items()
]

common = dict(target="qed", reward_threshold=GATE, similarity=CUTOFF, higher_is_better=True)
budget = ("reactions", BUDGET)

results = {
    "hub_batching": HubBatchingStrategy(hubs, None, **common).run(budget),
    "best_candidate": BestCandidateStrategy(pool, None, hub_compositions=comps, **common).run(budget),
}
for name, r in results.items():
    print(f"  {name:<16} {len(r.accepted):3d} molecules   {r.total_reactions:3d} reactions")
""",
    ),
    (
        "md",
        """
## 3. Resolve routes and write the tree

`hubbatching.export` takes **objects, not paths** — a `CampaignResult` and a route source — so
the schema is independent of where anything lives. Only the CLI knows about directories.

Note that the route map includes a route for every **hub**, not just every product. A hub is a
built intermediate; without its own route it appears as a *leaf* of its children's route trees
and the exporter correctly reports it as unpurchasable, telling a chemist to order a compound
the library itself makes.
""",
    ),
    (
        "py",
        """
from hubbatching.export import (
    CellProvenance, LoggedRouteSource, RouteAssembler,
    build_library, leaf_audit, write_cell_readme, write_dataset_readme, write_strategy,
)
from hubbatching.export.routes import final_step_index, load_stereo_records

routes = sample.routes
# With no supplier catalogue, the purchasable set is whatever the routes bottom out in.
built = set(routes)
purchasable = set()
for r in routes.values():
    if r.get("seed") and r["seed"] not in built:
        purchasable.add(r["seed"])
    for step in r.get("steps", []):
        purchasable |= {x for x in (step.get("reactants") or []) if x not in built}

assembler = RouteAssembler(routes, purchasable)
finals, extra_builds, _ = final_step_index(hubs)
stereo_records, stereo_stats = load_stereo_records(TOY)

print(f"{len(routes)} routes, {len(purchasable)} purchasable building blocks")
print(f"stereo ambiguity: {stereo_stats['n_multi_stereo_keys']} of {stereo_stats['n_keys']} keys")
""",
    ),
    (
        "py",
        """
cell_dir = OUT / "toy_qed_seedtoy"
summaries, audits = [], {}

for name, result in results.items():
    source = (LoggedRouteSource(assembler, final_steps=finals, extra_builds=extra_builds)
              if name == "hub_batching" else LoggedRouteSource(assembler))
    lib = build_library(result, source, purchasable, reward_name="qed", budget_reactions=BUDGET,
                        stereo_check=stereo_records or None)
    audit = leaf_audit(lib.trees, purchasable)
    audits[name] = audit
    summaries.append(write_strategy(cell_dir / name, lib, f"toy / {name}", schemes=True))
    print(f"  {name:<16} {len(lib.molecules):3d} molecules in {len(lib.batches):2d} batches, "
          f"{audit.n_unpurchasable} unpurchasable leaves")
""",
    ),
    (
        "md",
        """
`0 unpurchasable leaves` on both arms is the check passing. It is a check that can genuinely
fail — the usual cause is a fragment snapshot belonging to a *different* run: internally
complete, so its own coverage reads 100%, while this run's intermediates are silently bought
instead of built.
""",
    ),
    (
        "md",
        """
## 4. What a chemist actually receives
""",
    ),
    (
        "py",
        """
import csv

print("=== batches.csv (hub_batching) ===")
with (cell_dir / "hub_batching" / "batches.csv").open() as fh:
    for row in list(csv.DictReader(fh))[:5]:
        print(f"  {row['batch_id']}  {row['n_molecules']:>2} molecules  "
              f"{row['reactions_per_molecule']:>5} rxn/molecule   {row['shared_intermediate']}")

print("\\n=== the same, best_candidate ===")
with (cell_dir / "best_candidate" / "batches.csv").open() as fh:
    for row in list(csv.DictReader(fh))[:5]:
        print(f"  {row['batch_id']}  {row['n_molecules']:>2} molecules  "
              f"{row['reactions_per_molecule']:>5} rxn/molecule   {row['shared_intermediate']}")
""",
    ),
    (
        "py",
        """
biggest = max(
    csv.DictReader((cell_dir / "hub_batching" / "batches.csv").open()),
    key=lambda r: int(r["n_molecules"]),
)
batch_dir = cell_dir / "hub_batching" / biggest["batch_id"].replace("B", "batch_")
print((batch_dir / "protocol.md").read_text()[:2000])
""",
    ),
    (
        "py",
        """
print("=== buy_list.csv ===")
print((batch_dir / "buy_list.csv").read_text())
""",
    ),
    (
        "md",
        """
Every reactant is tagged **buy** or **make**, shared purchases are separated from diverging
ones, and every route bottoms out in something orderable. If your chemistry library carries
`catalog_id`, it appears here too — which turns a list of SMILES into something someone can
actually order from.
""",
    ),
    (
        "py",
        """
from IPython.display import Image, display

scheme = batch_dir / "scheme.png"
print(scheme)
display(Image(filename=str(scheme)))
""",
    ),
    (
        "md",
        """
## 5. `routes.json` is interoperable

It is written in AiZynthFinder's route-tree schema, so the output drops into existing
retrosynthesis tooling rather than needing a bespoke reader. (Verified on a real cell: 102 of
102 trees parse with `ReactionTree.from_dict`, all `is_solved`.)
""",
    ),
    (
        "py",
        """
trees = json.loads((cell_dir / "hub_batching" / "routes.json").read_text())
first = next(iter(trees.values()))
print(json.dumps(first, indent=1)[:900])
""",
    ),
    (
        "md",
        """
## From the shell

Everything above is one command:

```bash
hubbatching export --analysis-dir examples/toy \\
                   --enum-children examples/toy/enum_children.json \\
                   --reward-threshold 0.80 --budget-reactions 30 --seed toy
```

## What this does not claim

The cell README repeats these, so a directory opened in isolation is not misread:

- **Logged assembly routes, not optimal retrosynthesis.** A chemist may know a shorter route.
- **Connectivity-level plans, not procedures.** No solvents, temperatures, or stoichiometry.
- **Reaction counts, not yields.** A shared prefix concentrates *risk* as well as cost: one bad
  step in a prefix loses the whole plate.
- **Selection ran on stereo-stripped structures**, so two enantiomers can count as one molecule.
  The exporter measures how often that happened rather than restating it as a generic caveat.
""",
    ),
    (
        "py",
        """
shutil.rmtree(OUT, ignore_errors=True)
print("cleaned up", OUT)
""",
    ),
]
