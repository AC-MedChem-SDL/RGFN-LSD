"""``hubbatching demo`` -- the whole pipeline on the bundled toy dataset, in seconds.

No generator, no GPU, no downloads, no configuration. It runs the same code the published
numbers came from, on 432 real molecules built by real RDKit chemistry, and prints what each
stage produced. Use it to see the shape of the outputs before pointing anything at real data,
and as the first thing to run after installing to confirm the install works.

    hubbatching demo
    hubbatching demo --out-dir ./my-demo --budget 50

**What the numbers here are and are not.** The molecules, the reactions and the routes are real.
The reward is RDKit QED standing in for a target-specific oracle, and the policy
log-probabilities were generated from a self-consistent model of a trained GFlowNet rather than
recovered from one (``examples/toy/meta.json`` says so too). So the margin printed below
illustrates the *mechanism*; it is not a result, and it is not the paper's number. For the
published figures run ``reproduce/``, which reads committed artifacts from the real runs.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from hubbatching.paths import repo_root

BANNER = "=" * 78


def toy_dir() -> Path:
    """Locate the bundled toy dataset, whether running from a checkout or an install."""
    candidates = [
        repo_root() / "examples" / "toy",
        Path(__file__).resolve().parents[3] / "examples" / "toy",
    ]
    for c in candidates:
        if (c / "records.csv").exists():
            return c
    raise FileNotFoundError(
        "cannot find the bundled toy dataset (examples/toy/records.csv). If you are running "
        "from an installed package rather than a checkout, set HUBBATCH_REPO to the checkout, "
        "or regenerate it with `python tools/make_toy_dataset.py`."
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="hubbatching demo",
        description="Run the full pipeline on the bundled toy dataset.",
    )
    ap.add_argument("--out-dir", default="", help="where to write (default: ./hubbatching-demo)")
    ap.add_argument(
        "--reward-threshold",
        type=float,
        default=0.80,
        help="the hit gate, in the reward's own units. The toy reward is QED, so 0.80 keeps the "
        "more drug-like half (default: 0.80)",
    )
    ap.add_argument("--budget", type=int, default=30, help="reaction budget (default: 30)")
    ap.add_argument("--modes", type=int, default=40, help="mode budget (default: 40)")
    ap.add_argument(
        "--cutoff",
        type=float,
        default=0.5,
        help="Tanimoto diversity cutoff: two molecules closer than this are the same mode "
        "(default: 0.5)",
    )
    a = ap.parse_args()

    toy = toy_dir()
    out = Path(a.out_dir) if a.out_dir else Path.cwd() / "hubbatching-demo"
    out.mkdir(parents=True, exist_ok=True)

    meta = json.loads((toy / "meta.json").read_text())

    print(BANNER)
    print("hub-batching demo -- toy dataset")
    print(BANNER)
    print(f"  data      {toy}")
    print(f"  reward    {meta['reward_name']} ({meta.get('reward_description', '')})")
    print(f"  gate      {a.reward_threshold}   diversity cutoff {a.cutoff}")
    print(f"  output    {out}")
    print()
    print("  NOTE: molecules, reactions and routes are real; the reward and the policy")
    print("  log-probabilities are synthetic. These numbers show the mechanism, not a result.")
    print()

    # ---------------------------------------------------------------- 1. inspect
    print(BANNER)
    print("1. inspect -- what does this data support?")
    print(BANNER)
    from hubbatching.adapters.file_adapter import FileAdapter

    adapter = FileAdapter(str(toy))
    report = adapter.validate()
    for key, label in (
        ("can_rank_hubs", "rank hubs"),
        ("can_hub_batch", "run a campaign"),
        ("can_export_bench_plan", "export a bench plan"),
    ):
        print(f"   [{'y' if report[key] else '-'}] {label}")
    print()

    # ---------------------------------------------------------------- 2. pick hubs
    print(BANNER)
    print("2. pick-hubs -- rank intermediates by the flow the model already learned")
    print(BANNER)
    sys.argv = [
        "pick-hubs",
        "--records",
        str(toy / "records.csv"),
        "--out",
        str(out / "hubs.csv"),
        "--pool",
        "all",
        "--order",
        "flow_desc",
        "--n-hubs",
        "40",
    ]
    from hubbatching.cli import pick_hubs

    pick_hubs.main()
    print("   the row order of hubs.csv IS the strategy -- hub-batching walks it top to bottom")
    print()

    # ---------------------------------------------------------------- 3. campaign
    print(BANNER)
    print("3. campaign -- hub-batching vs best-candidate on identical chemistry")
    print(BANNER)
    sys.argv = [
        "campaign",
        "--analysis-dir",
        str(toy),
        "--enum-children",
        str(toy / "enum_children.json"),
        "--reward-threshold",
        str(a.reward_threshold),
        "--similarity",
        str(a.cutoff),
        "--budget-reactions",
        str(a.budget),
        "--budget-modes",
        str(a.modes),
        "--tag",
        "toy",
        "--out-dir",
        str(out),
    ]
    # The campaign driver dumps its full summary.json to stdout, which is right when you invoke
    # it directly and noise here -- the demo's job is to narrate, and the same JSON is written to
    # disk a few lines below. Swallow it rather than teaching the driver about a --quiet flag it
    # would only ever use from here.
    import contextlib
    import io

    from hubbatching.cli import campaign as campaign_cli

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        campaign_cli.main()
    print(
        f"   scored {len(json.loads((toy / 'routes.json').read_text()))} molecules over "
        f"{len(json.loads((toy / 'enum_children.json').read_text())['hubs'])} enumerated hubs"
    )

    # ---------------------------------------------------------------- 4. read it back
    summary = json.loads((out / "summary.json").read_text())
    hb, bc = summary["hub_batching"], summary["best_candidate"]
    key_at_budget = f"case1_modes_at_{a.budget}rxn"
    hb_m, bc_m = hb.get(key_at_budget), bc.get(key_at_budget)

    print()
    print(BANNER)
    print("what just happened")
    print(BANNER)
    print(f"  At a fixed budget of {a.budget} reactions:")
    print(f"    best-candidate  {bc_m} distinct high-reward molecules")
    print(f"    hub-batching    {hb_m} distinct high-reward molecules", end="")
    if bc_m and hb_m:
        print(f"   ({hb_m / bc_m:.2f}x)")
    else:
        print()
    print()
    print(f"  To reach {a.modes} molecules:")
    print(
        f"    best-candidate  {bc['total_reactions']} reactions "
        f"({bc['reactions_per_mode']} per molecule)"
    )
    print(
        f"    hub-batching    {hb['total_reactions']} reactions "
        f"({hb['reactions_per_mode']} per molecule)"
    )
    print()
    print(f"  Best-candidate spread its picks over {bc['distinct_hubs_used']} intermediates;")
    print(f"  hub-batching concentrated them into {hb['distinct_hubs_used']}. Same molecules")
    print("  available to both, same gate, same diversity rule -- only the chooser differs.")
    print()
    print("  Both arms are charged by the SAME count-once cost model, and best-candidate is")
    print("  credited for scaffolds its picks happen to share. Without that credit the margin")
    print("  above would look larger than it is.")
    print()
    print(BANNER)
    print("next")
    print(BANNER)
    print(f"  {out}/summary.json          every number above")
    print(f"  {out}/curve_*.csv           the full modes-vs-reactions curves")
    print(f"  {out}/hubs.csv              the ranked hubs")
    print()
    print("  hubbatching sweep  ...       how the margin moves with the diversity cutoff")
    print("  hubbatching export ...       turn a selected library into a bench plan")
    print("  docs/INPUT_CONTRACT.md       what your generator must emit to be used here")
    print("  notebooks/                   worked examples for each extension point")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
