#!/usr/bin/env python3
"""Generate ``artifacts/MANIFEST.csv`` -- what is committed, where it came from, who reads it.

**Generated, never hand-maintained.** A hand-written inventory of a directory is wrong the first
time something is added and nobody notices for months. Everything here is derived from the
filesystem plus the ``provenance.json`` each harvest script already writes, so the manifest
cannot describe a state the repository is not in.

``.gitignore`` refers to this file as the place an artifact too large to commit is recorded
instead -- with a fetch script and a checksum -- rather than being handled by a one-off ignore
rule. The note there says a previous repository accumulated a tail of those and silently lost a
publication figure that way.

    python3 tools/build_manifest.py
    python3 tools/build_manifest.py --check    # fail if the committed manifest is stale

## The `generation` column

This is the one field a reader most needs and the filesystem cannot supply. Results were
assembled over months during which the training budget, the hit gates, one reward and the
generator taxonomy all changed. Nothing on disk is *wrong*; some of it is no longer
*commensurable* with the rest, and a figure that mixes generations is a real hazard rather than
a hypothetical one.

So generation is declared in ``GENERATION`` below, per artifact group, and that declaration is
the thing to update when a re-run lands -- along with re-running the harvest script named in
``HARVESTED_BY``. Until then a group carries the generation it was measured under.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ARTIFACTS = REPO / "artifacts"
MANIFEST = ARTIFACTS / "MANIFEST.csv"

# Which harvest script produces each group. Re-running it is how a group is refreshed.
HARVESTED_BY = {
    "external": "tools/harvest/external.py",
    "mechanism": "tools/harvest/mechanism.py",
    "reaction_budget": "tools/harvest/reaction_budget.py",
    "rewards": "tools/harvest/selection_rewards.py",
    "similarity": "tools/harvest/selection_smiles.py",
    "sparrow_diversity": "tools/harvest/sparrow_diversity.py",
    "two_knob": "tools/harvest/two_knob_surface.py",
    "yield_risk": "tools/harvest/yield_risk.py",
}

# Which published exhibit reads each group. A group nothing reads is either dead weight or a
# figure that was lost -- both worth noticing.
READ_BY = {
    "external": "reproduce/table1_external.py",
    "mechanism": "reproduce/fig2_floor_and_ceiling.py",
    "reaction_budget": "reproduce/fig1_reaction_budget.py",
    "rewards": "reproduce/figA1_yield_risk.py",
    "similarity": "reproduce/fig3_selection_vs_enumeration.py",
    "sparrow_diversity": "reproduce/fig3_selection_vs_enumeration.py",
    "two_knob": "reproduce/figA2_two_knob_surface.py",
    "yield_risk": "reproduce/figA1_yield_risk.py",
}

# The measurement generation each group belongs to. UPDATE THIS when a re-run lands.
GENERATION = {group: "v1" for group in HARVESTED_BY}

# Per-path overrides, matched as a path PREFIX against the repo-relative path. More specific
# than the group default, because generation is not always uniform within a group.
#
# Three states, and the distinction between the last two is the one that matters:
#
#   v1           measured under v1 standards. A newer measurement of the same quantity will
#                exist once the re-run reaches this cell.
#   v1-stale     its SOURCE has already been regenerated. A refresh is available NOW -- re-run
#                the group's harvest script.
#   invalidated  NOT superseded. The quantity itself was redefined, so there is no newer
#                measurement of the same thing and there never will be. An invalidated artifact
#                cannot be refreshed by re-harvesting; it can only be re-measured or dropped.
#
# Collapsing "invalidated" into "superseded" would be the dangerous direction: it implies a
# newer number exists somewhere, and someone would go looking for it.
GENERATION_OVERRIDES = [
    # Every 6TD3 cell, in every group. The 6TD3-B CNN_VS oracle REPLACED the Tier2-Tier1
    # differential these cells were docked with, and the old differential was measured to be
    # exploitable by the generator itself. A different reward is a re-dock, not a re-gate, so
    # these are invalid rather than old. reproduce/fig1_reaction_budget.py already excludes
    # 6TD3 from the headline for exactly this reason and reports it alongside instead.
    (
        "artifacts/reaction_budget/seed42",
        "_6td3",
        "invalidated",
        "6TD3-B replaced this reward; re-dock, not re-gate",
    ),
    (
        "artifacts/reaction_budget/seed43",
        "_6td3",
        "invalidated",
        "6TD3-B replaced this reward; re-dock, not re-gate",
    ),
    (
        "artifacts/mechanism/greedy_ceiling",
        "_6td3",
        "invalidated",
        "6TD3-B replaced this reward; re-dock, not re-gate",
    ),
    # The external comparison's S3-GFN seed-43 pool was retrained on 2026-09-12, so the
    # committed head-to-head predates its own source. The retrain has since passed its four
    # verification checks (12,048 trace rows split 10,048 train / 2,000 eval; non-zero train_s,
    # so real training rather than a resume; hash seed present; no RESUME line), which is what
    # makes this re-harvestable NOW rather than pending. The file covers three seeds, so the
    # whole artifact is re-harvested rather than partially edited.
    (
        "artifacts/external",
        "",
        "v1-stale",
        "s3gfn_seh/seed43 retrained + verified 2026-09-12; re-harvest available now",
    ),
]


def generation_of(rel_path: str, group: str) -> tuple[str, str]:
    """(generation, note) for one artifact: the most specific override, else the group default."""
    for prefix, contains, generation, note in GENERATION_OVERRIDES:
        if rel_path.startswith(prefix) and (not contains or contains in rel_path):
            return generation, note
    return GENERATION.get(group, "unknown"), ""


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def group_of(path: Path) -> str:
    rel = path.relative_to(ARTIFACTS)
    return rel.parts[0] if len(rel.parts) > 1 else ""


def build_rows() -> list[dict]:
    provenance: dict[str, dict] = {}
    for p in ARTIFACTS.glob("*/provenance.json"):
        try:
            provenance[p.parent.name] = json.loads(p.read_text())
        except json.JSONDecodeError:
            provenance[p.parent.name] = {}

    # Meta files describing the directory are not artifacts of it. Without this the manifest
    # catalogues its own README as an ungrouped artifact that no figure reads, which then trips
    # the orphan detector -- a false positive in the one check whose value is that a hit means
    # something.
    META = {MANIFEST.name, "README.md"}

    rows = []
    for path in sorted(ARTIFACTS.rglob("*")):
        if not path.is_file() or (path.parent == ARTIFACTS and path.name in META):
            continue
        group = group_of(path)
        prov = provenance.get(group, {})
        rel = str(path.relative_to(REPO))
        generation, note = generation_of(rel, group)
        rows.append(
            {
                "path": rel,
                "group": group,
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
                "generation": generation,
                "generation_note": note,
                "harvested_by": HARVESTED_BY.get(group, ""),
                "read_by": READ_BY.get(group, ""),
                "source_subdir": prov.get("harvested_from_subdir", ""),
                "n_source_files": len(prov.get("sources", []) or []),
            }
        )
    return rows


COLS = [
    "path",
    "group",
    "bytes",
    "sha256",
    "generation",
    "generation_note",
    "harvested_by",
    "read_by",
    "source_subdir",
    "n_source_files",
]


def render(rows: list[dict]) -> str:
    import io

    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="fail if the committed manifest is stale")
    ap.add_argument("--summary", action="store_true", help="print a per-group summary")
    a = ap.parse_args()

    if not ARTIFACTS.exists():
        sys.exit(f"no artifacts directory at {ARTIFACTS}")

    rows = build_rows()
    rendered = render(rows)

    if a.check:
        if not MANIFEST.exists():
            print(f"{MANIFEST} does not exist. Run: python3 tools/build_manifest.py")
            return 1
        if MANIFEST.read_text() != rendered:
            print("artifacts/MANIFEST.csv is stale. Run: python3 tools/build_manifest.py")
            return 1
        print(f"manifest up to date ({len(rows)} files)")
        return 0

    MANIFEST.write_text(rendered)
    total = sum(r["bytes"] for r in rows)
    print(f"wrote {MANIFEST.relative_to(REPO)}  ({len(rows)} files, {total / 1024:.0f} KB)")

    if a.summary or True:
        by_group: dict[str, list[dict]] = {}
        for r in rows:
            by_group.setdefault(r["group"], []).append(r)
        print()
        width = max((len(g) for g in by_group), default=10)
        for group, items in sorted(by_group.items()):
            size = sum(i["bytes"] for i in items)
            gens = sorted({i["generation"] for i in items})
            reader = Path(items[0]["read_by"]).name or "(nothing)"
            print(
                f"  {group:<{width}}  {len(items):4d} files  {size / 1024:7.0f} KB  "
                f"[{'+'.join(gens)}]  -> {reader}"
            )

        flagged = [r for r in rows if r["generation"] not in ("v1",)]
        if flagged:
            print(f"\n  {len(flagged)} file(s) NOT plain v1:")
            seen = set()
            for r in flagged:
                key = (r["generation"], r["generation_note"])
                if key in seen:
                    continue
                seen.add(key)
                n = sum(1 for x in flagged if (x["generation"], x["generation_note"]) == key)
                print(f"    {r['generation']:<12} x{n:<4} {r['generation_note']}")
            print("\n    invalidated != superseded: a redefined quantity has no newer")
            print("    measurement of the same thing, so re-harvesting cannot fix it.")
        orphans = [g for g, i in by_group.items() if not i[0]["read_by"]]
        if orphans:
            print(f"\n  NOT READ BY ANY reproduce/ SCRIPT: {orphans}")
            print("  Either dead weight, or a figure that has gone missing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
