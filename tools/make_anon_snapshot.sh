#!/usr/bin/env bash
# Build the anonymous review artifact from the public repo.
#
# The whole point of this script is one assertion, at step 6: the built snapshot
# must pass check_identity.py with an EMPTY allowlist. The public repo permits
# identity in a handful of files; the snapshot permits it nowhere. If that check
# passes, there is provably no author identity left in the artifact -- rather than
# a promise that we remembered to look.
#
# Usage:
#   tools/make_anon_snapshot.sh                       # build into build/anon/
#   tools/make_anon_snapshot.sh --zip anon.zip        # also write a submission zip
#   tools/make_anon_snapshot.sh --out /tmp/snap
#
# Requires: a committed HEAD (the snapshot is taken from git, not the worktree,
# so uncommitted local paths can never leak into it).
set -euo pipefail

REPO="$(git rev-parse --show-toplevel)"
OUT="$REPO/build/anon"
ZIP=""
while [ $# -gt 0 ]; do
  case "$1" in
    --out) OUT="$2"; shift 2 ;;
    --zip) ZIP="$2"; shift 2 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

# Paths that must not exist in the artifact. Release engineering, site config, and
# agent tooling are all irrelevant to a reviewer and all carry identity.
DROP=(
  tools
  cluster
  .claude
  .github/workflows/identity.yml
  CITATION.cff
  CLAUDE.md
  docs/ANONYMITY.md
)

echo "==> staging tracked files at HEAD"
rm -rf "$OUT"; mkdir -p "$OUT"
git -C "$REPO" archive HEAD | tar -x -C "$OUT"

echo "==> dropping non-shipping paths"
for p in "${DROP[@]}"; do
  if [ -e "$OUT/$p" ]; then rm -rf "$OUT/$p"; echo "    - $p"; fi
done

echo "==> substituting identity-bearing files"
# LICENSE is verbatim Apache-2.0 and identity-free -- it is NOT substituted.
# Only NOTICE carries the copyright holders.
for f in NOTICE; do
  if [ -f "$REPO/tools/anon_templates/$f" ]; then
    cp "$REPO/tools/anon_templates/$f" "$OUT/$f"; echo "    ~ $f"
  fi
done

# Strip <!-- IDENTITY:BEGIN --> ... <!-- IDENTITY:END --> blocks from every text
# file, so one public README stays automatically in sync with its anonymous twin.
python3 - "$OUT" <<'PY'
import pathlib, re, sys
root = pathlib.Path(sys.argv[1])
block = re.compile(
    r"[ \t]*<!--[ \t]*IDENTITY:BEGIN[ \t]*-->.*?<!--[ \t]*IDENTITY:END[ \t]*-->[ \t]*\n?",
    re.DOTALL)
n = 0
for p in root.rglob("*"):
    if not p.is_file() or p.suffix.lower() not in {".md", ".txt", ".rst", ".cff", ".yaml", ".yml"}:
        continue
    try:
        text = p.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        continue
    stripped = block.sub("", text)
    if stripped != text:
        p.write_text(stripped, encoding="utf-8")
        n += 1
        print(f"    ~ stripped identity block: {p.relative_to(root)}")
print(f"    ({n} file(s) edited)")
PY

echo "==> normalising figure metadata timestamps"
# matplotlib stamps CreationDate into every PDF. Not identifying, but it is a
# fingerprint and it breaks byte-reproducibility of the figures.
python3 - "$OUT" <<'PY'
import pathlib, re, sys
root = pathlib.Path(sys.argv[1]); n = 0
pat = re.compile(rb"/(CreationDate|ModDate)\s*\(D:[^)]*\)")
for p in root.rglob("*.pdf"):
    blob = p.read_bytes()
    new = pat.sub(lambda m: b"/" + m.group(1) + b" (D:19700101000000Z)", blob)
    if new != blob:
        p.write_bytes(new); n += 1
print(f"    ({n} PDF(s) normalised)")
PY

echo "==> ASSERTING the snapshot is clean with NO allowlist"
if ! python3 "$REPO/tools/check_identity.py" --root "$OUT" --all --allowlist /dev/null; then
  echo ""
  echo "FAILED: identity survived into the snapshot. Fix the source repo (or add the"
  echo "path to DROP / wrap it in an IDENTITY block) and rebuild. Nothing was published."
  exit 1
fi

echo "==> initialising anonymous history (single commit, no author, fixed date)"
STAMP="2000-01-01T00:00:00+00:00"
git -C "$OUT" init -q -b main
git -C "$OUT" add -A
GIT_AUTHOR_NAME=Anonymous GIT_AUTHOR_EMAIL=anonymous@example.com \
GIT_COMMITTER_NAME=Anonymous GIT_COMMITTER_EMAIL=anonymous@example.com \
GIT_AUTHOR_DATE="$STAMP" GIT_COMMITTER_DATE="$STAMP" \
  git -C "$OUT" commit -q -m "Anonymous submission artifact"

if [ -n "$ZIP" ]; then
  echo "==> writing $ZIP"
  # Exclude .git: a zip is for supplementary upload, where history is pure risk.
  (cd "$OUT" && zip -qr "$ZIP" . -x '.git/*') && echo "    $(du -h "$ZIP" | cut -f1)  $ZIP"
fi

echo ""
echo "Snapshot ready: $OUT"
echo "Verify by hand before submitting:  git -C $OUT log --format='%an <%ae> %ad'"
