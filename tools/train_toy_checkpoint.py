#!/usr/bin/env python3
"""Train the toy checkpoint that ``notebooks/07_your_own_trained_model.ipynb`` loads.

The problem this solves: notebook 07 is the only one that drives a real trained model, and real
checkpoints here are 35-56 MB -- too large to commit, over the anonymous snapshot's size budget,
and a download the reader has to make before they can evaluate whether the download was worth
making. So this trains a deliberately small one against ``configs/hubbatching/toy_rgfn_qed.gin``, on a
cut-down library, with QED as the reward so nothing has to be fetched.

**The result is illustrative, not scientific.** It is trained for a few hundred iterations on
48 building blocks against a drug-likeness heuristic. It exists to prove the adapter path works
end to end on a laptop; no number produced from it means anything about chemistry.

    python3 tools/train_toy_checkpoint.py
    python3 tools/train_toy_checkpoint.py --iterations 200 --keep-run-dir

Needs the generator extra (``pip install -e '.[generators]'``). On this project's clusters,
prefix with the environment helper so dgl's libraries resolve.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

# ---------------------------------------------------------------------------------------------
# THIS BLOCK MUST STAY ABOVE EVERY OTHER IMPORT, and it is the reason this file does its heavy
# imports inside main() rather than at the top. torch and dgl read these variables once, at
# import time; setting them afterwards has no effect at all, which is a silent no-op rather than
# an error.
#
# CUDA_VISIBLE_DEVICES="" -- the config asks for CPU, but importing torch still PROBES the
# driver. On a shared login node that opened /dev/nvidia0 and then deadlocked in a futex, with
# the training loop never starting and CPU time frozen while elapsed time climbed. A toy run has
# no use for a GPU, and emptying this stops the probe rather than merely the use.
#
# WANDB_MODE=offline -- upstream's vendored logger config defaults to online, which uploads to
# wandb.ai under whatever account the machine is logged into. A tool that trains a throwaway
# checkpoint must not publish anything as a side effect of being run. The gin config sets this
# too; this is the belt to that braces, since the environment wins and is read earlier.
#
# thread caps -- login nodes limit per-user threads and OpenMP's default fan-out trips it
# ("libgomp: Thread creation failed: Resource temporarily unavailable").
for _var, _val in (
    ("CUDA_VISIBLE_DEVICES", ""),
    ("WANDB_MODE", "offline"),
    ("WANDB_SILENT", "true"),
    ("OMP_NUM_THREADS", "1"),
    ("MKL_NUM_THREADS", "1"),
    ("OPENBLAS_NUM_THREADS", "1"),
):
    os.environ.setdefault(_var, _val)
# ---------------------------------------------------------------------------------------------

REPO = Path(__file__).resolve().parents[1]
CONFIG = REPO / "configs" / "hubbatching" / "toy_rgfn_qed.gin"
DEST = REPO / "examples" / "toy_model" / "toy_rgfn_qed.pt"

# Above this the checkpoint stops being committable, which is the entire point of it. Enforced
# rather than hoped for: a config change that quietly enlarged the action space would otherwise
# produce a file nobody notices is too big until the snapshot build trips on it.
MAX_MB = 4.0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--iterations", type=int, default=None, help="override the config")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=str(DEST))
    ap.add_argument(
        "--run-dir",
        default="",
        help="where the trainer writes (default: a temporary directory that is then removed)",
    )
    ap.add_argument("--keep-run-dir", action="store_true", help="keep the trainer's own output")
    ap.add_argument(
        "--keep-full",
        action="store_true",
        help="write the full trainer checkpoint (optimizer + replay buffer) instead of a "
        "model-only one. Needed to RESUME training; roughly 5x the size.",
    )
    ap.add_argument("--max-mb", type=float, default=MAX_MB)
    a = ap.parse_args()

    if not CONFIG.exists():
        sys.exit(f"no config at {CONFIG}")
    library = REPO / "data" / "libraries" / "toy_v1"
    if not (library / "fragments.csv").exists():
        sys.exit(
            f"no toy library at {library}. Build it first:\n"
            "  python3 tools/make_toy_library.py"
        )

    try:
        import gin
        import torch  # noqa: F401
    except ImportError as exc:
        sys.exit(
            f"{exc}. Training needs the generator extra:\n"
            "  pip install -e '.[generators]'"
        )

    # Importing these registers the gin configurables, and must happen before parsing.
    #
    # Note the explicit NAME import. hubbatching.chemistry resolves GlueReactionDataFactory
    # lazily (so that reading a library does not require torch), which means importing the
    # package alone does NOT register it with gin -- the config then fails with "No configurable
    # matching reference '@GlueReactionDataFactory'". Touching the name is what registers it.
    from hubbatching.chemistry import GlueReactionDataFactory  # noqa: F401
    from rgfn.trainer.trainer import Trainer  # noqa: F401  (registers @Trainer)
    from rgfn.utils.helpers import seed_everything

    import tempfile

    run_dir = Path(a.run_dir) if a.run_dir else Path(tempfile.mkdtemp(prefix="toy_train_"))
    run_dir.mkdir(parents=True, exist_ok=True)

    seed_everything(a.seed)

    bindings = [f'user_root_dir="{run_dir}"', 'run_name="toy"']
    if a.iterations is not None:
        bindings.append(f"Trainer.n_iterations={a.iterations}")

    # The config's own includes are resolved relative to the repository root, and its library
    # path is repo-relative, so run from there regardless of where this was invoked.
    os.chdir(REPO)
    gin.parse_config_files_and_bindings([str(CONFIG)], bindings=bindings)

    print(f"training toy checkpoint -> {run_dir}")
    trainer = Trainer()
    trainer.train()
    trainer.close()

    # --- find what the trainer wrote and copy it out --------------------------------------
    candidates = sorted(run_dir.rglob("*.pt"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        sys.exit(f"training finished but wrote no .pt under {run_dir}")
    # Prefer the last checkpoint over the best-so-far: the adapter reconstructs the trained
    # objective, and "best" is selected on a metric that is meaningless for a toy run anyway.
    last = next((p for p in candidates if "last" in p.name), candidates[0])

    # --- strip training state -------------------------------------------------------------
    # A trainer checkpoint carries the optimizer moments and the replay buffer as well as the
    # model, and on a toy run those are THREE QUARTERS of the file: 4.5 MB of optimizer and
    # 3.9 MB of replay against 2.2 MB of actual weights. The adapter reads ckpt["model"] and
    # nothing else, so committing the rest would be committing megabytes that no reader can use.
    #
    # The cost of this, stated plainly: the stripped file CANNOT RESUME TRAINING. That is the
    # right trade for a checkpoint whose purpose is to be sampled from, and re-training it takes
    # about half an hour -- but pass --keep-full to write the unstripped file instead.
    import torch

    ckpt = torch.load(last, map_location="cpu", weights_only=False)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    if a.keep_full or not (isinstance(ckpt, dict) and "model" in ckpt):
        shutil.copy2(last, out)
        stripped = False
    else:
        torch.save({"model": ckpt["model"]}, out)
        stripped = True

    size_mb = out.stat().st_size / (1024 * 1024)
    full_mb = last.stat().st_size / (1024 * 1024)
    note = (
        f" (stripped from {full_mb:.1f} MB; inference only, cannot resume training)"
        if stripped
        else ""
    )
    print(f"\ncopied {last.name} -> {out}  ({size_mb:.1f} MB){note}")

    if not a.keep_run_dir and not a.run_dir:
        shutil.rmtree(run_dir, ignore_errors=True)

    if size_mb > a.max_mb:
        print(
            f"\nWARNING: {size_mb:.1f} MB exceeds the {a.max_mb} MB budget. This checkpoint is "
            "meant to be committed and to fit inside the anonymous snapshot's size cap. The "
            "action space is what drives the size -- shrink data/libraries/toy_v1 "
            "(tools/make_toy_library.py --fragments/--reactions) or hidden_dim in the config.",
            file=sys.stderr,
        )
        return 1

    print("\nNext: notebook 07 picks this up automatically, or point HB_CHECKPOINT at it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
