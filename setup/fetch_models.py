#!/usr/bin/env python3
"""Download trained model checkpoints named in ``setup/models.csv``.

Checkpoints are tens to hundreds of megabytes, so they are archived outside git and fetched on
demand. Everything about *where* they live is data in ``models.csv``, not logic here, so moving
or adding a host is a one-line edit to a CSV rather than a code change.

    python3 setup/fetch_models.py --list
    python3 setup/fetch_models.py toy_rgfn_seh
    python3 setup/fetch_models.py --all --dest data/checkpoints
    python3 setup/fetch_models.py --verify

**Standard library only, deliberately.** This is the first script someone runs, often before
they have installed anything, and sometimes on a cluster login node with an empty environment.
It should not be able to fail for a reason that has nothing to do with downloading a file.

Every entry carries a SHA-256 and it is always checked. A checkpoint that is silently truncated
-- a dropped connection, a proxy returning an error page with a 200 status -- loads as a model
with garbage weights and produces plausible, wrong numbers. That failure is invisible
downstream, so it gets caught here or not at all.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REGISTRY = Path(__file__).resolve().parent / "models.csv"
DEFAULT_DEST = REPO / "data" / "checkpoints"

CHUNK = 1 << 20  # 1 MiB


def load_registry() -> list[dict]:
    if not REGISTRY.exists():
        sys.exit(f"no registry at {REGISTRY}")
    with REGISTRY.open() as fh:
        rows = [r for r in csv.DictReader(fh) if r.get("name") and not r["name"].startswith("#")]
    return rows


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def download(url: str, dest: Path) -> None:
    """Stream to a temporary file, then move into place.

    Never write directly to the destination: an interrupted download that left a partial file at
    the real path would be picked up by the next run as though it were complete.
    """
    tmp = dest.with_suffix(dest.suffix + ".part")
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(url) as response:
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            with tmp.open("wb") as out:
                while True:
                    chunk = response.read(CHUNK)
                    if not chunk:
                        break
                    out.write(chunk)
                    done += len(chunk)
                    if total:
                        pct = 100 * done / total
                        print(f"\r    {human(done)} / {human(total)}  {pct:5.1f}%", end="")
                    else:
                        print(f"\r    {human(done)}", end="")
            print()
    except urllib.error.HTTPError as exc:
        tmp.unlink(missing_ok=True)
        sys.exit(f"    HTTP {exc.code} fetching {url}")
    except urllib.error.URLError as exc:
        tmp.unlink(missing_ok=True)
        sys.exit(f"    cannot reach {url}: {exc.reason}\n"
                 "    (compute nodes are often air-gapped -- try a login node)")
    shutil.move(str(tmp), str(dest))


def fetch_one(row: dict, dest_root: Path, force: bool) -> bool:
    name, url, want = row["name"], row["url"], (row.get("sha256") or "").strip()
    dest = dest_root / row.get("filename", f"{name}.pt")

    print(f"  {name}")
    if not url or url.startswith("TBD"):
        print("    no URL registered yet -- see setup/README.md")
        return False

    if dest.exists() and not force:
        if want and sha256(dest) == want:
            print(f"    already present and verified: {dest}")
            return True
        if want:
            print("    present but CHECKSUM MISMATCH -- re-downloading")
        else:
            print(f"    already present (no checksum registered): {dest}")
            return True

    download(url, dest)

    if want:
        got = sha256(dest)
        if got != want:
            dest.unlink(missing_ok=True)
            sys.exit(
                f"    CHECKSUM MISMATCH for {name}\n"
                f"      expected {want}\n"
                f"      got      {got}\n"
                "    The file has been deleted rather than left in place: a truncated or "
                "substituted checkpoint loads as a model with wrong weights and produces "
                "plausible, wrong numbers."
            )
        print(f"    verified {got[:16]}...")
    else:
        print("    WARNING: no checksum registered, nothing verified")
    print(f"    -> {dest}")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("names", nargs="*", help="model names from setup/models.csv")
    ap.add_argument("--all", action="store_true", help="fetch everything registered")
    ap.add_argument("--list", action="store_true", help="show the registry and what is present")
    ap.add_argument("--verify", action="store_true", help="re-check checksums of what is present")
    ap.add_argument("--force", action="store_true", help="re-download even if present and valid")
    ap.add_argument("--dest", default=str(DEFAULT_DEST), help=f"default: {DEFAULT_DEST}")
    a = ap.parse_args()

    rows = load_registry()
    dest_root = Path(a.dest)

    if a.list:
        width = max(len(r["name"]) for r in rows)
        print(f"\n  registry: {REGISTRY}")
        print(f"  dest:     {dest_root}\n")
        for r in rows:
            path = dest_root / r.get("filename", f"{r['name']}.pt")
            state = "present" if path.exists() else "-"
            size = r.get("size_mb", "?")
            print(f"  {state:>8}  {r['name']:<{width}}  {size:>6} MB  {r.get('description','')}")
        print()
        return 0

    if a.verify:
        bad = 0
        for r in rows:
            path = dest_root / r.get("filename", f"{r['name']}.pt")
            want = (r.get("sha256") or "").strip()
            if not path.exists() or not want:
                continue
            got = sha256(path)
            ok = got == want
            bad += not ok
            print(f"  {'ok  ' if ok else 'BAD '} {r['name']}")
        return 1 if bad else 0

    selected = rows if a.all else [r for r in rows if r["name"] in set(a.names)]
    if not selected:
        unknown = set(a.names) - {r["name"] for r in rows}
        if unknown:
            print(f"unknown model(s): {sorted(unknown)}", file=sys.stderr)
        print("nothing selected. Try --list, a name, or --all.", file=sys.stderr)
        return 2

    print(f"\nfetching {len(selected)} model(s) into {dest_root}\n")
    for r in selected:
        fetch_one(r, dest_root, a.force)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
