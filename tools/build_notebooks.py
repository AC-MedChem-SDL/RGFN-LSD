#!/usr/bin/env python3
"""Build ``notebooks/*.ipynb`` from the specs in ``tools/notebook_specs/``.

Notebooks are generated rather than hand-edited, for three reasons that all bite eventually:

* **Diffs.** A hand-edited notebook diffs as one enormous JSON line. A spec diffs as prose.
* **Outputs.** Generated notebooks are born with no stored outputs, no execution counts and no
  kernel metadata -- so they stay small, and they carry no username or kernel path into a tree
  the anonymity gate then has to scrub. CI enforces this; generating them means never fighting it.
* **Drift.** When an API changes, the fix is one edit to a spec, not a hunt through JSON.

A spec is a Python module exposing ``TITLE``, ``SUMMARY`` and ``CELLS`` -- a list of
``("md", text)`` and ``("py", code)`` pairs.

    python3 tools/build_notebooks.py
    python3 tools/build_notebooks.py --check     # fail if a committed notebook is stale
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SPECS = Path(__file__).resolve().parent / "notebook_specs"
OUT = REPO / "notebooks"


def load_spec(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def to_source(text: str) -> list[str]:
    """Notebook `source` is a list of lines, each keeping its newline except the last."""
    lines = text.strip("\n").split("\n")
    return [line + "\n" for line in lines[:-1]] + [lines[-1]] if lines else []


def build(module) -> dict:
    cells = []
    for kind, text in module.CELLS:
        if kind == "md":
            cells.append({"cell_type": "markdown", "metadata": {}, "source": to_source(text)})
        elif kind == "py":
            cells.append(
                {
                    "cell_type": "code",
                    "execution_count": None,  # never a number: that is a stored output
                    "metadata": {},
                    "outputs": [],
                    "source": to_source(text),
                }
            )
        else:
            raise ValueError(f"unknown cell kind {kind!r}")

    return {
        "cells": cells,
        "metadata": {
            # Deliberately minimal. A real kernelspec records the interpreter PATH, which is
            # both machine-specific and identifying; `python3` is resolved by the runtime.
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="fail if any notebook is out of date")
    a = ap.parse_args()

    OUT.mkdir(exist_ok=True)
    specs = sorted(SPECS.glob("[0-9]*.py"))
    if not specs:
        sys.exit(f"no specs found in {SPECS}")

    stale = []
    for path in specs:
        module = load_spec(path)
        nb = build(module)
        target = OUT / f"{path.stem}.ipynb"
        rendered = json.dumps(nb, indent=1, ensure_ascii=False) + "\n"
        if a.check:
            if not target.exists() or target.read_text() != rendered:
                stale.append(target.name)
        else:
            target.write_text(rendered)
            print(f"  {target.relative_to(REPO)}  ({len(nb['cells'])} cells)  {module.TITLE}")

    if a.check:
        if stale:
            print("stale notebooks: " + ", ".join(stale))
            print("run: python3 tools/build_notebooks.py")
            return 1
        print(f"all {len(specs)} notebooks up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
