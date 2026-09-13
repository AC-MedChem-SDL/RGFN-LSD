"""Model-agnostic data records + duck-type protocols for hub-batching hub analysis.

``docs/METHOD.md`` §3b: the selection strategies are written against a
lightweight **HubDAG-shaped protocol** so they never import a concrete DAG. In the
in-process path they operate on :class:`~hubbatching.dag.LiteHubDAG`
built from the trajectories the loop already sampled (single env, no adapter); in the
cross-env analysis path they operate on a richer persisted DAG exposing the same fields. Both
satisfy the protocols declared here, so one set of strategies serves both.

:class:`FlowRecord` is the single shared unit both DAG builders consume: one observed
``h --[one reaction]--> x --[stop]--> Terminal`` transition, carrying the four §2 log-terms
plus the canonical node keys (§6). It is produced per model — for RGFN by
``hubbatching.rgfn_extract`` (rgfn-native, in-env), for the cross-env baselines by
each generator's own worker, which writes them to ``records.csv`` (see
``docs/INPUT_CONTRACT.md``) for :class:`~hubbatching.adapters.file_adapter.FileAdapter` to read
back.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol, Sequence, runtime_checkable


@dataclass(frozen=True)
class FlowRecord:
    """One observed terminal transition ``h -> x`` (a hub and one of its terminal children).

    All log-terms are in natural log. ``hub_key`` / ``child_key`` are the cross-model
    canonical keys (RDKit canonical SMILES, **stereo stripped** — §6); the ``*_stereo_key``
    fields keep the stereo-aware secondary key for within-model work.
    """

    hub_key: str
    child_key: str
    reward: float  # R(x): raw proxy/oracle value (reward-based strategies, severe tests)
    log_reward: float  # log R(x): the shaped log reward the objective trains against
    log_pf_move: float  # log P_F(x | h): the composed one-reaction forward move
    log_pb_move: float  # log P_B(h | x): the model's own trained backward prob
    log_pf_stop: float  # log P_F(stop | x): the terminating factor (§2 — never dropped)
    hub_depth: int  # min #reactions to build h (the hub state's num_reactions)
    hub_stereo_key: str = ""
    child_stereo_key: str = ""


# --------------------------------------------------------------------------- protocols
# Structural types the selection strategies rely on. They are documentation + optional
# static typing; strategies duck-type against them and never isinstance-check, so any
# object exposing these attributes (LiteHubDAG here, the validation rich DAG there) works.


@runtime_checkable
class ChildEstimateLike(Protocol):
    key: str
    reward: float
    log_reward: float
    log_flow: float  # log F_hat(h; x) = logR + logP_B - logP_F(move) - logP_F(stop)


@runtime_checkable
class HubLike(Protocol):
    key: str
    depth: int
    visit_count: int
    children: Sequence[ChildEstimateLike]

    def child_log_flows(self) -> Sequence[float]:
        ...


@runtime_checkable
class HubDAGLike(Protocol):
    total_trajectories: int
    log_z: float
    higher_is_better: bool

    def hubs_iter(self) -> Iterable[HubLike]:
        ...
