"""Every filesystem root the package needs, resolved in exactly one place.

No module outside this one may contain an absolute path. That rule exists for two
reasons which happen to coincide: a hard-coded ``/home/<user>/...`` identifies its
author to a double-blind reviewer, and it stops the code running anywhere but the
machine it was written on. Route every path through here and both problems are
structurally impossible rather than remembered.

Roots, in resolution order:

==================  ====================================  ==========================
function            environment variable                  default
==================  ====================================  ==========================
:func:`repo_root`   ``HUBBATCH_REPO``                      inferred from this file
:func:`data_dir`    ``HUBBATCH_DATA``                      ``<repo>/data``
:func:`artifacts`   ``HUBBATCH_ARTIFACTS``                 ``<repo>/artifacts``
:func:`results`     ``HUBBATCH_RESULTS``                   ``<cwd>/results``
:func:`scratch`     ``HUBBATCH_SCRATCH`` / ``SCRATCH``     ``<repo>/runs``
==================  ====================================  ==========================

``artifacts()`` is the one that matters for reproduction: it holds the committed
intermediates every ``reproduce/`` script reads, so a reader with no cluster and no
GPU can still regenerate every published figure. ``scratch()`` is the opposite --
large regenerable run output, never committed.

``results()`` is where the CLI writes, and it is the one root that defaults to the
**working directory** rather than the repo. That is deliberate: a pip-installed
package must never write into its own site-packages directory, and someone running
``hubbatching campaign`` on their own data expects the output beside them rather
than buried in an installation whose location they did not choose.
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = ["repo_root", "data_dir", "artifacts", "results", "scratch", "describe"]


def _from_env(*names: str) -> Path | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return Path(value).expanduser()
    return None


def repo_root() -> Path:
    """The checkout root: ``src/hubbatching/paths.py`` -> three parents up."""
    override = _from_env("HUBBATCH_REPO")
    if override is not None:
        return override.resolve()
    return Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    """Inputs: building-block libraries, receptors, curated molecule sets."""
    return (_from_env("HUBBATCH_DATA") or repo_root() / "data").resolve()


def artifacts() -> Path:
    """Committed intermediates that ``reproduce/`` reads. Small, CSV/JSON only."""
    return (_from_env("HUBBATCH_ARTIFACTS") or repo_root() / "artifacts").resolve()


def results() -> Path:
    """Where the CLI writes campaign output. Defaults beside the caller, not in the package.

    Resolving this relative to the working directory is what lets an installed
    ``hubbatching`` be used on data that has nothing to do with this repository.
    """
    return (_from_env("HUBBATCH_RESULTS") or Path.cwd() / "results").resolve()


def scratch() -> Path:
    """Regenerable run output: samples, enumerations, checkpoints. Never committed.

    Falls back to ``$SCRATCH`` because cluster environments already set it, so a
    job script needs no extra configuration to write somewhere sensible.
    """
    return (_from_env("HUBBATCH_SCRATCH", "SCRATCH") or repo_root() / "runs").resolve()


def describe() -> str:
    """One line per root and where it came from -- print this in run logs.

    Provenance beats the path itself: knowing a root was *defaulted* rather than
    configured is what explains an empty directory.
    """
    rows = []
    for name, fn, envs in (
        ("repo", repo_root, ("HUBBATCH_REPO",)),
        ("data", data_dir, ("HUBBATCH_DATA",)),
        ("artifacts", artifacts, ("HUBBATCH_ARTIFACTS",)),
        ("results", results, ("HUBBATCH_RESULTS",)),
        ("scratch", scratch, ("HUBBATCH_SCRATCH", "SCRATCH")),
    ):
        source = next((f"${e}" for e in envs if os.environ.get(e)), "default")
        rows.append(f"  {name:<10} {fn()}  ({source})")
    return "hubbatching paths:\n" + "\n".join(rows)
