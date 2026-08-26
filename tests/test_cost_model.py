"""Tests for the count-once cost model.

This is the module the headline number rests on. Every published ratio is a quotient
of two numbers this code produces, so a silent change here moves the paper's central
claim without breaking anything else -- which is exactly what happened once already:
Logs/029 reported hub-batching "roughly halving" library cost (1,479 vs 820
reactions, ~1.8x), and Logs/033 found most of that was a promoted fragment being
charged once per molecule that used it instead of once per library. The corrected
naive-policy edge is ~1.13x. `test_shared_fragment_is_charged_once` is that bug.

cost.py imports nothing outside the standard library, so these run anywhere.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lsdflow.cost import FragmentCostTable  # noqa: E402


def recipe(num_reactions: int, reactants=(), seed=None) -> dict:
    return {"num_reactions": num_reactions,
            "steps": [{"reactants": list(reactants)}],
            "seed": seed}


def test_purchasable_fragments_are_free() -> None:
    """A block that was never promoted is bought, not built."""
    t = FragmentCostTable(promoted_set=set())
    assert t.shared_build_cost(["anything", "else"]) == (0, 0.0)


def test_single_promoted_fragment_costs_its_route_length() -> None:
    t = FragmentCostTable(promoted_set={"A"}, recipes={"A": recipe(3)})
    assert t.shared_build_cost(["A"]) == (3, 0.0)


def test_shared_fragment_is_charged_once() -> None:
    """The Logs/033 regression: the bug that inflated the original ~1.8x result.

    Ten molecules drawing on one promoted fragment cost that fragment once -- you
    synthesize a batch and draw from it. Charging per use is what produced 1,479 vs
    820 reactions and a claim that had to be retracted.
    """
    t = FragmentCostTable(promoted_set={"A"}, recipes={"A": recipe(4)})
    once = t.shared_build_cost(["A"])
    ten_uses = t.shared_build_cost(["A"] * 10)
    assert once == ten_uses == (4, 0.0)


def test_distinct_fragments_add() -> None:
    t = FragmentCostTable(promoted_set={"A", "B"},
                          recipes={"A": recipe(2), "B": recipe(5)})
    assert t.shared_build_cost(["A", "B"]) == (7, 0.0)


def test_nesting_pulls_in_sub_fragments() -> None:
    """A promoted fragment built from another charges both -- closure under recipes."""
    t = FragmentCostTable(
        promoted_set={"A", "B", "C"},
        recipes={"A": recipe(1, reactants=["B"]),
                 "B": recipe(2, reactants=["C"]),
                 "C": recipe(4)})
    assert t.closure(["A"]) == {"A", "B", "C"}
    assert t.shared_build_cost(["A"]) == (1 + 2 + 4, 0.0)


def test_nested_sub_fragment_shared_between_two_parents_is_still_once() -> None:
    """The property that makes the metric a *library* cost rather than a sum of molecules."""
    t = FragmentCostTable(
        promoted_set={"A", "B", "shared"},
        recipes={"A": recipe(1, reactants=["shared"]),
                 "B": recipe(1, reactants=["shared"]),
                 "shared": recipe(6)})
    assert t.shared_build_cost(["A", "B"]) == (1 + 1 + 6, 0.0)


def test_seed_counts_as_a_promoted_reactant() -> None:
    """A route's seed is consumed as surely as a step reactant."""
    t = FragmentCostTable(promoted_set={"A", "S"},
                          recipes={"A": recipe(1, seed="S"), "S": recipe(3)})
    assert t.closure(["A"]) == {"A", "S"}
    assert t.shared_build_cost(["A"]) == (4, 0.0)


def test_self_reference_does_not_loop() -> None:
    """Routes are written by other code; a self-referential one must not hang."""
    t = FragmentCostTable(promoted_set={"A"},
                          recipes={"A": recipe(2, reactants=["A"], seed="A")})
    assert t.closure(["A"]) == {"A"}
    assert t.shared_build_cost(["A"]) == (2, 0.0)


def test_cycle_between_two_fragments_terminates() -> None:
    t = FragmentCostTable(promoted_set={"A", "B"},
                          recipes={"A": recipe(1, reactants=["B"]),
                                   "B": recipe(1, reactants=["A"])})
    assert t.closure(["A"]) == {"A", "B"}
    assert t.shared_build_cost(["A"]) == (2, 0.0)


def test_falls_back_to_min_num_reactions_without_a_recipe() -> None:
    """A recipe-less checkpoint still prices, without nesting -- the Logs/027 behaviour."""
    t = FragmentCostTable(promoted_set={"A"}, min_num_reactions={"A": 5})
    assert t.unit_reactions("A") == 5
    assert t.shared_build_cost(["A"]) == (5, 0.0)


def test_unknown_promoted_fragment_costs_nothing_rather_than_raising() -> None:
    """Missing data must not be silently priced as expensive, nor crash a campaign."""
    t = FragmentCostTable(promoted_set={"A"})
    assert t.unit_reactions("A") == 0


def test_dollars_are_marginal_not_double_counted() -> None:
    """$ is the secondary axis, and it has the same once-only obligation as reactions."""
    t = FragmentCostTable(
        promoted_set={"A", "B"},
        recipes={"A": recipe(1, reactants=["B"]), "B": recipe(1)},
        dollar_costs={"A": 10.0, "B": 4.0})
    # A's own marginal cost is 10 - 4 = 6; B is charged its full 4 once via the closure.
    assert t.unit_dollars("A") == 6.0
    assert t.shared_build_cost(["A"]) == (2, 10.0)


def test_marginal_dollars_never_go_negative() -> None:
    """Cost tables are approximate; a sub-fragment priced above its parent must clamp."""
    t = FragmentCostTable(
        promoted_set={"A", "B"},
        recipes={"A": recipe(1, reactants=["B"]), "B": recipe(1)},
        dollar_costs={"A": 3.0, "B": 9.0})
    assert t.unit_dollars("A") == 0.0


def test_cost_is_order_independent() -> None:
    """A library is a set; pricing it must not depend on the order it is presented in."""
    t = FragmentCostTable(
        promoted_set={"A", "B", "C"},
        recipes={"A": recipe(1, reactants=["C"]), "B": recipe(2), "C": recipe(3)})
    assert t.shared_build_cost(["A", "B", "C"]) == t.shared_build_cost(["C", "B", "A"])
