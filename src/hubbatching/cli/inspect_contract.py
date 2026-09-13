"""``hubbatching inspect`` -- does this directory support what I am about to ask for?

Run this before a long job, not after one. It reads a generator's output directory, reports
which stages of the pipeline it can feed, and names what is missing for the ones it cannot.

The check that earns its keep is ``routes.json``. Hub ranking, the campaign and the cost model
all work without routes, so a run with none will complete, print plausible numbers, and look
fine -- and then the bench plan cannot be produced, and the routes are **not recoverable**: the
trajectory is gone once sampling ended. In this project that exact silence cost a re-sample of
36 of 40 cell-seeds, discovered months later. Thirty seconds here is the cheapest place to find
it.

    hubbatching inspect path/to/sample-dir
    hubbatching inspect path/to/sample-dir --enum-children path/to/enum_children.json
    hubbatching inspect path/to/sample-dir --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

STAGES = [
    ("can_rank_hubs", "rank hubs (pick-hubs)", "records.csv + meta.json"),
    ("can_hub_batch", "run a campaign (campaign / sweep / surface)", "+ enum_children.json"),
    ("can_export_bench_plan", "export a bench plan (export)", "+ routes.json"),
]


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="hubbatching inspect",
        description="Report which pipeline stages a generator's output directory can feed.",
    )
    ap.add_argument("sample_dir", help="directory holding records.csv and meta.json")
    ap.add_argument(
        "--enum-children",
        default=None,
        help="enum_children.json, if it lives outside sample_dir (enumeration output is large "
        "and often written elsewhere)",
    )
    ap.add_argument(
        "--no-routes-expected",
        action="store_true",
        help="declare that this generator has no synthesis routes to give (a fragment-attachment "
        "model, say), so their absence is reported as a property rather than a problem",
    )
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    a = ap.parse_args()

    from hubbatching.adapters.file_adapter import FileAdapter, MissingContractFile

    try:
        adapter = FileAdapter(
            a.sample_dir,
            enum_children=a.enum_children,
            routes_expected=not a.no_routes_expected,
        )
    except MissingContractFile as exc:
        if a.json:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        else:
            print(f"cannot read {a.sample_dir}:\n  {exc}", file=sys.stderr)
        return 1

    report = adapter.validate()

    if a.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if not report["blockers"] else 1

    print(f"\n{Path(a.sample_dir).resolve()}")
    print(f"  model        {report['model']}")
    print(f"  reward       {report['reward_name']}")
    print()
    present = [
        ("records.csv", report["has_records"]),
        ("meta.json", report["has_meta"]),
        ("compositions.json", report["has_compositions"]),
        ("routes.json", f"{report['n_routes']} routes" if report["has_routes"] else False),
        ("enum_children.json", report["has_enum_children"]),
    ]
    for name, state in present:
        mark = "-" if state is False else "y"
        extra = f"  ({state})" if isinstance(state, str) else ""
        print(f"  [{mark}] {name}{extra}")

    print("\n  you can:")
    for key, what, needs in STAGES:
        mark = "y" if report[key] else "-"
        suffix = "" if report[key] else f"   needs {needs}"
        print(f"  [{mark}] {what}{suffix}")

    if report["blockers"]:
        print("\n  blockers:")
        for b in report["blockers"]:
            print(f"    - {b}")
        print()
        return 1

    print("\n  nothing missing.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
