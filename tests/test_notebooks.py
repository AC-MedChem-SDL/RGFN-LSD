"""The notebooks must actually run.

A tutorial that raises on cell 4 is worse than no tutorial: it costs the reader their trust
before they have learned anything, and they cannot tell whether they broke it or we did. These
are the repository's documentation for four of its five extension points, so they are tested
like code.

Executing them here also catches the failure mode that documentation normally has no defence
against — an API changing underneath prose that still *reads* correctly.
"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
NOTEBOOKS = REPO / "notebooks"
SPECS = REPO / "tools" / "notebook_specs"


def notebook_paths():
    return sorted(NOTEBOOKS.glob("*.ipynb")) if NOTEBOOKS.exists() else []


pytestmark = pytest.mark.skipif(not notebook_paths(), reason="no notebooks built")


@pytest.mark.parametrize("nb_path", notebook_paths(), ids=lambda p: p.stem)
def test_notebook_runs(nb_path: Path):
    """Execute every code cell in order, in a fresh namespace."""
    matplotlib = pytest.importorskip("matplotlib")
    matplotlib.use("Agg")

    doc = json.loads(nb_path.read_text())
    namespace: dict = {"__name__": "__main__"}

    for i, cell in enumerate(doc["cells"]):
        if cell["cell_type"] != "code":
            continue
        source = "".join(cell["source"])
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                exec(compile(source, f"{nb_path.name}#cell{i}", "exec"), namespace)
        except Exception as exc:  # noqa: BLE001 - we want the cell number in the message
            pytest.fail(
                f"{nb_path.name} cell {i} raised {type(exc).__name__}: {exc}\n"
                f"--- cell source ---\n{source}"
            )


@pytest.mark.parametrize("nb_path", notebook_paths(), ids=lambda p: p.stem)
def test_notebook_has_no_stored_outputs(nb_path: Path):
    """Outputs bloat the repository, make diffs unreadable, and carry kernel paths and
    usernames into a tree the anonymity gate then has to scrub."""
    doc = json.loads(nb_path.read_text())
    for i, cell in enumerate(doc["cells"]):
        if cell["cell_type"] != "code":
            continue
        assert not cell.get("outputs"), f"{nb_path.name} cell {i} has stored outputs"
        assert (
            cell.get("execution_count") is None
        ), f"{nb_path.name} cell {i} has an execution count"


@pytest.mark.parametrize("nb_path", notebook_paths(), ids=lambda p: p.stem)
def test_notebook_metadata_is_not_machine_specific(nb_path: Path):
    """A real kernelspec records the interpreter PATH, which is identifying."""
    doc = json.loads(nb_path.read_text())
    blob = json.dumps(doc.get("metadata", {}))
    for marker in ("/home/", "/Users/", "C:\\\\", "conda/envs"):
        assert marker not in blob, f"{nb_path.name} metadata contains {marker!r}"


@pytest.mark.skipif(not SPECS.exists(), reason="specs not present")
def test_notebooks_match_their_specs():
    """Notebooks are generated. If a committed one has drifted from its spec, the spec is no
    longer the source of truth and the next regeneration would silently revert someone's edit."""
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, str(REPO / "tools" / "build_notebooks.py"), "--check"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
