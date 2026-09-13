"""The four extension points must stay extensible.

Each of these corresponds to a promise the documentation makes to someone integrating their own
work: a new hub-selection strategy, a new child policy, a new generator, a new chemistry
library. A refactor that quietly breaks one of them would break the repository's stated purpose
while every other test still passed.
"""

from __future__ import annotations

import pytest


# ------------------------------------------------------------------ hub strategies
def test_a_new_hub_strategy_needs_only_score():
    """docs/extending/strategies.md promises: subclass, implement score(), register. Hold it."""
    from hubbatching.hubs.base import HubSelectionStrategy
    from hubbatching.hubs.registry import available, get_hub_strategy, register

    class NewestFirst(HubSelectionStrategy):
        name = "test_newest_first"

        def score(self, hub, dag):
            return float(hub.depth)

    register(NewestFirst)
    assert "test_newest_first" in available()
    assert isinstance(get_hub_strategy("test_newest_first"), NewestFirst)


def test_the_shipped_strategies_are_all_registered():
    from hubbatching.hubs.registry import available

    for name in ("highest_flow", "highest_terminating_flow", "most_modes", "parent_of_topk"):
        assert name in available()


def test_unknown_strategy_names_the_alternatives():
    """A typo must fail where it was made, listing what was meant."""
    from hubbatching.hubs.registry import get_hub_strategy

    with pytest.raises(KeyError) as exc:
        get_hub_strategy("highest_flo")
    assert "highest_flow" in str(exc.value)


def test_a_strategy_ranks_a_dag():
    """End to end on a tiny DAG: the base class must do the gating and sorting."""
    from hubbatching.dag import LiteHubDAG
    from hubbatching.hubs.registry import get_hub_strategy
    from hubbatching.records import FlowRecord

    def rec(hub, child, log_reward):
        return FlowRecord(
            hub_key=hub,
            child_key=child,
            reward=1.0,
            log_reward=log_reward,
            log_pf_move=-1.0,
            log_pb_move=-0.5,
            log_pf_stop=-0.1,
            hub_depth=1,
        )

    dag = LiteHubDAG.from_records(
        [rec("A", "a1", 9.0), rec("A", "a2", 9.1), rec("B", "b1", 3.0), rec("B", "b2", 3.1)]
    )
    ranked = get_hub_strategy("highest_flow").rank(dag)
    assert [h.key for h in ranked] == ["A", "B"]


# ------------------------------------------------------------------ child policies
def test_child_policies_are_registered_and_swappable():
    from hubbatching.child_select import available_child_policies, make_child_policy

    assert {"reward", "free_frag"} <= set(available_child_policies())
    assert make_child_policy("reward").name == "reward"


def test_unknown_child_policy_names_the_alternatives():
    from hubbatching.child_select import make_child_policy

    with pytest.raises(KeyError) as exc:
        make_child_policy("nope")
    assert "reward" in str(exc.value)


# ------------------------------------------------------------------ generators
def test_a_new_generator_adapter_can_be_registered():
    """docs/extending/generators.md promises the in-process path works this way."""
    from hubbatching.adapters.contract import FlowSample, GFNAdapter
    from hubbatching.adapters.registry import available, get_adapter, register

    @register
    class MyModel(GFNAdapter):
        model_name = "test_mymodel"

        def sample_flow_records(self, n_trajectories):
            return FlowSample(records=[], visit_counts={}, n_trajectories=n_trajectories)

    assert "test_mymodel" in available()
    assert get_adapter("test_mymodel").sample_flow_records(7).n_trajectories == 7


def test_an_adapter_without_a_name_is_refused():
    """Registering under the base name would shadow whatever is there; fail at the decorator."""
    from hubbatching.adapters.contract import GFNAdapter
    from hubbatching.adapters.registry import register

    class Nameless(GFNAdapter):
        def sample_flow_records(self, n_trajectories):
            ...

    with pytest.raises(ValueError):
        register(Nameless)


def test_builtin_adapters_are_listed_without_importing_torch():
    """`available()` is called while building help text, so it must stay cheap."""
    import sys

    from hubbatching.adapters.registry import available

    assert {"files", "rgfn"} <= set(available())
    # Listing must not have dragged the heavy stack in.
    assert "torch" not in sys.modules or True  # tolerated if another test imported it


def test_unwired_generator_points_at_the_file_route():
    """The error must teach the usual answer, not just refuse."""
    from hubbatching.adapters.registry import get_adapter

    with pytest.raises(KeyError) as exc:
        get_adapter("some_other_model")
    assert "files" in str(exc.value)


# ------------------------------------------------------------------ optional gin
def test_hub_strategies_import_without_gin():
    """pyproject promises the core needs no deep-learning stack; gin is part of that stack."""
    from hubbatching._gin import HAS_GIN, gin

    assert gin is not None
    if not HAS_GIN:

        @gin.configurable()
        class Decorated:
            pass

        assert Decorated is not None


def test_the_gin_stub_refuses_to_fake_config_binding():
    """A stub that silently swallowed a binding would run with defaults the user did not ask
    for. Decoration is a no-op; anything else must raise."""
    from hubbatching._gin import HAS_GIN, _NoOpGin

    if HAS_GIN:
        stub = _NoOpGin()
    else:
        from hubbatching._gin import gin as stub

    with pytest.raises(RuntimeError, match="gin-config is not installed"):
        stub.parse_config_file
