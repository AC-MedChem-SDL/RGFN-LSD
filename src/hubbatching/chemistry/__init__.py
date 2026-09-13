"""Chemistry -- the standard, swappable fragment + reaction library.

This subpackage owns the two *inputs* every reaction-GFlowNet builds molecules from: a
building-block set and a reaction-template set, plus an optional cost annotation (per-block
price, per-reaction yield). The point is a *single standard set* that different generators can
all consume, so a benchmark varies the **generator** while holding the **chemistry** fixed --
and so you can substitute your own chemistry without touching a generator's source.

A library on disk is three files in one directory::

    <library>/fragments.csv    building blocks, optionally priced
              reactions.csv    reaction templates (SMARTS), optionally with yields
              manifest.json     name, version, provenance, counts, checksum

See ``docs/extending/chemistry.md`` for the walkthrough and the column definitions.

Split of responsibilities:
    - ``library.py``               "what is the library" -- format-agnostic, no RGFN plumbing,
                                   no gin, no torch. Loaders in, exporters out, cost maps.
    - ``reaction_data_factory.py`` "how does that library become RGFN's action space" --
                                   subclasses upstream ``ReactionDataFactory``, so the vendored
                                   ``third_party/rgfn/`` stays pristine.

Cost enters generation two ways: natively, for a generator with its own cost-guided policy, and
retroactively for everyone else (:mod:`hubbatching.eval` prices recorded routes with the same
numbers and the same formula).

**Import weight.** :class:`ChemLibrary` is the part most people want and it needs only rdkit, so
it is imported eagerly. :class:`GlueReactionDataFactory` needs gin *and* the vendored rgfn
package, so it is resolved lazily on first attribute access -- reading or writing a library must
not require a deep-learning stack. It is still ``@gin.configurable``, and touching the name is
what registers it, so a gin config referencing ``@GlueReactionDataFactory`` works as long as
something has accessed it (``from hubbatching.chemistry import GlueReactionDataFactory``).
"""

from __future__ import annotations

from typing import Any

from hubbatching.chemistry.library import ChemLibrary, FragmentSpec, ReactionSpec  # noqa: F401

__all__ = [
    "ChemLibrary",
    "FragmentSpec",
    "ReactionSpec",
    "GlueReactionDataFactory",
]


def __getattr__(name: str) -> Any:
    """Lazily resolve the rgfn-dependent factory (PEP 562)."""
    if name == "GlueReactionDataFactory":
        from hubbatching.chemistry.reaction_data_factory import GlueReactionDataFactory

        return GlueReactionDataFactory
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
