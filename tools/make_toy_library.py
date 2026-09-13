#!/usr/bin/env python3
"""Cut ``data/libraries/glue_standard_v1`` down to a toy library the laptop checkpoint trains on.

The full library is 418 fragments and 112 templates. A model over it is tens of megabytes,
because the policy heads are sized by the action space -- too large to commit, which is the
whole problem the toy checkpoint exists to solve.

So this selects a subset, and the selection is not arbitrary. Two properties have to survive or
the resulting model teaches the wrong thing:

* **Every kept template must still fire.** A template whose reactants are no longer in the
  fragment set is dead weight in the action space: it enlarges the policy head, is never
  selected, and its logits are never trained. Templates are kept only if they match at least
  ``--min-matches`` kept fragments on every side.
* **The chemistry must stay multi-step.** If no product of a reaction can react again, every
  molecule is one reaction from stock, there are no intermediates, and a hub-batching demo over
  it would be vacuous. Reported below, and the script says so when it fails.

    python3 tools/make_toy_library.py
    python3 tools/make_toy_library.py --fragments 60 --check
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

from rdkit import Chem, RDLogger
from rdkit.Chem import AllChem, Descriptors

RDLogger.DisableLog("rdApp.*")

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "data" / "libraries" / "glue_standard_v1"
OUT = REPO / "data" / "libraries" / "toy_v1"
SEED = 20260912


def load_source():
    with (SRC / "fragments.csv").open() as fh:
        frags = list(csv.DictReader(fh))
    with (SRC / "reactions.csv").open() as fh:
        rxns = list(csv.DictReader(fh))
    return frags, rxns


def fires_on(smarts: str, mols, cap: int = 24):
    """How many ordered fragment pairs this template actually produces a product from.

    Deliberately RunReactants rather than matching the reaction's own reactant templates with
    HasSubstructMatch. That looks like the cheaper test and it SEGFAULTS RDKit on some of these
    templates -- reaction-side queries carry features the substructure matcher will not accept.
    Firing the reaction is also the question we actually care about: a template that matches but
    never yields a product is still a dead action.

    Returns (n_pairs_that_fire, example_products).
    """
    try:
        rxn = AllChem.ReactionFromSmarts(smarts)
    except Exception:
        return 0, []
    if rxn is None or rxn.GetNumReactantTemplates() not in (1, 2):
        return 0, []
    n_react = rxn.GetNumReactantTemplates()
    hits, products = 0, []
    sample = mols[:cap]
    for i, a in enumerate(sample):
        if a is None:
            continue
        combos = [(a,)] if n_react == 1 else [(a, b) for b in sample if b is not None]
        for combo in combos:
            try:
                out = rxn.RunReactants(combo)
            except Exception:
                continue
            if not out:
                continue
            hits += 1
            if len(products) < 8:
                try:
                    prod = out[0][0]
                    Chem.SanitizeMol(prod)
                    products.append(prod)
                except Exception:
                    pass
            break
    return hits, products


def can_react_again(mol, kept_rxns, mols) -> bool:
    """Does this product participate in any kept reaction? If nothing does, the library is
    single-step: no intermediates, and a hub-batching demo over it would be vacuous."""
    for r in kept_rxns:
        try:
            rxn = AllChem.ReactionFromSmarts(r["reaction"])
        except Exception:
            continue
        if rxn is None:
            continue
        n = rxn.GetNumReactantTemplates()
        combos = [(mol,)] if n == 1 else [(mol, m) for m in mols[:12] if m is not None]
        for combo in combos:
            try:
                if rxn.RunReactants(combo):
                    return True
            except Exception:
                continue
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--fragments", type=int, default=48, help="target fragment count")
    ap.add_argument("--reactions", type=int, default=12, help="target template count")
    ap.add_argument(
        "--min-matches",
        type=int,
        default=2,
        help="a template is kept only if every reactant side matches at least this many kept "
        "fragments -- otherwise it is an action that can never be taken",
    )
    ap.add_argument("--check", action="store_true", help="verify the committed copy is current")
    a = ap.parse_args()

    rng = random.Random(SEED)
    frags, rxns = load_source()
    print(f"source: {len(frags)} fragments, {len(rxns)} templates")

    # --- fragments: prefer small ones. A toy model has a small hidden dim, and small building
    # blocks keep the products readable in a notebook rather than being 40-heavy-atom sprawl.
    scored = []
    for f in frags:
        mol = Chem.MolFromSmiles(f["smiles"])
        if mol is None:
            continue
        scored.append((Descriptors.HeavyAtomCount(mol), f))
    scored.sort(key=lambda x: x[0])
    # Take from the small end, but sample across it so the set is not all one motif.
    pool = scored[: max(a.fragments * 3, a.fragments)]
    kept_frags = [f for _, f in rng.sample(pool, min(a.fragments, len(pool)))]
    kept_smiles = [f["smiles"] for f in kept_frags]
    kept_mols = [Chem.MolFromSmiles(s) for s in kept_smiles]

    # --- templates: keep only those that actually fire on the kept fragments.
    usable = []
    for r in rxns:
        hits, _ = fires_on(r["reaction"], kept_mols)
        if hits >= a.min_matches:
            usable.append((hits, r))
    usable.sort(key=lambda x: -x[0])
    kept_rxns = [r for _, r in usable[: a.reactions]]

    print(
        f"kept:   {len(kept_frags)} fragments, {len(kept_rxns)} templates "
        f"({len(usable)} of {len(rxns)} fire at all)"
    )
    if not kept_rxns:
        sys.exit(
            "no template fires on the kept fragments -- lower --min-matches or raise --fragments"
        )

    # --- the property that makes this worth training on: can a product react again?
    products = []
    for r in kept_rxns:
        _, prods = fires_on(r["reaction"], kept_mols)
        products.extend(prods)
    checked = products[:20]
    multi_step = sum(1 for p in checked if can_react_again(p, kept_rxns, kept_mols))
    print(f"        {multi_step} of {len(checked)} sampled products can react again")
    if checked and multi_step == 0:
        print(
            "WARNING: no product re-reacts. Every molecule would be one reaction from stock, "
            "there would be no intermediates, and hub-batching over this library is vacuous."
        )

    # --- write
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "fragments.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["smiles", "group", "cost", "catalog_id"])
        w.writeheader()
        w.writerows({k: f.get(k, "") for k in w.fieldnames} for f in kept_frags)
    with (OUT / "reactions.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["reaction", "family", "comments", "yield"])
        w.writeheader()
        w.writerows({k: r.get(k, "") for k in w.fieldnames} for r in kept_rxns)

    def sha(p):
        return hashlib.sha256(p.read_bytes()).hexdigest()

    (OUT / "manifest.json").write_text(
        json.dumps(
            {
                "name": "toy_v1",
                "version": "1.0",
                "source": "data/libraries/glue_standard_v1, subset by tools/make_toy_library.py",
                "purpose": (
                    "Deliberately small, so a laptop-scale checkpoint trained on it is small "
                    "enough to commit. Illustrative of the mechanism; not a library anyone "
                    "should run a real campaign against."
                ),
                "n_fragments": len(kept_frags),
                "n_reactions": len(kept_rxns),
                "default_cost": 1.0,
                "default_yield": 0.5,
                "cost_units": "scent_small (unitless, relative price)",
                "seed": SEED,
                "fragments_sha256": sha(OUT / "fragments.csv"),
                "reactions_sha256": sha(OUT / "reactions.csv"),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
