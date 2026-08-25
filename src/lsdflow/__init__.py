"""LSD-Flow: post-hoc hub selection over a trained reaction GFlowNet.

The method reads a *trained, frozen* generator -- no retraining, no reward change --
recovers the state flow at pre-terminal intermediates ("hubs") by rearranging
detailed balance, ranks hubs by that estimate, exhaustively enumerates each
selected hub's one-reaction children, and walks the ranking greedily to assemble a
library under a fixed reaction budget.

What lives here:

``flow``            recover ``log F(h)`` at a hub from its sampled children
``dag``, ``records``  the in-memory hub DAG and the flow-record schema
``hubs/``           hub-ranking strategies (flow, visitation, reward-parent, ...)
``child_select``    which children of a chosen hub to take
``mode_select``     the reward gate plus the Tanimoto diversity filter
``campaign``        the greedy walk: ``HubBatchingStrategy`` and the
                    ``BestCandidateStrategy`` baseline it is measured against
``cost``            the count-once cost model that prices a selected library
``adapters/``       the only modules that touch a specific generator; everything
                    above is generator-agnostic and depends on neither torch nor rgfn

``cost`` is deliberately dependency-free: pricing a library is arithmetic over
routes, and keeping it that way means the number a paper quotes can be audited
without installing a deep-learning stack.
"""

from lsdflow import hubs  # noqa: F401
from lsdflow import paths  # noqa: F401
from lsdflow.campaign import (  # noqa: F401
    BestCandidateStrategy,
    CampaignPoint,
    CampaignResult,
    CampaignStrategy,
    Candidate,
    EnumChild,
    EnumeratedHub,
    HubBatchingStrategy,
    fragment_fanout,
    rank_fragments,
)
from lsdflow.child_select import (  # noqa: F401
    ChildSelectionPolicy,
    FreeFragChildPolicy,
    RewardChildPolicy,
    available_child_policies,
    make_child_policy,
)
from lsdflow.dag import ChildEstimate, Hub, LiteHubDAG  # noqa: F401
from lsdflow.records import FlowRecord  # noqa: F401
