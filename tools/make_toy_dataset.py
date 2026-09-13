#!/usr/bin/env python3
"""Generate ``examples/toy/`` -- the tiny, self-contained dataset the tutorials run on.

Why this exists rather than a fixture of random strings: everything downstream of
``records.csv`` is chemistry. A toy dataset made of fake SMILES would let the cost model run but
would draw nothing, export nothing a chemist could read, and quietly hide any bug that only
shows up on a real molecule. So this builds **real molecules** -- real building blocks, real
reaction templates fired by RDKit -- at a size that fits in a git repository and runs in
seconds.

What is real here and what is not, stated plainly because a tutorial dataset that is mistaken
for a result is worse than no tutorial dataset:

* **Real:** the building blocks, the reaction SMARTS, every product (RDKit actually ran the
  reaction), every synthesis route, and the molecular properties.
* **Synthetic:** the *reward* is RDKit's QED -- a genuine, deterministic, recognisable molecular
  property standing in for a target-specific oracle -- and the policy log-probabilities are
  generated from a self-consistent model of a trained GFlowNet rather than recovered from one.

The log-probabilities are worth one more sentence, because their structure is the thing being
demonstrated. For a converged GFlowNet every terminal child of a hub independently estimates the
*same* ``F(h)``; that agreement is what hub ranking reads and what ``U(h)`` measures. So each hub
is given a true ``log F(h)``, and each child's four log-terms are then chosen to reproduce it up
to a small per-child residual. The result behaves like a trained model: children of a hub agree,
hubs separate cleanly by flow, and ``U(h)`` is small but non-zero. Numbers computed from it are
illustrative of the *mechanism*; none of them is a scientific claim.

    python3 tools/make_toy_dataset.py            # writes examples/toy/
    python3 tools/make_toy_dataset.py --check    # verify the committed copy is reproducible
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import pathlib
import random
import sys
from pathlib import Path

from rdkit import Chem, RDLogger
from rdkit.Chem import QED, AllChem

# Import the REAL writer rather than reimplementing it. compositions.json must contain an entry
# for every hub as well as every child -- a hub missing from it prices at zero, which silently
# hands best-candidate's shared scaffolds away for free and inflates hub-batching's advantage.
# That is precisely the kind of bug a hand-rolled fixture introduces and nothing catches.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from hubbatching.adapters.artifacts import compositions_from_records  # noqa: E402
from hubbatching.flow import consensus_log_flow, log_flow_estimate  # noqa: E402

RDLogger.DisableLog("rdApp.*")

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "examples" / "toy"

# A deterministic seed everywhere: the committed dataset must be byte-reproducible, otherwise
# `--check` cannot tell "someone edited this" from "it regenerated differently".
SEED = 20260912

# --------------------------------------------------------------------------- chemistry
# One reaction family, real, and the single most common bond-forming step in medicinal chemistry.
# Used twice per molecule: once to build the hub, once to diversify it.
REACTIONS = {
    "amide_coupling": {
        "smarts": "[C:1](=[O:2])[OH].[N;H2,H1;!$(N-C=O):3]>>[C:1](=[O:2])[N:3]",
        "name": "amide coupling",
        "note": "carboxylic acid + primary/secondary amine (HATU, DIPEA, DMF)",
    },
}

# Base building blocks: purchasable, cheap, and real.
#
# The shape here is the whole point. A hub is NOT a purchasable block -- if it were, there would
# be nothing to amortize and both strategies would tie. A hub is an *intermediate you have to
# build*: a bifunctional core acylated on one end, leaving the other end free to diversify. So
# every final molecule is two reactions from stock, and the question hub-batching answers is
# whether you pay that first reaction once per molecule or once per hub.

# Bifunctional cores: a free amine AND a free carboxylic acid on the same scaffold.
CORES = [
    ("Nc1ccc(cc1)C(=O)O", "4-aminobenzoic acid"),
    ("Nc1cccc(c1)C(=O)O", "3-aminobenzoic acid"),
    ("NC1CCC(CC1)C(=O)O", "4-aminocyclohexanecarboxylic acid"),
    ("NCc1ccc(cc1)C(=O)O", "4-(aminomethyl)benzoic acid"),
    ("OC(=O)C1CCNCC1", "piperidine-4-carboxylic acid"),
    ("Nc1ccc(cn1)C(=O)O", "6-aminonicotinic acid"),
]

# Caps: acylate the core's amine in step 1. Core x cap = the hub set.
CAPS = [
    ("CC(=O)O", "acetic acid"),
    ("OC(=O)C1CC1", "cyclopropanecarboxylic acid"),
    ("OC(=O)c1ccc(F)cc1", "4-fluorobenzoic acid"),
    ("OC(=O)c1cccnc1", "nicotinic acid"),
    ("OC(=O)COC", "methoxyacetic acid"),
    ("OC(=O)c1ccco1", "furan-2-carboxylic acid"),
]

# The diversifying partners: coupled to the hub's free acid in step 2.
AMINES = [
    ("NCc1ccccc1", "benzylamine"),
    ("NCC1CC1", "cyclopropylmethylamine"),
    ("NCCc1ccncc1", "2-(pyridin-4-yl)ethylamine"),
    ("NC1CCOCC1", "4-aminotetrahydropyran"),
    ("NCc1ccc(F)cc1", "4-fluorobenzylamine"),
    ("NCCN1CCOCC1", "2-morpholinoethylamine"),
    ("NC1CCN(C)CC1", "1-methylpiperidin-4-amine"),
    ("NCc1cccs1", "thiophen-2-ylmethylamine"),
    ("NCC(F)(F)F", "2,2,2-trifluoroethylamine"),
    ("NC1CCCC1", "cyclopentylamine"),
    ("NCc1ccncc1", "4-picolylamine"),
    ("NC1CCCCC1", "cyclohexylamine"),
]


def canon(smiles: str) -> str:
    mol = Chem.MolFromSmiles(smiles)
    return Chem.MolToSmiles(mol) if mol else ""


def strip_stereo(smiles: str) -> str:
    """The cross-model canonical key: RDKit canonical SMILES with stereochemistry removed.

    Keys must come from ONE function everywhere. A route keyed differently from its hub is worse
    than no route -- the lookup silently returns nothing and the caller prices the wrong molecule.
    """
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return ""
    Chem.RemoveStereochemistry(mol)
    return Chem.MolToSmiles(mol)


def run_reaction(rxn_key: str, a: str, b: str) -> str | None:
    """Fire a real template; return the canonical product, or None if it did not apply."""
    rxn = AllChem.ReactionFromSmarts(REACTIONS[rxn_key]["smarts"])
    ma, mb = Chem.MolFromSmiles(a), Chem.MolFromSmiles(b)
    if ma is None or mb is None:
        return None
    for products in rxn.RunReactants((ma, mb)):
        if not products:
            continue
        try:
            p = products[0]
            Chem.SanitizeMol(p)
            return Chem.MolToSmiles(p)
        except Exception:
            continue
    return None


def reward_of(smiles: str) -> float:
    """The stand-in oracle: RDKit QED. Real, deterministic, and recognisable."""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return 0.0
    return float(QED.qed(mol))


# --------------------------------------------------------------------------- build
def build():
    rng = random.Random(SEED)

    # --- Step 1: build the hubs, for real. ---------------------------------------------------
    # Step 1 of 2: acylate each bifunctional core's amine with each cap. The product still
    # carries the core's free carboxylic acid, so it is an INTERMEDIATE, not a final compound --
    # that is what makes it a hub. Costs one reaction from stock, hence depth 1.
    hubs = []
    for core_smi, core_name in CORES:
        for cap_smi, cap_name in CAPS:
            hub_smi = run_reaction("amide_coupling", cap_smi, core_smi)
            if not hub_smi:
                continue
            # Guard the thing that would silently ruin the dataset: if the cap acylated the
            # core's own acid, or the core's acid was consumed, there is nothing left to
            # diversify and this is not a hub at all.
            if not Chem.MolFromSmiles(hub_smi).HasSubstructMatch(
                Chem.MolFromSmarts("[CX3](=O)[OX2H1]")
            ):
                continue
            hubs.append(
                {
                    "smiles": hub_smi,
                    "name": f"{cap_name} + {core_name}",
                    "core": canon(core_smi),
                    "cap": canon(cap_smi),
                    "depth": 1,  # one reaction from purchasable stock
                    "build_step": {
                        "reaction": REACTIONS["amide_coupling"]["smarts"],
                        "reaction_name": REACTIONS["amide_coupling"]["name"],
                        "reactants": [canon(cap_smi)],
                        "input": canon(core_smi),
                        "product": hub_smi,
                    },
                }
            )

    # --- Step 2: diversify each hub, for real. -----------------------------------------------
    # Step 2 of 2: couple the hub's free acid with each amine. One reaction per child, which is
    # exactly the marginal cost hub-batching is built to exploit.
    seen_products = set()
    for hub in hubs:
        children = []
        for amine, aname in AMINES:
            product = run_reaction("amide_coupling", hub["smiles"], amine)
            if not product or product in seen_products:
                continue
            seen_products.add(product)
            children.append(
                {
                    "smiles": product,
                    "reward": round(reward_of(product), 6),
                    "added_promoted": [],  # every block is base stock: nothing to amortize
                    "amine": canon(amine),
                    "amine_name": aname,
                    "num_reactions": hub["depth"] + 1,  # FULLY NESTED: build hub, then couple
                    "reaction": [
                        {
                            "reaction": REACTIONS["amide_coupling"]["smarts"],
                            "reaction_name": REACTIONS["amide_coupling"]["name"],
                            "reactants": [canon(amine)],
                            "input": hub["smiles"],
                            "product": product,
                        }
                    ],
                }
            )
        hub["children"] = children

    hubs = [h for h in hubs if len(h["children"]) >= 2]

    # --- Step 3: synthesize a self-consistent flow field. ------------------------------------
    # Give each hub a true log F(h) that correlates with how good its children are -- that is
    # what a trained model would have learned -- then derive each child's log-terms so they
    # recover it up to a small residual.
    beta = 8.0  # reward -> log-reward temperature, as a shaped reward would use
    for hub in hubs:
        rewards = [c["reward"] for c in hub["children"]]
        hub["mean_reward"] = sum(rewards) / len(rewards)
        # True log-flow: more good children, and better ones, means more flow through the hub.
        hub["true_log_flow"] = beta * hub["mean_reward"] + math.log(len(hub["children"]))

    records = []
    for hub in hubs:
        n = len(hub["children"])
        mean_r = hub["mean_reward"]
        for child in hub["children"]:
            log_reward = beta * child["reward"]
            # P_F(x|h): a softmax-ish forward policy over this hub's children, biased to reward.
            log_pf_move = -math.log(n) + 0.6 * (child["reward"] - mean_r) * beta * 0.25
            # P_F(stop|x): high but not certain, as a trained policy at a good terminal.
            log_pf_stop = math.log(rng.uniform(0.80, 0.97))
            # Choose log P_B(h|x) to make the identity land on the hub's true flow, plus a small
            # residual so U(h) is non-zero (a perfectly consistent field would be a giveaway
            # that the numbers were manufactured, and would make U(h) uninterpretable).
            residual = rng.gauss(0.0, 0.12)
            log_pb_move = hub["true_log_flow"] + residual - log_reward + log_pf_move + log_pf_stop
            log_pb_move = min(log_pb_move, 0.0)  # a log-probability cannot exceed 0
            records.append(
                {
                    "hub_key": strip_stereo(hub["smiles"]),
                    "child_key": strip_stereo(child["smiles"]),
                    "reward": round(child["reward"], 6),
                    "log_reward": round(log_reward, 6),
                    "log_pf_move": round(log_pf_move, 6),
                    "log_pb_move": round(log_pb_move, 6),
                    "log_pf_stop": round(log_pf_stop, 6),
                    "hub_depth": hub["depth"],
                    "hub_stereo_key": hub["smiles"],
                    "child_stereo_key": child["smiles"],
                }
            )

    # --- Step 4: routes, one per molecule, grounded in the template that actually fired. ------
    #
    # A route is emitted for every HUB as well as every product. A hub is a built intermediate,
    # not something you buy, so without its own route it appears as a leaf of its children's
    # route trees and the exporter correctly reports it as unpurchasable -- telling a chemist to
    # order a compound the library itself makes. Every route must bottom out in real stock.
    routes = {}
    for hub in hubs:
        routes[strip_stereo(hub["smiles"])] = {
            "seed": hub["core"],
            "num_reactions": hub["depth"],
            "steps": [hub["build_step"]],
        }
    for hub in hubs:
        for child in hub["children"]:
            routes[strip_stereo(child["smiles"])] = {
                "seed": hub["core"],
                "num_reactions": child["num_reactions"],
                # Both steps, in order, each grounded in the template that actually fired. The
                # first is shared by every child of this hub -- which is precisely the reaction
                # hub-batching pays for once and best-candidate pays for per molecule.
                "steps": [hub["build_step"], child["reaction"][0]],
            }

    # --- Step 5: write the contract. ---------------------------------------------------------
    OUT.mkdir(parents=True, exist_ok=True)

    with (OUT / "records.csv").open("w", newline="") as fh:
        cols = [
            "hub_key",
            "child_key",
            "reward",
            "log_reward",
            "log_pf_move",
            "log_pb_move",
            "log_pf_stop",
            "hub_depth",
            "hub_stereo_key",
            "child_stereo_key",
        ]
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(records)

    # Hubs are written in flow-descending order: the file's order IS the strategy, so a reader
    # who walks it top to bottom is running highest-flow-first without configuring anything.
    #
    # Order by the RECOVERED flow, not by the true log F(h) this script invented. The recovered
    # estimate is the only one a real pipeline can see, and it differs from the truth by the
    # per-child residual -- so ordering by the truth would produce a file whose order `pick-hubs`
    # could not reproduce from the same records. Same statistic the highest_flow strategy uses,
    # from the same function, so there is one definition rather than a lookalike.
    recovered = {}
    for hub in hubs:
        key = strip_stereo(hub["smiles"])
        recovered[key] = consensus_log_flow(
            [
                log_flow_estimate(
                    log_reward=r["log_reward"],
                    log_pb_move=r["log_pb_move"],
                    log_pf_move=r["log_pf_move"],
                    log_pf_stop=r["log_pf_stop"],
                )
                for r in records
                if r["hub_key"] == key
            ]
        )
    ordered = sorted(hubs, key=lambda h: recovered[strip_stereo(h["smiles"])], reverse=True)
    enum = {
        "hubs": [
            {
                "hub_input": h["smiles"],
                "hub_key": strip_stereo(h["smiles"]),
                "depth": h["depth"],
                "promoted": [],
                "uncertainty": round(
                    _variance(
                        [
                            r["log_reward"] + r["log_pb_move"] - r["log_pf_move"] - r["log_pf_stop"]
                            for r in records
                            if r["hub_key"] == strip_stereo(h["smiles"])
                        ]
                    ),
                    6,
                ),
                "n_effective": len(h["children"]),
                "children": [
                    {
                        "smiles": c["smiles"],
                        "reward": c["reward"],
                        "added_promoted": c["added_promoted"],
                        "reaction": c["reaction"],
                    }
                    for c in h["children"]
                ],
            }
            for h in ordered
        ]
    }
    (OUT / "enum_children.json").write_text(json.dumps(enum, indent=1) + "\n")
    (OUT / "routes.json").write_text(json.dumps(routes, indent=1) + "\n")

    # No dynamic library in the toy set: every block is base stock, so no molecule has promoted
    # fragments and the nested-amortization path is a well-defined no-op. That is a deliberate
    # choice -- it keeps the toy cost model arithmetic a reader can do by hand.
    # One definition, shared with every real generator: a child costs hub_depth + 1, a hub costs
    # hub_depth, and BOTH are keyed so the cost model can find them.
    compositions = compositions_from_records(records)
    (OUT / "compositions.json").write_text(json.dumps(compositions, indent=1) + "\n")

    meta = {
        "model": "toy",
        "reward_name": "qed",
        "reward_description": "RDKit QED -- a stand-in for a target-specific oracle",
        "log_z": round(max(h["true_log_flow"] for h in hubs) + 1.5, 6),
        "higher_is_better": True,
        "n_trajectories": len(records),
        "strip_stereo": True,
        "generated_by": "tools/make_toy_dataset.py",
        "seed": SEED,
        "synthetic": True,
        "caveat": (
            "Molecules, reactions and routes are real (RDKit fired every template). The reward "
            "is QED standing in for an oracle, and the policy log-probabilities are generated "
            "from a self-consistent model of a trained GFlowNet rather than recovered from one. "
            "Numbers from this dataset illustrate the mechanism; none is a scientific claim."
        ),
    }
    (OUT / "meta.json").write_text(json.dumps(meta, indent=1) + "\n")

    return hubs, records, routes


def _variance(xs):
    xs = [x for x in xs if x == x]
    if len(xs) < 2:
        return float("nan")
    m = sum(xs) / len(xs)
    return sum((x - m) ** 2 for x in xs) / len(xs)


def digest() -> str:
    h = hashlib.sha256()
    for p in sorted(OUT.glob("*")):
        if p.is_file():
            h.update(p.name.encode())
            h.update(p.read_bytes())
    return h.hexdigest()[:16]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--check",
        action="store_true",
        help="regenerate into a temp dir and confirm the committed copy is byte-identical",
    )
    a = ap.parse_args()

    if a.check:
        before = digest() if OUT.exists() else ""
        build()
        after = digest()
        if before and before != after:
            print(f"TOY DATASET CHANGED: {before} -> {after}")
            return 1
        print(f"toy dataset reproducible ({after})")
        return 0

    hubs, records, routes = build()
    print(f"wrote {OUT}")
    print(f"  {len(hubs)} hubs, {len(records)} records, {len(routes)} routes")
    enum = json.loads((OUT / "enum_children.json").read_text())
    for h in enum["hubs"][:6]:
        print(f"    U(h)={h['uncertainty']:6.3f}  {len(h['children']):3d} children  {h['hub_key']}")
    if len(enum["hubs"]) > 6:
        print(f"    ... and {len(enum['hubs']) - 6} more, in recovered-flow order")
    print(f"  digest {digest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
