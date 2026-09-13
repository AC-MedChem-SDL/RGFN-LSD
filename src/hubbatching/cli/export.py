"""``hubbatching export`` -- turn a selected library into something a chemist can make.

This is the end of the pipeline and the point of it. Everything upstream produces a *number*;
this produces a directory a synthetic chemist can work from without reading any of our code:
what to buy, what reaction to run at each step, which molecules are made together off one shared
intermediate, and what each intermediate looks like.

The layout, per cell = (generator, target, seed), per strategy::

    <out-root>/<generator>_<target>_seed<N>/
      README.md                 gate, budget, every input by path and checksum, the caveats
      hub_batching/
        molecules.csv           one row per molecule
        batches.csv             one row per batch (a shared intermediate and its diversifications)
        routes.json             AiZynth-compatible route trees -- an interoperable view
        steps.csv               one row per reaction step -- the flat view
        batch_01/
          buy_list.csv          what to order for this batch
          protocol.md           ordered, human-readable steps
          scheme.png            the rendered reaction scheme
        batch_02/ ...
      best_candidate/ ...

**Both strategies are exported, always.** They run on identical chemistry -- same enumeration,
same gate, same budget, only the chooser differs -- so the two directories are directly
comparable, and the contrast is the point rather than a by-product. On one real cell that reads
as 75 molecules in 6 batches against 27 molecules in 25 batches for the same 100 reactions.

    hubbatching export --analysis-dir <sample-dir> \\
                       --enum-children <enum-dir>/enum_children.json \\
                       --reward-threshold <your gate> --seed 43

**The gate is required and never guessed.** Thresholds are empirical grid points -- the score at
which 5% of property-matched decoys pass -- and rounding one breaks the property it is defined
by. Defaulting it would silently export a different library.

Three things are verified rather than asserted, and each names its failing case:

* **every leaf is purchasable.** A route that says *buy X* for an unbuyable X is a broken cell,
  not a footnote. The failing case is a fragment snapshot belonging to a different run:
  internally complete, so its own coverage reads 100%, while this run's promoted fragments are
  silently bought instead of built.
* **the route tree and the flat step table agree.** They are built by different code paths -- a
  recursive expansion versus a linear walk -- so the check can genuinely fail.
* **the stereo-aware SMILES matches the sampler's own record.** A route keyed differently from
  its molecule prices the wrong thing with no error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="hubbatching export",
        description="Export a selected library as a chemist-facing route dataset.",
    )
    ap.add_argument(
        "--analysis-dir",
        required=True,
        help="the generator's contract directory (records.csv, meta.json, routes.json, "
        "compositions.json) -- see docs/INPUT_CONTRACT.md",
    )
    ap.add_argument("--enum-children", required=True, help="enum_children.json")
    ap.add_argument(
        "--snapshot",
        default="",
        help="promoted-fragment recipes (fragments_<N>.json). Omit for a generator with no "
        "dynamic library -- every block is then base stock and there is nothing to nest.",
    )
    ap.add_argument(
        "--reward-threshold",
        type=float,
        required=True,
        help="the hit gate, in the reward's own units. REQUIRED and never defaulted.",
    )
    ap.add_argument("--similarity", type=float, default=0.5, help="diversity cutoff (default 0.5)")
    ap.add_argument("--higher-is-better", type=lambda s: s.lower() != "false", default=None)
    ap.add_argument("--budget-reactions", type=int, default=100)
    ap.add_argument("--child-policy", default="reward", choices=["reward", "free_frag"])
    ap.add_argument("--prebuild-k", type=int, default=0)
    ap.add_argument("--generator", default="", help="default: meta.json 'model'")
    ap.add_argument("--target", default="", help="default: meta.json 'reward_name'")
    ap.add_argument("--seed", default="", help="seed label for the cell directory name")
    ap.add_argument("--cell", default="", help="override the whole cell directory name")
    ap.add_argument(
        "--out-root", default="", help="default: $HUBBATCH_RESULTS/routes, else ./routes"
    )
    ap.add_argument("--no-schemes", action="store_true", help="skip the batch scheme PNGs")
    ap.add_argument(
        "--strategies",
        default="hub_batching,best_candidate",
        help="which arms to export. Both by default, because the comparison is the point: they "
        "run on identical chemistry and only the chooser differs.",
    )
    ap.add_argument(
        "--rank-by",
        default="build_score",
        help="fragment ranking for --prebuild-k (build_score | fanout | reward)",
    )
    ap.add_argument(
        "--note",
        action="append",
        default=[],
        help="extra 'known limitations' line for this cell's README (repeatable)",
    )
    a = ap.parse_args()

    from hubbatching.adapters.file_adapter import FileAdapter
    from hubbatching.campaign import (
        BestCandidateStrategy,
        Candidate,
        HubBatchingStrategy,
        rank_fragments,
    )
    from hubbatching.child_select import make_child_policy
    from hubbatching.cost import load_cost_table_from_snapshot
    from hubbatching.export import (
        CellProvenance,
        LoggedRouteSource,
        RouteAssembler,
        build_library,
        leaf_audit,
        write_cell_readme,
        write_dataset_readme,
        write_strategy,
    )
    from hubbatching.export.routes import final_step_index, load_stereo_records
    from hubbatching.paths import results as results_root

    def assembler_leaf_set(route_map) -> set:
        """Every SMILES a route bottoms out in -- the implied stock when no catalogue is given."""
        built = {k for k in route_map}
        leaves = set()
        for r in route_map.values():
            seed = r.get("seed")
            if seed and seed not in built:
                leaves.add(seed)
            for step in r.get("steps", []):
                for reactant in step.get("reactants", []) or []:
                    if reactant not in built:
                        leaves.add(reactant)
        return leaves

    adir = Path(a.analysis_dir)
    adapter = FileAdapter(str(adir), enum_children=a.enum_children)
    report = adapter.validate()
    if not report["can_export_bench_plan"]:
        print("cannot export a bench plan from this directory:", file=sys.stderr)
        for b in report["blockers"]:
            print(f"  - {b}", file=sys.stderr)
        print(
            "\nRoutes are what a bench plan is made of, and they are NOT recoverable after "
            "sampling ends. See docs/INPUT_CONTRACT.md.",
            file=sys.stderr,
        )
        return 1

    meta = adapter.meta
    generator = a.generator or meta.get("model") or "unknown"
    target = a.target or meta.get("reward_name") or "unknown"
    higher = a.higher_is_better
    if higher is None:
        higher = bool(meta.get("higher_is_better", True))
    cell = a.cell or (f"{generator}_{target}_seed{a.seed}" if a.seed else f"{generator}_{target}")
    out_root = Path(a.out_root) if a.out_root else results_root() / "routes"
    cell_dir = out_root / cell

    # ---------------------------------------------------------------- load, one pass each
    sample = adapter.sample_flow_records()
    comps = json.loads((adir / "compositions.json").read_text())
    # ONE loader, with reactions attached. There is deliberately no second implementation to
    # parity-check against: two loaders over the same file drift, and when they do every
    # exported artifact describes a library that was never selected, with nothing raising.
    hubs = adapter.enumerated_hubs(with_reactions=True)

    n_children = sum(len(h.children) for h in hubs)
    n_with_rxn = sum(1 for h in hubs for c in h.children if getattr(c, "template", ""))
    coverage = n_with_rxn / n_children if n_children else 0.0
    print(
        f"\n[export] {cell}: {len(hubs)} hubs, {n_children:,} enumerated children, "
        f"reaction coverage {coverage:.2%}"
    )
    if coverage < 1.0:
        print(
            f"[export] WARNING: {1 - coverage:.2%} of enumerated children carry no reaction. "
            "Those cannot be routed and will be dropped if selected."
        )

    snapshot = json.loads(Path(a.snapshot).read_text()) if a.snapshot else {}
    cost_table = load_cost_table_from_snapshot(snapshot)
    purchasable = set(snapshot.get("initial_smiles_set") or ())
    recipes = snapshot.get("smiles_to_route") or {}
    # Recipes WIN on overlap: a promoted fragment's own logged build is the authority on how it
    # is made, and it is the sub-route that gets expanded inline so no step ever says "buy X"
    # for an X the library itself builds.
    routes = {**sample.routes, **recipes}
    print(
        f"[export] catalogue {len(purchasable)} blocks | {len(recipes)} fragment recipes | "
        f"{len(sample.routes):,} sampled routes -> {len(routes):,} route entries"
    )
    # Without a catalogue the leaf audit would compare every leaf against an EMPTY set and
    # report all of them unpurchasable -- a check that always fires, which is exactly as useless
    # as one that cannot. So derive the stock from the routes' own leaves and say plainly that
    # the check was not independently verified for this cell.
    catalogue_known = bool(purchasable)
    if not catalogue_known:
        purchasable = assembler_leaf_set(routes)
        print(
            f"[export] NOTE: no catalogue supplied (--snapshot), so the purchasable set was "
            f"inferred from the routes' own {len(purchasable)} leaves. Every leaf is then "
            "purchasable by construction; that check is NOT independently verified here."
        )

    prebuilt = None
    if a.prebuild_k > 0:
        ranked = rank_fragments(
            hubs, cost_table, a.reward_threshold, method=a.rank_by, higher_is_better=higher
        )
        prebuilt = {f for f, _ in ranked[: a.prebuild_k]}

    finals, extra_builds, n_missing_product = final_step_index(hubs)
    if n_missing_product:
        print(f"[export] {n_missing_product:,} children carry no product and cannot be routed")

    assembler = RouteAssembler(routes, purchasable)
    stereo_records, stereo_stats = load_stereo_records(adir)
    if stereo_stats["n_keys"]:
        print(
            f"[export] {len(stereo_records):,} stereo records for the independent SMILES check; "
            f"{stereo_stats['n_multi_stereo_keys']:,} of {stereo_stats['n_keys']:,} flat keys "
            "were seen in more than one configuration (the enantiomer merge, measured)"
        )

    # candidate pool for the best-candidate arm
    best, parents = {}, {}
    for r in sample.records:
        if r.child_key not in best or (r.reward > best[r.child_key]) == higher:
            best[r.child_key] = r.reward
        parents.setdefault(r.child_key, set()).add(r.hub_key)
    cands = [
        Candidate(
            smiles=s,
            reward=rw,
            num_reactions=int(comps.get(s, {}).get("num_reactions", 1)),
            promoted=tuple(comps.get(s, {}).get("promoted", ())),
            parents=tuple(sorted(parents.get(s, ()))),
        )
        for s, rw in best.items()
    ]

    common = dict(
        target=target,
        reward_threshold=a.reward_threshold,
        similarity=a.similarity,
        higher_is_better=higher,
    )
    budget = ("reactions", a.budget_reactions)

    # ---------------------------------------------------------------- export each strategy
    summaries, audits = [], {}
    for name in [s.strip() for s in a.strategies.split(",") if s.strip()]:
        if name == "hub_batching":
            result = HubBatchingStrategy(
                hubs,
                cost_table,
                child_policy=make_child_policy(a.child_policy),
                prebuilt_fragments=prebuilt,
                **common,
            ).run(budget)
            source = LoggedRouteSource(assembler, final_steps=finals, extra_builds=extra_builds)
        else:
            result = BestCandidateStrategy(cands, cost_table, hub_compositions=comps, **common).run(
                budget
            )
            source = LoggedRouteSource(assembler)  # a sampled terminal carries its own route

        lib = build_library(
            result,
            source,
            purchasable,
            reward_name=target,
            budget_reactions=a.budget_reactions,
            stereo_check=stereo_records or None,
        )
        audit = leaf_audit(lib.trees, purchasable)
        audits[name] = audit
        summary = write_strategy(cell_dir / name, lib, f"{cell} / {name}", schemes=not a.no_schemes)
        summaries.append(summary)
        print(
            f"[export] {name:<16} {summary['n_molecules']:3d} molecules in "
            f"{summary['n_batches']:3d} batches, "
            f"{summary['reactions_used']}/{a.budget_reactions} reactions, "
            f"{audit.n_unpurchasable} unpurchasable leaves"
        )
        if audit.n_unpurchasable:
            print(
                "    ^ a route says 'buy X' for an X that cannot be bought. Usually a --snapshot "
                "belonging to a DIFFERENT run: internally complete, so its own coverage reads "
                "100%, while this run's promoted fragments are silently bought instead of built."
            )

    artifacts = {"analysis_dir": str(adir), "enum_children": str(a.enum_children)}
    if a.snapshot:
        artifacts["snapshot"] = str(a.snapshot)
    # A sidecar digest beside a frozen enumeration is authoritative: re-hashing hundreds of
    # megabytes to reprint a number the run already recorded is slow AND a chance to disagree
    # with it.
    artifact_md5 = {}
    sidecar = Path(a.enum_children).with_suffix(".md5")
    if sidecar.is_file():
        artifact_md5["enum_children"] = sidecar.read_text().strip().split()[0]

    limitations = list(a.note)
    if not catalogue_known:
        limitations.append(
            "No building-block catalogue was supplied (--snapshot), so the purchasable set was "
            "inferred from the routes' own leaves. Every leaf is purchasable BY CONSTRUCTION "
            "here; that check was not independently verified for this cell."
        )
    if stereo_stats.get("n_multi_stereo_keys"):
        limitations.append(
            f"{stereo_stats['n_multi_stereo_keys']} of {stereo_stats['n_keys']} molecules were "
            "seen in more than one stereochemical configuration. Selection ran on "
            "stereo-stripped structures, so those were counted as one molecule."
        )

    prov = CellProvenance(
        cell=cell,
        generator=generator,
        target=target,
        reward_name=target,
        hit_threshold=a.reward_threshold,
        higher_is_better=higher,
        budget_reactions=a.budget_reactions,
        similarity_cutoff=a.similarity,
        similarity_metric="Tanimoto, Morgan r=3/2048",
        artifacts=artifacts,
        artifact_md5=artifact_md5,
        config={
            "child_policy": a.child_policy,
            "prebuild_k": a.prebuild_k,
            "rank_by": a.rank_by if a.prebuild_k else "",
            "strategies": a.strategies,
        },
        limitations=limitations,
    )
    write_cell_readme(cell_dir / "README.md", prov, summaries, audits)
    write_dataset_readme(out_root)
    (cell_dir / "export_summary.json").write_text(
        json.dumps({s["strategy"]: s for s in summaries}, indent=2, default=str) + "\n"
    )

    print(f"\n  {cell_dir}\n  README.md reads it as chemistry.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
