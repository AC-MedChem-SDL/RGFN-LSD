"""Name -> hub-selection-strategy registry (proposal §1: "adding a new strategy must be
trivial").

The harness and configs refer to strategies by their short ``name``; calling code and gin
configs can also reference the classes directly (each is ``@gin.configurable``). To add a
strategy: implement it under this package, decorate with ``@gin.configurable``, and add it to
``_STRATEGIES`` below (and make sure it is imported from ``lsdflow.hubs``).
"""

from __future__ import annotations

from typing import Dict, List, Type

from lsdflow.hubs.base import HubSelectionStrategy
from lsdflow.hubs.highest_flow import HighestFlowStrategy
from lsdflow.hubs.highest_terminating_flow import (
    HighestTerminatingFlowStrategy,
)
from lsdflow.hubs.highest_visitation import HighestVisitationStrategy
from lsdflow.hubs.lowest_uncertainty import LowestUncertaintyStrategy
from lsdflow.hubs.most_modes import MostModesStrategy
from lsdflow.hubs.parent_of_topk import ParentOfTopKStrategy
from lsdflow.hubs.ucb import UcbHubStrategy

_STRATEGIES: Dict[str, Type[HubSelectionStrategy]] = {
    cls.name: cls
    for cls in (
        HighestTerminatingFlowStrategy,
        HighestFlowStrategy,
        MostModesStrategy,
        ParentOfTopKStrategy,
        HighestVisitationStrategy,
        LowestUncertaintyStrategy,
        UcbHubStrategy,
    )
}


def available() -> List[str]:
    return sorted(_STRATEGIES)


def register(cls: Type[HubSelectionStrategy]) -> Type[HubSelectionStrategy]:
    _STRATEGIES[cls.name] = cls
    return cls


def get_hub_strategy(name: str, **kwargs) -> HubSelectionStrategy:
    try:
        cls = _STRATEGIES[name]
    except KeyError:
        raise KeyError(f"Unknown hub strategy {name!r}. Available: {available()}") from None
    return cls(**kwargs)
