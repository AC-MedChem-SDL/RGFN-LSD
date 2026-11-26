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
# Venue submission caps (total upload, PDF included). GEM/NeurIPS workshop: 50 MB.
# Keep headroom for the paper itself, so the artifact is checked against less.
MAX_MB=40
while [ $# -gt 0 ]; do
  case "$1" in
    --out) OUT="$2"; shift 2 ;;
    --zip) ZIP="$2"; shift 2 ;;
    --max-mb) MAX_MB="$2"; shift 2 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

# Paths that must not exist in the artifact. Release engineering, site config, and
# agent tooling are all irrelevant to a reviewer and all carry identity.
# Drop the RELEASE tooling, not all of tools/. `tools/` began as the identity toolchain alone,
# so dropping it wholesale was right; it now also holds builders a reviewer legitimately wants --
# the toy dataset the T0 demo runs on, the notebook generator, the artifact manifest, the link
# checker. Dropping those would hand over a tree whose own regeneration instructions point at
# files that are not there.
#
# Anything named here must also have its tests named below, or the snapshot ships tests that
# error on a missing file.
DROP=(
  tools/check_identity.py
  tools/make_anon_snapshot.sh
  tools/identity_allowlist.txt
  tools/identity_denylist.txt
  tools/anon_templates
  tools/review
  tools/harvest        # reads the research tree by path; useless without it, and names it
  cluster
  .claude
  .github/workflows/identity.yml
  CITATION.cff
  RGFN_HB_NeurIPS_workshop_paper.pdf
  docs/ANONYMITY.md
  # These test the release tooling dropped above -- shipping them would hand a reviewer tests
  # that error on a missing file. Named individually rather than dropping tests/ wholesale, so
  # method tests ship.
  tests/test_check_identity.py
  tests/test_make_anon_snapshot.py
)

# On NFS, rm -rf can fail with "Directory not empty" because files still open
# elsewhere linger as .nfs* handles -- and the previous run left a git repo here.
# Move the stale tree aside rather than aborting the build.
rm_robust() {
  target="$1"
  [ -e "$target" ] || return 0
  rm -rf "$target" 2>/dev/null && return 0
  aside="${target}.stale.$$"
  mv "$target" "$aside" || { echo "cannot clear $target" >&2; return 1; }
  rm -rf "$aside" 2>/dev/null || true   # best effort; ignored next run
  return 0
}

echo "==> staging tracked files at HEAD"
rm_robust "$OUT"; mkdir -p "$OUT"
git -C "$REPO" archive HEAD | tar -x -C "$OUT"

echo "==> dropping non-shipping paths"
# A DROP entry that matches nothing is NOT harmless: a typo in an identity-bearing path would
# silently ship that file while the build reported success. So a drop that does nothing is an
# error -- but only when the file was actually THERE to drop.
#
# The precise condition is "tracked at HEAD, yet still present after dropping". That fails
# exactly when something that should have been removed was not, and it passes naturally on a
# repository that simply does not contain a given path (a minimal test fixture, or a checkout
# with no cluster/ directory). Listing exceptions by hand would drift; asking git does not.
drop_failed=()
for p in "${DROP[@]}"; do
  if [ -e "$OUT/$p" ]; then
    rm -rf "$OUT/$p"
    echo "    - $p"
    # Removed above, so anything still here is a removal that did not take.
    [ -e "$OUT/$p" ] && drop_failed+=("$p (removal failed)")
  elif git -C "$REPO" ls-files --error-unmatch "$p" >/dev/null 2>&1; then
    # Tracked at HEAD but absent from the staged tree: the archive and the list disagree.
    drop_failed+=("$p (tracked at HEAD but not staged)")
  else
    echo "    . $p (not in this repository)"
  fi
done
if [ ${#drop_failed[@]} -gt 0 ]; then
  echo >&2
  echo "ABORT: DROP did not do what it says:" >&2
  for p in "${drop_failed[@]}"; do echo "  $p" >&2; done
  echo >&2
  echo "An identity-bearing file may be shipping. Fix the path or the removal." >&2
  exit 1
fi

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

# Dropping files can leave empty directories behind, which read as missing content.
find "$OUT" -mindepth 1 -type d -empty -delete

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
  (cd "$OUT" && zip -qr "$ZIP" . -x '.git/*')
  bytes=$(wc -c < "$ZIP" | tr -d ' ')
  cap=$(( MAX_MB * 1048576 ))
  # Compare bytes, not truncated megabytes: integer MB rounds a 900 KB artifact to
  # 0 and would silently pass a zero cap.
  human=$(awk -v b="$bytes" 'BEGIN{printf "%.1f", b/1048576}')
  echo "    ${human} MB  $ZIP"
  if [ "$bytes" -gt "$cap" ]; then
    echo ""
    echo "FAILED: artifact is ${human} MB, over the ${MAX_MB} MB budget."
    echo "Do not raise the cap. Move large assets to the deposit and leave a"
    echo "checksum in artifacts/MANIFEST.csv -- reviewers need the numbers a"
    echo "figure was drawn from, not the rendered figure."
    echo "Largest entries:"
    (cd "$OUT" && find . -path ./.git -prune -o -type f -print0 \
      | xargs -0 du -k 2>/dev/null | sort -rn | head -10 \
      | awk '{printf "      %6.1f MB  %s\n", $1/1024, $2}')
    exit 1
  fi
fi

echo ""
echo "Snapshot ready: $OUT"
echo "Verify by hand before submitting:  git -C $OUT log --format='%an <%ae> %ad'"
