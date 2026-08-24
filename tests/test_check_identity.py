"""Tests for the anonymity gate.

Everything in the release process rests on tools/check_identity.py being both
sensitive (it fires on every surface) and specific (it can reach CLEAN). A linter
that cries wolf gets disabled; one that never fires is decoration. Both failure
modes are covered here.

These tests are hermetic: they build their own deny-list and allow-list from
placeholder strings rather than reading the real ones. That keeps the suite
independent of edits to the real deny-list -- and keeps this file free of the very
identity it tests for, so the gate passes over its own test suite.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[1] / "tools" / "check_identity.py"

DENYLIST = """\
person:literal:Ada Placeholder
person:regex:[\\w.+-]+@example\\.edu
site:literal:examplecluster
site:literal:alloc-xyz
hosting:literal:example-org
"""


@pytest.fixture()
def tree(tmp_path: Path) -> Path:
    """A minimal repo-shaped tree, with its rule files kept OUTSIDE the scan root.

    A deny-list stored inside the tree it governs is itself a finding -- it
    necessarily contains every string it forbids. The real repo handles that by
    allowlisting the file; the tests dodge it entirely by putting the rules in a
    sibling directory, so no test depends on that exemption being in place.
    """
    rules = tmp_path / "rules"
    rules.mkdir()
    (rules / "deny.txt").write_text(DENYLIST)
    (rules / "allow.txt").write_text("NOTICE\n")
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "clean.py").write_text("from lsdflow.paths import artifacts\n")
    return repo


def run(tree: Path, *extra: str, allowlist: str | None = None) -> subprocess.CompletedProcess:
    rules = tree.parent / "rules"
    args = [sys.executable, str(TOOL), "--root", str(tree), "--all",
            "--denylist", str(rules / "deny.txt"),
            "--allowlist", allowlist or str(rules / "allow.txt"), *extra]
    return subprocess.run(args, capture_output=True, text=True)


def test_clean_tree_passes(tree: Path) -> None:
    r = run(tree)
    assert r.returncode == 0, r.stdout
    assert "CLEAN" in r.stdout


def test_name_in_content_is_caught(tree: Path) -> None:
    (tree / "src" / "leak.py").write_text("# written by Ada Placeholder\n")
    r = run(tree)
    assert r.returncode == 1
    assert "CONTENT/person" in r.stdout


def test_email_regex_is_caught(tree: Path) -> None:
    (tree / "src" / "leak.py").write_text("contact: someone@example.edu\n")
    assert run(tree).returncode == 1


def test_identity_in_a_filename_is_caught(tree: Path) -> None:
    """The surface a content grep misses: innocuous text, identifying name."""
    (tree / "src" / "examplecluster_report.md").write_text("all nodes healthy\n")
    r = run(tree)
    assert r.returncode == 1
    assert "PATHNAME/site" in r.stdout


def test_allowlisted_file_may_carry_identity(tree: Path) -> None:
    (tree / "NOTICE").write_text("Copyright 2026 Ada Placeholder\n")
    assert run(tree).returncode == 0


def test_allowlist_does_not_excuse_a_bad_filename(tree: Path) -> None:
    """Allowlisting covers contents only; a filename leaks from any directory."""
    (tree / "NOTICE").write_text("Copyright 2026 Ada Placeholder\n")
    (tree / "examplecluster.md").write_text("nothing here\n")
    r = run(tree)
    assert r.returncode == 1
    assert "PATHNAME" in r.stdout


def test_empty_allowlist_re_exposes_allowlisted_files(tree: Path) -> None:
    """The assertion make_anon_snapshot.sh relies on."""
    (tree / "NOTICE").write_text("Copyright 2026 Ada Placeholder\n")
    assert run(tree).returncode == 0
    assert run(tree, allowlist="/dev/null").returncode == 1


def test_machine_specific_abspath_is_caught(tree: Path) -> None:
    (tree / "src" / "paths.sh").write_text("OUT=/home/someone/runs\n")
    r = run(tree)
    assert r.returncode == 1
    assert "ABSPATH" in r.stdout


def test_portable_abspaths_are_not_flagged(tree: Path) -> None:
    """/usr/bin/env in a shebang must not be noise, or the check gets switched off."""
    (tree / "src" / "ok.sh").write_text("#!/usr/bin/env bash\nexec /usr/bin/python3\n")
    assert run(tree).returncode == 0


def test_abspath_check_can_be_disabled(tree: Path) -> None:
    (tree / "src" / "paths.sh").write_text("OUT=/home/someone/runs\n")
    assert run(tree, "--no-abspath").returncode == 0


def test_pdf_metadata_is_caught(tree: Path) -> None:
    (tree / "fig.pdf").write_bytes(
        b"%PDF-1.4\n<< /Creator (matplotlib) /Author (Ada Placeholder) >>\n%%EOF\n")
    r = run(tree)
    assert r.returncode == 1
    assert "BINARY" in r.stdout


def test_report_mode_never_fails(tree: Path) -> None:
    (tree / "src" / "leak.py").write_text("# Ada Placeholder\n")
    r = run(tree, "--report")
    assert r.returncode == 0
    assert "CONTENT/person" in r.stdout


def test_findings_are_deduplicated_across_overlapping_rules(tree: Path) -> None:
    """One line matching two rules is one place to fix, so it is reported once."""
    (tree / "src" / "leak.py").write_text("Ada Placeholder <someone@example.edu>\n")
    import json
    r = run(tree, "--json", "--report")
    findings = json.loads(r.stdout)["findings"]
    person = [f for f in findings if f["category"] == "person"]
    assert len(person) == 1, person


def test_missing_denylist_is_an_error_not_a_silent_pass(tree: Path) -> None:
    """A typo'd path must never be indistinguishable from a clean tree."""
    r = subprocess.run(
        [sys.executable, str(TOOL), "--root", str(tree), "--all",
         "--denylist", str(tree / "nope.txt")], capture_output=True, text=True)
    assert r.returncode != 0
    assert "no rules loaded" in (r.stdout + r.stderr)


def test_gitignore_has_no_trailing_comments() -> None:
    """gitignore has no trailing comments: '#' after a pattern is literal text.

    Regression guard. `build/  # comment` silently matched nothing, and the
    snapshot build output was committed on the first push.
    """
    path = Path(__file__).resolve().parents[1] / ".gitignore"
    offenders = [
        (i, line)
        for i, line in enumerate(path.read_text().splitlines(), 1)
        if line.strip() and not line.strip().startswith("#") and "#" in line
    ]
    assert not offenders, f"trailing comments render these patterns inert: {offenders}"
