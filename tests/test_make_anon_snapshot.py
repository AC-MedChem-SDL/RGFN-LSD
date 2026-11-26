"""Integration tests for the snapshot build.

CI already exercises the happy path on every push (it builds the real snapshot).
What it cannot show is that the build *refuses* — so these tests cover the paths
that must fail, which are the ones that would let identity reach a reviewer.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "tools" / "make_anon_snapshot.sh"

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git required")


def build_repo(tmp_path: Path, extra: dict[str, str] | None = None) -> Path:
    """A miniature copy of this repo: real tools, minimal content, one commit."""
    repo = tmp_path / "repo"
    (repo / "tools").mkdir(parents=True)
    for name in ("check_identity.py", "make_anon_snapshot.sh",
                 "identity_denylist.txt", "identity_allowlist.txt"):
        shutil.copy(REPO / "tools" / name, repo / "tools" / name)
    (repo / "tools" / "anon_templates").mkdir()
    shutil.copy(REPO / "tools" / "anon_templates" / "NOTICE",
                repo / "tools" / "anon_templates" / "NOTICE")
    notice = "Copyright 2026 Mark Stevens\n"  # identity-check: ignore (fixture)
    (repo / "NOTICE").write_text(notice)
    readme = "# x\n<!-- IDENTITY:BEGIN -->\nby Mark Stevens\n<!-- IDENTITY:END -->\n"  # identity-check: ignore (fixture)
    (repo / "README.md").write_text(readme)
    for rel, body in (extra or {}).items():
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.name=T", "-c", "user.email=t@e.co",
                    "commit", "-qm", "init"], cwd=repo, check=True)
    return repo


def run_build(repo: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(repo / "tools" / "make_anon_snapshot.sh"), *extra],
                          cwd=repo, capture_output=True, text=True)


def test_clean_repo_builds(tmp_path: Path) -> None:
    r = run_build(build_repo(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "CLEAN" in r.stdout


def test_identity_outside_an_identity_block_blocks_the_build(tmp_path: Path) -> None:
    """The assertion the whole release process rests on."""
    leak = {"docs/leak.md": "we ran this on balam\n"}  # identity-check: ignore (fixture)
    repo = build_repo(tmp_path, leak)
    r = run_build(repo)
    assert r.returncode == 1
    assert "FAILED" in r.stdout
    assert "Nothing was published" in r.stdout


def test_snapshot_history_has_exactly_one_anonymous_author(tmp_path: Path) -> None:
    repo = build_repo(tmp_path)
    assert run_build(repo).returncode == 0
    log = subprocess.run(["git", "-C", str(repo / "build" / "anon"), "log",
                          "--format=%an <%ae>"], capture_output=True, text=True, check=True)
    assert log.stdout.strip() == "Anonymous <anonymous@example.com>"


def test_notice_is_substituted_and_readme_block_stripped(tmp_path: Path) -> None:
    repo = build_repo(tmp_path)
    assert run_build(repo).returncode == 0
    out = repo / "build" / "anon"
    assert "Anonymous Authors" in (out / "NOTICE").read_text()
    assert "Mark Stevens" not in (out / "README.md").read_text()  # identity-check: ignore


def test_named_workshop_paper_is_dropped(tmp_path: Path) -> None:
    paper = "RGFN_HB_NeurIPS_workshop_paper.pdf"
    repo = build_repo(tmp_path, {paper: "named workshop paper"})
    assert run_build(repo).returncode == 0
    assert not (repo / "build" / "anon" / paper).exists()


def test_oversize_artifact_is_refused(tmp_path: Path) -> None:
    """A venue size cap is a hard limit; the build must not hand over an overage."""
    repo = build_repo(tmp_path)
    r = run_build(repo, "--zip", str(tmp_path / "a.zip"), "--max-mb", "0")
    assert r.returncode == 1
    assert "over the 0 MB budget" in r.stdout


def test_repeated_builds_do_not_trip_on_the_previous_git_repo(tmp_path: Path) -> None:
    """Regression: rm -rf over a just-created git tree fails on NFS."""
    repo = build_repo(tmp_path)
    for _ in range(3):
        assert run_build(repo).returncode == 0
