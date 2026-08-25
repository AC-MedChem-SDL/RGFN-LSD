"""Hub-selection strategies (``HubDAG`` -> ranked hubs) — proposal §3a."""

from lsdflow.hubs.base import HubSelectionStrategy  # noqa: F401
from lsdflow.hubs.highest_flow import HighestFlowStrategy  # noqa: F401
from lsdflow.hubs.highest_terminating_flow import (  # noqa: F401
    HighestTerminatingFlowStrategy,
)
from lsdflow.hubs.highest_visitation import (  # noqa: F401
    HighestVisitationStrategy,
)
from lsdflow.hubs.lowest_uncertainty import (  # noqa: F401
    LowestUncertaintyStrategy,
)
from lsdflow.hubs.most_modes import MostModesStrategy  # noqa: F401
from lsdflow.hubs.parent_of_topk import ParentOfTopKStrategy  # noqa: F401
from lsdflow.hubs.registry import (  # noqa: F401
    available,
    get_hub_strategy,
    register,
)
from lsdflow.hubs.ucb import UcbHubStrategy  # noqa: F401
