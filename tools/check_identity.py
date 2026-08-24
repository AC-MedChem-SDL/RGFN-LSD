#!/usr/bin/env python3
"""Fail if anything in the tree could de-anonymize the authors.

Double-blind review leaks through five channels, and this checks four of them
(the fifth, hosting identity, is a delivery decision -- see docs/ANONYMITY.md):

  1. CONTENT   -- names, emails, usernames, cluster names, allocation codes in text
  2. PATHNAME  -- the same, in file and directory *names* (a content grep misses these)
  3. ABSPATH   -- machine-specific absolute paths, identifying or not; these also
                  break portability, so the rule earns its keep outside review
  4. BINARY    -- metadata embedded in PDF/PNG/XLSX/IPYNB (creator, author, title)

The patterns themselves live in a data file (default ``tools/identity_denylist.txt``)
so that this source file carries no identity of its own and can ship anywhere.

Usage
-----
    python3 tools/check_identity.py                  # tracked files, fail on any hit
    python3 tools/check_identity.py --report         # print findings, always exit 0
    python3 tools/check_identity.py --root /tmp/snap --all   # audit a built snapshot
    python3 tools/check_identity.py --json           # machine-readable

Exit codes: 0 clean (or --report), 1 findings, 2 bad invocation.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

# Absolute-path prefixes that are machine-independent and therefore fine to hardcode.
SAFE_ABS_PREFIXES = (
    "/usr/", "/bin/", "/sbin/", "/lib/", "/etc/", "/opt/", "/dev/null", "/dev/stdin",
    "/dev/stdout", "/dev/stderr", "/tmp/", "/var/tmp/", "/proc/", "/sys/",
)
ABSPATH_RE = re.compile(r"(?<![\w.\-/])(/(?:home|scratch|project|Users|work|gpfs|nfs|mnt)/[\w.\-/]+)")

# Directories never worth walking. Kept small on purpose: a real leak hiding in a
# skipped directory is worse than a slow run.
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
             "node_modules", ".venv", "venv", ".eggs", "build", "dist"}

BINARY_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".xlsx", ".xls", ".docx",
                   ".pptx", ".npy", ".npz", ".pkl", ".pt", ".ckpt", ".so", ".zip"}

PDF_META_RE = re.compile(rb"/(Creator|Producer|Author|Title|Subject|Keywords)\s*\(([^)]{0,300})\)")

# Line-level escape hatch, for lines that must contain a forbidden pattern to do
# their job: this checker's own test fixtures, and documentation showing an
# example of what not to write. Use it sparingly and always with a reason -- it is
# the one way identity can walk past the gate.
SUPPRESS_RE = re.compile(r"identity-check:\s*ignore")


@dataclass
class Rule:
    category: str
    pattern: re.Pattern
    source: str  # the raw denylist line, for error messages


@dataclass
class Finding:
    surface: str      # CONTENT | PATHNAME | ABSPATH | BINARY
    category: str
    path: str
    line: int         # 0 when not line-addressable
    excerpt: str
    rule: str

    def as_row(self) -> str:
        loc = f"{self.path}:{self.line}" if self.line else self.path
        return f"  [{self.surface}/{self.category}] {loc}\n      {self.excerpt}"


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    scanned: int = 0
    skipped_binary_meta: int = 0


def load_rules(paths: list[Path]) -> list[Rule]:
    """Parse ``category:kind:pattern`` lines. kind is ``literal`` or ``regex``."""
    rules: list[Rule] = []
    for p in paths:
        if not p.exists():
            continue
        for raw in p.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(":", 2)
            if len(parts) != 3:
                sys.exit(f"{p}: malformed rule (want category:kind:pattern): {raw!r}")
            category, kind, pat = (s.strip() for s in parts)
            if kind == "literal":
                rx = re.compile(re.escape(pat), re.IGNORECASE)
            elif kind == "regex":
                try:
                    rx = re.compile(pat, re.IGNORECASE)
                except re.error as exc:
                    sys.exit(f"{p}: bad regex {pat!r}: {exc}")
            else:
                sys.exit(f"{p}: unknown kind {kind!r} (want literal|regex): {raw!r}")
            rules.append(Rule(category, rx, line))
    if not rules:
        sys.exit("no rules loaded -- pass --denylist or create tools/identity_denylist.txt")
    return rules


def load_allowlist(path: Path) -> list[re.Pattern]:
    """Repo-relative globs where identity is permitted (LICENSE, CITATION.cff, ...)."""
    if not path.exists():
        return []
    out = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            out.append(re.compile(_glob_to_re(line)))
    return out


def _glob_to_re(glob: str) -> str:
    # ``**`` spans separators, ``*`` does not. Anchored at both ends.
    out, i = ["^"], 0
    while i < len(glob):
        if glob.startswith("**/", i):
            out.append("(?:.*/)?"); i += 3
        elif glob.startswith("**", i):
            out.append(".*"); i += 2
        elif glob[i] == "*":
            out.append("[^/]*"); i += 1
        elif glob[i] == "?":
            out.append("[^/]"); i += 1
        else:
            out.append(re.escape(glob[i])); i += 1
    out.append("$")
    return "".join(out)


def list_files(root: Path, use_git: bool) -> list[Path]:
    if use_git:
        try:
            res = subprocess.run(["git", "-C", str(root), "ls-files", "-z"],
                                 capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            sys.exit(f"{root} is not a git repo (or git is missing) -- use --all")
        names = [n for n in res.stdout.decode().split("\0") if n]
        return [root / n for n in names]
    files = []
    for p in root.rglob("*"):
        if p.is_dir():
            continue
        if any(part in SKIP_DIRS for part in p.relative_to(root).parts):
            continue
        files.append(p)
    return sorted(files)


def extract_binary_metadata(path: Path) -> list[str]:
    """Return metadata strings embedded in a binary, for targeted reporting."""
    out: list[str] = []
    suffix = path.suffix.lower()
    try:
        if suffix == ".pdf":
            blob = path.read_bytes()
            for m in PDF_META_RE.finditer(blob):
                out.append(f"{m.group(1).decode()}={m.group(2).decode('latin-1')}")
        elif suffix == ".png":
            blob = path.read_bytes()
            pos = 8
            while pos + 8 <= len(blob):
                length = int.from_bytes(blob[pos:pos + 4], "big")
                ctype = blob[pos + 4:pos + 8]
                if ctype in (b"tEXt", b"iTXt", b"zTXt"):
                    out.append(blob[pos + 8:pos + 8 + min(length, 300)].decode("latin-1"))
                if ctype == b"IDAT":  # metadata precedes image data; stop early
                    break
                pos += 12 + length
        elif suffix in (".xlsx", ".docx", ".pptx"):
            with zipfile.ZipFile(path) as z:
                for name in ("docProps/core.xml", "docProps/app.xml"):
                    if name in z.namelist():
                        out.append(z.read(name).decode("utf-8", "replace"))
        elif suffix == ".ipynb":
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            out.append(json.dumps(data.get("metadata", {})))
    except Exception as exc:  # a malformed asset is a reporting problem, not a crash
        out.append(f"<unreadable metadata: {type(exc).__name__}>")
    return out


def scan(root: Path, files: list[Path], rules: list[Rule],
         allow: list[re.Pattern], check_abspath: bool) -> Report:
    rep = Report()
    seen: set[tuple[str, str, str, int, str]] = set()

    def add(f: Finding) -> None:
        # Overlapping rules routinely match the same span (an email matches both the
        # name regex and the domain regex). Report the location once per category so
        # the counts mean "places to fix", not "rules that fired".
        key = (f.surface, f.category, f.path, f.line, f.excerpt)
        if key not in seen:
            seen.add(key)
            rep.findings.append(f)

    for path in files:
        try:
            rel = str(path.relative_to(root))
        except ValueError:
            rel = str(path)
        allowed = any(a.match(rel) for a in allow)

        # --- surface 2: the pathname itself (never allowlisted: a filename that
        # names a cluster node leaks even inside an allowlisted file's directory)
        for rule in rules:
            if rule.pattern.search(rel):
                add(Finding("PATHNAME", rule.category, rel, 0, rel, rule.source))

        if not path.is_file() or path.is_symlink():
            continue
        rep.scanned += 1

        suffix = path.suffix.lower()
        if suffix in BINARY_SUFFIXES:
            # --- surface 4: raw bytes (catches anything) + structured metadata
            try:
                blob = path.read_bytes()
            except OSError:
                continue
            text = blob.decode("latin-1")
            if not allowed:
                for rule in rules:
                    m = rule.pattern.search(text)
                    if m:
                        lo, hi = max(0, m.start() - 40), min(len(text), m.end() + 40)
                        add(Finding("BINARY", rule.category, rel, 0,
                                    repr(text[lo:hi]), rule.source))
            for meta in extract_binary_metadata(path):
                for rule in rules:
                    if rule.pattern.search(meta) and not allowed:
                        add(Finding("BINARY", rule.category, rel, 0,
                                    f"metadata: {meta[:160]}", rule.source))
            continue

        # --- surfaces 1 and 3: text content
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "\0" in content[:8192]:  # unknown binary type; fall back to byte scan
            rep.skipped_binary_meta += 1
        for lineno, line in enumerate(content.splitlines(), start=1):
            if len(line) > 4000:
                line = line[:4000]
            if SUPPRESS_RE.search(line):
                continue
            if not allowed:
                for rule in rules:
                    m = rule.pattern.search(line)
                    if m:
                        add(Finding("CONTENT", rule.category, rel, lineno,
                                    line.strip()[:200], rule.source))
            if check_abspath:
                for m in ABSPATH_RE.finditer(line):
                    hit = m.group(1)
                    if hit.startswith(SAFE_ABS_PREFIXES):
                        continue
                    add(Finding("ABSPATH", "portability", rel, lineno,
                                line.strip()[:200], f"absolute path {hit}"))
    return rep


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=None,
                    help="tree to scan (default: git toplevel of cwd)")
    ap.add_argument("--denylist", type=Path, action="append", default=None,
                    help="rule file; repeatable (default: tools/identity_denylist.txt "
                         "plus tools/identity_denylist.local.txt if present)")
    ap.add_argument("--allowlist", type=Path, default=None,
                    help="globs where identity is permitted "
                         "(default: tools/identity_allowlist.txt)")
    ap.add_argument("--all", action="store_true",
                    help="walk the filesystem instead of using git ls-files")
    ap.add_argument("--no-abspath", action="store_true",
                    help="skip the machine-specific absolute-path check")
    ap.add_argument("--report", action="store_true", help="always exit 0")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    ap.add_argument("--max-per-category", type=int, default=12,
                    help="examples printed per category (default 12)")
    args = ap.parse_args()

    if args.root:
        root = args.root.resolve()
    else:
        try:
            top = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                                 capture_output=True, check=True, text=True)
            root = Path(top.stdout.strip())
        except (subprocess.CalledProcessError, FileNotFoundError):
            root = Path.cwd()
    if not root.is_dir():
        sys.exit(f"--root {root} is not a directory")

    here = Path(__file__).resolve().parent
    denylists = args.denylist or [here / "identity_denylist.txt",
                                  here / "identity_denylist.local.txt"]
    allowpath = args.allowlist or (here / "identity_allowlist.txt")

    rules = load_rules(denylists)
    allow = load_allowlist(allowpath)
    files = list_files(root, use_git=not args.all)
    rep = scan(root, files, rules, allow, check_abspath=not args.no_abspath)

    if args.json:
        print(json.dumps({
            "root": str(root), "files_scanned": rep.scanned,
            "findings": [f.__dict__ for f in rep.findings],
        }, indent=2))
        return 0 if (args.report or not rep.findings) else 1

    by_cat: dict[tuple[str, str], list[Finding]] = {}
    for f in rep.findings:
        by_cat.setdefault((f.surface, f.category), []).append(f)

    print(f"identity check: {rep.scanned} files under {root}")
    if not rep.findings:
        print("CLEAN -- no identity or machine-specific paths found.")
        return 0

    files_hit = len({f.path for f in rep.findings})
    print(f"\n{len(rep.findings)} finding(s) across {files_hit} file(s):\n")
    for (surface, category), items in sorted(by_cat.items()):
        n_files = len({i.path for i in items})
        print(f"{surface}/{category}: {len(items)} hit(s) in {n_files} file(s)")
        for item in items[:args.max_per_category]:
            print(item.as_row())
        if len(items) > args.max_per_category:
            print(f"      ... and {len(items) - args.max_per_category} more")
        print()
    return 0 if args.report else 1


if __name__ == "__main__":
    sys.exit(main())
