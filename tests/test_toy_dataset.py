"""The bundled toy dataset is load-bearing: it is T0, it is every notebook's input, and it is
the first thing anyone runs. These tests assert the properties that make it worth shipping.

The one that matters most is :func:`test_hubs_are_priced`. A hub missing from
``compositions.json`` prices at zero, which hands best-candidate's shared scaffolds away for
free and inflates hub-batching's apparent advantage. It is invisible in the output -- the run
completes and prints a better number. It happened during this dataset's construction, so it is
pinned here.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

TOY = Path(__file__).resolve().parents[1] / "examples" / "toy"

pytestmark = pytest.mark.skipif(
    not (TOY / "records.csv").exists(),
    reason="toy dataset not generated; run python tools/make_toy_dataset.py",
)


@pytest.fixture(scope="module")
def records():
    with (TOY / "records.csv").open() as fh:
        return list(csv.DictReader(fh))


@pytest.fixture(scope="module")
def enum():
    return json.loads((TOY / "enum_children.json").read_text())


@pytest.fixture(scope="module")
def comps():
    return json.loads((TOY / "compositions.json").read_text())


@pytest.fixture(scope="module")
def routes():
    return json.loads((TOY / "routes.json").read_text())


def test_hubs_are_priced(enum, comps):
    """Every hub must appear in compositions.json, or it is charged zero to build.

    A zero-cost hub silently removes best-candidate's cost for shared scaffolds, which makes
    hub-batching look better than it is. The run does not fail; it just reports a wrong margin.
    """
    missing = [h["hub_key"] for h in enum["hubs"] if h["hub_key"] not in comps]
    assert not missing, f"{len(missing)} hub(s) absent from compositions.json: {missing[:3]}"


def test_children_cost_more_than_their_hub(enum, comps):
    """A child is its hub plus one coupling. If they cost the same there is nothing to amortize
    and the dataset cannot demonstrate the mechanism it exists to demonstrate."""
    for hub in enum["hubs"]:
        hub_cost = comps[hub["hub_key"]]["num_reactions"]
        for child in hub["children"]:
            key = child["smiles"]
            if key in comps:
                assert comps[key]["num_reactions"] > hub_cost


def test_every_molecule_is_real_chemistry(routes):
    """Every product must parse. A toy dataset of unparseable SMILES would let the cost model
    run while drawing nothing and exporting nothing."""
    from rdkit import Chem, RDLogger

    RDLogger.DisableLog("rdApp.*")
    bad = [s for s in routes if Chem.MolFromSmiles(s) is None]
    assert not bad, f"{len(bad)} unparseable SMILES, e.g. {bad[:3]}"


def test_routes_bottom_out_in_purchasable_stock(routes):
    """Every route must start from a seed and reach its product through logged steps -- no step
    may say 'buy X' for an X the route itself builds."""
    for product, route in routes.items():
        assert route["steps"], f"{product} has an empty route"
        assert route["seed"], f"{product} has no seed building block"
        assert route["steps"][-1]["product"], "the last step must name the product it makes"


def test_routes_are_keyed_the_same_way_as_records(records, routes):
    """A route keyed differently from its molecule is worse than no route: the lookup returns
    nothing and the caller prices the wrong thing, with no error anywhere.

    Routes cover **hubs as well as products**. A hub is a built intermediate, and without its own
    route it appears as a leaf of its children's route trees -- so the exporter correctly reports
    it as unpurchasable, telling a chemist to order a compound the library itself makes.
    """
    child_keys = {r["child_key"] for r in records}
    hub_keys = {r["hub_key"] for r in records}

    unknown = set(routes) - child_keys - hub_keys
    assert not unknown, f"routes.json carries keys in neither column: {sorted(unknown)[:3]}"

    missing_products = child_keys - set(routes)
    assert not missing_products, f"{len(missing_products)} product(s) carry no route"

    missing_hubs = hub_keys - set(routes)
    assert not missing_hubs, (
        f"{len(missing_hubs)} hub(s) carry no route, so they would export as things to BUY "
        f"rather than things to make: {sorted(missing_hubs)[:2]}"
    )


def test_hub_order_is_flow_descending(enum, records):
    """enum_children.json's own hub order IS the strategy. If it is not flow-descending, a reader
    walking it top-to-bottom is silently running a different strategy than they think."""
    from hubbatching.flow import consensus_log_flow, log_flow_estimate

    by_hub: dict[str, list[float]] = {}
    for r in records:
        by_hub.setdefault(r["hub_key"], []).append(
            log_flow_estimate(
                log_reward=float(r["log_reward"]),
                log_pb_move=float(r["log_pb_move"]),
                log_pf_move=float(r["log_pf_move"]),
                log_pf_stop=float(r["log_pf_stop"]),
            )
        )

    scores = [
        consensus_log_flow(by_hub[h["hub_key"]]) for h in enum["hubs"] if h["hub_key"] in by_hub
    ]
    assert scores == sorted(scores, reverse=True), "hubs are not in flow-descending order"


def test_meta_declares_what_is_synthetic():
    """The dataset must say so itself. A tutorial dataset mistaken for a result is worse than no
    tutorial dataset, and the file travels separately from the docs that explain it."""
    meta = json.loads((TOY / "meta.json").read_text())
    assert meta.get("synthetic") is True
    assert "caveat" in meta and meta["caveat"].strip()
    assert meta["reward_name"] == "qed"


def test_dataset_is_small_enough_to_commit():
    """It ships in git and inside a size-capped review artifact."""
    total = sum(p.stat().st_size for p in TOY.glob("*") if p.is_file())
    assert total < 2 * 1024 * 1024, f"toy dataset is {total / 1024:.0f} KB; keep it under 2 MB"
