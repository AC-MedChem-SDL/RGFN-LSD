"""``hubbatching`` command line: run the method on your own data.

The package API is the library; this is the way in for someone who has a generator's output
and wants a library out of it. Every subcommand is a thin wrapper over a module here, and each
module keeps its own ``main()`` so it also runs standalone
(``python -m hubbatching.cli.campaign ...``).

The pipeline, in order::

    your generator  ->  records.csv + meta.json (+ routes.json)      docs/INPUT_CONTRACT.md
          |
          |  hubbatching inspect      does this directory support what I want?
          v
    hubbatching pick-hubs             rank hubs by recovered flow        -> hubs.csv
          |
          |  your generator enumerates each hub's children              -> enum_children.json
          v
    hubbatching campaign              both strategies at one operating point
    hubbatching sweep                 curves over diversity cutoff / budget
    hubbatching surface               the two-knob (reward bar x cutoff) grid
    hubbatching export                a selected library -> a bench plan

``hubbatching demo`` runs the whole thing on the bundled toy dataset in seconds, with no
generator, no GPU and no downloads. It is the fastest way to see what the outputs look like
before pointing anything at real data.
"""

from __future__ import annotations

__all__ = ["main"]


def main(argv=None) -> int:
    """Entry point for the ``hubbatching`` console script."""
    from hubbatching.cli.__main__ import main as _main

    return _main(argv)
