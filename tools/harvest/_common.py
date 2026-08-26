"""Shared helpers for the harvest scripts.

Harvesting is the one place this project copies data from a machine-specific tree
into a committed artifact, so it is also the one place a username can enter the
repository. Both helpers below exist to stop that happening by construction rather
than by review.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def md5(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.md5()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def redact_paths(obj, keep: int = 2):
    """Replace absolute paths with their trailing components, recursively.

    Run summaries carry bookkeeping paths -- which slice files were merged, where a
    pool was read from -- that no figure reads but that do carry a username into a
    committed artifact. Keeping the last two components preserves what is actually
    informative (how many slices, which ones) and drops the machine prefix.

    This is redaction, not deletion: the md5 of the unredacted original is recorded
    in the harvest's provenance.json, so the copy remains checkable against its source.
    """
    if isinstance(obj, dict):
        return {k: redact_paths(v, keep) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_paths(v, keep) for v in obj]
    if isinstance(obj, str) and obj.startswith("/"):
        parts = Path(obj).parts[-keep:]
        return str(Path(*parts)) if parts else obj
    return obj
