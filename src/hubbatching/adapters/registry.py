"""Name -> generator-adapter registry: the "bring your own generator" seam.

Hub-batching reads a *trained, frozen* generator. Everything above :mod:`hubbatching.adapters`
is generator-agnostic -- it operates on :class:`~hubbatching.records.FlowRecord` and
:class:`~hubbatching.dag.LiteHubDAG`, which any model can be made to emit. This module is where
a particular model gets attached.

There are **two** ways to attach one, and the second is the one most people want.

1. **In-process** (:class:`~hubbatching.adapters.contract.GFNAdapter`). Subclass it, implement
   ``sample_flow_records``, call :func:`register`. Requires that your model imports in the same
   Python process as ``hubbatching`` -- fine when it does, impossible when it does not.

2. **On disk** (:class:`~hubbatching.adapters.file_adapter.FileAdapter`, registered as
   ``"files"``). Run your model **in its own environment**, write the file contract with
   :mod:`hubbatching.adapters.artifacts` (pure stdlib, so it imports anywhere), and point
   hub-batching at the directory. Nothing needs to co-import.

Option 2 is not a fallback -- it is how the published work was actually done. The generators in
the paper live in mutually incompatible conda environments and no two of them co-import; the
file contract is what made them comparable. If you are integrating a new model, start there and
reach for option 1 only if you specifically want the in-process path.

See ``docs/extending/generators.md`` for the walkthrough and ``docs/INPUT_CONTRACT.md`` for the
byte-level file formats.

Adding your own::

    from hubbatching.adapters.contract import FlowSample, GFNAdapter
    from hubbatching.adapters.registry import register

    @register
    class MyModelAdapter(GFNAdapter):
        model_name = "mymodel"

        def sample_flow_records(self, n_trajectories: int) -> FlowSample:
            ...

    adapter = get_adapter("mymodel", **kwargs)
"""

from __future__ import annotations

from typing import Callable, Dict, List, Type

from hubbatching.adapters.contract import GFNAdapter

# name -> factory. A factory rather than the class itself so an adapter whose import is
# expensive (torch, a CUDA context) is only paid for when it is actually asked for --
# ``available()`` has to stay cheap enough to call while building a --help string.
_ADAPTERS: Dict[str, Callable[..., GFNAdapter]] = {}


def register(cls: Type[GFNAdapter]) -> Type[GFNAdapter]:
    """Class decorator: register ``cls`` under its ``model_name``.

    Returns the class unchanged, so it stacks with other decorators and the decorated name stays
    importable.
    """
    name = getattr(cls, "model_name", None)
    if not name or name == "base":
        raise ValueError(
            f"{cls.__name__} must set a distinct `model_name` class attribute before it can be "
            "registered -- it is the key callers and the CLI use."
        )
    _ADAPTERS[name] = cls
    return cls


def register_factory(name: str, factory: Callable[..., GFNAdapter]) -> None:
    """Register a callable that builds an adapter. Use for a model whose import is expensive
    enough that it should not happen until the adapter is actually requested."""
    _ADAPTERS[name] = factory


def available() -> List[str]:
    """Every registered adapter name, sorted."""
    return sorted(_ADAPTERS)


def get_adapter(name: str, **kwargs) -> GFNAdapter:
    """Instantiate the adapter registered under ``name``.

    Raises ``KeyError`` naming what *is* registered -- an unknown generator has to fail at the
    typo, not later as a confusing attribute error partway through a campaign.
    """
    try:
        factory = _ADAPTERS[name]
    except KeyError:
        raise KeyError(
            f"Unknown generator adapter {name!r}. Registered: {available()}. "
            "To attach your own model see docs/extending/generators.md -- the usual answer is "
            "the 'files' adapter, which needs no shared Python environment."
        ) from None
    return factory(**kwargs)


# ---------------------------------------------------------------- built-ins
# Both deferred. ``file_adapter`` is stdlib+rdkit and always safe, but ``rgfn_adapter`` pulls in
# torch and the vendored rgfn package, which a reader auditing the cost model has no reason to
# install -- and an unconditional import here would make ``import hubbatching`` require it.


def _rgfn_factory(**kwargs) -> GFNAdapter:
    from hubbatching.adapters.rgfn_adapter import RGFNAdapter

    return RGFNAdapter(**kwargs)


def _file_factory(**kwargs) -> GFNAdapter:
    from hubbatching.adapters.file_adapter import FileAdapter

    return FileAdapter(**kwargs)


register_factory("rgfn", _rgfn_factory)
register_factory("files", _file_factory)
