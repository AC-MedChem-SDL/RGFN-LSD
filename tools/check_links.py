#!/usr/bin/env python3
"""Check that every relative link in the documentation resolves.

Documentation rots by pointing at things that moved or never existed, and that failure is
invisible until a reader follows the link and finds nothing. This repository started with
several such pointers -- to files named in the README's planned layout that were never written,
and to research-tree paths that do not exist here at all.

**Code fences are skipped**, which is not an optimisation but a correctness requirement: a
reaction SMARTS like ``[C:1](=[O:2])[OH]`` is a valid markdown link by syntax, and a checker
that does not know it is inside a fence reports two false positives on every chemistry example.
A checker with false positives stops being read, which costs the same as not having one.

    python3 tools/check_links.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", "build", "__pycache__", ".pytest_cache", "node_modules"}
LINK = re.compile(r"\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
FENCE = re.compile(r"^\s*(```|~~~)")


def strip_fences(text: str) -> str:
    """Blank out fenced code blocks, preserving line numbers."""
    out, in_fence = [], False
    for line in text.split("\n"):
        if FENCE.match(line):
            in_fence = not in_fence
            out.append("")
            continue
        out.append("" if in_fence else line)
    return "\n".join(out)


def main() -> int:
    md_files = [p for p in REPO.rglob("*.md") if not SKIP_DIRS & set(p.relative_to(REPO).parts)]
    broken = []
    checked = 0
    for md in sorted(md_files):
        body = strip_fences(md.read_text())
        for lineno, line in enumerate(body.split("\n"), 1):
            # Inline code spans can also contain link-shaped text.
            line = re.sub(r"`[^`]*`", "", line)
            for _label, target in LINK.findall(line):
                if target.startswith(("http://", "https://", "#", "mailto:")):
                    continue
                path = target.split("#")[0]
                if not path:
                    continue
                checked += 1
                if not (md.parent / path).resolve().exists():
                    broken.append((md.relative_to(REPO), lineno, target))

    print(f"checked {checked} relative link(s) across {len(md_files)} markdown file(s)")
    if broken:
        print(f"\n{len(broken)} BROKEN:")
        for f, lineno, target in broken:
            print(f"  {f}:{lineno}  ->  {target}")
        return 1
    print("all resolve")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
