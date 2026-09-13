"""Optional gin-config support.

Hub-selection strategies are ``@gin.configurable`` so that a gin config can name one, which is
how the RGFN training stack is driven. But gin is RGFN plumbing: someone attaching their own
generator, auditing the cost model, or writing a new hub strategy has no use for it, and
``pyproject.toml`` promises that the core needs no deep-learning stack.

So gin is imported if it is there and stubbed if it is not. With gin installed the decorator is
the real one and every config that worked before still works; without it the decorator returns
the class untouched and everything except *configuring strategies from a gin file* behaves
identically.

Use it exactly as you would use gin::

    from hubbatching._gin import gin

    @gin.configurable()
    class MyStrategy(HubSelectionStrategy):
        ...

:data:`HAS_GIN` says which mode you are in, for code that needs to care (almost nothing does).
"""

from __future__ import annotations

from typing import Any

try:  # pragma: no cover - trivial, and exercised by whichever branch the env has
    import gin as _gin

    HAS_GIN = True
except ImportError:  # pragma: no cover
    _gin = None
    HAS_GIN = False


class _NoOpGin:
    """Stand-in exposing just enough of gin's surface for decoration to be a no-op.

    Deliberately minimal. It does NOT pretend to parse configs -- if gin is absent and something
    tries to bind a value, that should fail loudly rather than silently ignore the binding and
    run with defaults the user did not ask for.
    """

    @staticmethod
    def configurable(*args: Any, **kwargs: Any):
        # Supports both `@gin.configurable` and `@gin.configurable(...)`.
        if len(args) == 1 and not kwargs and callable(args[0]):
            return args[0]

        def _decorator(obj):
            return obj

        return _decorator

    def __getattr__(self, name: str):
        raise RuntimeError(
            f"gin-config is not installed, so `gin.{name}` is unavailable. Hub strategies are "
            "usable without gin; only configuring them from a .gin file needs it. Install with "
            "`pip install gin-config` (or `pip install 'hubbatching[generators]'`)."
        )


gin = _gin if HAS_GIN else _NoOpGin()

__all__ = ["gin", "HAS_GIN"]
